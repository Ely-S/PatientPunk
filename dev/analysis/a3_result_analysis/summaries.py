"""Summary table generation for A3."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from dev.analysis.a3_result_analysis.common import (
    compact_markdown_table,
    float_value,
    int_value,
    read_json,
    utc_now_iso,
    write_csv,
    write_json,
)
from dev.analysis.a3_result_analysis.loaders import A2ExportData


COMMENT_DISTRIBUTION_COLUMNS = ["group", "count", "status", "is_codeable", "skip_reason", "used_context", "attribution_confidence", "parent_kind", "year_month"]
CLAIM_DISTRIBUTION_COLUMNS = ["group", "count", "claim_type", "assertion", "experiencer", "confidence", "used_context", "parent_kind", "year_month", "normalized_label_canonical"]
CLAIM_LABEL_FREQUENCY_COLUMNS = [
    "claim_type",
    "normalized_label",
    "normalized_label_clean",
    "n_claims",
    "first_seen_run_id",
    "example_raw_text",
    "example_evidence_quote",
    "n_comments",
    "n_runs",
]
CONTEXT_QUALITY_COLUMNS = ["metric", "count"]
ATTEMPT_QUALITY_COLUMNS = ["metric", "group", "count", "value"]
DENOMINATOR_COLUMNS = ["name", "value", "source_table", "source_filter", "description"]


def distribution(rows: list[dict[str, Any]], columns: list[str]) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, ...]] = Counter()
    for row in rows:
        key = tuple(str(row.get(column, "") or "") for column in columns)
        counts[key] += 1
    out = []
    for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        payload = {column: value for column, value in zip(columns, key)}
        payload["count"] = count
        out.append(payload)
    return out


def label_frequency(claims: list[dict[str, str]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for claim in claims:
        key = (
            claim.get("claim_type", ""),
            claim.get("normalized_label", ""),
            claim.get("normalized_label_clean", ""),
        )
        item = grouped.setdefault(
            key,
            {
                "claim_type": key[0],
                "normalized_label": key[1],
                "normalized_label_clean": key[2],
                "n_claims": 0,
                "comment_ids": set(),
                "run_ids": set(),
                "first_seen_run_id": claim.get("run_id", ""),
                "example_raw_text": claim.get("raw_text", ""),
                "example_evidence_quote": claim.get("evidence_quote", ""),
            },
        )
        item["n_claims"] += 1
        item["comment_ids"].add(claim.get("comment_id", ""))
        item["run_ids"].add(claim.get("run_id", ""))
    rows = []
    for item in grouped.values():
        rows.append(
            {
                **{key: value for key, value in item.items() if key not in {"comment_ids", "run_ids"}},
                "n_comments": len([value for value in item["comment_ids"] if value]),
                "n_runs": len([value for value in item["run_ids"] if value]),
            }
        )
    return sorted(rows, key=lambda row: (-row["n_claims"], row["claim_type"], row["normalized_label_clean"]))


def denominator_summary(data: A2ExportData, normalized_claim_count: int, audit_counts: dict[str, int] | None = None) -> list[dict[str, Any]]:
    audit_counts = audit_counts or {}
    comments = data.comments
    claims = data.claims
    attempted = len({row.get("work_item_id") for row in data.attempts if row.get("work_item_id")})
    succeeded = sum(1 for row in comments if row.get("status") in {"succeeded", "deterministic_skipped"})
    codeable = sum(1 for row in comments if str(row.get("is_codeable", "")).strip() in {"1", "true", "True"})
    skipped = sum(1 for row in comments if row.get("skip_reason"))
    failed = sum(1 for row in comments if row.get("status") == "failed")
    rows = [
        _den("n_work_items_selected", len(comments), "comment_rows.csv", "all rows", "A2 selected target comments."),
        _den("n_comments_attempted", attempted, "attempts.csv", "distinct work_item_id", "Comments sent through model attempts."),
        _den("n_comments_succeeded", succeeded, "comment_rows.csv", "status in succeeded/deterministic_skipped", "Comments with final usable A2 result."),
        _den("n_comments_codeable", codeable, "comment_rows.csv", "is_codeable true", "Comments with at least one target-author claim."),
        _den("n_comments_skipped", skipped, "comment_rows.csv", "skip_reason present", "Comments skipped by model or deterministic rule."),
        _den("n_comments_failed", failed, "comment_rows.csv", "status failed", "Comments with final unresolved failure."),
        _den("n_claims_extracted", len(claims), "claim_rows.csv", "all rows", "Extracted target-author claims."),
        _den("n_claims_after_normalization", normalized_claim_count, "claim_rows_normalized.csv", "all rows", "Claims after A3 normalization pass."),
        _den("n_comments_audited", audit_counts.get("comments", 0), "reviewed audit comments", "reviewed labels", "Reviewed comment audit rows."),
        _den("n_claims_audited", audit_counts.get("claims", 0), "reviewed audit claims", "reviewed labels", "Reviewed claim audit rows."),
    ]
    return rows


def write_summary_outputs(
    *,
    data: A2ExportData,
    normalized_claims: list[dict[str, Any]],
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_quality = dict(data.run_report)
    run_quality["a3_generated_at_utc"] = utc_now_iso()
    write_json(output_dir / "run_quality_report.json", run_quality)
    (output_dir / "run_quality_report.md").write_text(_run_quality_markdown(run_quality), encoding="utf-8")

    comment_dist = []
    for columns in [["status"], ["is_codeable"], ["skip_reason"], ["used_context"], ["attribution_confidence"], ["parent_kind"], ["year_month"]]:
        for row in distribution(data.comments, columns):
            comment_dist.append({"group": "+".join(columns), **row})
    write_csv(output_dir / "comment_distribution.csv", comment_dist, COMMENT_DISTRIBUTION_COLUMNS)

    claim_dist = []
    for columns in [["claim_type"], ["assertion"], ["experiencer"], ["confidence"], ["used_context"], ["parent_kind"], ["year_month"], ["claim_type", "normalized_label_canonical"]]:
        for row in distribution(normalized_claims, columns):
            claim_dist.append({"group": "+".join(columns), **row})
    write_csv(output_dir / "claim_distribution.csv", claim_dist, CLAIM_DISTRIBUTION_COLUMNS)

    label_rows = label_frequency(normalized_claims)
    write_csv(output_dir / "claim_label_frequency.csv", label_rows, CLAIM_LABEL_FREQUENCY_COLUMNS)

    context_rows = _context_summary(data.comments, normalized_claims)
    write_csv(output_dir / "context_quality_summary.csv", context_rows, CONTEXT_QUALITY_COLUMNS)

    attempt_rows = _attempt_summary(data.attempts)
    write_csv(output_dir / "attempt_quality_summary.csv", attempt_rows, ATTEMPT_QUALITY_COLUMNS)

    denom_rows = denominator_summary(data, len(normalized_claims))
    write_csv(output_dir / "denominator_summary.csv", denom_rows, DENOMINATOR_COLUMNS)

    return {
        "run_quality": run_quality,
        "comment_distribution": comment_dist,
        "claim_distribution": claim_dist,
        "claim_label_frequency": label_rows,
        "context_quality_summary": context_rows,
        "attempt_quality_summary": attempt_rows,
        "denominator_summary": denom_rows,
    }


def _den(name: str, value: int, source_table: str, source_filter: str, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "value": value,
        "source_table": source_table,
        "source_filter": source_filter,
        "description": description,
    }


def _run_quality_markdown(report: dict[str, Any]) -> str:
    rows = [{"metric": key, "value": value} for key, value in report.items() if key not in {"claim_count_distribution", "error_counts", "status_counts"}]
    return "# A3 Run Quality Report\n\n" + compact_markdown_table(rows, ["metric", "value"])


def _context_summary(comments: list[dict[str, str]], claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "metric": "comments_used_context",
            "count": sum(1 for row in comments if str(row.get("used_context", "")).strip() in {"1", "true", "True"}),
        },
        {
            "metric": "claims_used_context",
            "count": sum(1 for row in claims if str(row.get("used_context", "")).strip() in {"1", "true", "True"}),
        },
        {
            "metric": "low_attribution_comments",
            "count": sum(1 for row in comments if row.get("attribution_confidence") == "low"),
        },
        {
            "metric": "non_target_evidence_claims",
            "count": sum(1 for row in claims if row.get("evidence_source") != "target_comment"),
        },
    ]


def _attempt_summary(attempts: list[dict[str, str]]) -> list[dict[str, Any]]:
    if not attempts:
        return []
    by_status = Counter(row.get("status", "") for row in attempts)
    by_error = Counter(row.get("error_type", "") or "none" for row in attempts)
    total_tokens = sum(int_value(row.get("total_tokens")) for row in attempts)
    total_cost = sum(float_value(row.get("cost_usd")) for row in attempts)
    rows = [
        {"metric": "attempt_count", "group": "all", "count": len(attempts), "value": len(attempts)},
        {"metric": "total_tokens", "group": "all", "count": len(attempts), "value": total_tokens},
        {"metric": "cost_usd", "group": "all", "count": len(attempts), "value": total_cost},
    ]
    rows.extend({"metric": "attempt_status", "group": key, "count": value, "value": value} for key, value in by_status.items())
    rows.extend({"metric": "attempt_error_type", "group": key, "count": value, "value": value} for key, value in by_error.items())
    return rows
