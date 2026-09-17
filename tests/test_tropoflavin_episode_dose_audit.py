from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from studies.tropoflavin_nootropics.episode_dose_audit import (
    DEFAULT_AUDIT,
    HighDoseAudit,
    app,
    apply_high_dose_audit,
    audit_note,
    count_rate,
    load_audit,
)
from studies.tropoflavin_nootropics.study_support import STUDY_ROOT


@pytest.fixture
def historical_report() -> str:
    report = (
        "# Same-post 7,8-DHF episode analysis\n\n"
        "## Coverage\n\n| Combined | 1828 | 673 | remaining coverage |\n\n"
        "## Combined primary models\n\n"
        "| side-effect reporting | 122 | 81 | 1.03 | 0.72 to 1.47 | 0.8820 |\n\n"
        "## Combined dose descriptives\n\n"
        "| 50 to <100 mg | 25 | 16 | 50.0 mg | 15/25 (60.0%) | 11/25 (44.0%) |\n"
        "| >=100 mg | 11 | 9 | 100.0 mg | 10/11 (90.9%) | 1/11 (9.1%) |\n\n"
        "## Combined route descriptives\n\n"
        "| nasal mucosal | 11 | 7 | 10/11 (90.9%) | 1/11 (9.1%) |\n\n"
        "| episode_records.jsonl | "
        "1df095a6a7a9a1a2250bd4fb32f7bf3ca20bb4f3d84ffdcf9ec44cfad63bdd37 |\n"
    )
    return report + "\n".join(
        f"| {subreddit} | combined.db | {digest} |"
        for subreddit, digest in load_audit().database_sha256.items()
    ) + "\n"


def test_frozen_audit_accounts_for_every_candidate() -> None:
    audit = load_audit()
    assert audit.candidate_episodes == 11
    assert audit.excluded_other_compound == 4
    assert audit.excluded_boundary_range == 1
    assert audit.retained_episodes == 6
    assert audit.retained_authors == 4
    assert audit.retained_explicit_severity_reports == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("retained_episodes", 7),
        ("retained_authors", 7),
        ("retained_positive_reports", 7),
        ("candidate_positive_reports", 4),
        ("retained_side_effect_reports", 2),
        ("retained_explicit_severity_reports", 2),
        ("excluded_other_compound", -1),
        ("retained_episodes", "6"),
        ("episode_records_sha256", "unknown"),
        ("author_hash", "must not be accepted"),
    ],
)
def test_invalid_or_private_audit_fields_are_rejected(field: str, value: object) -> None:
    payload = load_audit().model_dump()
    payload[field] = value
    with pytest.raises(ValidationError):
        HighDoseAudit.model_validate(payload)


def test_wilson_intervals_include_uncertainty_at_zero_events() -> None:
    assert count_rate(5, 6) == "5/6 (83.3%; 43.6% to 97.0%)"
    assert count_rate(1, 6) == "1/6 (16.7%; 3.0% to 56.4%)"
    assert count_rate(0, 6) == "0/6 (0.0%; 0.0% to 39.0%)"
    with pytest.raises(ValueError):
        count_rate(7, 6)


def test_correction_changes_only_reviewed_row_and_labels_models(historical_report: str) -> None:
    audit = load_audit()
    corrected = apply_high_dose_audit(historical_report, audit)
    high_dose = next(line for line in corrected.splitlines() if line.startswith("| >=100 mg"))
    assert high_dose == (
        "| >=100 mg (audited) | 6 | 4 | unavailable | "
        "5/6 (83.3%; 43.6% to 97.0%) | 1/6 (16.7%; 3.0% to 56.4%) |"
    )
    assert "10/11" not in high_dose
    assert "| nasal mucosal | 11 | 7 | 10/11 (90.9%) | 1/11 (9.1%) |" in corrected
    assert "| 50 to <100 mg | 25 | 16 | 50.0 mg | 15/25 (60.0%) | 11/25 (44.0%) |" in corrected
    assert "## Combined primary models (pre-audit)" in corrected
    assert "| side-effect reporting | 122 | 81 | 1.03 | 0.72 to 1.47 | 0.8820 |" in corrected
    assert "cannot support refitting models" in corrected
    assert audit_note(audit) in corrected
    assert apply_high_dose_audit(corrected, audit) == corrected


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("| Combined | 1828 | 673 |", "| Combined | 1829 | 673 |"),
        ("1df095a6a7a9a1a2250bd4fb32f7bf3ca20bb4f3d84ffdcf9ec44cfad63bdd37", "0" * 64),
        ("47bd9f879b53356724ba0d7b6a58422ba66827bfd00d1e9db94718909339831f", "0" * 64),
        ("| >=100 mg | 11 | 9 |", "| >=100 mg | 12 | 9 |"),
        ("10/11 (90.9%)", "9/11 (81.8%)"),
    ],
)
def test_changed_cohorts_require_a_new_audit(
    historical_report: str, old: str, new: str
) -> None:
    with pytest.raises(ValueError, match="re-audit inputs"):
        apply_high_dose_audit(historical_report.replace(old, new), load_audit())


def test_failed_publication_does_not_replace_existing_output(
    tmp_path: Path, historical_report: str
) -> None:
    source = tmp_path / "historical.md"
    source.write_text(historical_report.replace("| Combined | 1828", "| Combined | 1829"))
    destination = tmp_path / "published.md"
    destination.write_text("previous report")
    result = CliRunner().invoke(app, [
        "--report", str(source), "--output", str(destination), "--audit", str(DEFAULT_AUDIT),
    ])
    assert result.exit_code == 1
    assert "re-audit inputs" in result.output
    assert destination.read_text() == "previous report"


def test_committed_episode_report_matches_reviewed_audit() -> None:
    report = (STUDY_ROOT / "reports" / "78dhf_episode_analysis.md").read_text(encoding="utf-8")
    assert "## High-dose audit correction" in report
    assert apply_high_dose_audit(report, load_audit()) == report


def test_default_episode_generator_cannot_silently_skip_audit() -> None:
    from studies.tropoflavin_nootropics.analyze_78dhf_episodes import (
        EpisodeAnalysisConfig,
    )

    assert EpisodeAnalysisConfig.model_fields["high_dose_audit"].default == DEFAULT_AUDIT
