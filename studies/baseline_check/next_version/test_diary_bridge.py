"""Regression cases for the diary bridge's time windows and missing outcomes."""

from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from diary_bridge import Attempt, analyse, score_window


START = date(2026, 1, 5)
ITEMS = ["walk", "phone", "meal"]


def entry(item, at, followed_until=None, cost_at=None):
    return dict(item=item, at=at, followed_until=followed_until, cost_at=cost_at)


def panel():
    days = [{"date": (START + timedelta(days=n)).isoformat(), "complete": True, "attempts": []} for n in range(7)]
    days[0]["attempts"] = [entry("walk", "2026-01-05T08:00Z", "2026-01-10T08:00Z", "2026-01-07T20:00Z")]
    days[1]["attempts"] = [
        entry("meal", "2026-01-06T08:00Z", "2026-01-11T08:00Z", "2026-01-06T18:00Z"),
        entry("meal", "2026-01-06T20:00Z", "2026-01-11T20:00Z"),
    ]
    days[5]["attempts"] = [entry("phone", "2026-01-10T08:00Z", "2026-01-15T08:00Z")]
    days[6]["attempts"] = [entry("phone", "2026-01-11T08:00Z", "2026-01-16T08:00Z", "2026-01-15T02:00Z")]
    return {"items": ITEMS, "participants": [
        {"id": "demo-person-1", "severity": "moderate", "time_zone": "UTC", "week_starts": ["2026-01-05"],
         "days": days},
        {"id": "demo-person-2", "severity": "severe", "time_zone": "UTC",
         "week_starts": ["2026-01-05", "2026-01-12"], "days": days[:5]},
    ]}


class DiaryBridgeTests(unittest.TestCase):
    def test_cli_isolates_weekday_loss_from_longer_followup(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "demo.json"
            source.write_text(json.dumps(panel()), encoding="utf-8")
            script = Path(__file__).with_name("diary_bridge.py")
            output = subprocess.check_output([sys.executable, str(script), str(source)], text=True)
        self.assertNotIn("demo-person", output)
        report = json.loads(output)
        self.assertEqual(report["overall"]["weeks"], 3)
        self.assertEqual(report["overall"]["participants"], 2)
        moderate = report["by_severity"]["moderate"]
        self.assertEqual(moderate["attempts_excluded_by_five_day_window"]["Sat"], 1)
        self.assertEqual(moderate["attempts_excluded_by_five_day_window"]["Sun"], 1)
        self.assertEqual(moderate["policies"]["five_days_48h"]["item_weeks_by_state"]["not_attempted"], 1)
        self.assertEqual(moderate["policies"]["reference"]["item_weeks_by_state"]["mixed"], 2)
        comparison = moderate["paired_score_comparisons"]
        self.assertEqual(comparison["seven_minus_five_days_at_48h"]["mean_difference_complete_pairs"], 1)
        self.assertEqual(comparison["72h_minus_48h_at_seven_days"]["mean_difference_complete_pairs"], -1)
        self.assertEqual(moderate["attempt_outcomes_against_reference"]["48h"]["no_cost"]["cost"], 2)
        self.assertEqual(moderate["attempt_outcomes_against_reference"]["72h"]["no_cost"]["cost"], 1)

    def test_missing_days_keep_the_paired_score_unknown(self):
        severe = analyse(panel(), 120)["by_severity"]["severe"]
        self.assertEqual(severe["logged_days_by_weekday"]["Sat"], 0)
        pair = severe["paired_score_comparisons"]["seven_minus_five_days_at_48h"]
        self.assertEqual(pair["complete_pair_weeks"], 0)
        self.assertIsNone(pair["mean_difference_complete_pairs"])
        self.assertEqual(pair["mean_difference_bounds_all_weeks"], [0, 2])

    def test_unknown_cost_can_coexist_with_a_confirmed_cost_free_attempt(self):
        unknown = Attempt.from_record(entry("walk", "2026-01-05T08:00Z", "2026-01-06T08:00Z"))
        confirmed = Attempt.from_record(entry("walk", "2026-01-06T08:00Z", "2026-01-10T08:00Z"))
        bounds, states = score_window(["walk"], [unknown], 48, missing_days=0)
        self.assertEqual((bounds, states["unknown"]), ((0, 1), 1))
        bounds, states = score_window(["walk"], [unknown, confirmed], 48, missing_days=0)
        self.assertEqual((bounds, states["cost_free_with_unknown"]), ((1, 1), 1))

    def test_partial_day_preserves_observed_attempts(self):
        data = panel()
        saturday = data["participants"][0]["days"][5]
        saturday["complete"] = False
        data["participants"][0]["days"] = [saturday]
        moderate = analyse(data, 120)["by_severity"]["moderate"]
        self.assertEqual(moderate["logged_days_by_weekday"]["Sat"], 1)
        self.assertEqual(moderate["complete_days_by_weekday"]["Sat"], 0)
        states = moderate["policies"]["seven_days_48h"]["item_weeks_by_state"]
        self.assertEqual(states["cost_free_with_unknown"], 1)
        self.assertEqual(states["unknown"], 2)

    def test_followup_counts_elapsed_hours_across_a_clock_change(self):
        attempt = Attempt.from_record(entry("walk", "2026-03-07T12:00:00-08:00",
                                            cost_at="2026-03-09T13:00:00-07:00"))
        self.assertIsNone(attempt.had_cost(47))
        self.assertIs(attempt.had_cost(48), True)

    def test_duplicate_weeks_and_unzoned_timestamps_fail(self):
        data = panel()
        data["participants"][0]["week_starts"].append("2026-01-05")
        with self.assertRaisesRegex(ValueError, "overlapping"):
            analyse(data, 120)
        with self.assertRaisesRegex(ValueError, "UTC offset"):
            Attempt.from_record(entry("walk", "2026-01-05T08:00"))
