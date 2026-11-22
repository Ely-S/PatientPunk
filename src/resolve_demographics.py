"""Turn per-post demographic claims into one user_profiles row per user, in code (#206).

Resolution is recomputed from demographic_claims_latest on every run, so it needs no state of its
own: a restart, a re-read that retracted claims, or a newer reference date is picked up by the next
call. A user gets a new row only when their resolved profile differs from user_profiles_latest.
Each row keeps the age in years (a real number), advanced to the reference date, beside its decade.
When the author gave a range or decade instead of a number, the age is that range's midpoint
("late 30s" -> 37.5).
"""
import math
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone

from import_posts import DELETED_USER_ID
from patientpunk.db import PROFILE_FIELDS, _bucketize_age, apply_schema, latest_profiles


def _years_between(start: int, end: int) -> int:
    a, b = (datetime.fromtimestamp(t, timezone.utc) for t in (start, end))
    return b.year - a.year - ((b.month, b.day) < (a.month, a.day))


_DECADE = re.compile(r"\b(early|mid|late)?[\s-]*(\d)0\s*'?s\b")
_RANGE = re.compile(r"(\d{1,3})\s*(?:-|–|to)\s*(\d{1,3})")
# Where in its decade each phrase points: early = lower half, late = upper half, mid or none = the centre.
_DECADE_PART = {"early": 2.5, "mid": 5.0, "late": 7.5}


def _estimate(value: str) -> tuple[float, bool] | None:
    """(age in years, estimated) from what the author wrote: a number as given; a range or decade at
    its midpoint ("25-34" -> 29.5, "30s" or "mid-30s" -> 35, "early 40s" -> 42.5, "late 30s" -> 37.5).
    None when there is no age in it."""
    text = value.strip().lower()
    try:
        number = float(text)
        return (number, False) if math.isfinite(number) else None
    except ValueError:
        pass
    if m := _RANGE.fullmatch(text):
        low, high = int(m[1]), int(m[2])
        return ((low + high) / 2, True) if low <= high else None
    if m := _DECADE.search(text):
        return int(m[2]) * 10 + _DECADE_PART.get(m[1], 5.0), True
    return None


def _age_now(value: str, date: int | None, reference: int | None) -> tuple[float, bool] | None:
    """(age, estimated) advanced to the reference date; None when unparseable or out of range."""
    stated = _estimate(value)
    if stated is None:
        return None
    age, estimated = stated
    if date is not None and reference is not None:
        age += _years_between(date, reference)
    return (age, estimated) if _bucketize_age(str(age)) else None


def _resolve(claims: list[tuple], reference: int | None) -> tuple[tuple, set[str]]:
    """claims: (post_date, post_id, field, value), oldest first. Returns the profile row
    in PROFILE_FIELDS order and the fields whose claims disagree. Text values are compared
    ignoring case; sex is stored lowercase."""
    by_field = defaultdict(list)
    countries = {}
    for date, post_id, field, value in claims:
        value = value.strip()
        by_field[field].append((date, post_id, value.lower() if field == "sex" else value))
        if field == "country":
            countries[post_id] = value.casefold()
    ages = [a for a in (_age_now(v, d, reference) for d, _, v in by_field["age"]) if a is not None]
    age = ages[-1][0] if ages else None
    age_bucket = _bucketize_age(str(age)) if age is not None else None
    sex = by_field["sex"][-1][2] if by_field["sex"] else None
    country = by_field["country"][-1][2] if by_field["country"] else None
    key = country.casefold() if country else None
    states = [v for _, p, v in by_field["state"] if countries.get(p, key) == key]
    state = states[-1] if states else None
    # A city counts only from a post that names the resolved country and state, or neither.
    state_key = state.casefold() if state else None
    state_of = {p: v.casefold() for _, p, v in by_field["state"]}
    cities = [v for _, p, v in by_field["city"]
              if countries.get(p, key) == key and state_of.get(p, state_key) == state_key]
    city = cities[-1] if cities else None
    location = " / ".join(x for x in (country, state) if x) or None
    disagree = {f for f, rows in by_field.items()
                if f != "age" and len({v.casefold() for _, _, v in rows}) > 1}
    # Two different stated numbers disagree; an estimate disagrees only when its decade differs.
    stated = {a for a, estimated in ages if not estimated}
    if len(stated) > 1 or len({_bucketize_age(str(a)) for a, _ in ages}) > 1:
        disagree.add("age")
    return (age_bucket, age, sex, location, city), disagree


def resolve_profiles(conn: sqlite3.Connection, run_id: int, failed_users=frozenset()) -> dict:
    """Write a user_profiles row under ``run_id`` (a demographics run) for every user whose posts some
    run has read and whose resolved profile differs from their current one, with empty fields where
    nothing is known. Users in ``failed_users`` are skipped, so their previous profile stays current;
    the ``deleted`` placeholder for authorless posts is never a patient and never gets a profile.
    The reference date (the newest post_date) is recorded in the run's config. Commits; returns counts."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(user_profiles)")}
    if not set(PROFILE_FIELDS) <= columns or not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'demographic_claims_latest'").fetchone():
        apply_schema(conn)  # a database built before the claim tables or a profile column; this commits
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
        resolved = tuple("" if v is None else str(v) for v in profile)
        if p is None or tuple(p[k] for k in PROFILE_FIELDS) != resolved:
            rows.append((user, run_id, *profile))
    with conn:
        conn.executemany(
            f"INSERT INTO user_profiles (user_id, run_id, {', '.join(PROFILE_FIELDS)}) "
            f"VALUES ({', '.join('?' * (len(PROFILE_FIELDS) + 2))})", rows)
        conn.execute("UPDATE extraction_runs SET config = json_set(config, '$.reference_date', ?) WHERE run_id = ?",
                     (reference, run_id))
    return {"profiles_written": len(rows), "reference_date": reference, "disagreements": dict(disagreements)}
