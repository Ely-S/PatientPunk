"""Turn per-post demographic claims into one user_profiles row per user, in code (#206).

Resolution is recomputed from demographic_claims_latest on every run, so it needs no state of its
own: a restart, a re-read that retracted claims, or a newer reference date is picked up by the next
call. A user gets a new row only when their resolved profile differs from user_profiles_latest.
"""
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone

from import_posts import DELETED_USER_ID
from patientpunk.db import _bucketize_age, apply_schema, latest_profiles


def _years_between(start: int, end: int) -> int:
    a, b = (datetime.fromtimestamp(t, timezone.utc) for t in (start, end))
    return b.year - a.year - ((b.month, b.day) < (a.month, a.day))


def _age_now(value: str, date: int | None, reference: int | None) -> int | str | None:
    """A stated age advanced to the reference date. A decade ("mid-30s") can't be advanced, so it is
    returned as its bucket; anything unparseable or out of range is None and ignored."""
    try:
        age = int(float(value))
    except (ValueError, OverflowError):
        return _bucketize_age(value)
    if date is not None and reference is not None:
        age += _years_between(date, reference)
    return age if _bucketize_age(str(age)) else None


def _resolve(claims: list[tuple], reference: int | None) -> tuple[tuple, set[str]]:
    """claims: (post_date, post_id, field, value), oldest first. Returns the profile row and the
    fields whose claims disagree. Text values are compared ignoring case; sex is stored lowercase."""
    by_field = defaultdict(list)
    for date, post_id, field, value in claims:
        value = value.strip()
        if not value:
            continue  # a blank claim states nothing, so it can't replace an earlier value
        by_field[field].append((date, post_id, value.lower() if field == "sex" else value))
    ages = [a for a in (_age_now(v, d, reference) for d, _, v in by_field["age"]) if a is not None]
    age = _bucketize_age(str(ages[-1])) if ages else None
    sex = by_field["sex"][-1][2] if by_field["sex"] else None
    # Walk the posts oldest first; naming a different country clears the state, so an old state
    # never pairs with a new country. A state stated before any country pairs with the first one.
    countries = {p: v for _, p, v in by_field["country"]}
    states = {p: v for _, p, v in by_field["state"]}
    country = state = None
    for post_id in dict.fromkeys(p for _, p, _, _ in claims):
        if post_id in countries:
            if country and countries[post_id].casefold() != country.casefold():
                state = None
            country = countries[post_id]
        state = states.get(post_id, state)
    location = " / ".join(x for x in (country, state) if x) or None
    disagree = {f for f, rows in by_field.items()
                if f != "age" and len({v.casefold() for _, _, v in rows}) > 1}
    exact = {a for a in ages if isinstance(a, int)}
    if len(exact) > 1 or len({_bucketize_age(str(a)) for a in ages}) > 1:
        disagree.add("age")
    return (age, sex, location), disagree


def resolve_profiles(conn: sqlite3.Connection, run_id: int, failed_users=frozenset()) -> dict:
    """Write a user_profiles row under ``run_id`` (a demographics run) for every user whose posts some
    run has read and whose resolved profile differs from their current one, with empty fields where
    nothing is known. Users in ``failed_users`` are skipped, so their previous profile stays current;
    the ``deleted`` placeholder for authorless posts is never a patient and never gets a profile.
    The reference date (the newest post_date) is recorded in the run's config. Commits; returns counts."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'demographic_claims_latest'").fetchone():
        apply_schema(conn)  # a database built before the claim tables; this commits
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
    current = latest_profiles(conn)

    disagreements, rows = Counter(), []
    for user in sorted(read - set(failed_users) - {DELETED_USER_ID}):
        profile, disagree = _resolve(claims.get(user, []), reference)
        disagreements.update(disagree)
        p = current.get(user)
        if p is None or (p["age_bucket"], p["sex"], p["location"]) != tuple(v or "" for v in profile):
            rows.append((user, run_id, *profile))
    with conn:
        conn.executemany(
            "INSERT INTO user_profiles (user_id, run_id, age_bucket, sex, location) VALUES (?, ?, ?, ?, ?)", rows)
        conn.execute("UPDATE extraction_runs SET config = json_set(config, '$.reference_date', ?) WHERE run_id = ?",
                     (reference, run_id))
    return {"profiles_written": len(rows), "reference_date": reference, "disagreements": dict(disagreements)}
