#!/usr/bin/env python3
"""Extract self-reported demographics and conditions one post at a time from SQLite posts.

Each post goes to the model alone and its checked answers are stored with the words they came from:
demographic claims in demographic_claims, and each condition the author states, with its severity,
as an observation in conditions (#220). post_runs records every post a run read. resolve_profiles
then turns each user's claims into one user_profiles row in code (#206); conditions_latest holds
each user's newest observation of each condition.
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
from prompts.demographic_prompt import POST_DEMOGRAPHICS_PROMPT
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
SEVERITIES = ("severe", "moderate", "mild", "resolved")  # a phrase naming several takes the first: "moderate to severe" is severe
MAX_REPLY_TOKENS = 800  # a post listing many symptoms, each with its quote, needs more than 300
# One name for the conditions most often written several ways, so conditions_latest keeps one row for
# each. Other names are kept as the model wrote them, in lower case. The author's words stay in evidence.
_CONDITION_ALIASES = {
    "long covid": ("long-covid", "longcovid", "lc", "long covid (lc)", "long hauler", "long haul covid",
                   "long-haul covid", "long haul", "pasc", "post covid", "post-covid", "post covid syndrome",
                   "post-covid syndrome", "post-covid condition", "post covid condition"),
    "me/cfs": ("me", "cfs", "mecfs", "me cfs", "me / cfs", "chronic fatigue syndrome", "myalgic encephalomyelitis"),
    "pots": ("pots syndrome", "postural orthostatic tachycardia syndrome", "postural tachycardia syndrome"),
    "mcas": ("mast cell activation syndrome",),
    "pem": ("post-exertional malaise", "post exertional malaise"),
    "small fiber neuropathy": ("sfn", "small fibre neuropathy"),
    "eds": ("ehlers-danlos syndrome", "ehlers danlos syndrome", "ehlers-danlos"),
}
_CONDITIONS = {alias: name for name, aliases in _CONDITION_ALIASES.items() for alias in (name, *aliases)}


def _post_text(title: str | None, body: str) -> str:
    """Title and body, or "" for a post with nothing to read."""
    body = body.strip()
    if body.casefold() in REMOVED_BODIES:
        body = ""
    return "\n".join(part for part in ((title or "").strip(), body) if part)


def _ask(client, prompt: str, parse: Callable[[str], object]):
    """parse(reply), re-asking at a higher temperature while the reply is unreadable."""
    for attempt, temperature in enumerate(TEMPERATURES, start=1):
        try:
            # validate keeps an unreadable reply out of the cache, so a later run asks the model again.
            return parse(llm_call(client, prompt, model=MODEL_FAST, max_tokens=MAX_REPLY_TOKENS, temperature=temperature,
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


def _says(text: str, phrase: str, ignore_case: bool = True) -> bool:
    """Whether ``text`` contains ``phrase`` as whole words: "M" isn't in "I'm 34"."""
    flags = re.IGNORECASE if ignore_case else 0
    return re.search(rf"(?<![\w'’]){re.escape(phrase)}(?![\w'’])", text, flags) is not None


def _bare(item: object, text: str, ignore_case: bool = True) -> str | None:
    """A value given without its {value, evidence} wrapper, kept only when the post says it as whole words."""
    bare = _words(item)
    return bare if bare and _says(text, bare, ignore_case) else None


def parse_claims(result: dict, text: str = "") -> dict[str, tuple[str, str]]:
    """{field: (value, evidence)} from a per-post reply. A field the post doesn't state, or a value
    without a quote, is left out. A field given as a bare value instead of {value, evidence} is kept
    when the value appears as whole words in ``text``, the post, which is then its quote, and left out
    otherwise, so one badly shaped field doesn't lose the others."""
    claims = {}
    for field in CLAIM_FIELDS:
        item = result.get(field)
        if item is None:
            continue
        if not isinstance(item, dict):
            bare = _bare(item, text)
            item = {"value": bare, "evidence": bare} if bare else {}
            if not item:
                log.info("Dropping a %s claim not in {value, evidence} form", field)
        value, evidence = _claim_value(field, item.get("value")), item.get("evidence")
        if value and isinstance(evidence, str) and evidence.strip():
            claims[field] = (value, evidence.strip())
    return claims


def canonical_condition(name: str) -> str:
    """One name for a condition written several ways ("LC", "Long-COVID" -> "long covid"); others in lower case."""
    plain = re.sub(r"\s+", " ", name.strip().casefold().replace("’", "'")).removesuffix(".")
    return _CONDITIONS.get(plain, plain)


def parse_conditions(result: dict, text: str = "") -> list[tuple[str, str, str | None, str]]:
    """[(name, "illness" | "symptom", severity or None, evidence)] from a per-post reply, one per
    condition. An entry needs a name and a quote; a bare name is kept only when the post says it
    as whole words. A condition listed twice keeps the entry that states a severity. A missing or
    badly shaped list is no conditions."""
    entries = result.get("conditions")
    if not isinstance(entries, list):
        if entries is not None:
            log.info("Dropping conditions that aren't a list")
        return []
    parsed = {}
    for entry in entries:
        if not isinstance(entry, dict):
            # Case counts for a bare name: "ME" and "POTS" aren't "help me" or "pots and pans".
            bare = _bare(entry, text, ignore_case=False) if isinstance(entry, str) else None
            entry = {"name": bare, "evidence": bare} if bare else {}
        name, evidence = entry.get("name"), entry.get("evidence")
        name = _words(name) if isinstance(name, str) else None
        if not name or not isinstance(evidence, str) or not evidence.strip():
            continue
        kind = str(entry.get("type") or "").strip().lower()
        stated = str(entry.get("severity") or "").lower()
        severity = next((s for s in SEVERITIES if re.search(rf"\b{s}\b", stated)), None)
        name = canonical_condition(name)
        observation = (name, kind if kind in ("illness", "symptom") else "illness",
                       severity, evidence.strip())
        if name not in parsed or (parsed[name][2] is None and observation[2]):  # keep a stated severity
            parsed[name] = observation
    return list(parsed.values())


def parse_post(raw: str, text: str = "") -> tuple[dict, list]:
    """(claims, conditions) from a per-post reply. Only a reply that isn't one of these objects
    raises LLMParseError."""
    result = parse_json_object(raw)
    if result.keys().isdisjoint((*CLAIM_FIELDS, "conditions")):
        raise LLMParseError("Expected a demographics JSON object")
    return parse_claims(result, text), parse_conditions(result, text)


BLOCKED = object()  # a read's result when the content filter blocks the call


def read_post(client, text: str) -> tuple[dict, list] | object:
    try:
        return _ask(client, POST_DEMOGRAPHICS_PROMPT + wrap_untrusted_text(text), lambda raw: parse_post(raw, text))
    except LLMContentFilteredError:
        # The filter blocks the same post every time, so retrying would leave it unread, and its
        # author's profile frozen, for good. It is recorded as read, keeping what an earlier read found.
        log.warning("Content filter blocked a post; recording it as read and keeping what an earlier read found")
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
    tokens = (chars + posts * len(POST_DEMOGRAPHICS_PROMPT)) // 4
    return {"posts": posts, "users": len(users), "post_calls": posts, "approx_input_tokens": tokens}


# Posts whose newest demographics read is from before conditions were read per post (#220), so
# conditions_latest has nothing from them until a --reread.
READ_WITHOUT_CONDITIONS = (
    "SELECT COUNT(*) FROM (SELECT pr.post_id, MAX(pr.run_id) AS run_id FROM post_runs pr "
    "  JOIN extraction_runs r ON r.run_id = pr.run_id WHERE r.extraction_type = 'demographics' "
    "  GROUP BY pr.post_id) newest JOIN extraction_runs r ON r.run_id = newest.run_id "
    "WHERE NOT IFNULL(json_extract(r.config, '$.reads_conditions'), 0)")


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

    def record(user_id: str, post_id: str, claims: dict, conditions: list) -> None:
        conn.execute("INSERT INTO post_runs (run_id, post_id) VALUES (?, ?)", (run_id, post_id))
        conn.executemany(
            "INSERT INTO demographic_claims (run_id, post_id, field, value, evidence) VALUES (?, ?, ?, ?, ?)",
            [(run_id, post_id, field, value, evidence) for field, (value, evidence) in claims.items()])
        conn.executemany(
            "INSERT INTO conditions (run_id, user_id, post_id, condition_name, condition_type, severity, evidence)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)", [(run_id, user_id, post_id, *c) for c in conditions])
        counts["posts_read"] += 1
        counts["claims"] += len(claims)
        counts["conditions"] += len(conditions)

    def jobs():  # consumed on this thread by _in_parallel, so record() may write here
        for user_id, posts in islice(groupby(rows, key=itemgetter(0)), limit or None):
            read_users.append(user_id)
            for _, post_id, title, body in posts:
                if text := _post_text(title, body):
                    yield (user_id, post_id), text
                else:
                    record(user_id, post_id, {}, [])  # nothing to read: recorded as read without a model call

    for n, ((user_id, post_id), reply) in enumerate(_in_parallel(client, jobs(), read_post), start=1):
        if reply is None:
            counts["posts_failed"] += 1
        elif reply is BLOCKED:
            # A block says nothing about what the post states, so what an earlier read found still
            # stands: its claims and conditions are carried forward under this run (none on a first read).
            claims = conn.execute(
                "SELECT field, value, evidence FROM demographic_claims_latest WHERE post_id = ?", (post_id,))
            conditions = conn.execute(
                "SELECT condition_name, condition_type, severity, evidence FROM condition_observations "
                "WHERE post_id = ?", (post_id,)).fetchall()
            record(user_id, post_id, {field: (value, evidence) for field, value, evidence in claims}, conditions)
            counts["posts_blocked"] += 1
        else:
            record(user_id, post_id, *reply)
        if n % COMMIT_EVERY == 0:
            conn.commit()
            log.info("Read %d posts (%d failed)", counts["posts_read"], counts["posts_failed"])
    conn.commit()
    return read_users


def _users_with_unread_posts(conn, since: int) -> set[str]:
    """Users whose claims are incomplete: a post failed, or a --limit run hasn't reached it yet."""
    return {u for (u,) in conn.execute(f"SELECT DISTINCT p.user_id {UNREAD_POSTS}", (DELETED_USER_ID, since))}


def run_demographics(db_path: Path, *, limit: int = 0, reread: bool = False, dry_run: bool = False) -> dict:
    """Read new posts (every post with ``reread``) into claims and condition observations, and resolve
    profiles. ``limit`` caps the number of users read. Returns the run's counts, or with
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
        if not reread and (stale := conn.execute(READ_WITHOUT_CONDITIONS).fetchone()[0]):
            log.warning("%d posts were read before conditions were read per post, so conditions_latest has "
                        "nothing from them. Run --reread to read them again.", stale)
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
            "max_reply_tokens": MAX_REPLY_TOKENS,
            "reads_conditions": True,
            "temperatures": TEMPERATURES,
            "workers": MAX_IN_FLIGHT,
        }, commit_hash=get_git_commit())
        if reread:
            since = run_id
        log.info("Extraction run %s%s: %s", run_id, " (rereading every post)" if reread else "",
                 _plan(conn, since, limit))
        counts = {"posts_read": 0, "posts_failed": 0, "posts_blocked": 0, "claims": 0, "conditions": 0}

        read_users = _read_posts(client, conn, reader, run_id, since, limit, counts)
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
        description="Extract demographics and conditions one post at a time from a corpus database."
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
