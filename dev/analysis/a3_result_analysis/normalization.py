"""Claim-label normalization for A3."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from dev.analysis.a3_result_analysis.common import (
    NORMALIZATION_VERSION,
    file_sha256,
    read_csv,
    sha256_json,
    utc_now_iso,
    write_csv,
    write_json,
)


_PUNCT = re.compile(r"[^\w%/+\- ]+")
_WS = re.compile(r"\s+")


NORMALIZATION_MAP_COLUMNS = [
    "schema_version",
    "prompt_version",
    "claim_type",
    "raw_label_clean",
    "canonical_label",
    "analysis_bucket",
    "rule_type",
    "rule_version",
    "review_status",
    "notes",
]
CLAIM_BASE_COLUMNS = [
    "id",
    "result_id",
    "work_item_id",
    "run_id",
    "source_line",
    "comment_id",
    "claim_index",
    "claim_id",
    "claim_stable_id",
    "claim_hash",
    "claim_type",
    "raw_text",
    "normalized_label",
    "normalized_label_canonical",
    "experiencer",
    "assertion",
    "confidence",
    "evidence_quote",
    "evidence_source",
    "evidence_json",
    "used_context",
    "context_comment_ids_used_json",
    "attribution_confidence",
    "date_utc",
    "year_month",
    "parent_kind",
    "body_length",
    "model",
    "schema_version",
    "prompt_version",
]


def clean_label(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = _PUNCT.sub(" ", text)
    return _WS.sub(" ", text).strip()


def build_draft_normalization_map(claims: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str, str]] = set()
    rows: list[dict[str, str]] = []
    for claim in claims:
        clean = clean_label(claim.get("normalized_label") or claim.get("raw_text"))
        if not clean:
            continue
        key = (
            claim.get("schema_version", ""),
            claim.get("prompt_version", ""),
            claim.get("claim_type", ""),
            clean,
        )
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "schema_version": key[0],
                "prompt_version": key[1],
                "claim_type": key[2],
                "raw_label_clean": key[3],
                "canonical_label": key[3],
                "analysis_bucket": "",
                "rule_type": "passthrough",
                "rule_version": NORMALIZATION_VERSION,
                "review_status": "unreviewed",
                "notes": "",
            }
        )
    return sorted(rows, key=lambda row: (row["claim_type"], row["raw_label_clean"]))


def load_normalization_map(path: Path | None, claims: list[dict[str, str]]) -> list[dict[str, str]]:
    if path is not None and path.exists():
        return read_csv(path)
    return build_draft_normalization_map(claims)


def normalize_claim_rows(
    claims: list[dict[str, str]],
    *,
    map_rows: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    map_rows = map_rows or build_draft_normalization_map(claims)
    lookup = {
        (row.get("schema_version", ""), row.get("prompt_version", ""), row.get("claim_type", ""), row.get("raw_label_clean", "")): row
        for row in map_rows
    }
    out: list[dict[str, Any]] = []
    for claim in claims:
        clean = clean_label(claim.get("normalized_label") or claim.get("raw_text"))
        key = (
            claim.get("schema_version", ""),
            claim.get("prompt_version", ""),
            claim.get("claim_type", ""),
            clean,
        )
        match = lookup.get(key)
        normalized = dict(claim)
        normalized["normalized_label_clean"] = clean
        normalized["normalized_label_canonical"] = (match or {}).get("canonical_label", clean)
        normalized["analysis_bucket"] = (match or {}).get("analysis_bucket", "")
        normalized["normalization_version"] = NORMALIZATION_VERSION
        normalized["normalization_rule"] = (match or {}).get("rule_type", "passthrough")
        normalized["normalization_review_status"] = (match or {}).get("review_status", "unreviewed")
        normalized["normalization_notes"] = (match or {}).get("notes", "")
        out.append(normalized)
    return out


def write_normalization_outputs(
    *,
    claims: list[dict[str, str]],
    output_dir: Path,
    map_path: Path | None = None,
) -> dict[str, Any]:
    map_rows = load_normalization_map(map_path, claims)
    normalized = normalize_claim_rows(claims, map_rows=map_rows)
    map_output = output_dir / "normalization_map.csv"
    claims_output = output_dir / "claim_rows_normalized.csv"
    write_csv(map_output, map_rows, NORMALIZATION_MAP_COLUMNS)
    claim_columns = list(normalized[0].keys()) if normalized else _normalized_claim_columns(claims)
    write_csv(claims_output, normalized, claim_columns)
    manifest = {
        "normalization_version": NORMALIZATION_VERSION,
        "normalization_map_sha256": file_sha256(map_output),
        "claim_rows_normalized_sha256": file_sha256(claims_output),
        "source_claim_count": len(claims),
        "normalized_claim_count": len(normalized),
        "map_row_count": len(map_rows),
        "generated_at_utc": utc_now_iso(),
        "map_payload_hash": sha256_json(map_rows),
    }
    write_json(output_dir / "normalization_manifest.json", manifest)
    return {"map_rows": map_rows, "normalized_claims": normalized, "manifest": manifest}


def _normalized_claim_columns(claims: list[dict[str, str]]) -> list[str]:
    base = list(claims[0].keys()) if claims else list(CLAIM_BASE_COLUMNS)
    extra = [
        "normalized_label_clean",
        "normalized_label_canonical",
        "analysis_bucket",
        "normalization_version",
        "normalization_rule",
        "normalization_review_status",
        "normalization_notes",
    ]
    for column in extra:
        if column not in base:
            base.append(column)
    return base
