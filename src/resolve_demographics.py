"""Turn per-post demographic claims into one user_profiles row per user, in code (#206).

Resolution is recomputed from demographic_claims_latest on every run, so it needs no state of its
own: a restart, a re-read that retracted claims, or a newer reference date is picked up by the next
call. A user gets a new row only when their resolved profile differs from user_profiles_latest.
"""
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone

from patientpunk.db import _bucketize_age, apply_schema


def _years_between(start: int, end: int) -> int:
    a, b = (datetime.fromtimestamp(t, timezone.utc) for t in (start, end))
    return b.year - a.year - ((b.month, b.day) < (a.month, a.day))


def _resolve(claims: list[tuple], reference: int | None) -> tuple[tuple, set[str]]:
    """claims: (post_date, post_id, field, value), oldest first. Returns the profile row and the
    fields whose claims disagree."""
    by_field = defaultdict(list)
    countries = {}
    for date, post_id, field, value in claims:
        by_field[field].append((date, post_id, value))
        if field == "country":
            countries[post_id] = value
    ages = [int(v) + (_years_between(d, reference) if d is not None and reference is not None else 0)
            for d, _, v in by_field["age"]]
    age = _bucketize_age(str(ages[-1])) if ages else None
    sex = by_field["sex"][-1][2] if by_field["sex"] else None
    country = by_field["country"][-1][2] if by_field["country"] else None
    states = [v for _, p, v in by_field["state"] if countries.get(p, country) == country]
    location = " / ".join(x for x in (country, states[-1] if states else None) if x) or None
    disagree = {f for f, rows in by_field.items() if len({v for _, _, v in rows}) > 1 and f != "age"}
    if len(set(ages)) > 1:
        disagree.add("age")
    return (age, sex, location), disagree


def resolve_profiles(conn: sqlite3.Connection, run_id: int, failed_users=frozenset()) -> dict:
    """Write a user_profiles row under ``run_id`` (a demographics run) for every user whose posts some
    run has read and whose resolved profile differs from their current one, with empty fields where
    nothing is known. Users in ``failed_users`` are skipped, so their previous profile stays current.
    The reference date (the newest post_date) is recorded in the run's config. Commits; returns counts."""
    apply_schema(conn)  # creates the claim tables and views on a database built before them
    reference = conn.execute("SELECT MAX(post_date) FROM posts").fetchone()[0]
    claims = defaultdict(list)
    for user, *claim in conn.execute(
            "SELECT c.user_id, p.post_date, c.post_id, c.field, c.value FROM demographic_claims_latest c "
            "JOIN posts p ON p.post_id = c.post_id "
            "ORDER BY p.post_date IS NOT NULL, p.post_date, c.post_id"):
        claims[user].append(tuple(claim))
    read = {u for (u,) in conn.execute(
        "SELECT DISTINCT p.user_id FROM post_runs pr JOIN posts p ON p.post_id = pr.post_id "
        "JOIN extraction_runs r ON r.run_id = pr.run_id WHERE r.extraction_type = 'demographics'")}
    current = {u: tuple(row) for u, *row in conn.execute(
        "SELECT user_id, age_bucket, sex, location FROM user_profiles_latest")}

    disagreements, rows = Counter(), []
    for user in sorted(read - set(failed_users)):
        profile, disagree = _resolve(claims.get(user, []), reference)
        disagreements.update(disagree)
        if current.get(user) != profile:
            rows.append((user, run_id, *profile))
    with conn:
        conn.executemany(
            "INSERT INTO user_profiles (user_id, run_id, age_bucket, sex, location) VALUES (?, ?, ?, ?, ?)", rows)
        conn.execute("UPDATE extraction_runs SET config = json_set(config, '$.reference_date', ?) WHERE run_id = ?",
                     (reference, run_id))
    return {"profiles_written": len(rows), "reference_date": reference, "disagreements": dict(disagreements)}
