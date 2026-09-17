"""Synthetic statistical and privacy contracts for the reconstructed severity analysis."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from studies.tropoflavin_nootropics.comparator_support import load_comparator_cohort
from studies.tropoflavin_nootropics.severity_model_data import (
    AuthorUnit,
    EffectUnit,
    decode_effects,
    load_model_data,
    route_family,
    screen_doses,
)
from studies.tropoflavin_nootropics.severity_models import (
    Coefficient,
    ModelSettings,
    Observation,
    RunConfig,
    app,
    eligibility,
    fit_model,
    observations,
    run_models,
)


def _database(path: Path, *, second: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as con, con:
        con.executescript(
            "CREATE TABLE treatment (id INTEGER, canonical_name TEXT);"
            "CREATE TABLE treatment_reports (user_id TEXT, drug_id INTEGER, side_effects TEXT);"
            "CREATE TABLE pipeline_b_compound_exposures "
            "(author_hash TEXT, target_compound TEXT, dose_band TEXT, route_bucket TEXT, "
            "quantitative_dose_midpoints_mg_json TEXT);"
            "INSERT INTO treatment VALUES (1, '7,8-dhf');"
        )
        effects = [
            {"side_effect": "headache", "severity": "severe" if second else "mild"},
            {"side_effect": "nausea", "severity": None},
        ]
        con.executemany(
            "INSERT INTO treatment_reports VALUES (?, 1, ?)",
            [("private-person-A", json.dumps(effects)), ("private-person-B", "[]")],
        )
        con.execute(
            "INSERT INTO pipeline_b_compound_exposures VALUES (?, ?, ?, ?, ?)",
            (
                "private-person-A",
                "7,8-DHF",
                "10 to <25 mg",
                "swallowed oral" if second else "oral mucosal",
                "[10, 20]",
            ),
        )


def test_database_loading_deduplicates_and_never_mutates_source(tmp_path: Path) -> None:
    first, second = tmp_path / "one" / "sentiment.db", tmp_path / "two" / "sentiment.db"
    _database(first)
    _database(second, second=True)
    snapshots = {path: path.read_bytes() for path in (first, second)}
    data = load_model_data(tmp_path, load_comparator_cohort())
    assert len(data.units) == 2
    author = next(unit for unit in data.units if unit.author == "private-person-A")
    assert len(author.effects) == 2
    assert sorted(e.grade for e in author.effects if e.grade is not None) == [3]
    assert author.route == "oral"
    # Repeated identical numeric values across communities do not reweight the mean.
    assert author.dose_mg == pytest.approx(np.sqrt(200))
    assert all(path.read_bytes() == original for path, original in snapshots.items())
    assert eligibility(data.units)[0].graded_authors == 1


def test_missing_severity_is_not_zero_and_repeat_effects_do_not_weight_average() -> (
    None
):
    unit = AuthorUnit(
        "a",
        "7,8-DHF",
        (
            EffectUnit("headache", "neurologic", 3),
            EffectUnit("nausea", "GI", None),
            EffectUnit("insomnia", "sleep", 1),
        ),
        20,
        "oral",
    )
    rows = observations((unit,), "ordinal_grade")
    assert [row.outcome for row in rows] == [3, 1]
    assert observations((unit,), "mean_grade")[0].outcome == 2
    assert observations((unit,), "maximum_grade")[0].outcome == 3
    assert observations((unit,), "moderate_plus")[0].outcome == 1
    ungraded = AuthorUnit(
        "b", "7,8-DHF", (EffectUnit("headache", "neurologic", None),), 20, "oral"
    )
    assert observations((ungraded,), "moderate_plus") == ()
    assert observations((ungraded,), "any_effect")[0].outcome == 1


def test_conflicting_doses_and_routes_are_not_assigned_an_arbitrary_exposure(
    tmp_path: Path,
) -> None:
    first, second = tmp_path / "one" / "sentiment.db", tmp_path / "two" / "sentiment.db"
    _database(first)
    _database(second)
    with closing(sqlite3.connect(second)) as con, con:
        con.execute(
            "UPDATE pipeline_b_compound_exposures SET dose_band='50 to <100 mg', quantitative_dose_midpoints_mg_json='[75]', route_bucket='parenteral'"
        )
    data = load_model_data(tmp_path, load_comparator_cohort())
    exposed = next(unit for unit in data.units if unit.effects)
    assert exposed.dose_mg is None
    assert exposed.route is None


def test_rejects_inferred_or_invalid_grade() -> None:
    assert decode_effects('["severe headache"]')[0].grade is None
    with pytest.raises(ValidationError):
        decode_effects('[{"side_effect":"headache","severity":"very bad"}]')


def test_high_dose_screen_keeps_route_only_information() -> None:
    unit = AuthorUnit("a", "7,8-DHF", (), 100, "oral")
    screened, summaries = screen_doses((unit,))
    assert screened[0].dose_excluded
    assert summaries[0].primary_dose_exclusions == 1
    assert observations(screened, "any_effect")[0].log2_dose is None
    assert observations(screened, "any_effect")[0].route == "oral"
    assert route_family("nasal mucosal") == "nasal"
    assert route_family("other explicit") == "other explicit"
    assert route_family("not reported") is None


def _synthetic(outcome: str, *, n: int = 160) -> tuple[Observation, ...]:
    rng = np.random.default_rng(281)
    rows = []
    for i in range(n):
        x = float(rng.uniform(0, 4))
        if outcome == "binary":
            y = float(rng.binomial(1, 1 / (1 + np.exp(-(-1 + 0.5 * x)))))
        elif outcome == "count":
            y = float(rng.poisson(np.exp(0.2 + 0.2 * x)))
        elif outcome == "ordinal":
            y = float(1 + np.digitize(0.7 * x + rng.logistic(), [0, 2, 4]))
        else:
            y = 1 + 0.3 * x + float(rng.normal(0, 0.3))
        rows.append(
            Observation(
                author=f"person-{i}",
                compound="test",
                outcome=y,
                dose_mg=2**x,
                log2_dose=x,
                route="oral" if i % 2 else "nasal",
                domain="same",
            )
        )
    return tuple(rows)


@pytest.mark.parametrize(
    "outcome,generator,scale",
    [
        ("any_effect", "binary", "odds_ratio"),
        ("effect_count", "count", "count_ratio"),
        ("ordinal_grade", "ordinal", "odds_ratio"),
        ("mean_grade", "linear", "severity_points"),
        ("maximum_grade", "linear", "severity_points"),
        ("moderate_plus", "binary", "odds_ratio"),
    ],
)
def test_supported_model_has_finite_95_percent_interval(
    outcome, generator, scale
) -> None:
    status, terms = fit_model(
        _synthetic(generator), outcome, "dose_route", "test", ModelSettings()
    )
    assert status.status == "fit", status.reason
    dose = next(term for term in terms if term.term == "log2_dose")
    assert dose.scale == scale
    assert dose.ci_low <= dose.estimate <= dose.ci_high
    assert dose.estimate > (0 if scale == "severity_points" else 1)
    assert Coefficient.model_validate_json(dose.model_dump_json()) == dose


def test_repeated_effects_cannot_fake_twenty_independent_authors() -> None:
    rows = tuple(
        row.model_copy(update={"author": f"person-{i % 2}"})
        for i, row in enumerate(_synthetic("ordinal"))
    )
    status, terms = fit_model(rows, "ordinal_grade", "dose", "test", ModelSettings())
    assert status.authors == 2
    assert status.status == "not_estimable"
    assert terms == ()


def test_rare_routes_and_sparse_interaction_are_reported() -> None:
    rows = tuple(
        row.model_copy(update={"route": "nasal" if i == 0 else "oral"})
        for i, row in enumerate(_synthetic("binary"))
    )
    status, terms = fit_model(rows, "any_effect", "route", "test", ModelSettings())
    assert status.rare_route_records_excluded == 1
    assert status.reason == "fewer than two supported route levels"
    assert not terms
    rows = tuple(
        row.model_copy(update={"route": "nasal" if row.log2_dose > 2 else "oral"})
        for row in _synthetic("binary")
    )
    status, terms = fit_model(
        rows, "any_effect", "dose_route_interaction", "test", ModelSettings()
    )
    assert status.status == "not_estimable"
    assert "dose variation" in status.reason
    assert not terms


def test_pooled_fixed_effects_account_for_compound_offset() -> None:
    a = _synthetic("linear")
    b = tuple(
        row.model_copy(
            update={
                "compound": "test-b",
                "outcome": row.outcome + 2 + 0.1 * (i % 3 - 1),
            }
        )
        for i, row in enumerate(a)
    )
    status, terms = fit_model(
        a + b, "mean_grade", "dose", "all compounds", ModelSettings()
    )
    assert status.status == "fit"
    assert any(term.term.startswith("C(compound)") for term in terms)
    assert next(
        term for term in terms if term.term == "log2_dose"
    ).estimate == pytest.approx(0.3, abs=0.07)


def test_cli_service_emits_only_aggregate_artifacts(tmp_path: Path) -> None:
    _database(tmp_path / "input" / "community" / "sentiment.db")
    output = tmp_path / "output"
    run_models(RunConfig(run_root=tmp_path / "input", output_directory=output))
    assert len(list(output.iterdir())) == 4
    for path in output.iterdir():
        contents = path.read_text(encoding="utf-8")
        assert "private-person" not in contents
        assert "author_hash" not in contents
        assert str(tmp_path) not in contents
    manifest = json.loads((output / "severity_reconstructed_manifest.json").read_text())
    assert manifest["schema_id"] == "tropoflavin_severity_reconstruction_v1"
    assert "not exact historical reproduction" in manifest["reconstruction_status"]


def test_cli_is_actionable_and_sanitizes_bad_private_boundary_values(
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    assert runner.invoke(app, ["--help"]).exit_code == 0
    path = tmp_path / "input" / "one" / "sentiment.db"
    _database(path)
    with closing(sqlite3.connect(path)) as con, con:
        con.execute(
            "UPDATE treatment_reports SET side_effects=?",
            ('[{"side_effect":"private-name-do-not-echo", "severity":"invalid"}]',),
        )
    result = runner.invoke(
        app,
        [
            "--run-root",
            str(tmp_path / "input"),
            "--output-dir",
            str(tmp_path / "output"),
        ],
    )
    assert result.exit_code == 1
    assert "Check input schema" in result.output
    assert "private-name-do-not-echo" not in result.output
