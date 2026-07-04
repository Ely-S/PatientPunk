from __future__ import annotations

import sqlite3
from pathlib import Path

from dev.analysis.cluster.analysis import build_comment_clusters, load_comment_cluster_assignments
from dev.analysis.cluster.common import read_csv


def test_build_comment_clusters_groups_obvious_themes(tmp_path: Path) -> None:
    report_dir = _make_a4_report(tmp_path)
    comment_db = _make_comment_db(tmp_path)

    result = build_comment_clusters(
        a4_report=report_dir,
        output_dir=tmp_path / "clusters",
        comment_db=comment_db,
        min_meaningful_comments=4,
        n_clusters=2,
        write_feature_matrix=True,
    )

    assert result["ok"] is True
    assert result["meaningful_clustering"] is True
    assert result["n_claim_rows"] == 4
    assert result["n_comments_with_claims"] == 4
    assert result["n_joined_comment_bodies"] == 4
    assert result["n_clusters"] == 2

    assignments = load_comment_cluster_assignments(tmp_path / "clusters")
    by_comment = {row["comment_id"]: row["cluster_id"] for row in assignments}
    assert by_comment["c1"] == by_comment["c2"]
    assert by_comment["c3"] == by_comment["c4"]
    assert by_comment["c1"] != by_comment["c3"]

    summary = read_csv(tmp_path / "clusters" / "cluster_summary.csv")
    assert len(summary) == 2
    assert (tmp_path / "clusters" / "comment_feature_matrix.csv").exists()
    assert (tmp_path / "clusters" / "cluster_readiness_report.json").exists()


def test_build_comment_clusters_flags_tiny_samples(tmp_path: Path) -> None:
    report_dir = _make_a4_report(tmp_path, comment_ids=["c1", "c3"])
    comment_db = _make_comment_db(tmp_path)

    result = build_comment_clusters(
        a4_report=report_dir,
        output_dir=tmp_path / "clusters",
        comment_db=comment_db,
        min_meaningful_comments=10,
        n_clusters=2,
    )

    assert result["ok"] is True
    assert result["meaningful_clustering"] is False
    assert result["n_comments_with_claims"] == 2
    assert result["warnings"]


def _make_a4_report(tmp_path: Path, comment_ids: list[str] | None = None) -> Path:
    report_dir = tmp_path / "a4_report"
    report_dir.mkdir()
    mart = report_dir / "evidence_mart.sqlite"
    rows = [
        {
            "comment_id": "c1",
            "source_line": "1",
            "claim_id": "claim_1",
            "claim_index": "1",
            "claim_type": "symptom",
            "normalized_label_canonical": "post exertional malaise",
            "normalized_label_clean": "post exertional malaise",
            "normalized_label": "PEM",
            "raw_text": "Fatigue and post exertional malaise crash after walking.",
            "evidence_quote": "I crash after walking and have fatigue.",
            "used_context": "0",
            "attribution_confidence": "high",
            "year_month": "2020-01",
            "parent_kind": "post",
        },
        {
            "comment_id": "c2",
            "source_line": "2",
            "claim_id": "claim_2",
            "claim_index": "1",
            "claim_type": "symptom",
            "normalized_label_canonical": "brain fog fatigue",
            "normalized_label_clean": "brain fog fatigue",
            "normalized_label": "Brain fog fatigue",
            "raw_text": "Brain fog fatigue and exertion crashes keep recurring.",
            "evidence_quote": "brain fog and exertion crashes",
            "used_context": "0",
            "attribution_confidence": "high",
            "year_month": "2020-01",
            "parent_kind": "post",
        },
        {
            "comment_id": "c3",
            "source_line": "3",
            "claim_id": "claim_3",
            "claim_index": "1",
            "claim_type": "treatment",
            "normalized_label_canonical": "antihistamine",
            "normalized_label_clean": "antihistamine",
            "normalized_label": "Antihistamine",
            "raw_text": "Famotidine and cetirizine helped histamine reactions.",
            "evidence_quote": "famotidine and cetirizine helped",
            "used_context": "0",
            "attribution_confidence": "high",
            "year_month": "2020-01",
            "parent_kind": "post",
        },
        {
            "comment_id": "c4",
            "source_line": "4",
            "claim_id": "claim_4",
            "claim_index": "1",
            "claim_type": "treatment",
            "normalized_label_canonical": "histamine diet",
            "normalized_label_clean": "histamine diet",
            "normalized_label": "Histamine diet",
            "raw_text": "Low histamine diet and antihistamines reduced flushing.",
            "evidence_quote": "low histamine diet reduced flushing",
            "used_context": "0",
            "attribution_confidence": "high",
            "year_month": "2020-01",
            "parent_kind": "post",
        },
    ]
    if comment_ids is not None:
        wanted = set(comment_ids)
        rows = [row for row in rows if row["comment_id"] in wanted]

    with sqlite3.connect(mart) as conn:
        conn.execute(
            """
            CREATE TABLE claims (
                comment_id TEXT,
                source_line TEXT,
                claim_id TEXT,
                claim_index TEXT,
                claim_type TEXT,
                normalized_label_canonical TEXT,
                normalized_label_clean TEXT,
                normalized_label TEXT,
                raw_text TEXT,
                evidence_quote TEXT,
                used_context TEXT,
                attribution_confidence TEXT,
                year_month TEXT,
                parent_kind TEXT
            )
            """
        )
        for row in rows:
            conn.execute(
                """
                INSERT INTO claims (
                    comment_id, source_line, claim_id, claim_index, claim_type,
                    normalized_label_canonical, normalized_label_clean, normalized_label,
                    raw_text, evidence_quote, used_context, attribution_confidence,
                    year_month, parent_kind
                )
                VALUES (
                    :comment_id, :source_line, :claim_id, :claim_index, :claim_type,
                    :normalized_label_canonical, :normalized_label_clean, :normalized_label,
                    :raw_text, :evidence_quote, :used_context, :attribution_confidence,
                    :year_month, :parent_kind
                )
                """,
                row,
            )
    return report_dir


def _make_comment_db(tmp_path: Path) -> Path:
    db = tmp_path / "comments.sqlite"
    bodies = {
        "c1": "Walking causes fatigue, PEM, and a physical crash.",
        "c2": "The brain fog and fatigue flare after exertion.",
        "c3": "Cetirizine and famotidine calmed histamine symptoms.",
        "c4": "A low histamine diet and antihistamines reduced flushing.",
    }
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE comments (id TEXT PRIMARY KEY, body TEXT)")
        for comment_id, body in bodies.items():
            conn.execute("INSERT INTO comments (id, body) VALUES (?, ?)", (comment_id, body))
    return db
