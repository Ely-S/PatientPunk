#!/usr/bin/env python3
"""Extract self-reported demographics and conditions from SQLite posts."""

import argparse
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
    wrap_untrusted_text,
)
from patientpunk.db import _bucketize_age, apply_schema, register_run
from prompts.demographic_prompt import DEMOGRAPHICS_PROMPT
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

MAX_USER_CHARS = 8_000
SEPARATOR = "\n---\n"
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


def _combine_posts(texts: Iterable[str]) -> str:
    parts, size = [], 0
    for text in texts:  # stop reading once the cap is reached
        parts.append(text)
        size += len(text) + len(SEPARATOR)
        if size >= MAX_USER_CHARS:
            break
    return SEPARATOR.join(parts)[:MAX_USER_CHARS]


def _user_inputs(rows: Iterable[tuple[str, str | None, str]]) -> Iterator[tuple[str, str]]:
    for user_id, posts in groupby(rows, key=itemgetter(0)):
        if combined := _combine_posts(_post_texts(posts)):
            yield user_id, combined


def _single_place(value: object) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        if value and value.casefold() not in UNKNOWN_PLACES and not MULTIPLE_PLACES.search(value):
            return value
    return None


def _normalize_demographics(result: dict) -> dict:
    sex = result.get("sex")
    age = result.get("age")
    if isinstance(age, float) and age.is_integer():
        age = int(age)  # JSON 34.0
    return {
        "age": self_reported_age(age),
        "sex": SEX_VALUES.get(sex.strip().casefold()) if isinstance(sex, str) else None,
        "country": _single_place(result.get("country")),
        "state": _single_place(result.get("state")),
    }


def _condition_name(condition: object) -> str:
    name = condition.get("condition_name") if isinstance(condition, dict) else condition
    return name.strip() if isinstance(name, str) else ""


def _parse_reply(raw: str) -> dict:
    result = parse_json_object(raw)  # tolerates fences, prose around the object and trailing commas
    if RESPONSE_FIELDS.isdisjoint(result):
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
    """Yield (user_id, result or None on a per-user failure), with up to MAX_IN_FLIGHT calls running.
    Users are submitted only as earlier calls finish, so a permanent error leaves the rest unsent."""
    users = iter(users)
    with ThreadPoolExecutor(max_workers=MAX_IN_FLIGHT) as pool:
        pending = {pool.submit(extract_demographics, client, text): user_id
                   for user_id, text in islice(users, MAX_IN_FLIGHT)}
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
                    result = None
                yield user_id, result
            for user_id, text in islice(users, len(completed)):
                pending[pool.submit(extract_demographics, client, text)] = user_id


def _write_result(conn: Connection, run_id: int, user_id: str, result: dict) -> int:
    # The age as last stated, not advanced to a reference date: a per-user reply doesn't say which
    # post it came from. Ranges and decades were rejected in _normalize_demographics.
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
            "INSERT INTO conditions (run_id, user_id, condition_type, condition_name) VALUES (?, ?, ?, ?)",
            (run_id, user_id, kind if kind in ("illness", "symptom") else "illness", name),
        )
        conditions_written += 1
    return conditions_written


def run_demographics(db_path: Path, *, limit: int = 0):
    client = get_client()
    with closing(open_db(db_path)) as conn:
        apply_schema(conn)  # a database from before user_profiles.age/city or extraction_runs.finished_at
        run_id = register_run(conn, "demographics", {
            "provider": LLM_PROVIDER,
            "reasoning_mode": LLM_REASONING_MODE,
            "git_dirty": git_is_dirty(),
            "model": MODEL_FAST,
            "limit": limit,
            "max_user_chars": MAX_USER_CHARS,
            "temperatures": TEMPERATURES,
            "workers": MAX_IN_FLIGHT,
        }, commit_hash=get_git_commit())
        log.info("Extraction run %s", run_id)

        profiles_written = conditions_written = failures = 0
        # Stream posts on a separate connection. If another writer commits while
        # this cursor is open, upgrading its WAL read snapshot would fail with SQLITE_BUSY_SNAPSHOT.
        with closing(open_db(db_path)) as reader, closing(reader.execute(
            "SELECT user_id, title, body_text FROM posts WHERE user_id != ? "
            "ORDER BY user_id, post_date DESC, post_id",
            (DELETED_USER_ID,),
        )) as rows:
            users = _user_inputs(rows)
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
        conn.execute("UPDATE extraction_runs SET finished_at = ? WHERE run_id = ?", (int(time.time()), run_id))
        conn.commit()

    log.info("Done: %d profiles, %d conditions written, %d failures", profiles_written, conditions_written, failures)


def main():
    parser = argparse.ArgumentParser(
        description=f"Extract demographics and conditions from up to {MAX_USER_CHARS:,} characters per user."
    )
    parser.add_argument("--db", required=True, type=Path, help="Path to the corpus SQLite database")
    parser.add_argument("--limit", type=int, default=0, help="Limit to N eligible users (0 = all)")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be nonnegative")
    run_demographics(args.db, limit=args.limit)


if __name__ == "__main__":
    main()
