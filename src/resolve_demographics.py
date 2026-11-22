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


# Dashes and apostrophes as they arrive from phones and pasted text, made plain before matching.
_PLAIN = str.maketrans({"–": "-", "—": "-", "‐": "-", "‑": "-", "’": "'", "‘": "'"})
_LEAD = re.compile(r"^(?:i'?m|i am|in my|my|about|around|aged?|~)\s*")
_UNITS = re.compile(r"(?<=\d)\s*(?:years?\s+old|years?|yrs?|y/?o)\b")
_RANGE = re.compile(r"(\d{1,3})\s*(?:-|to)\s*(\d{1,3})")
_DECADE_RANGE = re.compile(r"(\d)0\s*'?s?\s*(?:-|to)\s*(\d)0\s*'?s")  # "20s-30s", "20-30s"
_DECADE = re.compile(r"(early|mid|late)?[\s-]*(\d)0\s*'?s")
# Where in its decade each phrase points: early = lower half, late = upper half, mid or none = the centre.
_DECADE_PART = {"early": 2.5, "mid": 5.0, "late": 7.5}


def _estimate(value: str) -> tuple[float, bool] | None:
    """(age in years, estimated) from what the author wrote: a number as given; a range or decade at
    its midpoint ("25-34" -> 29.5, "30s" or "mid-30s" -> 35, "early 40s" -> 42.5, "late 30s" -> 37.5,
    "20s-30s" -> 30). The whole value must be the age, give or take "in my", "~" or "years old";
    an open-ended "65+" or "60s+" has no midpoint. None when there is no age in it."""
    text = value.strip().lower().translate(_PLAIN)
    if text.endswith("+"):
        return None
    text = _UNITS.sub("", _LEAD.sub("", text)).strip()
    try:
        number = float(text)
        return (number, False) if math.isfinite(number) else None
    except ValueError:
        pass
    if m := _RANGE.fullmatch(text):
        low, high = int(m[1]), int(m[2])
        return ((low + high) / 2, True) if low <= high else None
    if m := _DECADE_RANGE.fullmatch(text):
        low, high = int(m[1]) * 10, int(m[2]) * 10 + 10  # "20s-30s" spans 20 to 40
        return ((low + high) / 2, True) if low < high else None
    if m := _DECADE.fullmatch(text):
        return int(m[2]) * 10 + _DECADE_PART.get(m[1], 5.0), True
    return None


def stated_age(value: str) -> tuple[float, bool] | None:
    """(age, estimated) as stated, when it is from 10 to 99 (#206); a range or decade gives its midpoint."""
    stated = _estimate(value)
    return stated if stated is not None and 10 <= stated[0] <= 99 else None


def _age_now(value: str, date: int | None, reference: int | None) -> tuple[float, bool] | None:
    """(age, estimated): a stated age advanced to the reference date; a range or decade is advanced
    from its midpoint. None when unparseable or out of range."""
    stated = stated_age(value)
    if stated is None:
        return None
    age, estimated = stated
    if date is not None and reference is not None:
        age += _years_between(date, reference)
    return age, estimated


SEX_VALUES = {
    "f": "female", "female": "female", "woman": "female",
    "m": "male", "male": "male", "man": "male",
    "nb": "non-binary", "nonbinary": "non-binary", "non-binary": "non-binary", "non binary": "non-binary",
}


def normalize_sex(stated: str) -> str | None:
    """female, male or non-binary from the author's words, which may hold several values (#214):
    non-binary wins over a binary value ("non-binary | female" -> non-binary), and other words are
    ignored ("female | suspected intersex" -> female). None when no rule applies ("trans man",
    "female | male"); the words themselves stay in sex_stated."""
    values = {SEX_VALUES.get(part.strip().casefold()) for part in stated.split("|")} - {None}
    if "non-binary" in values:
        return "non-binary"
    return values.pop() if len(values) == 1 else None


def _resolve(claims: list[tuple], reference: int | None) -> tuple[tuple, set[str]]:
    """claims: (post_date, post_id, field, value), oldest first. Returns the profile row
    in PROFILE_FIELDS order and the fields whose claims disagree. Text values are compared
    ignoring case. sex_stated is the newest sex claim as written, and sex its normalized value."""
    by_field = defaultdict(list)
    for date, post_id, field, value in claims:
        value = value.strip()
        if not value:
            continue  # a blank claim states nothing, so it can't replace an earlier value
        by_field[field].append((date, post_id, value))
    ages = [a for a in (_age_now(v, d, reference) for d, _, v in by_field["age"]) if a is not None]
    age = ages[-1][0] if ages else None
    age_bucket = _bucketize_age(str(age)) if age is not None else None
    sex_stated = by_field["sex"][-1][2] if by_field["sex"] else None
    sex = normalize_sex(sex_stated) if sex_stated else None
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
    # City: walk the posts oldest first; naming a different country or state clears it, so an old
    # city never pairs with a new place.
    named = {f: {p: v.casefold() for _, p, v in by_field[f]} for f in ("country", "state")}
    cities = {p: v for _, p, v in by_field["city"]}
    place, city = {}, None
    for post_id in order:
        for f in ("country", "state"):
            if post_id in named[f]:
                if place.get(f, named[f][post_id]) != named[f][post_id]:
                    city = None
                place[f] = named[f][post_id]
        city = cities.get(post_id, city)
    disagree = {f for f, rows in by_field.items()
                if f != "age" and len({v.casefold() for _, _, v in rows}) > 1}
    # Stated ages within a year agree (whole-year advancing can put the same age a year apart);
    # an estimate from a range or decade disagrees only when its decade differs.
    stated = [a for a, estimated in ages if not estimated]
    decades = {_bucketize_age(str(a)) for a, estimated in ages if estimated}
    if ((stated and max(stated) - min(stated) > 1) or len(decades) > 1
            or (decades and stated and not decades <= {_bucketize_age(str(a)) for a in stated})):
        disagree.add("age")
    return (age_bucket, age, sex, sex_stated, location, city), disagree


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
