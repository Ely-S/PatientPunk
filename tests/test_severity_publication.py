"""Synthetic contracts for aggregate publication, without any private run fixtures."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import get_args

import pytest
from PIL import Image
from pydantic import ValidationError
from typer.testing import CliRunner

from studies.tropoflavin_nootropics import publish_severity_reports as publication
from studies.tropoflavin_nootropics import severity_report_data as schema
from studies.tropoflavin_nootropics.privacy import require_private_aggregate_artifacts


def write_rows(path: Path, rows: list[schema.AggregateRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(type(rows[0]).model_fields))
        writer.writeheader()
        writer.writerows(row.model_dump() for row in rows)


@pytest.fixture
def synthetic_checkpoint(tmp_path: Path) -> Path:
    compounds = [name for name in get_args(schema.Compound) if name != "all compounds"]
    root = tmp_path / "data"
    base, linear, fine = (
        root / prefix
        for prefix in (publication.BASE, publication.LINEAR, publication.FINE)
    )
    write_rows(
        base / "side_effect_severity_by_compound.csv",
        [
            schema.CompoundSummary(
                scope="all communities, globally deduplicated",
                compound=name,
                authors=100,
                authors_with_any_side_effect=20,
                any_side_effect_percent="20.0%",
                authors_with_explicit_severity=10,
                severity_coverage_of_side_effect_authors="50.0%",
                authors_with_explicit_moderate_or_worse=5,
                authors_with_explicit_severe_or_worse=2,
            )
            for name in compounds
        ],
    )
    write_rows(
        linear / "severity_model_eligibility.csv",
        [
            schema.LinearEligibility(
                compound=name,
                explicit_severity_authors=10,
                dose_model_authors=2,
                route_model_authors=4,
                dose_and_route_model_authors=2,
                dose_and_route_routes=1,
                dose_and_route_unique_doses=2,
            )
            for name in compounds
        ],
    )
    write_rows(
        fine / "fine_grained_eligibility.csv",
        [
            schema.FineEligibility(
                compound=name,
                classified_authors=100,
                authors_with_any_side_effect=20,
                authors_with_explicit_severity=10,
                distinct_explicitly_graded_effects=12,
                dose_linked_authors=10,
                route_linked_authors=10,
                dose_and_route_linked_authors=5,
                dose_linked_graded_effects=3,
                route_linked_graded_effects=4,
                dose_and_route_linked_graded_effects=3,
            )
            for name in compounds
        ],
    )
    write_rows(
        fine / "moderate_or_worse_leading_effects.csv",
        [
            schema.LeadingEffect(
                compound="7,8-DHF",
                side_effect="anxiety or panic",
                authors=2,
                moderate=1,
                severe=1,
                life_threatening=0,
            )
        ],
    )
    write_rows(
        fine / "fine_grained_dose_bucket_definitions.csv",
        [
            schema.DoseDefinition(
                compound=name,
                first_cut_mg=10,
                second_cut_mg=20,
                basis="synthetic treatment-specific tertiles",
            )
            for name in compounds
        ],
    )
    buckets = []
    for dimension in ("dose bucket", "route", "dose bucket + route"):
        for unit in ("author-treatment", "distinct explicitly graded side effect"):
            buckets.append(
                schema.BucketEstimate(
                    unit=unit,
                    dimension=dimension,
                    compound="7,8-DHF",
                    dose_bucket=None if dimension == "route" else "low (<=10 mg)",
                    route="oral" if dimension != "dose bucket" else None,
                    observations=5,
                    any_side_effect_percent=40 if unit == "author-treatment" else None,
                    mean_distinct_side_effect_count=1.2
                    if unit == "author-treatment"
                    else None,
                    graded_authors=2,
                    mean_maximum_severity=2 if unit == "author-treatment" else None,
                    maximum_95_ci_low=1 if unit == "author-treatment" else None,
                    maximum_95_ci_high=3 if unit == "author-treatment" else None,
                    mean_average_severity=2,
                    average_95_ci_low=2 if unit == "author-treatment" else None,
                    average_95_ci_high=2 if unit == "author-treatment" else None,
                    mild_effects=2 if unit != "author-treatment" else None,
                    moderate_effects=1 if unit != "author-treatment" else None,
                    severe_effects=2 if unit != "author-treatment" else None,
                    life_threatening_effects=0 if unit != "author-treatment" else None,
                )
            )
    write_rows(fine / "fine_grained_bucket_estimates.csv", buckets)
    write_rows(
        linear / "severity_model_status.csv",
        [
            schema.LinearStatus(
                analysis_set="primary",
                scope="treatment-specific",
                compound="7,8-DHF",
                model="dose only",
                linked_authors_before_route_filter=2,
                eligible_authors=2,
                rare_route_records_excluded=0,
                status="not estimable",
                reason="fewer than 20 eligible authors",
            )
        ],
    )
    write_rows(
        fine / "fine_grained_model_status.csv",
        [
            schema.FineStatus(
                outcome="average severity",
                scope="treatment-specific",
                compound="7,8-DHF",
                model="dose only",
                observations_before_filters=10,
                eligible_observations=2,
                rare_route_records_excluded=0,
                status="not estimable",
                reason="fewer than 20 observations",
            )
        ],
    )
    write_rows(
        linear / "severity_model_coefficients.csv",
        [
            schema.LinearCoefficient(
                analysis_set="primary",
                scope="treatment-specific",
                compound="BPC-157",
                model="dose only",
                authors=30,
                term="log2 dose (per doubling)",
                estimate=0.1,
                estimate_95_ci_low=-0.2,
                estimate_95_ci_high=0.4,
                p_value=0.4,
                route_reference=None,
                compound_reference=None,
                r_squared=0.1,
                adjusted_r_squared=0.05,
            )
        ],
    )
    write_rows(
        fine / "fine_grained_model_coefficients.csv",
        [
            schema.FineCoefficient(
                outcome=outcome,
                scope="treatment-specific",
                compound="BPC-157",
                model="dose + route",
                observations=30,
                author_clusters=30,
                term="log2 dose (per doubling)",
                scale="severity-score points",
                estimate=-0.1,
                estimate_95_ci_low=-0.3,
                estimate_95_ci_high=0.1,
                p_value=0.3,
                route_reference="parenteral",
                compound_reference=None,
                safety_bucket_reference=None,
            )
            for outcome in ("maximum severity", "average severity")
        ],
    )
    write_rows(
        fine / "moderate_or_worse_model_coefficients.csv",
        [
            schema.ModerateCoefficient(
                compound="BPC-157",
                outcome="at least one moderate+ effect",
                analysis_population="explicitly graded authors",
                model="dose only",
                term="dose doubling",
                authors=30,
                moderate_or_worse_authors=15,
                odds_ratio=1.2,
                odds_ratio_95_ci_low=0.5,
                odds_ratio_95_ci_high=2.5,
                p_value=0.5,
                route_reference=None,
            )
        ],
    )
    lower, upper = schema.wilson_interval(3, 5)
    write_rows(
        fine / "moderate_or_worse_bpc_dose_route_cells.csv",
        [
            schema.ModerateCell(
                compound="BPC-157",
                dose_bucket="low (<=0.25 mg)",
                route="oral",
                graded_authors=5,
                moderate_or_worse_numerator=3,
                moderate_or_worse_denominator=5,
                moderate_or_worse_rate=0.6,
                moderate_or_worse_95_ci_low=lower,
                moderate_or_worse_95_ci_high=upper,
            )
        ],
    )
    write_rows(
        linear / "severity_model_predictions.csv",
        [
            schema.MeanPrediction(
                scope="treatment-specific",
                model="dose only",
                compound="BPC-157",
                dose_bucket="low",
                route=None,
                authors=5,
                median_dose_mg=0.25,
                observed_mean_max_severity=2,
                observed_mean_95_ci_low=1,
                observed_mean_95_ci_high=3,
                adjusted_predicted_mean=2.1,
                adjusted_mean_95_ci_low=1.5,
                adjusted_mean_95_ci_high=2.7,
            )
        ],
    )
    write_rows(
        fine / "fine_grained_severity_probabilities.csv",
        [
            schema.SeverityPrediction(
                scope="treatment-specific",
                model="dose + route",
                compound="BPC-157",
                dose_bucket="low",
                route="oral",
                observed_effects_in_stratum=5,
                authors_in_stratum=3,
                representative_dose_mg=0.25,
                moderate_or_worse_probability=0.6,
                moderate_or_worse_95_ci_low=0.3,
                moderate_or_worse_95_ci_high=0.9,
                severe_or_worse_probability=0.4,
                severe_or_worse_95_ci_low=0.2,
                severe_or_worse_95_ci_high=0.6,
                mild_probability=0.4,
                mild_95_ci_low=0.1,
                mild_95_ci_high=0.7,
                moderate_probability=0.2,
                moderate_95_ci_low=0.1,
                moderate_95_ci_high=0.3,
                severe_probability=0.4,
                severe_95_ci_low=0.2,
                severe_95_ci_high=0.6,
                life_threatening_probability=0,
                life_threatening_95_ci_low=0,
                life_threatening_95_ci_high=0,
            )
        ],
    )
    settings = schema.FrozenModelManifest(
        schema_id="tropoflavin_side_effect_fine_grained_models_v1",
        generated_at="2026-09-03T23:41:08Z",
        author_unit="author-treatment",
        effect_unit="author-treatment-effect",
        occurrence_model="GEE",
        burden_model="GEE",
        severity_model="ordinal GEE",
        summary_models="OLS",
        dose_definition="log2 mg",
        route_definition="single route family",
        confidence_interval="95% robust",
        min_model_n=20,
        min_route_level_n=5,
        min_interaction_cell_n=5,
        robust_log_dose_z=4,
        exclude_78dhf_at_or_above_mg=100,
        databases=(
            schema.DatabaseDigest(
                community="synthetic",
                filename="sentiment.db",
                size_bytes=1,
                sha256="a" * 64,
            ),
        ),
    )
    (fine / "fine_grained_manifest.json").write_text(
        settings.model_dump_json(), encoding="utf-8"
    )
    for path in (
        base / "side_effect_severity_manifest.json",
        linear / "severity_model_manifest.json",
        fine / "moderate_or_worse_manifest.json",
    ):
        path.write_text('{"synthetic": true}', encoding="utf-8")
    return root


def test_synthetic_publication_is_portable_aggregate_only(
    synthetic_checkpoint: Path, tmp_path: Path
) -> None:
    output = tmp_path / "publication"
    paths = publication.publish_reports(
        publication.PublishConfig(
            data_root=synthetic_checkpoint, output_directory=output
        )
    )
    assert {path.name for path in paths} == {
        "severity_checkpoint.md",
        "severity_checkpoint_models.md",
        "severity_checkpoint_exposures.md",
        "severity_checkpoint_provenance.json",
        "severity_moderate_or_worse.png",
        "severity_eligibility.png",
        "severity_moderate_models.png",
    }
    texts = tuple(path for path in paths if path.suffix in (".md", ".json"))
    require_private_aggregate_artifacts(texts)
    for path in texts:
        content = path.read_text(encoding="utf-8")
        assert str(tmp_path) not in content
        assert "author_hash" not in content and "body_text" not in content
    main = (output / "severity_checkpoint.md").read_text(encoding="utf-8")
    assert "5/100 (5.0%; 2.2% to 11.2%)" in main
    assert "5/10 (50.0%; 23.7% to 76.3%)" in main
    assert "not clinical incidence" in main and "does not rerun" in main
    exposures = (output / "severity_checkpoint_exposures.md").read_text(
        encoding="utf-8"
    )
    assert "[identical limits]" in exposures
    assert "Historical adjusted maximum-severity means" in exposures
    assert "Historical ordinal severity probabilities" in exposures
    assert "Mean within-author average (95% CI)" in exposures
    models = (output / "severity_checkpoint_models.md").read_text(encoding="utf-8")
    assert "fewer than 20 observations" in models
    manifest = json.loads((output / "severity_checkpoint_provenance.json").read_text())
    assert set(manifest) == {
        "schema_id",
        "mode",
        "checkpoint",
        "sources",
        "frozen_settings",
        "proportion_interval",
    }
    assert all(
        set(item) == {"relative_path", "sha256", "size_bytes"}
        for item in manifest["sources"]
    )
    assert all(
        len(item["sha256"]) == 64 and not Path(item["relative_path"]).is_absolute()
        for item in manifest["sources"]
    )
    for path in paths:
        if path.suffix == ".png":
            with Image.open(path) as image:
                assert image.width >= 2000 and image.height >= 1000
                assert image.getextrema() != ((255, 255),) * 4


@pytest.mark.parametrize(
    ("successes", "total", "expected"),
    [
        (11, 22, (0.3072210627, 0.6927789373)),
        (0, 1, (0, 0.7934506856)),
        (1, 1, (0.2065493144, 1)),
        (5, 6, (0.4364971778, 0.9699466303)),
    ],
)
def test_wilson_known_reference(
    successes: int, total: int, expected: tuple[float, float]
) -> None:
    assert schema.wilson_interval(successes, total) == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize(("successes", "total"), [(0, 0), (-1, 5), (6, 5)])
def test_wilson_invalid_denominator(successes: int, total: int) -> None:
    with pytest.raises(ValueError):
        schema.wilson_interval(successes, total)


def test_reject_record_level_column_before_reading_values(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.csv"
    path.write_text("compound,author_hash\n7,secret-value\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unexpected aggregate schema") as caught:
        schema.read_aggregate_csv(path, schema.LinearEligibility)
    assert "secret-value" not in str(caught.value)


def test_reject_noncanonical_effect_and_wrong_grade_total() -> None:
    payload = {
        "compound": "7,8-DHF",
        "side_effect": "private verbatim narrative",
        "authors": 2,
        "moderate": 1,
        "severe": 1,
        "life_threatening": 0,
    }
    with pytest.raises(ValidationError, match="canonical"):
        schema.LeadingEffect.model_validate(payload)
    payload.update(side_effect="anxiety or panic", authors=3)
    with pytest.raises(ValidationError, match="total"):
        schema.LeadingEffect.model_validate(payload)


def test_mismatch_across_checkpoint_tables_fails(synthetic_checkpoint: Path) -> None:
    path = synthetic_checkpoint / publication.FINE / "fine_grained_eligibility.csv"
    rows = list(schema.read_aggregate_csv(path, schema.FineEligibility))
    rows[0] = rows[0].model_copy(update={"classified_authors": 101})
    write_rows(path, rows)
    with pytest.raises(ValueError, match="Cross-file eligibility mismatch"):
        publication.load_checkpoint(synthetic_checkpoint)


def test_cli_uses_environment_and_fails_without_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATIENTPUNK_DATA", str(tmp_path))
    result = CliRunner().invoke(
        publication.app, ["--output-directory", str(tmp_path / "reports")]
    )
    assert result.exit_code == 1
    assert "Publication failed" in result.output


def test_missing_and_degenerate_intervals_stay_distinct() -> None:
    assert publication.estimate(None, None, None) == "not estimable"
    assert publication.estimate(2, None, None) == "2.00; CI not estimable"
    assert publication.estimate(2, 2, 2) == "2.00 (2.00 to 2.00) [identical limits]"
    assert publication.rate(0, 0) == "0/0; not estimable"


def test_tiny_model_terms_do_not_round_to_exact_zero() -> None:
    assert publication.estimate(2e-15, 1e-15, 3e-15) == "2e-15 (1e-15 to 3e-15)"
    assert publication.p_value(1e-12) == "<0.0001"


def test_invalid_row_value_is_not_echoed(synthetic_checkpoint: Path) -> None:
    path = synthetic_checkpoint / publication.LINEAR / "severity_model_eligibility.csv"
    rows = list(schema.read_aggregate_csv(path, schema.LinearEligibility))
    rows[0] = rows[0].model_copy(update={"compound": "private-unsupported-label"})
    write_rows(path, rows)
    with pytest.raises(ValueError, match="content withheld") as caught:
        schema.read_aggregate_csv(path, schema.LinearEligibility)
    assert "private-unsupported-label" not in str(caught.value)


def test_saved_wilson_limits_cannot_be_changed_silently(
    synthetic_checkpoint: Path,
) -> None:
    path = (
        synthetic_checkpoint
        / publication.FINE
        / "moderate_or_worse_bpc_dose_route_cells.csv"
    )
    rows = list(schema.read_aggregate_csv(path, schema.ModerateCell))
    rows[0] = rows[0].model_copy(update={"moderate_or_worse_95_ci_low": 0.5})
    write_rows(path, rows)
    with pytest.raises(ValueError, match="content withheld"):
        publication.load_checkpoint(synthetic_checkpoint)
