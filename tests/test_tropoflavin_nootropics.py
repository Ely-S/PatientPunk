from __future__ import annotations

import csv
from pathlib import Path

import pytest

from studies.tropoflavin_nootropics.study_support import (
    PipelineBRecord,
    StudyPaths,
    bind_strict_doses,
    compound_for_treatment,
    linked_values,
    load_pipeline_b_records,
    readonly_sqlite_uri,
    summarize_target_values,
)


def _record(**updates: str) -> PipelineBRecord:
    values = {
        "author_hash": "author-1",
        "treatment_outcome": "",
        "dosage_treatment": "",
        "dosage_value": "",
        "administration_route_treatment": "",
        "administration_route_value": "",
    }
    values.update(updates)
    return PipelineBRecord.model_validate(values)


def test_loader_rejects_records_from_before_linked_fields(tmp_path: Path) -> None:
    path = tmp_path / "records.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["author_hash", "dosage"])
        writer.writeheader()
        writer.writerow({"author_hash": "author-1", "dosage": "5 mg"})

    with pytest.raises(ValueError, match=r"predates the linked dose/route schema.*Rerun pipeline B"):
        load_pipeline_b_records(path)


def test_linked_values_preserve_alignment_and_reject_mismatch() -> None:
    record = _record(
        dosage_treatment="7,8-DHF | magnesium",
        dosage_value="5 mg | 200 mg",
    )
    assert [(pair.treatment, pair.value) for pair in linked_values(record, "dosage")] == [
        ("7,8-DHF", "5 mg"),
        ("magnesium", "200 mg"),
    ]

    invalid = _record(dosage_treatment="7,8-DHF | magnesium", dosage_value="5 mg")
    with pytest.raises(ValueError, match="misaligned"):
        linked_values(invalid, "dosage")


def test_derivative_classification_takes_precedence_over_parent_alias() -> None:
    assert compound_for_treatment("4'-DMA-7,8-DHF") == "4'-DMA"
    assert compound_for_treatment("eutropoflavin") == "4'-DMA"
    assert compound_for_treatment("7,8-DHF") == "7,8-DHF"
    assert compound_for_treatment("magnesium") is None


def test_target_summaries_use_only_explicit_linked_pairs() -> None:
    records = [
        _record(
            author_hash="a",
            dosage_treatment="7,8-DHF | magnesium",
            dosage_value="5 mg | 200 mg",
            administration_route_treatment="7,8-DHF",
            administration_route_value="sublingual",
        ),
        _record(
            author_hash="b",
            dosage_treatment="4'-DMA-7,8-DHF",
            dosage_value="20 mg",
            administration_route_treatment="4'-DMA-7,8-DHF",
            administration_route_value="oral",
        ),
    ]

    doses = summarize_target_values(records, "dosage")
    routes = summarize_target_values(records, "administration_route")

    assert doses.counts["7,8-DHF"] == {"5 mg": 1}
    assert doses.counts["4'-DMA"] == {"20 mg": 1}
    assert doses.authors == {"7,8-DHF": {"a"}, "4'-DMA": {"b"}}
    assert routes.counts["7,8-DHF"] == {"sublingual": 1}
    assert routes.counts["4'-DMA"] == {"oral": 1}


def test_strict_binder_rejects_single_letter_intervening_compound() -> None:
    assert bind_strict_doses("I take 7,8-DHF 10 mg each morning") == [10.0]
    assert bind_strict_doses("I take 7,8-DHF and B 10 mg each morning") == []


def test_study_paths_are_absolute_and_sqlite_uri_is_read_only() -> None:
    paths = StudyPaths()
    assert paths.database.is_absolute()
    assert paths.records.is_absolute()
    assert readonly_sqlite_uri(paths.database).startswith("file:")
    assert readonly_sqlite_uri(paths.database).endswith("?mode=ro")
