"""Compare activity windows and follow-up horizons using a prospective diary export."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SEVERITY_GROUPS = {"mild", "moderate", "severe", "very_severe", "unknown"}
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
ITEM_STATES = ("cost_free_only", "mixed", "cost_free_with_unknown", "cost_only", "not_attempted", "unknown")
ATTEMPT_STATES = {True: "cost", False: "no_cost", None: "unknown"}


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Supply timestamp values as strings")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    if parsed.utcoffset() is None:
        raise ValueError("Diary times must include a UTC offset")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class Attempt:
    item: str
    at: datetime
    followed_until: datetime | None
    cost_at: datetime | None

    @classmethod
    def from_record(cls, record):
        at = timestamp(record["at"])
        followed = record["followed_until"]
        cost = record["cost_at"]
        attempt = cls(record["item"], at, timestamp(followed) if followed is not None else None,
                      timestamp(cost) if cost is not None else None)
        if any(end is not None and end < at for end in (attempt.followed_until, attempt.cost_at)):
            raise ValueError("Follow-up and cost onset must be at or after the attempt")
        return attempt

    def had_cost(self, hours):
        cutoff = self.at + timedelta(hours=hours)
        if self.cost_at is not None and self.cost_at <= cutoff:
            return True
        if self.followed_until is not None and self.followed_until >= cutoff:
            return False
        return None


@dataclass(frozen=True)
class DiaryDay:
    complete: bool
    attempts: tuple[Attempt, ...]


def read_days(records, items, zone):
    days = {}
    for record in records:
        day = date.fromisoformat(record["date"])
        if day in days:
            raise ValueError("Duplicate activity diary date within a participant")
        complete = record["complete"]
        if not isinstance(complete, bool):
            raise ValueError("A diary date must be marked complete or partial")
        attempts = tuple(Attempt.from_record(row) for row in record["attempts"])
        if any(attempt.item not in items or attempt.at.astimezone(zone).date() != day for attempt in attempts):
            raise ValueError("Each attempt must use a listed item and belong to its diary date in local time")
        if len({(attempt.item, attempt.at) for attempt in attempts}) != len(attempts):
            raise ValueError("Duplicate attempt time for the same item")
        days[day] = DiaryDay(complete, attempts)
    return days


def score_window(items, attempts, hours, missing_days):
    outcomes = defaultdict(set)
    for attempt in attempts:
        outcomes[attempt.item].add(attempt.had_cost(hours))

    states = Counter()
    for item in items:
        observed = outcomes[item]
        if False in observed and True in observed:
            states["mixed"] += 1
        elif False in observed:
            states["cost_free_with_unknown" if None in observed or missing_days else "cost_free_only"] += 1
        elif None in observed or missing_days:
            states["unknown"] += 1
        else:
            states["cost_only" if True in observed else "not_attempted"] += 1

    minimum = states["cost_free_only"] + states["mixed"] + states["cost_free_with_unknown"]
    return (minimum, minimum + states["unknown"]), states


@dataclass
class Week:
    participant: str
    severity: str
    scheduled_days: Counter
    logged_days: Counter
    complete_days: Counter
    attempts: Counter
    omitted_attempts: Counter
    scores: dict
    item_states: dict
    followup: dict


def evaluate_week(participant, severity, start, diary, items, reference_hours):
    dates = [start + timedelta(days=offset) for offset in range(7)]
    days = [diary.get(day, DiaryDay(False, ())) for day in dates]
    attempts = [attempt for day in days for attempt in day.attempts]
    early_attempts = [attempt for day in days[:5] for attempt in day.attempts]
    missing = sum(not day.complete for day in days)
    windows = {
        "five_days_48h": (early_attempts, 48, sum(not day.complete for day in days[:5])),
        "seven_days_48h": (attempts, 48, missing),
        "seven_days_72h": (attempts, 72, missing),
        "reference": (attempts, reference_hours, missing),
    }
    scores = {}
    item_states = {}
    for label, (entries, hours, unlogged) in windows.items():
        scores[label], item_states[label] = score_window(items, entries, hours, unlogged)

    followup = {label: Counter() for label in ("48h", "72h")}
    for attempt in attempts:
        reference = attempt.had_cost(reference_hours)
        for hours in (48, 72):
            earlier = attempt.had_cost(hours)
            followup[f"{hours}h"][ATTEMPT_STATES[earlier], ATTEMPT_STATES[reference]] += 1

    return Week(
        participant, severity,
        Counter(day.weekday() for day in dates),
        Counter(day.weekday() for day in dates if day in diary),
        Counter(day.weekday() for day, entry in zip(dates, days) if entry.complete),
        Counter({day.weekday(): len(entry.attempts) for day, entry in zip(dates, days)}),
        Counter({day.weekday(): len(entry.attempts) for day, entry in zip(dates[5:], days[5:])}),
        scores, item_states, followup,
    )


def weekday_totals(weeks, attribute):
    return {name: sum(getattr(week, attribute)[index] for week in weeks)
            for index, name in enumerate(WEEKDAYS)}


def compare_scores(weeks, left, right, *, adding_days):
    differences = []
    bounds = []
    people = set()
    for week in weeks:
        a_low, a_high = week.scores[left]
        b_low, b_high = week.scores[right]
        # Adding days can only add qualifying items. Extending follow-up can only remove them.
        lower, upper = b_low - a_high, b_high - a_low
        bounds.append((max(0, lower), upper) if adding_days else (lower, min(0, upper)))
        if a_low == a_high and b_low == b_high:
            differences.append(b_low - a_low)
            people.add(week.participant)

    return {
        "complete_pair_weeks": len(differences),
        "complete_pair_participants": len(people),
        "mean_difference_complete_pairs": mean(differences) if differences else None,
        "mean_absolute_difference_complete_pairs": mean(map(abs, differences)) if differences else None,
        "mean_difference_bounds_all_weeks": [mean(column) for column in zip(*bounds)],
    }


def summarize(weeks):
    policies = {}
    for label in weeks[0].scores:
        policies[label] = {
            "weeks_with_exact_score": sum(week.scores[label][0] == week.scores[label][1] for week in weeks),
            "item_weeks_by_state": {state: sum(week.item_states[label][state] for week in weeks)
                                    for state in ITEM_STATES},
        }

    outcomes = ATTEMPT_STATES.values()
    followup = {
        label: {early: {reference: sum(week.followup[label][early, reference] for week in weeks)
                        for reference in outcomes} for early in outcomes}
        for label in ("48h", "72h")
    }
    return {
        "participants": len({week.participant for week in weeks}),
        "weeks": len(weeks),
        "scheduled_days_by_weekday": weekday_totals(weeks, "scheduled_days"),
        "logged_days_by_weekday": weekday_totals(weeks, "logged_days"),
        "complete_days_by_weekday": weekday_totals(weeks, "complete_days"),
        "attempts_by_weekday": weekday_totals(weeks, "attempts"),
        "attempts_excluded_by_five_day_window": weekday_totals(weeks, "omitted_attempts"),
        "policies": policies,
        "attempt_outcomes_against_reference": followup,
        "paired_score_comparisons": {
            "seven_minus_five_days_at_48h": compare_scores(weeks, "five_days_48h", "seven_days_48h",
                                                           adding_days=True),
            "72h_minus_48h_at_seven_days": compare_scores(weeks, "seven_days_48h", "seven_days_72h",
                                                          adding_days=False),
            "reference_minus_seven_days_72h": compare_scores(weeks, "seven_days_72h", "reference",
                                                             adding_days=False),
        },
    }


def analyse(data, reference_hours):
    if reference_hours < 72:
        raise ValueError("The reference horizon must be at least 72 hours")
    items = data["items"]
    if (not isinstance(items, list) or not items or any(not isinstance(item, str) or not item for item in items)
            or len(set(items)) != len(items)):
        raise ValueError("Supply a nonempty fixed set of unique items")

    weeks = []
    participants = set()
    for person in data["participants"]:
        identifier = person["id"]
        severity = person["severity"]
        if not isinstance(identifier, str) or not identifier or identifier in participants or severity not in SEVERITY_GROUPS:
            raise ValueError("Participant identifiers must be unique and severity must use a listed group")
        participants.add(identifier)
        starts = sorted(date.fromisoformat(raw) for raw in person["week_starts"])
        if not starts or any((b - a).days < 7 for a, b in zip(starts, starts[1:])):
            raise ValueError("Supply at least one study week per participant and avoid overlapping weeks")
        diary = read_days(person["days"], items, ZoneInfo(person["time_zone"]))
        weeks.extend(evaluate_week(identifier, severity, start, diary, items, reference_hours)
                     for start in starts)
    if not weeks:
        raise ValueError("Supply at least one participant with a scheduled study week")

    groups = defaultdict(list)
    for week in weeks:
        groups[week.severity].append(week)
    return {
        "reference_hours": reference_hours,
        "items_per_week": len(items),
        "overall": summarize(weeks),
        "by_severity": {severity: summarize(group) for severity, group in sorted(groups.items())},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diary", type=Path)
    parser.add_argument("--reference-hours", type=int, default=120, help="Longer follow-up horizon (default 120)")
    args = parser.parse_args()
    try:
        with args.diary.open(encoding="utf-8") as source:
            report = analyse(json.load(source), args.reference_hours)
    except (KeyError, OSError, TypeError, ValueError, OverflowError, ZoneInfoNotFoundError) as error:
        parser.exit(2, f"Invalid diary input ({type(error).__name__}). Check the input contract.\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
