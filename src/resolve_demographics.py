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
    """A stated age (10-99, #206) advanced to the reference date. A decade ("mid-30s") can't be
    advanced, so it is returned as its bucket; anything unparseable or out of range is None and ignored."""
    try:
        age = int(float(value))
    except (ValueError, OverflowError):
        return _bucketize_age(value)
    if not 10 <= age <= 99:
        return None
    if date is not None and reference is not None:
        age += _years_between(date, reference)
    return age


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
    # The latest country, plus the latest state from that country (#206). A state from a post that
    # names no country belongs to the nearest country named before it, or else the first named after
    # it, so US, then "Texas", then UK is "UK": an old state never pairs with a new country.
    order = {p: i for i, p in enumerate(dict.fromkeys(p for _, p, _, _ in claims))}
    named = [(order[p], v.casefold()) for _, p, v in by_field["country"]]
    country = by_field["country"][-1][2] if by_field["country"] else None

    def state_country(post_id):
        i = order[post_id]
        before = [c for j, c in named if j <= i]
        after = [c for j, c in named if j > i]
        return before[-1] if before else (after[0] if after else None)

    states = [v for _, p, v in by_field["state"] if state_country(p) in (country and country.casefold(), None)]
    location = " / ".join(x for x in (country, states[-1] if states else None) if x) or None
    disagree = {f for f, rows in by_field.items()
                if f != "age" and len({v.casefold() for _, _, v in rows}) > 1}
    # Exact ages within a year agree: whole-year advancing can put the same age a year apart.
    exact = [a for a in ages if isinstance(a, int)]
    decades = {a for a in ages if isinstance(a, str)}
    if ((exact and max(exact) - min(exact) > 1) or len(decades) > 1
            or (decades and exact and not decades <= {_bucketize_age(str(a)) for a in exact})):
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
    run_type = conn.execute("SELECT extraction_type FROM extraction_runs WHERE run_id = ?", (run_id,)).fetchone()
    if run_type != ("demographics",):
        raise ValueError(f"run {run_id} is not a demographics run; user_profiles_latest would ignore its rows")
    reference = conn.execute("SELECT MAX(post_date) FROM posts").fetchone()[0]
    claims = defaultdict(list)
    for user, *claim in conn.execute(
            "SELECT p.user_id, p.post_date, c.post_id, c.field, c.value FROM demographic_claims_latest c "
            "JOIN posts p ON p.post_id = c.post_id "
            "ORDER BY p.post_date IS NOT NULL, p.post_date, c.post_id"):
        claims[user].append(tuple(claim))
    read = {u for (u,) in conn.execute(
        "SELECT DISTINCT p.user_id FROM posts p WHERE EXISTS (SELECT 1 FROM post_runs pr "
        "JOIN extraction_runs r ON r.run_id = pr.run_id "
        "WHERE pr.post_id = p.post_id AND r.extraction_type = 'demographics')")}
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
