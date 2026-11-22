#!/usr/bin/env python3
"""Extract self-reported demographics and conditions from SQLite posts."""

import argparse
import json
import re
import sys
import time
from collections.abc import Iterable, Iterator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import closing
from itertools import groupby, islice
from operator import itemgetter
from pathlib import Path
from sqlite3 import Connection

sys.path.insert(0, str(Path(__file__).parent))

from import_posts import DELETED_USER_ID
from patientpunk._utils import (
    LLMContentFilteredError,
    LLMResponseError,
    self_reported_age,
    strip_markdown_fences,
    wrap_untrusted_text,
)
from patientpunk.db import _bucketize_age
from prompts.demographic_prompt import DEMOGRAPHICS_PROMPT
from utilities import (
    MODEL_FAST,
    LLMParseError,
    get_client,
    get_git_commit,
    is_transient_or_truncated,
    llm_call,
    log,
)
from utilities.db import open_db

MAX_USER_CHARS = 8_000
MAX_IN_FLIGHT = 10
COMMIT_EVERY = 20
TEMPERATURES = (0.0, 0.7, 1.0)
REMOVED_BODIES = {"[removed]", "[deleted]"}
RESPONSE_FIELDS = {"age", "sex", "country", "state", "conditions"}
SEX_VALUES = {
    "f": "female",
    "female": "female",
    "woman": "female",
    "m": "male",
    "male": "male",
    "man": "male",
    "nb": "non-binary",
    "nonbinary": "non-binary",
    "non-binary": "non-binary",
    "non binary": "non-binary",
}
MULTIPLE_PLACES = re.compile(r"[,/|;\r\n]|\s+or\s+", re.IGNORECASE)
UNKNOWN_PLACES = {"unknown", "none", "null", "not stated", "n.a."}


def _post_texts(posts: Iterable[tuple[str, str | None, str]]) -> Iterator[str]:
    for _, title, body in posts:
        body = body.strip()
        if body.casefold() in REMOVED_BODIES:
            continue
        text = "\n".join(part for part in ((title or "").strip(), body) if part)
        if text:
            yield text


def _combine_posts(
    texts: Iterable[str], *, max_posts: int | None, max_chars: int | None,
) -> str:
    separator = "\n---\n"
    parts = []
    remaining = MAX_USER_CHARS
    for text in islice(texts, max_posts):
        prefix = separator if parts else ""
        if remaining <= len(prefix):
            break
        part = prefix + text[:min(max_chars or MAX_USER_CHARS, remaining - len(prefix))]
        parts.append(part)
        remaining -= len(part)
        if not remaining:
            break
    return "".join(parts)


def _user_inputs(
    rows: Iterable[tuple[str, str | None, str]], *, max_posts: int | None, max_chars: int | None,
) -> Iterator[tuple[str, str]]:
    for user_id, posts in groupby(rows, key=itemgetter(0)):
        combined = _combine_posts(_post_texts(posts), max_posts=max_posts, max_chars=max_chars)
        if combined:
            yield user_id, combined


def _single_place(value: object) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        if value and value.casefold() not in UNKNOWN_PLACES and not MULTIPLE_PLACES.search(value):
            return value
    return None


def _normalize_demographics(result: dict) -> dict:
    sex = result.get("sex")
    return {
        "age": self_reported_age(result.get("age")),
        "sex": SEX_VALUES.get(sex.strip().casefold()) if isinstance(sex, str) else None,
        "country": _single_place(result.get("country")),
        "state": _single_place(result.get("state")),
    }


def _condition_name(condition: object) -> str:
    name = condition.get("condition_name") if isinstance(condition, dict) else condition
    return name.strip() if isinstance(name, str) else ""


def _parse_reply(raw: str) -> dict:
    try:
        result = json.loads(strip_markdown_fences(raw))
    except ValueError as exc:
        raise LLMParseError("Expected a demographics JSON object") from exc
    if not isinstance(result, dict) or RESPONSE_FIELDS.isdisjoint(result):
        raise LLMParseError("Expected a demographics JSON object")

    conditions = result.get("conditions")
    if conditions is None:
        conditions = []
    if not isinstance(conditions, list) or any(not _condition_name(item) for item in conditions):
        raise LLMParseError("Expected a list of named conditions")
    return {**_normalize_demographics(result), "conditions": conditions}


def extract_demographics(client, text: str) -> dict:
    """Read demographics and conditions from one author's prepared text."""
    prompt = DEMOGRAPHICS_PROMPT + wrap_untrusted_text(text)
    for attempt, temperature in enumerate(TEMPERATURES, start=1):
        try:
            raw = llm_call(client, prompt, model=MODEL_FAST, max_tokens=300, temperature=temperature)
            return _parse_reply(raw)
        except LLMContentFilteredError:
            raise
        except (LLMParseError, LLMResponseError):
            if attempt == len(TEMPERATURES):
                raise
            log.info("Unreadable demographics reply (%d/%d), retrying", attempt, len(TEMPERATURES))
    raise AssertionError("Unreachable")


def _extract_users(client, users: Iterable[tuple[str, str]]) -> Iterator[tuple[str, dict | None]]:
    pool = ThreadPoolExecutor(max_workers=MAX_IN_FLIGHT)
    users = iter(users)
    pending = {}
    try:
        for user_id, text in islice(users, MAX_IN_FLIGHT):
            pending[pool.submit(extract_demographics, client, text)] = user_id

        while pending:
            completed, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                user_id = pending.pop(future)
                try:
                    result = future.result()
                except Exception as exc:
                    if not isinstance(exc, LLMParseError) and not is_transient_or_truncated(exc):
                        log.error("Stopping demographics run: %s failed (%s)", user_id, type(exc).__name__)
                        raise
                    log.warning("Skipping demographics for %s (%s)", user_id, type(exc).__name__)
                    yield user_id, None
                else:
                    yield user_id, result

            # Check all completed requests for fatal errors before scheduling replacements.
            for user_id, text in islice(users, len(completed)):
                pending[pool.submit(extract_demographics, client, text)] = user_id
    finally:
        pool.shutdown(cancel_futures=True)


def _write_result(conn: Connection, run_id: int, user_id: str, result: dict) -> int:
    age = result["age"]
    age_bucket = _bucketize_age(str(age)) if age is not None else None
    location = " / ".join(filter(None, (result["country"], result["state"]))) or None
    # city stays empty: per-post extraction (#206) fills it.
    conn.execute(
        "INSERT INTO user_profiles (user_id, run_id, age_bucket, age, sex, location) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, run_id, age_bucket, age, result["sex"], location),
    )

    conditions_written = 0
    for condition in result["conditions"]:
        name = _condition_name(condition).lower()
        kind = condition.get("condition_type") if isinstance(condition, dict) else None
        kind = kind.strip().lower() if isinstance(kind, str) else None
        conn.execute(
            "INSERT INTO conditions (run_id, user_id, post_id, condition_type, condition_name, severity) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, user_id, None, kind if kind in ("illness", "symptom") else "illness", name, None),
        )
        conditions_written += 1
    return conditions_written


def run_demographics(
    db_path: Path, *, limit: int = 0, max_posts: int | None = None, max_chars: int | None = None,
):
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    if (max_posts is not None and max_posts < 1) or (max_chars is not None and max_chars < 1):
        raise ValueError("max_posts and max_chars must be positive when set")

    client = get_client()
    with closing(open_db(db_path)) as conn:
        run_config = {
            "limit": limit,
            "model": MODEL_FAST,
            "max_user_chars": MAX_USER_CHARS,
            "max_posts": max_posts,
            "max_chars": max_chars,
            "temperatures": TEMPERATURES,
            "workers": MAX_IN_FLIGHT,
        }
        cursor = conn.execute(
            "INSERT INTO extraction_runs (run_at, commit_hash, extraction_type, config) VALUES (?, ?, ?, ?)",
            (int(time.time()), get_git_commit(), "demographics", json.dumps(run_config)),
        )
        run_id = cursor.lastrowid
        conn.commit()
        log.info("Extraction run %s", run_id)

        profiles_written = conditions_written = failures = 0
        # Stream posts on a separate connection. If another writer commits while
        # this cursor is open, upgrading its WAL read snapshot would fail with SQLITE_BUSY_SNAPSHOT.
        with closing(open_db(db_path)) as reader, closing(reader.execute(
            "SELECT user_id, title, body_text FROM posts WHERE user_id != ? "
            "ORDER BY user_id, post_date DESC, post_id",
            (DELETED_USER_ID,),
        )) as rows:
            users = _user_inputs(rows, max_posts=max_posts, max_chars=max_chars)
            with closing(_extract_users(client, islice(users, limit or None))) as results:
                for processed, (user_id, result) in enumerate(results, start=1):
                    if result is None:
                        failures += 1
                    else:
                        conditions_written += _write_result(conn, run_id, user_id, result)
                        profiles_written += 1
                    if processed % COMMIT_EVERY == 0:
                        conn.commit()
                        log.info("Processed %d users (%d failures)", processed, failures)
        conn.commit()

    log.info("Done: %d profiles, %d conditions written, %d failures", profiles_written, conditions_written, failures)


def main():
    parser = argparse.ArgumentParser(
        description=f"Extract demographics and conditions from up to {MAX_USER_CHARS:,} characters per user."
    )
    parser.add_argument("--db", required=True, type=Path, help="Path to the corpus SQLite database")
    parser.add_argument("--limit", type=int, default=0, help="Limit to N eligible users (0 = all)")
    parser.add_argument("--max-posts", type=int, help="Optional limit on posts per user")
    parser.add_argument("--max-chars", type=int, help="Optional character limit per post, including its title")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be nonnegative")
    for flag, value in (("--max-posts", args.max_posts), ("--max-chars", args.max_chars)):
        if value is not None and value < 1:
            parser.error(f"{flag} must be positive")
    run_demographics(args.db, limit=args.limit, max_posts=args.max_posts, max_chars=args.max_chars)


if __name__ == "__main__":
    main()
