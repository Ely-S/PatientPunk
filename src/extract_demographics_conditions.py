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
MULTIPLE_PLACES = re.compile(r"[,/|;\r\n]|\s+or\s+", re.IGNORECASE)
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
    return None if MULTIPLE_PLACES.search(text) else text  # one country, state or city


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
    return _ask(client, POST_DEMOGRAPHICS_PROMPT + wrap_untrusted_text(text), parse_claims)


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


def _newest_reread(conn) -> int:
    (run_id,) = conn.execute(
        "SELECT COALESCE(MAX(run_id), 0) FROM extraction_runs "
        "WHERE extraction_type = 'demographics' AND json_extract(config, '$.reread')").fetchone()
    return run_id


def run_demographics(db_path: Path, *, limit: int = 0, reread: bool = False) -> dict:
    """Read every post no demographics run has read since the newest --reread run (all posts with
    ``reread``), store its claims, extract conditions for the users read, and resolve their profiles.
    ``limit`` caps the number of users read."""
    client = get_client()
    with closing(open_db(db_path)) as conn, closing(open_db(db_path)) as reader:
        # Stream posts on a separate connection: a long-lived cursor on the writing connection would
        # fail with SQLITE_BUSY_SNAPSHOT once another process commits.
        apply_schema(conn)  # claim tables and columns missing from an older database
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
        since = _newest_reread(conn)  # this run, with --reread
        log.info("Extraction run %s%s", run_id, " (rereading every post)" if reread else "")

        rows = reader.execute(
            "SELECT p.user_id, p.post_id, p.title, p.body_text FROM posts p WHERE p.user_id != ? AND NOT EXISTS ("
            "  SELECT 1 FROM post_runs pr JOIN extraction_runs r ON r.run_id = pr.run_id"
            "  WHERE pr.post_id = p.post_id AND r.extraction_type = 'demographics' AND pr.run_id >= ?)"
            " ORDER BY p.user_id, p.post_id",
            (DELETED_USER_ID, since))
        users = islice(groupby(rows, key=itemgetter(0)), limit or None)
        read_users: list[str] = []
        failed_users: set[str] = set()
        counts = {"posts_read": 0, "posts_failed": 0, "claims": 0, "conditions": 0, "conditions_failed": 0}

        def record(post_id: str, claims: dict) -> None:
            conn.execute("INSERT INTO post_runs (run_id, post_id) VALUES (?, ?)", (run_id, post_id))
            conn.executemany(
                "INSERT INTO demographic_claims (run_id, post_id, field, value, evidence) VALUES (?, ?, ?, ?, ?)",
                [(run_id, post_id, field, value, evidence) for field, (value, evidence) in claims.items()])
            counts["posts_read"] += 1
            counts["claims"] += len(claims)

        def post_jobs():  # consumed on this thread by _in_parallel, so record() may write here
            for user_id, posts in users:
                read_users.append(user_id)
                for _, post_id, title, body in posts:
                    if text := _post_text(title, body):
                        yield (user_id, post_id), text
                    else:
                        record(post_id, {})  # nothing to read: recorded as read without a model call

        for n, ((user_id, post_id), claims) in enumerate(_in_parallel(client, post_jobs(), read_post), start=1):
            if claims is None:
                failed_users.add(user_id)
                counts["posts_failed"] += 1
            else:
                record(post_id, claims)
            if n % COMMIT_EVERY == 0:
                conn.commit()
                log.info("Read %d posts (%d failed)", counts["posts_read"], counts["posts_failed"])
        conn.commit()

        # Conditions: one call per user read this run, over their newest posts up to MAX_USER_CHARS.
        wanted = set(read_users)
        histories = (
            (user_id, _combine_posts(t for _, title, body in posts if (t := _post_text(title, body))))
            for user_id, posts in groupby(reader.execute(
                "SELECT user_id, title, body_text FROM posts WHERE user_id != ? "
                "ORDER BY user_id, post_date DESC, post_id", (DELETED_USER_ID,)), key=itemgetter(0))
            if user_id in wanted)
        for user_id, conditions in _in_parallel(client, ((u, t) for u, t in histories if t), read_conditions):
            if conditions is None:
                counts["conditions_failed"] += 1
                continue
            conn.executemany(
                "INSERT INTO conditions (run_id, user_id, condition_name, condition_type) VALUES (?, ?, ?, ?)",
                [(run_id, user_id, name, kind) for name, kind in conditions])
            counts["conditions"] += len(conditions)
        conn.commit()

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
    run_demographics(args.db, limit=args.limit, reread=args.reread)


if __name__ == "__main__":
    main()
