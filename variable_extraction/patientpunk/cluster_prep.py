"""
patientpunk.cluster_prep
~~~~~~~~~~~~~~~~~~~~~~~~~
Turn an extraction's ``records.csv`` into a clustering-ready, per-patient
feature matrix -- and report whether it is actually clusterable.

Pipeline-output ``records.csv`` is per-RECORD (one row per post), wide, and full
of high-cardinality multi-value free-text -- not clusterable as-is.  This module:

  1. aggregates to one row per PATIENT (union of values across their records);
  2. drops fields below a coverage threshold (the sparse tail);
  3. encodes the remaining fields, collapsing cardinality to a controlled
     vocabulary (top-k values per field + an "other" bucket) so the matrix is
     dense enough to cluster -- the single biggest clusterability lever; and
  4. (optional, needs scikit-learn) reports clusterability: n, p/n, density,
     pairwise similarity, and silhouette across k.

The matrix builder uses only the stdlib; the report uses scikit-learn + numpy if
installed (``pip install 'patientpunk[cluster]'``).
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from ._utils import META_SKIP_COLUMNS


def read_records(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# Carry-along columns kept for analysis but NOT clustered: the raw
# "drug: outcome: symptom" triple (high-cardinality; the bucket lives in
# treatment_outcome_label) and the decomposed drug / symptom names.
_ANALYSIS_CARRY = {
    "treatment_outcome", "treatment_outcome_drug", "treatment_outcome_symptom",
}


def _data_fields(header: list[str], meta: set[str]) -> list[str]:
    return [c for c in header
            if c not in meta and c not in _ANALYSIS_CARRY
            and not c.endswith(("__provenance", "__confidence"))]


def aggregate_patients(rows: list[dict], *, key_col: str = "author_hash",
                       sep: str = " | ", meta: frozenset[str] = META_SKIP_COLUMNS):
    """``rows`` -> ({patient_id: {field: set(values)}}, data_fields).

    One entry per distinct *key_col*; multi-values are unioned across the
    patient's records and normalized (stripped, lowercased).
    """
    if not rows:
        return {}, []
    fields = _data_fields(list(rows[0].keys()), meta)
    pat: dict = defaultdict(lambda: defaultdict(set))
    for r in rows:
        pid = (r.get(key_col) or "").strip()
        if not pid:
            continue
        for f in fields:
            for v in (r.get(f) or "").split(sep):
                v = v.strip().lower()
                if v:
                    pat[pid][f].add(v)
    return {pid: dict(d) for pid, d in pat.items()}, fields


def field_coverage(patients: dict, fields: list[str]) -> dict[str, float]:
    n = len(patients) or 1
    return {f: sum(1 for p in patients.values() if p.get(f)) / n for f in fields}


def select_fields(patients: dict, fields: list[str], min_coverage: float):
    cov = field_coverage(patients, fields)
    kept = sorted([f for f in fields if cov[f] >= min_coverage], key=lambda f: -cov[f])
    return kept, cov


# Column predicates (defined at module scope to avoid late-binding closures).
def _value_match(value):
    return lambda have: 1 if value in have else 0


def _has_other(topset):
    return lambda have: 1 if (have - topset) else 0


def _has_any(have):
    return 1 if have else 0


def build_matrix(patients: dict, fields: list[str], *,
                 encode: str = "topk", top_k: int = 8):
    """Return (patient_ids, feature_names, X) with X a list[list[int]] 0/1 matrix.

    encode:
      ``presence``  -- one binary column per field (has any value); collapses
                       cardinality entirely.
      ``topk``      -- per field, columns for the top_k most frequent values plus
                       a ``<field>:other`` bucket for the long tail (the
                       controlled-vocab default).
      ``multihot``  -- one column per distinct (field, value); no collapse.
    """
    pids = sorted(patients)
    columns: list[tuple[str, str, callable]] = []  # (name, field, predicate)
    for f in fields:
        if encode == "presence":
            columns.append((f, f, _has_any))
            continue
        counter = Counter(v for p in patients.values() for v in p.get(f, ()))
        if encode == "multihot":
            for v in sorted(counter):
                columns.append((f"{f}={v}", f, _value_match(v)))
        else:  # topk
            top = [v for v, _ in counter.most_common(top_k)]
            for v in top:
                columns.append((f"{f}={v}", f, _value_match(v)))
            columns.append((f"{f}:other", f, _has_other(set(top))))

    names = [c[0] for c in columns]
    X = [[pred(patients[pid].get(field, set())) for _, field, pred in columns]
         for pid in pids]
    return pids, names, X


def write_matrix(path: Path, pids: list[str], names: list[str], X: list[list[int]],
                 key_col: str = "patient_id") -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([key_col] + names)
        for pid, row in zip(pids, X):
            w.writerow([pid] + row)


def readiness_report(pids: list[str], names: list[str], X: list[list[int]]) -> dict:
    """Clusterability report.  n / p-over-n / density always; pairwise similarity
    + silhouette-by-k when scikit-learn + numpy are installed."""
    n, p = len(pids), len(names)
    total = n * p
    ones = sum(sum(row) for row in X)
    out = {
        "n_patients": n,
        "n_features": p,
        "p_over_n": round(p / n, 2) if n else 0.0,
        "density": round(ones / total, 4) if total else 0.0,
        "sklearn": False,
    }
    try:
        import numpy as np
        from sklearn.cluster import AgglomerativeClustering
        from sklearn.metrics import pairwise_distances, silhouette_score
    except ImportError:
        return out
    if n < 3:
        return out
    out["sklearn"] = True
    Xa = np.array(X, dtype=int)
    D = pairwise_distances(Xa, metric="jaccard")
    # All-zero rows (patients with no extracted features) yield Jaccard 0/0 = NaN,
    # which propagates into silhouette/median. Treat them as maximally dissimilar.
    D = np.nan_to_num(D, nan=1.0)
    sims = (1 - D)[np.triu_indices(n, 1)]
    out["similarity_median"] = round(float(np.median(sims)), 3)
    out["similarity_mean"] = round(float(sims.mean()), 3)
    sil = {}
    for k in range(2, min(8, n)):
        labels = AgglomerativeClustering(
            n_clusters=k, metric="precomputed", linkage="average").fit_predict(D)
        sil[k] = round(float(silhouette_score(D, labels, metric="precomputed")), 3)
    out["silhouette_by_k"] = sil
    if sil:
        out["best_k"] = max(sil, key=sil.get)
        out["best_silhouette"] = sil[out["best_k"]]
    return out
