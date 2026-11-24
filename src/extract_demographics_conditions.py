#!/usr/bin/env python3
"""Extract self-reported demographics one post at a time, and conditions per user, from SQLite posts.

Each post goes to the model alone and its checked answers are stored as claims (demographic_claims),
with the words they came from; post_runs records every post a run read. resolve_profiles then turns
each user's claims into one user_profiles row in code (#206). Conditions keep one call per user.
"""

import argparse
import re
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import closing
from itertools import groupby, islice
from operator import itemgetter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from import_posts import DELETED_USER_ID
from patientpunk._utils import LLMContentFilteredError, LLMResponseError, wrap_untrusted_text
from patientpunk.db import apply_schema, register_run
from prompts.demographic_prompt import CONDITIONS_PROMPT, POST_DEMOGRAPHICS_PROMPT
from resolve_demographics import resolve_profiles, stated_age
from utilities import (
    LLM_PROVIDER,
    LLM_REASONING_MODE,
    MODEL_FAST,
    LLMParseError,
    get_client,
    get_git_commit,
    git_is_dirty,
    is_transient_or_truncated,
    llm_call,
    log,
    parse_json_object,
)
from utilities.db import open_db

MAX_USER_CHARS = 8_000  # per-user conditions call only
SEPARATOR = "\n---\n"
MAX_IN_FLIGHT = 10
COMMIT_EVERY = 200
TEMPERATURES = (0.0, 0.7, 1.0)
REMOVED_BODIES = {"[removed]", "[deleted]"}
CLAIM_FIELDS = ("age", "sex", "country", "state", "city")
MULTIPLE_PLACES = re.compile(r"[/|;\r\n]|\s+or\s+", re.IGNORECASE)
# A comma inside one place's name: "Washington, D.C.", "Korea, Republic of", "Congo, Democratic Republic of the"
ONE_PLACE_COMMA = re.compile(
    r",\s*(?:D\.?\s*C\.?|(?:the\s+)?(?:[a-z]+\s+)?(?:republic|kingdom|federation|states?)\s+of(?:\s+the)?)\s*$",
    re.IGNORECASE,
)
UNKNOWN_VALUES = {"unknown", "none", "null", "not stated", "n.a.", "n/a"}


def _post_text(title: str | None, body: str) -> str:
    """Title and body, or "" for a post with nothing to read."""
    body = body.strip()
    if body.casefold() in REMOVED_BODIES:
        body = ""
    return "\n".join(part for part in ((title or "").strip(), body) if part)


def _combine_posts(texts: Iterable[str]) -> str:
    parts, size = [], 0
    for text in texts:  # stop reading once the cap is reached
        parts.append(text)
        size += len(text) + len(SEPARATOR)
        if size >= MAX_USER_CHARS:
            break
    return SEPARATOR.join(parts)[:MAX_USER_CHARS]


def _ask(client, prompt: str, parse: Callable[[str], object]):
    """parse(reply), re-asking at a higher temperature while the reply is unreadable."""
    for attempt, temperature in enumerate(TEMPERATURES, start=1):
        try:
            # validate keeps an unreadable reply out of the cache, so a later run asks the model again.
            return parse(llm_call(client, prompt, model=MODEL_FAST, max_tokens=300, temperature=temperature,
                                  validate=parse))
        except LLMContentFilteredError:
            raise
        except (LLMParseError, LLMResponseError):
            if attempt == len(TEMPERATURES):
                raise
            log.info("Unreadable reply (%d/%d), retrying", attempt, len(TEMPERATURES))
    raise AssertionError("Unreachable")


# ── Per-post claims ──────────────────────────────────────────────────────────

def _words(value: object) -> str | None:
    if isinstance(value, float) and value.is_integer():
        value = int(value)  # JSON 34.0
    if isinstance(value, (int, str)) and not isinstance(value, bool):
        text = str(value).strip()
        if text and text.casefold() not in UNKNOWN_VALUES:
            return text
    return None


def _claim_value(field: str, value: object) -> str | None:
    """The value to store, as stated, or None when it isn't one the resolve step can use."""
    text = _words(value)
    if text is None:
        return None
    if field == "age":
        return text if stated_age(text) is not None else None  # 10-99, or a range or decade within it
    if field == "sex":
        return text  # every stated value kept, "non-binary | female" included (#214)
    # One place. A city may carry its region after a comma ("Austin, TX"); a country or state may not.
    if MULTIPLE_PLACES.search(text) or (field != "city" and "," in ONE_PLACE_COMMA.sub("", text)):
        return None
    return text


def parse_claims(raw: str, text: str = "") -> dict[str, tuple[str, str]]:
    """{field: (value, evidence)} from a per-post reply. A field the post doesn't state, or a value
    without a quote, is left out. A field given as a bare value instead of {value, evidence} is kept
    when the value appears word for word in ``text``, the post, which is then its quote, and left out
    otherwise, so one badly shaped field doesn't lose the others. Only a reply that isn't a
    demographics object raises LLMParseError."""
    result = parse_json_object(raw)
    if result.keys().isdisjoint(CLAIM_FIELDS):
        raise LLMParseError("Expected a demographics JSON object")
    claims = {}
    for field in CLAIM_FIELDS:
        item = result.get(field)
        if item is None:
            continue
        if not isinstance(item, dict):
            bare = _words(item)
            item = {"value": bare, "evidence": bare} if bare and bare.casefold() in text.casefold() else {}
            if not item:
                log.info("Dropping a %s claim not in {value, evidence} form", field)
        value, evidence = _claim_value(field, item.get("value")), item.get("evidence")
        if value and isinstance(evidence, str) and evidence.strip():
            claims[field] = (value, evidence.strip())
    return claims


BLOCKED = object()  # a read's result when the content filter blocks the call


def read_post(client, text: str) -> dict[str, tuple[str, str]] | object:
    try:
        return _ask(client, POST_DEMOGRAPHICS_PROMPT + wrap_untrusted_text(text), lambda raw: parse_claims(raw, text))
    except LLMContentFilteredError:
        # The filter blocks the same post every time, so retrying would leave it unread, and its
        # author's profile frozen, for good. It is recorded as read, keeping its earlier claims.
        log.warning("Content filter blocked a post; recording it as read and keeping its earlier claims")
        return BLOCKED


# ── Per-user conditions ──────────────────────────────────────────────────────

def _condition_name(condition: object) -> str:
    name = condition.get("condition_name") if isinstance(condition, dict) else condition
    return name.strip() if isinstance(name, str) else ""


def parse_conditions(raw: str) -> list[tuple[str, str]]:
    """[(name, "illness" | "symptom")] from a conditions reply."""
    conditions = parse_json_object(raw).get("conditions")
    if conditions is None:
        return []
    if not isinstance(conditions, list):
        raise LLMParseError("Expected a list of conditions")
    parsed = []
    for condition in filter(_condition_name, conditions):  # an entry without a name is dropped, as on main
        kind = condition.get("condition_type") if isinstance(condition, dict) else None
        kind = kind.strip().lower() if isinstance(kind, str) else None
        parsed.append((_condition_name(condition).lower(), kind if kind in ("illness", "symptom") else "illness"))
    return parsed


def read_conditions(client, text: str) -> list[tuple[str, str]]:
    return _ask(client, CONDITIONS_PROMPT + wrap_untrusted_text(text), parse_conditions)


# ── Running ──────────────────────────────────────────────────────────────────

def _in_parallel(client, jobs: Iterable[tuple], read: Callable) -> Iterator[tuple[tuple, object | None]]:
    """Yield (key, read(client, text), or None on a per-item failure) for each (key, text) job, with up
    to MAX_IN_FLIGHT calls running. Jobs are submitted only as earlier calls finish, so a permanent
    error stops the run with the rest unsent."""
    jobs = iter(jobs)
    with ThreadPoolExecutor(max_workers=MAX_IN_FLIGHT) as pool:
        pending = {pool.submit(read, client, text): key for key, text in islice(jobs, MAX_IN_FLIGHT)}
        while pending:
            completed, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                key = pending.pop(future)
                try:
                    result = future.result()
                except Exception as exc:
                    if not isinstance(exc, LLMParseError) and not is_transient_or_truncated(exc):
                        log.error("Stopping demographics run: %s failed (%s)", key, type(exc).__name__)
                        raise
                    log.warning("Skipping %s (%s)", key, type(exc).__name__)
                    result = None
                yield key, result
            for key, text in islice(jobs, len(completed)):
                pending[pool.submit(read, client, text)] = key


def _reread_checkpoint(conn) -> tuple[int, int | None]:
    """(checkpoint, stopped): the newest finished --reread run (0 if none), and a newer --reread run that
    stopped before finishing, if any."""
    stopped = None
    for run_id, finished in conn.execute(
            "SELECT run_id, finished_at IS NOT NULL FROM extraction_runs "
            "WHERE extraction_type = 'demographics' AND json_extract(config, '$.reread') ORDER BY run_id DESC"):
        if finished:
            return run_id, stopped
        stopped = stopped or run_id
    return 0, stopped


def _plan(conn, since: int, limit: int) -> dict:
    """What a run would send: unread posts and their users (the first ``limit`` users), and a rough
    input-token count (4 characters a token, prompts included). Posts with nothing to read are counted,
    so it is an upper bound."""
    users = conn.execute(
        f"SELECT COUNT(*), SUM(LENGTH(COALESCE(p.title, '')) + LENGTH(COALESCE(p.body_text, ''))) "
        f"{UNREAD_POSTS} GROUP BY p.user_id ORDER BY p.user_id", (DELETED_USER_ID, since)).fetchall()
    users = users[:limit or None]
    posts, chars = sum(n for n, _ in users), sum(c or 0 for _, c in users)
    tokens = (chars + posts * len(POST_DEMOGRAPHICS_PROMPT)
              + len(users) * (len(CONDITIONS_PROMPT) + MAX_USER_CHARS)) // 4
    return {"posts": posts, "users": len(users), "post_calls": posts, "conditions_calls": len(users),
            "approx_input_tokens": tokens}


# Posts no demographics run has read since the checkpoint run.
UNREAD_POSTS = (
    "FROM posts p WHERE p.user_id != ? AND NOT EXISTS ("
    "  SELECT 1 FROM post_runs pr JOIN extraction_runs r ON r.run_id = pr.run_id"
    "  WHERE pr.post_id = p.post_id AND r.extraction_type = 'demographics' AND pr.run_id >= ?)")


def _read_posts(client, conn, reader, run_id: int, since: int, limit: int, counts: dict) -> list[str]:
    """Read each unread post and store its claims. A successful read gets a post_runs row; a failed
    one doesn't, so the next run reads it again. Returns the users read."""
    rows = reader.execute(
        f"SELECT p.user_id, p.post_id, p.title, p.body_text {UNREAD_POSTS} ORDER BY p.user_id, p.post_id",
        (DELETED_USER_ID, since))
    read_users = []

    def record(post_id: str, claims: dict) -> None:
        conn.execute("INSERT INTO post_runs (run_id, post_id) VALUES (?, ?)", (run_id, post_id))
        conn.executemany(
            "INSERT INTO demographic_claims (run_id, post_id, field, value, evidence) VALUES (?, ?, ?, ?, ?)",
            [(run_id, post_id, field, value, evidence) for field, (value, evidence) in claims.items()])
        counts["posts_read"] += 1
        counts["claims"] += len(claims)

    def jobs():  # consumed on this thread by _in_parallel, so record() may write here
        for user_id, posts in islice(groupby(rows, key=itemgetter(0)), limit or None):
            read_users.append(user_id)
            for _, post_id, title, body in posts:
                if text := _post_text(title, body):
                    yield (user_id, post_id), text
                else:
                    record(post_id, {})  # nothing to read: recorded as read without a model call

    for n, ((user_id, post_id), claims) in enumerate(_in_parallel(client, jobs(), read_post), start=1):
        if claims is None:
            counts["posts_failed"] += 1
        elif claims is BLOCKED:
            # A block says nothing about what the post states, so what an earlier read found still
            # stands: its claims are carried forward under this run (none on a first read).
            earlier = conn.execute(
                "SELECT field, value, evidence FROM demographic_claims_latest WHERE post_id = ?", (post_id,))
            record(post_id, {field: (value, evidence) for field, value, evidence in earlier})
            counts["posts_blocked"] += 1
        else:
            record(post_id, claims)
        if n % COMMIT_EVERY == 0:
            conn.commit()
            log.info("Read %d posts (%d failed)", counts["posts_read"], counts["posts_failed"])
    conn.commit()
    return read_users


def _users_with_unread_posts(conn, since: int) -> set[str]:
    """Users whose claims are incomplete: a post failed, or a --limit run hasn't reached it yet."""
    return {u for (u,) in conn.execute(f"SELECT DISTINCT p.user_id {UNREAD_POSTS}", (DELETED_USER_ID, since))}


def _read_conditions(client, conn, reader, run_id: int, users: set[str], counts: dict) -> None:
    """One conditions call per user in ``users``, over their newest posts up to MAX_USER_CHARS. A failed
    call writes nothing for that user, and nothing schedules it again: the next call for that user
    comes when a run reads one of their posts. Commits every COMMIT_EVERY users, so the write lock isn't
    held for the whole pass."""
    histories = (
        (user_id, _combine_posts(t for _, title, body in posts if (t := _post_text(title, body))))
        for user_id, posts in groupby(reader.execute(
            "SELECT user_id, title, body_text FROM posts WHERE user_id != ? "
            "ORDER BY user_id, post_date DESC, post_id", (DELETED_USER_ID,)), key=itemgetter(0))
        if user_id in users)
    jobs = ((u, t) for u, t in histories if t)
    for n, (user_id, conditions) in enumerate(_in_parallel(client, jobs, read_conditions), start=1):
        if conditions is None:
            counts["conditions_failed"] += 1
        else:
            conn.executemany(
                "INSERT INTO conditions (run_id, user_id, condition_name, condition_type) VALUES (?, ?, ?, ?)",
                [(run_id, user_id, name, kind) for name, kind in conditions])
            counts["conditions"] += len(conditions)
        if n % COMMIT_EVERY == 0:
            conn.commit()
    conn.commit()


def run_demographics(db_path: Path, *, limit: int = 0, reread: bool = False, dry_run: bool = False) -> dict:
    """Read new posts (every post with ``reread``) into claims, extract conditions for the users read,
    and resolve profiles. ``limit`` caps the number of users read. Returns the run's counts, or with
    ``dry_run`` only what it would send (_plan), with no model call and no run recorded."""
    if reread and limit:
        # A limited reread would become the newest reread checkpoint, so the next ordinary run would
        # reread every post the limit skipped: a paid full-corpus run nobody asked for.
        raise ValueError("--reread reads every post; it can't be combined with --limit")
    # Posts stream on a second connection: a long-lived cursor on the writing connection would fail
    # with SQLITE_BUSY_SNAPSHOT once another process commits.
    with closing(open_db(db_path)) as conn, closing(open_db(db_path)) as reader:
        apply_schema(conn)  # claim tables and columns missing from an older database
        # Only a finished --reread moves the checkpoint. A reread that stopped (a bad key, Ctrl-C) isn't
        # resumed by an ordinary run, which would make it a paid full-corpus reread nobody asked for. A new
        # --reread starts over: replies already cached for the same prompt cost nothing, and after a
        # prompt change every post should be read again anyway.
        since, stopped = _reread_checkpoint(conn)
        if stopped and not reread:
            log.warning("The --reread in run %s stopped before finishing; this run reads only new and failed "
                        "posts. Run --reread again to reread every post.", stopped)
        if dry_run:
            plan = _plan(conn, 1 << 62 if reread else since, limit)  # with --reread, every post is unread
            log.info("Dry run, nothing sent: %s", plan)
            return plan
        client = get_client()
        run_id = register_run(conn, "demographics", {
            "provider": LLM_PROVIDER,
            "reasoning_mode": LLM_REASONING_MODE,
            "git_dirty": git_is_dirty(),
            "model": MODEL_FAST,
            "limit": limit,
            "reread": reread,
            "max_user_chars": MAX_USER_CHARS,
            "temperatures": TEMPERATURES,
            "workers": MAX_IN_FLIGHT,
        }, commit_hash=get_git_commit())
        if reread:
            since = run_id
        log.info("Extraction run %s%s: %s", run_id, " (rereading every post)" if reread else "",
                 _plan(conn, since, limit))
        counts = {"posts_read": 0, "posts_failed": 0, "posts_blocked": 0, "claims": 0, "conditions": 0,
                  "conditions_failed": 0}

        read_users = _read_posts(client, conn, reader, run_id, since, limit, counts)
        _read_conditions(client, conn, reader, run_id, set(read_users), counts)
        # Resolution recomputes from all claims, so it also finishes a run that stopped before here.
        # Users with unread posts keep their previous profile until all their posts are read.
        failed_users = _users_with_unread_posts(conn, since)
        stats = resolve_profiles(conn, run_id, failed_users)  # commits
        conn.execute("UPDATE extraction_runs SET finished_at = ? WHERE run_id = ?", (int(time.time()), run_id))
        conn.commit()

    counts.update(users=len(read_users), failed_users=len(failed_users), **stats)
    log.info("Done: %s", counts)
    return counts


def main():
    parser = argparse.ArgumentParser(
        description="Extract demographics one post at a time, and conditions per user, from a corpus database."
    )
    parser.add_argument("--db", required=True, type=Path, help="Path to the corpus SQLite database")
    parser.add_argument("--limit", type=int, default=0, help="Read the posts of at most N users (0 = all)")
    parser.add_argument("--reread", action="store_true",
                        help="Read every post again, for example after a prompt change")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print how many posts, model calls and approximate input tokens a run would "
                             "send, then exit without calling the model")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be nonnegative")
    if args.reread and args.limit:
        parser.error("--reread reads every post; it can't be combined with --limit")
    plan = run_demographics(args.db, limit=args.limit, reread=args.reread, dry_run=args.dry_run)
    if args.dry_run:
        print(plan)


if __name__ == "__main__":
    main()
