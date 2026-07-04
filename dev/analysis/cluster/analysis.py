"""Cluster A4-extracted comments for exploratory analysis."""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from dev.analysis.a0_extraction.comment_context import DEFAULT_DB
from dev.analysis.cluster.common import (
    CLUSTER_VERSION,
    DEFAULT_CLUSTER_ROOT,
    read_csv,
    resolve_evidence_mart,
    slug,
    utc_now_compact,
    write_csv,
    write_json,
    write_jsonl,
)


CLAIM_COLUMNS = [
    "comment_id",
    "source_line",
    "claim_id",
    "claim_index",
    "claim_type",
    "normalized_label_canonical",
    "normalized_label_clean",
    "normalized_label",
    "raw_text",
    "evidence_quote",
    "used_context",
    "attribution_confidence",
    "year_month",
    "parent_kind",
]


def build_comment_clusters(
    *,
    a4_report: str | Path,
    output_dir: str | Path | None = None,
    comment_db: str | Path = DEFAULT_DB,
    include_comment_body: bool = True,
    include_claim_text: bool = True,
    include_evidence_quotes: bool = True,
    min_meaningful_comments: int = 10,
    max_features: int = 5000,
    min_df: int = 1,
    ngram_range: tuple[int, int] = (1, 2),
    distance_threshold: float = 0.65,
    n_clusters: int | None = None,
    write_feature_matrix: bool = False,
) -> dict[str, Any]:
    """Build exploratory comment clusters from an A4 report or evidence mart.

    `a4_report` can point either to an A4 report directory or directly to
    `evidence_mart.sqlite`. The function writes a small cluster package and
    returns the readiness report.
    """
    a4_report_path = Path(a4_report)
    mart_path = resolve_evidence_mart(a4_report_path)
    if not mart_path.exists():
        raise FileNotFoundError(f"A4 evidence mart not found: {mart_path}")

    out_dir = Path(output_dir) if output_dir is not None else _default_output_dir(a4_report_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    claim_rows = load_claim_rows(mart_path)
    comment_rows, join_stats = build_comment_documents(
        claim_rows,
        comment_db=Path(comment_db),
        include_comment_body=include_comment_body,
        include_claim_text=include_claim_text,
        include_evidence_quotes=include_evidence_quotes,
    )

    if not comment_rows:
        return _write_empty_package(
            out_dir=out_dir,
            mart_path=mart_path,
            comment_db=Path(comment_db),
            claim_row_count=len(claim_rows),
            min_meaningful_comments=min_meaningful_comments,
            join_stats=join_stats,
        )

    vector_result = _vectorize(comment_rows, max_features=max_features, min_df=min_df, ngram_range=ngram_range)
    labels, clustering_mode = _cluster_vectors(
        vector_result["matrix"],
        n_clusters=n_clusters,
        distance_threshold=distance_threshold,
    )
    cluster_ids = _stable_cluster_ids(comment_rows, labels)
    similarities = _pairwise_similarities(comment_rows, vector_result["similarity"])

    assignments = _assignment_rows(comment_rows, labels, cluster_ids)
    summary = _summary_rows(comment_rows, assignments)
    top_terms = _top_terms_rows(comment_rows, vector_result["matrix"], vector_result["feature_names"])
    cluster_terms = _cluster_terms_rows(comment_rows, assignments, vector_result["matrix"], vector_result["feature_names"])
    examples = _example_rows(comment_rows, assignments)

    outputs = {
        "assignments": "comment_cluster_assignments.csv",
        "summary": "cluster_summary.csv",
        "examples": "cluster_examples.csv",
        "similarity": "cosine_similarity.csv",
        "top_terms": "top_tfidf_terms.csv",
        "cluster_terms": "cluster_terms.csv",
        "readiness": "cluster_readiness_report.json",
        "manifest": "cluster_manifest.json",
    }
    write_csv(out_dir / outputs["assignments"], assignments, ASSIGNMENT_COLUMNS)
    write_csv(out_dir / outputs["summary"], summary, SUMMARY_COLUMNS)
    write_csv(out_dir / outputs["examples"], examples, EXAMPLE_COLUMNS)
    write_csv(out_dir / outputs["similarity"], similarities, SIMILARITY_COLUMNS)
    write_csv(out_dir / outputs["top_terms"], top_terms, TOP_TERMS_COLUMNS)
    write_csv(out_dir / outputs["cluster_terms"], cluster_terms, CLUSTER_TERMS_COLUMNS)
    if write_feature_matrix:
        feature_rows = _feature_matrix_rows(comment_rows, vector_result["matrix"], vector_result["feature_names"])
        outputs["feature_matrix"] = "comment_feature_matrix.csv"
        write_csv(out_dir / outputs["feature_matrix"], feature_rows)

    manifest = _manifest(
        out_dir=out_dir,
        mart_path=mart_path,
        comment_db=Path(comment_db),
        configuration={
            "include_comment_body": include_comment_body,
            "include_claim_text": include_claim_text,
            "include_evidence_quotes": include_evidence_quotes,
            "min_meaningful_comments": min_meaningful_comments,
            "max_features": max_features,
            "min_df": min_df,
            "ngram_range": list(ngram_range),
            "distance_threshold": distance_threshold,
            "n_clusters": n_clusters,
            "write_feature_matrix": write_feature_matrix,
        },
        outputs=outputs,
    )
    write_json(out_dir / outputs["manifest"], manifest)

    readiness = {
        "ok": True,
        "cluster_version": CLUSTER_VERSION,
        "input_mart": str(mart_path),
        "comment_db": str(comment_db),
        "output_dir": str(out_dir),
        "clustering_mode": clustering_mode,
        "n_claim_rows": len(claim_rows),
        "n_comments_with_claims": len(comment_rows),
        "n_joined_comment_bodies": join_stats["joined_bodies"],
        "n_clusters": len(summary),
        "n_pairwise_comparisons": len(similarities),
        "tfidf_shape": [int(vector_result["matrix"].shape[0]), int(vector_result["matrix"].shape[1])],
        "meaningful_clustering": len(comment_rows) >= min_meaningful_comments,
        "meaningful_min_comments": min_meaningful_comments,
        "warnings": _warnings(comment_rows, min_meaningful_comments),
        "outputs": outputs,
    }
    write_json(out_dir / outputs["readiness"], readiness)
    return readiness


def load_comment_cluster_assignments(cluster_dir: str | Path) -> list[dict[str, str]]:
    """Read `comment_cluster_assignments.csv` from a cluster output directory."""
    return read_csv(Path(cluster_dir) / "comment_cluster_assignments.csv")


def load_claim_rows(mart_path: Path) -> list[dict[str, Any]]:
    with sqlite3.connect(mart_path) as conn:
        conn.row_factory = sqlite3.Row
        available = {row[1] for row in conn.execute("PRAGMA table_info(claims)").fetchall()}
        if "claims" not in {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
            raise ValueError(f"No claims table found in {mart_path}")
        selected = [column for column in CLAIM_COLUMNS if column in available]
        if "comment_id" not in selected:
            raise ValueError(f"claims table in {mart_path} does not have comment_id")
        order_cols = [column for column in ["source_line", "claim_index", "claim_id"] if column in selected]
        order_sql = ", ".join(order_cols) if order_cols else "comment_id"
        sql = (
            f"SELECT {', '.join(selected)} FROM claims "
            "WHERE COALESCE(comment_id, '') != '' "
            f"ORDER BY {order_sql}"
        )
        return [dict(row) for row in conn.execute(sql)]


def build_comment_documents(
    claim_rows: list[dict[str, Any]],
    *,
    comment_db: Path,
    include_comment_body: bool,
    include_claim_text: bool,
    include_evidence_quotes: bool,
) -> tuple[list[dict[str, Any]], dict[str, int | bool]]:
    grouped: dict[str, dict[str, Any]] = {}
    for claim in claim_rows:
        comment_id = str(claim.get("comment_id") or "").strip()
        if not comment_id:
            continue
        group = grouped.setdefault(
            comment_id,
            {
                "comment_id": comment_id,
                "source_line": str(claim.get("source_line") or ""),
                "year_month": str(claim.get("year_month") or ""),
                "parent_kind": str(claim.get("parent_kind") or ""),
                "claim_ids": [],
                "claim_types": [],
                "labels": [],
                "claim_texts": [],
                "evidence_quotes": [],
                "used_context_any": 0,
                "low_attribution_any": 0,
                "body": "",
                "body_joined": 0,
            },
        )
        _append_nonempty(group["claim_ids"], claim.get("claim_id"))
        _append_nonempty(group["claim_types"], claim.get("claim_type"))
        _append_nonempty(
            group["labels"],
            claim.get("normalized_label_canonical")
            or claim.get("normalized_label_clean")
            or claim.get("normalized_label"),
        )
        if include_claim_text:
            _append_nonempty(group["claim_texts"], claim.get("raw_text"))
        if include_evidence_quotes:
            _append_nonempty(group["evidence_quotes"], claim.get("evidence_quote"))
        if _boolish(claim.get("used_context")):
            group["used_context_any"] = 1
        if _low_attribution(claim.get("attribution_confidence")):
            group["low_attribution_any"] = 1

    bodies = _load_comment_bodies(comment_db, list(grouped)) if include_comment_body else {}
    joined_bodies = 0
    for comment_id, body in bodies.items():
        if comment_id in grouped and body.strip():
            grouped[comment_id]["body"] = body
            grouped[comment_id]["body_joined"] = 1
            joined_bodies += 1

    rows = []
    for group in grouped.values():
        group["document"] = _document_text(group, include_comment_body=include_comment_body)
        group["claim_types"] = sorted(set(group["claim_types"]))
        group["labels"] = sorted(set(group["labels"]))
        rows.append(group)
    rows.sort(key=_comment_sort_key)
    return rows, {
        "comment_db_exists": comment_db.exists(),
        "requested_bodies": len(grouped) if include_comment_body else 0,
        "joined_bodies": joined_bodies,
    }


def _default_output_dir(a4_report: Path) -> Path:
    if a4_report.is_dir():
        return a4_report / "clusters"
    return DEFAULT_CLUSTER_ROOT / f"{slug(a4_report.stem)}_{utc_now_compact()}"


def _write_empty_package(
    *,
    out_dir: Path,
    mart_path: Path,
    comment_db: Path,
    claim_row_count: int,
    min_meaningful_comments: int,
    join_stats: dict[str, int | bool],
) -> dict[str, Any]:
    outputs = {
        "assignments": "comment_cluster_assignments.csv",
        "summary": "cluster_summary.csv",
        "examples": "cluster_examples.csv",
        "similarity": "cosine_similarity.csv",
        "top_terms": "top_tfidf_terms.csv",
        "cluster_terms": "cluster_terms.csv",
        "readiness": "cluster_readiness_report.json",
        "manifest": "cluster_manifest.json",
    }
    write_csv(out_dir / outputs["assignments"], [], ASSIGNMENT_COLUMNS)
    write_csv(out_dir / outputs["summary"], [], SUMMARY_COLUMNS)
    write_csv(out_dir / outputs["examples"], [], EXAMPLE_COLUMNS)
    write_csv(out_dir / outputs["similarity"], [], SIMILARITY_COLUMNS)
    write_csv(out_dir / outputs["top_terms"], [], TOP_TERMS_COLUMNS)
    write_csv(out_dir / outputs["cluster_terms"], [], CLUSTER_TERMS_COLUMNS)
    manifest = _manifest(out_dir=out_dir, mart_path=mart_path, comment_db=comment_db, configuration={}, outputs=outputs)
    write_json(out_dir / outputs["manifest"], manifest)
    readiness = {
        "ok": True,
        "cluster_version": CLUSTER_VERSION,
        "input_mart": str(mart_path),
        "comment_db": str(comment_db),
        "output_dir": str(out_dir),
        "clustering_mode": "no_comments_with_claims",
        "n_claim_rows": claim_row_count,
        "n_comments_with_claims": 0,
        "n_joined_comment_bodies": join_stats["joined_bodies"],
        "n_clusters": 0,
        "n_pairwise_comparisons": 0,
        "tfidf_shape": [0, 0],
        "meaningful_clustering": False,
        "meaningful_min_comments": min_meaningful_comments,
        "warnings": ["No comments with claims were available to cluster."],
        "outputs": outputs,
    }
    write_json(out_dir / outputs["readiness"], readiness)
    return readiness


def _vectorize(comment_rows: list[dict[str, Any]], *, max_features: int, min_df: int, ngram_range: tuple[int, int]) -> dict[str, Any]:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError as exc:
        raise RuntimeError("Install the cluster extra before clustering: pip install '.[cluster]'") from exc

    documents = [row["document"] or row["comment_id"] for row in comment_rows]
    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=ngram_range,
        min_df=min_df,
        max_features=max_features,
    )
    try:
        matrix = vectorizer.fit_transform(documents)
    except ValueError:
        vectorizer = TfidfVectorizer(lowercase=False, token_pattern=r"(?u)\b\w+\b")
        matrix = vectorizer.fit_transform([row["comment_id"] for row in comment_rows])
    return {
        "matrix": matrix,
        "feature_names": vectorizer.get_feature_names_out(),
        "similarity": cosine_similarity(matrix),
    }


def _cluster_vectors(matrix: Any, *, n_clusters: int | None, distance_threshold: float) -> tuple[list[int], str]:
    try:
        from sklearn.cluster import AgglomerativeClustering
    except ImportError as exc:
        raise RuntimeError("Install the cluster extra before clustering: pip install '.[cluster]'") from exc

    n_rows = int(matrix.shape[0])
    if n_rows == 1:
        return [0], "single_comment"

    dense = matrix.toarray()
    kwargs: dict[str, Any] = {"linkage": "average"}
    if n_clusters is None:
        kwargs["n_clusters"] = None
        kwargs["distance_threshold"] = distance_threshold
        mode = f"agglomerative_cosine_distance_threshold_{distance_threshold}"
    else:
        kwargs["n_clusters"] = n_clusters
        mode = f"agglomerative_cosine_n_clusters_{n_clusters}"

    try:
        labels = AgglomerativeClustering(metric="cosine", **kwargs).fit_predict(dense)
    except TypeError:
        labels = AgglomerativeClustering(affinity="cosine", **kwargs).fit_predict(dense)
    return [int(label) for label in labels], mode


def _stable_cluster_ids(comment_rows: list[dict[str, Any]], labels: list[int]) -> dict[int, str]:
    by_label: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row, label in zip(comment_rows, labels):
        by_label[label].append(row)
    ordered_labels = sorted(by_label, key=lambda label: min(_comment_sort_key(row) for row in by_label[label]))
    return {label: f"cluster_{index + 1:03d}" for index, label in enumerate(ordered_labels)}


def _assignment_rows(comment_rows: list[dict[str, Any]], labels: list[int], cluster_ids: dict[int, str]) -> list[dict[str, Any]]:
    rows = []
    for row, label in zip(comment_rows, labels):
        rows.append(
            {
                "comment_id": row["comment_id"],
                "source_line": row["source_line"],
                "cluster_id": cluster_ids[label],
                "sklearn_label": label,
                "n_claims": len(row["claim_ids"]),
                "n_claim_types": len(row["claim_types"]),
                "n_labels": len(row["labels"]),
                "body_joined": row["body_joined"],
                "used_context_any": row["used_context_any"],
                "low_attribution_any": row["low_attribution_any"],
            }
        )
    return rows


def _summary_rows(comment_rows: list[dict[str, Any]], assignments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_comment = {row["comment_id"]: row for row in comment_rows}
    members_by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for assignment in assignments:
        members_by_cluster[assignment["cluster_id"]].append(by_comment[assignment["comment_id"]])

    rows = []
    for cluster_id, members in sorted(members_by_cluster.items()):
        claim_type_counts = Counter(item for member in members for item in member["claim_types"])
        label_counts = Counter(item for member in members for item in member["labels"])
        representative = max(members, key=lambda member: (len(member["claim_ids"]), member["comment_id"]))
        rows.append(
            {
                "cluster_id": cluster_id,
                "n_comments": len(members),
                "total_claims": sum(len(member["claim_ids"]) for member in members),
                "top_claim_types": _format_counts(claim_type_counts),
                "top_labels": _format_counts(label_counts),
                "representative_comment_id": representative["comment_id"],
                "representative_source_line": representative["source_line"],
            }
        )
    return rows


def _example_rows(comment_rows: list[dict[str, Any]], assignments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_comment = {row["comment_id"]: row for row in comment_rows}
    rows = []
    for assignment in assignments:
        comment = by_comment[assignment["comment_id"]]
        rows.append(
            {
                "cluster_id": assignment["cluster_id"],
                "comment_id": assignment["comment_id"],
                "source_line": assignment["source_line"],
                "example_claim": _first(comment["claim_texts"]),
                "example_quote": _first(comment["evidence_quotes"]),
            }
        )
    return rows


def _pairwise_similarities(comment_rows: list[dict[str, Any]], similarity: Any) -> list[dict[str, Any]]:
    rows = []
    for left_index, left in enumerate(comment_rows):
        for right_index, right in enumerate(comment_rows):
            if left_index >= right_index:
                continue
            score = float(similarity[left_index, right_index])
            rows.append(
                {
                    "left_comment_id": left["comment_id"],
                    "right_comment_id": right["comment_id"],
                    "cosine_similarity": round(score, 6),
                    "cosine_distance": round(1.0 - score, 6),
                }
            )
    return rows


def _top_terms_rows(comment_rows: list[dict[str, Any]], matrix: Any, feature_names: Any) -> list[dict[str, Any]]:
    rows = []
    for index, comment in enumerate(comment_rows):
        vector = matrix.getrow(index)
        scored = sorted(zip(vector.indices, vector.data), key=lambda item: item[1], reverse=True)[:15]
        rows.append(
            {
                "comment_id": comment["comment_id"],
                "source_line": comment["source_line"],
                "top_tfidf_terms": "; ".join(f"{feature_names[column]}:{score:.4f}" for column, score in scored),
            }
        )
    return rows


def _cluster_terms_rows(comment_rows: list[dict[str, Any]], assignments: list[dict[str, Any]], matrix: Any, feature_names: Any) -> list[dict[str, Any]]:
    cluster_to_indices: dict[str, list[int]] = defaultdict(list)
    for index, assignment in enumerate(assignments):
        cluster_to_indices[assignment["cluster_id"]].append(index)

    rows = []
    for cluster_id, indices in sorted(cluster_to_indices.items()):
        submatrix = matrix[indices]
        means = submatrix.mean(axis=0).A1
        best = sorted(enumerate(means), key=lambda item: item[1], reverse=True)[:20]
        rows.append(
            {
                "cluster_id": cluster_id,
                "n_comments": len(indices),
                "top_tfidf_terms": "; ".join(f"{feature_names[column]}:{score:.4f}" for column, score in best if score > 0),
            }
        )
    return rows


def _feature_matrix_rows(comment_rows: list[dict[str, Any]], matrix: Any, feature_names: Any) -> list[dict[str, Any]]:
    dense = matrix.toarray()
    rows = []
    for index, comment in enumerate(comment_rows):
        row: dict[str, Any] = {"comment_id": comment["comment_id"], "source_line": comment["source_line"]}
        for feature_index, feature_name in enumerate(feature_names):
            value = float(dense[index][feature_index])
            if value:
                row[f"tfidf__{feature_name}"] = round(value, 8)
        rows.append(row)
    return rows


def _manifest(
    *,
    out_dir: Path,
    mart_path: Path,
    comment_db: Path,
    configuration: dict[str, Any],
    outputs: dict[str, str],
) -> dict[str, Any]:
    return {
        "cluster_version": CLUSTER_VERSION,
        "created_at_utc": utc_now_compact(),
        "input_mart": str(mart_path),
        "comment_db": str(comment_db),
        "output_dir": str(out_dir),
        "configuration": configuration,
        "outputs": outputs,
    }


def _warnings(comment_rows: list[dict[str, Any]], min_meaningful_comments: int) -> list[str]:
    warnings = []
    if len(comment_rows) < min_meaningful_comments:
        warnings.append(
            f"Only {len(comment_rows)} comments with claims were clustered; "
            f"treat output as a mechanics check until at least {min_meaningful_comments} are available."
        )
    if sum(row["body_joined"] for row in comment_rows) < len(comment_rows):
        warnings.append("Some comments could not be joined back to the A0 comment body database.")
    return warnings


def _load_comment_bodies(comment_db: Path, comment_ids: list[str]) -> dict[str, str]:
    if not comment_db.exists() or not comment_ids:
        return {}
    with sqlite3.connect(comment_db) as conn:
        conn.row_factory = sqlite3.Row
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "comments" not in tables:
            return {}
        columns = {row[1] for row in conn.execute("PRAGMA table_info(comments)").fetchall()}
        if "id" not in columns or "body" not in columns:
            return {}
        placeholders = ",".join("?" for _ in comment_ids)
        sql = f"SELECT id, body FROM comments WHERE id IN ({placeholders})"
        return {str(row["id"]): str(row["body"] or "") for row in conn.execute(sql, comment_ids)}


def _document_text(group: dict[str, Any], *, include_comment_body: bool) -> str:
    parts = []
    parts.extend(f"claim_type {value}" for value in group["claim_types"])
    parts.extend(f"label {value}" for value in group["labels"])
    parts.extend(group["claim_texts"])
    parts.extend(group["evidence_quotes"])
    if include_comment_body and group["body"]:
        parts.append(group["body"])
    return "\n".join(part for part in parts if part).strip()


def _append_nonempty(items: list[str], value: Any) -> None:
    text = str(value or "").strip()
    if text:
        items.append(text)


def _boolish(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _low_attribution(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return bool(text and text != "high")


def _comment_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    try:
        source_line = int(float(row.get("source_line") or 0))
    except (TypeError, ValueError):
        source_line = 0
    return source_line, str(row.get("comment_id") or "")


def _format_counts(counter: Counter[str], limit: int = 8) -> str:
    return "; ".join(f"{name}:{count}" for name, count in counter.most_common(limit))


def _first(values: list[str]) -> str:
    return values[0] if values else ""


ASSIGNMENT_COLUMNS = [
    "comment_id",
    "source_line",
    "cluster_id",
    "sklearn_label",
    "n_claims",
    "n_claim_types",
    "n_labels",
    "body_joined",
    "used_context_any",
    "low_attribution_any",
]
SUMMARY_COLUMNS = [
    "cluster_id",
    "n_comments",
    "total_claims",
    "top_claim_types",
    "top_labels",
    "representative_comment_id",
    "representative_source_line",
]
EXAMPLE_COLUMNS = ["cluster_id", "comment_id", "source_line", "example_claim", "example_quote"]
SIMILARITY_COLUMNS = ["left_comment_id", "right_comment_id", "cosine_similarity", "cosine_distance"]
TOP_TERMS_COLUMNS = ["comment_id", "source_line", "top_tfidf_terms"]
CLUSTER_TERMS_COLUMNS = ["cluster_id", "n_comments", "top_tfidf_terms"]
