"""Loader guarantees for the v2 psychedelics study.

Covers run selection (a database with several runs must never be resolved
implicitly) and the claim-level dose/outcome linkage.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "studies/psychedelics/v2"))
import psychedelics_v2 as P  # noqa: E402


# ── Run selection (PX-17) ──────────────────────────────────────────────────

@pytest.fixture
def runs_db(tmp_path):
    """Factory: build an in-file database holding the given run ids."""
    def build(*run_ids):
        path = tmp_path / f"{'_'.join(run_ids) or 'empty'}.db"
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE probe_run (run_id TEXT, config_json TEXT, created_at TEXT)")
        con.executemany(
            "INSERT INTO probe_run VALUES (?, ?, ?)",
            [(r, json.dumps({"model": r}), "2026-06-13") for r in run_ids],
        )
        con.commit()
        return con
    return build


def test_select_run_accepts_a_lone_run(runs_db):
    con = runs_db("aaa")
    assert P.select_run(con)[0] == "aaa"


def test_select_run_rejects_an_empty_database(runs_db):
    con = runs_db()
    with pytest.raises(ValueError, match="no probe_run rows"):
        P.select_run(con)


def test_select_run_refuses_to_choose_among_several_runs(runs_db):
    con = runs_db("aaa", "bbb")
    with pytest.raises(ValueError, match="contains 2 runs"):
        P.select_run(con)


def test_select_run_pins_an_explicit_run(runs_db):
    con = runs_db("aaa", "bbb")
    assert P.select_run(con, "bbb")[0] == "bbb"


def test_select_run_reads_the_environment_override(runs_db, monkeypatch):
    con = runs_db("aaa", "bbb")
    monkeypatch.setenv(P.RUN_ENV_VAR, "aaa")
    assert P.select_run(con)[0] == "aaa"


def test_select_run_rejects_an_unknown_run(runs_db):
    con = runs_db("aaa")
    with pytest.raises(ValueError, match="not in this database"):
        P.select_run(con, "zzz")


# ── Dose/outcome linkage (PX-01) ───────────────────────────────────────────

BINS = {("psilocybin", "g"): ("psilocybin / g",
                              [(1, "<=1 g"), (3, "1-3 g"), (np.inf, ">3 g")])}


def frames(doses, effects):
    empty = pd.DataFrame()
    return P.Frames(run={}, members=empty, units=empty, attempts=empty, claims=empty,
                    effects=pd.DataFrame(effects), adverse=empty,
                    doses=pd.DataFrame(doses))


def dose(claim_id, patient, amount, drug="psilocybin", unit="g"):
    return {"claim_id": claim_id, "patient": patient, "drug": drug,
            "amount_lower": amount, "unit_canon": unit}


def effect(claim_id, patient, direction, drug="psilocybin"):
    return {"claim_id": claim_id, "patient": patient, "drug": drug,
            "direction": direction}


def test_discordant_episodes_from_one_reporter_stay_on_their_own_doses():
    """The defect PX-01 describes: one reporter, two doses, opposite outcomes.

    A (patient, drug) join would mark both bins helped *and* worsened. The claim
    key keeps each outcome on the dose it was reported with.
    """
    rows, _ = dose_rows(
        [dose("c1", 7, 0.5), dose("c2", 7, 5.0)],
        [effect("c1", 7, "helped"), effect("c2", 7, "worsened")],
    )
    got = rows.set_index("dose bin")[["helped", "worsened"]]
    assert got.loc["<=1 g"].tolist() == [True, False]
    assert got.loc[">3 g"].tolist() == [False, True]


def test_no_outcome_is_copied_onto_more_than_one_bin():
    rows, _ = dose_rows(
        [dose("c1", 7, 0.5), dose("c2", 7, 5.0)],
        [effect("c1", 7, "helped")],
    )
    assert rows["dose bin"].tolist() == ["<=1 g"]


def test_a_claim_straddling_two_bins_is_excluded_whole():
    rows, audit = dose_rows(
        [dose("c1", 7, 0.5), dose("c1", 7, 5.0)],
        [effect("c1", 7, "helped")],
    )
    assert rows.empty
    straddle = audit.set_index("step").loc["excluded: claim straddles >1 dose bin"]
    assert straddle["claims"] == 1


def test_repeated_doses_within_one_bin_collapse_to_one_row():
    rows, _ = dose_rows(
        [dose("c1", 7, 0.5), dose("c1", 7, 0.8)],
        [effect("c1", 7, "helped")],
    )
    assert len(rows) == 1


def test_a_claim_without_effects_is_excluded_and_counted():
    rows, audit = dose_rows([dose("c1", 7, 0.5)], [effect("c9", 7, "helped")])
    assert rows.empty
    assert audit.set_index("step").loc["excluded: claim carries no effect record",
                                       "claims"] == 1


def test_audit_reconciles_retained_and_excluded_records():
    rows, audit = dose_rows(
        [dose("c1", 7, 0.5), dose("c2", 7, 5.0), dose("c3", 8, 2.0),
         dose("c3", 8, 0.5), dose("c4", 9, 1.5, unit="count")],
        [effect("c1", 7, "helped"), effect("c2", 7, "worsened"),
         effect("c3", 8, "helped")],
    )
    a = audit.set_index("step")["records"]
    assert a["dose records with amount + canonical unit"] == 5
    assert a["in a binned drug/unit subset"] == 4      # the count-unit row drops out
    assert a["excluded: claim straddles >1 dose bin"] == 2   # c3's two records
    assert a["retained for dose/outcome analysis"] == len(rows) == 2


def dose_rows(doses, effects):
    return P.dose_outcome_rows(frames(doses, effects), BINS)


# ── Symptom classification (PX-02, PX-03) ──────────────────────────────────

@pytest.mark.parametrize("target, expected", [
    ("PEM", "pem_explicit"),
    ("post-exertional malaise", "pem_explicit"),
    ("crashing after a walk", "pem_explicit"),
    ("exercise intolerance", "exertion_intolerance"),
    ("stamina", "exertion_intolerance"),
    ("fatigue", "fatigue_general"),
    ("exhaustion", "fatigue_general"),
    ("ME/CFS", "fatigue_general"),        # a diagnosis, not a PEM statement
    ("low energy", "low_energy"),
    ("joint pain", "pain"),
    ("brain fog", "mood_cognitive"),
    ("hair loss", "other"),
    ("", "unspecified"),
    (None, "unspecified"),
])
def test_display_label_is_the_most_specific_match(target, expected):
    assert P.classify_symptom(target) == expected


def test_generic_fatigue_is_never_labelled_pem():
    """The defect PX-02 describes: the v1 composite called all of these PEM."""
    for target in ("fatigue", "low energy", "always tired", "exhausted"):
        assert "pem_explicit" not in P.symptom_labels(target)


def test_a_target_naming_two_symptoms_keeps_both_labels():
    """PX-03: pattern order decided this record's category; now it holds both."""
    labels = P.symptom_labels("brain fog and fatigue")
    assert set(labels) == {"mood_cognitive", "fatigue_general"}
    assert P.classify_symptom("brain fog and fatigue") == "mood_cognitive"


def test_a_target_naming_three_symptoms_keeps_all_three():
    labels = P.symptom_labels("pain, low energy and depression")
    assert set(labels) == {"pain", "low_energy", "mood_cognitive"}


def test_pem_language_outranks_the_fatigue_it_also_matches():
    labels = P.symptom_labels("post-exertional fatigue after exercise")
    assert set(labels) == {"pem_explicit", "exertion_intolerance", "fatigue_general"}
    assert labels[0] == "pem_explicit"


def test_labels_come_back_in_precedence_order():
    order = [name for name, _ in P.SYMPTOM_PATTERNS]
    labels = P.symptom_labels("energy, pain, PEM")
    assert list(labels) == sorted(labels, key=order.index)
