"""Validation sample builder and scorer (scripts/build_validation_sample.py, score_validation.py)."""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_validation_sample as B  # noqa: E402
import score_validation as S  # noqa: E402

RUN = "run-x"


def _effect(direction, target):
    return {"direction": direction, "confidence": "high", "target": target}


def _claim(effects=(), adverse=(), included=True):
    return {
        "subject": "self" if included else "other",
        "exposure_status": "actual_use",
        "adverse_event_status": "reported" if adverse else "not_stated",
        "doses": [], "effects": list(effects), "adverse_events": list(adverse),
    }


@pytest.fixture
def probe_db(tmp_path):
    """Three ketamine accounts, one with many fatigue records, plus an excluded claim."""
    path = tmp_path / "probe.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE probe_run (run_id TEXT);
        CREATE TABLE unit (run_id TEXT, unit_key TEXT, author_hash TEXT, target TEXT);
        CREATE TABLE source_window (run_id TEXT, unit_key TEXT, source_window_id TEXT,
                                    source_type TEXT, text TEXT);
        CREATE TABLE claim (run_id TEXT, claim_id TEXT, unit_key TEXT, source_window_id TEXT,
                            included INTEGER, values_json TEXT, evidence_json TEXT);
    """)
    con.execute("INSERT INTO probe_run VALUES (?)", (RUN,))
    claims = [("a", _claim([_effect("helped", "fatigue")])) for _ in range(5)]
    claims += [("b", _claim([_effect("no_effect", "low energy")])),
               ("c", _claim(adverse=[{"category": "other", "raw_event": "x",
                                      "confidence": "high", "severity": "severe"}])),
               ("c", _claim(included=False))]
    for i, (author, values) in enumerate(claims):
        unit = f"u{i}"
        con.execute("INSERT INTO unit VALUES (?,?,?,?)", (RUN, unit, author, "ketamine"))
        con.execute("INSERT INTO source_window VALUES (?,?,?,?,?)",
                    (RUN, unit, "w", "post", "window text"))
        evidence = [{"field_path": "subject", "quote": "q"},
                    {"field_path": "exposure_status", "quote": "q"},
                    {"field_path": "effects[0]", "quote": "eq"},
                    {"field_path": "adverse_events[0]", "quote": "aq"}]
        con.execute("INSERT INTO claim VALUES (?,?,?,?,?,?,?)",
                    (RUN, f"c{i}", unit, "w", int(values["subject"] == "self"),
                     json.dumps(values), json.dumps(evidence)))
    con.commit()
    con.close()
    return path


def test_sample_caps_rows_per_account_and_never_repeats_a_record(probe_db):
    rows = B.sample(B.load_records(probe_db, RUN), seed=1)
    ketamine_fatigue = [r for r in rows if r["stratum"] == "fatigue_ketamine"]
    assert sum(r["author"] == "a" for r in ketamine_fatigue) == B.MAX_PER_ACCOUNT
    keys = [(r["claim_id"], r["record_type"], r["record_index"]) for r in rows]
    assert len(keys) == len(set(keys))
    assert {r["stratum"] for r in rows} >= {"fatigue_ketamine", "severe_adverse_event",
                                            "random_excluded"}


def test_sample_is_reproducible_for_a_seed(probe_db):
    records = B.load_records(probe_db, RUN)
    ids = lambda rows: [r["claim_id"] for r in rows]  # noqa: E731
    assert ids(B.sample(records, seed=7)) == ids(B.sample(records, seed=7))


def test_sheet_omits_identifiers_and_prefills_inapplicable_scores(probe_db, tmp_path):
    out = tmp_path / "sheet.csv"
    B.write_sheet(B.sample(B.load_records(probe_db, RUN), seed=1), out, 1, RUN)
    rows = list(csv.DictReader(out.open()))
    assert not [c for c in rows[0] if "author" in c or c == "source_id"]
    ae = next(r for r in rows if r["record_type"] == "adverse_event")
    assert ae["direction"] == "n/a" and ae["describes_pem"] == "n/a" and ae["ae_severity"] == ""
    effect = next(r for r in rows if r["record_type"] == "effect")
    assert effect["ae_category"] == "n/a" and effect["direction"] == ""


def test_load_records_refuses_an_unknown_run(probe_db):
    with pytest.raises(SystemExit, match="not in"):
        B.load_records(probe_db, "other-run")


def _scored(tmp_path, rows):
    out = tmp_path / "scored.csv"
    cols = ["stratum", *B.SCORE_COLUMNS, B.PEM_COLUMN, "seed", "run_id"]
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: "n/a" for c in cols} | {"seed": 1, "run_id": RUN} | r)
    return out


def test_precision_excludes_unclear_and_uses_wilson():
    import pandas as pd
    p = S.precision(pd.Series(["correct"] * 9 + ["incorrect", "unclear", "n/a"]))
    assert (p["correct"], p["incorrect"], p["unclear"], p["n"]) == (9, 1, 1, 10)
    assert p["precision"] == pytest.approx(0.9)
    assert p["ci_low"] < 0.9 < p["ci_high"] < 1.0


def test_report_fails_a_target_and_answers_pem(tmp_path):
    rows = [{"stratum": "pem_explicit", "quote_supports_field": "correct",
             "describes_pem": "yes"} for _ in range(3)]
    rows += [{"stratum": "severe_adverse_event", "quote_supports_field": "incorrect",
              "ae_severity": "correct"}]
    text = S.report(S.load_sheet(_scored(tmp_path, rows)))
    assert "`quote_supports_field` ≥100%: **FAIL**" in text
    assert "pem_explicit: 3 of 3 describe PEM" in text
    assert "1 of 1" in text and "Unscored" not in text


def test_load_sheet_rejects_unknown_verdicts(tmp_path):
    with pytest.raises(SystemExit, match="unrecognised"):
        S.load_sheet(_scored(tmp_path, [{"stratum": "x", "direction": "yes"}]))


# ── Repeat-pass agreement (scripts/compare_probe_runs.py) ──────────────────

import compare_probe_runs as C  # noqa: E402


def test_kappa_is_one_for_identical_labels_and_zero_for_chance():
    assert C.cohen_kappa([True, False, True], [True, False, True]) == (1.0, 1.0)
    kappa, raw = C.cohen_kappa([True, True, False, False], [True, False, True, False])
    assert kappa == pytest.approx(0.0) and raw == 0.5


def test_compare_treats_a_missing_pair_as_negative():
    pair = {"directions": {"helped"}, "ae_status": "reported", "severe": True,
            "classes": {"pain"}}
    rows = {r["field"]: r for r in C.compare({("a", "lsd"): pair}, {}, {("a", "lsd"), ("b", "lsd")})}
    assert rows["any helped"]["agreement"] == 0.5
    assert rows["AE status"]["positive (left)"] == 1 and rows["AE status"]["positive (right)"] == 0
    assert rows["symptom-class set: exact match (effect-bearing in either run)"]["agreement"] == 0.0
