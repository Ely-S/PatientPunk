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
DC = re.compile(r",\s*D\.?\s*C\.?$", re.IGNORECASE)  # "Washington, D.C." is one place
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
            return parse(llm_call(client, prompt, model=MODEL_FAST, max_tokens=300, temperature=temperature))
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
    if MULTIPLE_PLACES.search(text) or (field != "city" and "," in DC.sub("", text)):
        return None
    return text


def parse_claims(raw: str) -> dict[str, tuple[str, str]]:
    """{field: (value, evidence)} from a per-post reply. A field the post doesn't state, or a value
    without a quote, is left out; a reply in the wrong shape raises LLMParseError."""
    result = parse_json_object(raw)
    if result.keys().isdisjoint(CLAIM_FIELDS):
        raise LLMParseError("Expected a demographics JSON object")
    claims = {}
    for field in CLAIM_FIELDS:
        item = result.get(field)
        if item is None:
            continue
        if not isinstance(item, dict):
            raise LLMParseError(f"Expected {field} to be null or an object with value and evidence")
        value, evidence = _claim_value(field, item.get("value")), item.get("evidence")
        if value and isinstance(evidence, str) and evidence.strip():
            claims[field] = (value, evidence.strip())
    return claims


def read_post(client, text: str) -> dict[str, tuple[str, str]]:
    try:
        return _ask(client, POST_DEMOGRAPHICS_PROMPT + wrap_untrusted_text(text), parse_claims)
    except LLMContentFilteredError:
        # The filter blocks the same post every time, so retrying would leave it unread, and its
        # author's profile frozen, for good. It is recorded as read with no claims instead.
        log.warning("Content filter blocked a post; recording it as read with no claims")
        return {}


# ── Per-user conditions ──────────────────────────────────────────────────────

def _condition_name(condition: object) -> str:
    name = condition.get("condition_name") if isinstance(condition, dict) else condition
    return name.strip() if isinstance(name, str) else ""


def parse_conditions(raw: str) -> list[tuple[str, str]]:
    """[(name, "illness" | "symptom")] from a conditions reply."""
    conditions = parse_json_object(raw).get("conditions")
    if conditions is None:
        return []
    if not isinstance(conditions, list) or any(not _condition_name(item) for item in conditions):
        raise LLMParseError("Expected a list of named conditions")
    parsed = []
    for condition in conditions:
        kind = condition.get("condition_type") if isinstance(condition, dict) else None
        kind = kind.strip().lower() if isinstance(kind, str) else None
        parsed.append((_condition_name(condition).lower(), kind if kind in ("illness", "symptom") else "illness"))
    return parsed


BLOCKED = object()  # read_conditions' result when the content filter blocks the call


def read_conditions(client, text: str) -> list[tuple[str, str]] | object:
    try:
        return _ask(client, CONDITIONS_PROMPT + wrap_untrusted_text(text), parse_conditions)
    except LLMContentFilteredError:
        log.warning("Content filter blocked a conditions call; keeping that user's current conditions")
        return BLOCKED


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


def _reread_checkpoints(conn) -> tuple[int, int | None]:
    """(since, unfinished): the run the newest finished --reread read from (0 if none), and, when a newer
    --reread stopped before finishing, the run it read from. A reread's starting run is its own, or the
    unfinished reread's it resumed (config.reread_since)."""
    unfinished = None
    for run_id, finished, since in conn.execute(
            "SELECT run_id, finished_at IS NOT NULL, json_extract(config, '$.reread_since') FROM extraction_runs "
            "WHERE extraction_type = 'demographics' AND json_extract(config, '$.reread') ORDER BY run_id DESC"):
        since = since or run_id
        if finished:
            return since, unfinished
        unfinished = unfinished or since
    return 0, unfinished


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


# Users with a post read by a run that checks conditions, and no conditions check since: users read
# this run, and users whose conditions call failed in an earlier run. Runs from before condition_runs
# (no config.checks_conditions) never make a user due, so upgrading doesn't recheck everyone.
CONDITIONS_DUE = (
    "SELECT DISTINCT p.user_id FROM post_runs pr JOIN posts p ON p.post_id = pr.post_id "
    "JOIN extraction_runs r ON r.run_id = pr.run_id "
    "WHERE r.extraction_type = 'demographics' AND json_extract(r.config, '$.checks_conditions') "
    "AND p.user_id != ? AND NOT EXISTS ("
    "  SELECT 1 FROM condition_runs cr WHERE cr.user_id = p.user_id AND cr.run_id >= pr.run_id)")


def _read_conditions(client, conn, reader, run_id: int, counts: dict) -> None:
    """One conditions call per due user (CONDITIONS_DUE), over their newest posts up to MAX_USER_CHARS.
    A checked user gets a condition_runs row; a failed call writes nothing, so the next run checks that
    user again. A call the content filter blocks would be blocked every time, so it counts as a check that
    carries the user's current conditions forward. (Conditions move per post later, #195.)"""
    users = {u for (u,) in conn.execute(CONDITIONS_DUE, (DELETED_USER_ID,))}

    def checked(user_id: str, conditions: list) -> None:
        conn.execute("INSERT INTO condition_runs (run_id, user_id) VALUES (?, ?)", (run_id, user_id))
        conn.executemany(
            "INSERT INTO conditions (run_id, user_id, condition_name, condition_type) VALUES (?, ?, ?, ?)",
            [(run_id, user_id, name, kind) for name, kind in conditions])
        counts["conditions"] += len(conditions)

    histories = (
        (user_id, _combine_posts(t for _, title, body in posts if (t := _post_text(title, body))))
        for user_id, posts in groupby(reader.execute(
            "SELECT user_id, title, body_text FROM posts WHERE user_id != ? "
            "ORDER BY user_id, post_date DESC, post_id", (DELETED_USER_ID,)), key=itemgetter(0))
        if user_id in users)

    def jobs():  # consumed on this thread by _in_parallel, so checked() may write here
        for user_id, text in histories:
            if text:
                yield user_id, text
            else:
                checked(user_id, [])  # nothing left to read, so no current conditions

    for user_id, conditions in _in_parallel(client, jobs(), read_conditions):
        if conditions is None:
            counts["conditions_failed"] += 1
        elif conditions is BLOCKED:
            current = conn.execute("SELECT condition_name, condition_type FROM conditions_latest WHERE user_id = ?",
                                   (user_id,)).fetchall()
            checked(user_id, current)
            counts["conditions_blocked"] += 1
        else:
            checked(user_id, conditions)
    conn.commit()


def run_demographics(db_path: Path, *, limit: int = 0, reread: bool = False) -> dict:
    """Read new posts (every post with ``reread``) into claims, check conditions for the users read and
    those whose earlier check failed, and resolve profiles. ``limit`` caps the number of users read. Returns the run's counts."""
    if reread and limit:
        # A limited reread would become the newest reread checkpoint, so the next ordinary run would
        # reread every post the limit skipped: a paid full-corpus run nobody asked for.
        raise ValueError("--reread reads every post; it can't be combined with --limit")
    client = get_client()
    # Posts stream on a second connection: a long-lived cursor on the writing connection would fail
    # with SQLITE_BUSY_SNAPSHOT once another process commits.
    with closing(open_db(db_path)) as conn, closing(open_db(db_path)) as reader:
        apply_schema(conn)  # claim tables and columns missing from an older database
        # Only a finished --reread moves the checkpoint. A reread that stopped (a bad key, Ctrl-C) is
        # resumed by the next --reread, never by an ordinary run: that would be a paid full-corpus
        # reread nobody asked for.
        since, unfinished = _reread_checkpoints(conn)
        if unfinished and not reread:
            log.warning("The --reread from run %s stopped before finishing; this run reads only new and "
                        "failed posts. Run with --reread to finish it.", unfinished)
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
            "checks_conditions": True,
        }, commit_hash=get_git_commit())
        if reread:
            since = unfinished or run_id
            conn.execute("UPDATE extraction_runs SET config = json_set(config, '$.reread_since', ?) WHERE run_id = ?",
                         (since, run_id))
            conn.commit()
            log.info("Extraction run %s (rereading every post%s)", run_id,
                     f", resuming run {unfinished}" if unfinished else "")
        else:
            log.info("Extraction run %s", run_id)
        counts = {"posts_read": 0, "posts_failed": 0, "claims": 0, "conditions": 0, "conditions_failed": 0,
                  "conditions_blocked": 0}

        read_users = _read_posts(client, conn, reader, run_id, since, limit, counts)
        _read_conditions(client, conn, reader, run_id, counts)
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
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be nonnegative")
    if args.reread and args.limit:
        parser.error("--reread reads every post; it can't be combined with --limit")
    run_demographics(args.db, limit=args.limit, reread=args.reread)


if __name__ == "__main__":
    main()
