"""
patientpunk.evaluate
~~~~~~~~~~~~~~~~~~~~~
Per-field evaluation of an extraction against a reference label set.

Given a REFERENCE ``records.csv`` (gold human labels, or a trusted/strong-model
silver reference) and a CANDIDATE ``records.csv`` (e.g. a cheaper model you plan
to run at scale on dispersed compute), score each field so you can decide --
*per field* -- whether the candidate is good enough, or should be dropped from
the clustering feature set / kept on the reference model.

You cannot scale an extraction you have never measured.  This is the instrument:
point it at (reference, candidate) and read the per-field scorecard.

Metrics per field (multi-label: cells are split on the multi-value separator and
compared as case-insensitive sets):
  precision / recall / f1   -- over the values present (candidate vs reference)
  agreement_present         -- among rows where *either* side has a value, the
                               fraction whose value SETS match exactly
                               (excludes both-empty rows so sparse fields aren't
                               trivially inflated)
  ref_fill / cand_fill      -- fill rate on each side

Pure functions; no API calls.
"""

from __future__ import annotations

import csv
import statistics
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ._utils import META_SKIP_COLUMNS

DEFAULT_KEY = ("author_hash", "post_id")


def _value_set(cell, sep: str) -> set[str]:
    """Split a CSV cell into a normalized (lowercased, stripped) set of values."""
    if cell is None:
        return set()
    s = str(cell).strip()
    if not s:
        return set()
    return {v.strip().lower() for v in s.split(sep) if v.strip()}


def load_records(path: Path, key=DEFAULT_KEY) -> tuple[dict, list[str]]:
    """Load a records.csv into a dict keyed by the *key* columns + its fieldnames."""
    rows: dict[tuple, dict] = {}
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        for r in reader:
            rows[tuple(r.get(c, "") for c in key)] = r
    return rows, fieldnames


def _data_fields(sample_row: dict) -> list[str]:
    return [
        c for c in sample_row
        if c not in META_SKIP_COLUMNS
        and not c.endswith("__provenance")
        and not c.endswith("__confidence")
    ]


def score_field(pairs: list[tuple], sep: str) -> dict:
    """Score one field from a list of ``(ref_cell, cand_cell)`` pairs."""
    tp = ref_total = cand_total = 0
    n_present = exact_present = ref_fill = cand_fill = 0
    for ref_cell, cand_cell in pairs:
        ref_set, cand_set = _value_set(ref_cell, sep), _value_set(cand_cell, sep)
        if ref_set:
            ref_fill += 1
        if cand_set:
            cand_fill += 1
        if not ref_set and not cand_set:
            continue
        n_present += 1
        tp += len(ref_set & cand_set)
        ref_total += len(ref_set)
        cand_total += len(cand_set)
        if ref_set == cand_set:
            exact_present += 1
    precision = tp / cand_total if cand_total else 0.0
    recall = tp / ref_total if ref_total else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "agreement_present": round(exact_present / n_present, 3) if n_present else 1.0,
        "n_present": n_present,
        "ref_fill": ref_fill,
        "cand_fill": cand_fill,
    }


class EvalResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    per_field: dict
    overall: dict
    n_reference: int
    n_candidate: int
    n_matched: int   # rows present in BOTH files by key


def score_extraction(
    reference_rows: dict,
    candidate_rows: dict,
    *,
    fields: list[str] | None = None,
    sep: str = " | ",
) -> EvalResult:
    """Score *candidate_rows* against *reference_rows* (both keyed dicts) per field."""
    keys = [k for k in reference_rows if k in candidate_rows]
    if fields is None:
        any_ref = next(iter(reference_rows.values()), {})
        fields = _data_fields(any_ref)

    per_field: dict[str, dict] = {}
    for fld in fields:
        pairs = [(reference_rows[k].get(fld, ""), candidate_rows[k].get(fld, "")) for k in keys]
        per_field[fld] = score_field(pairs, sep)

    scored = [m for m in per_field.values() if m["n_present"] > 0]
    overall = {
        "macro_f1": round(statistics.mean([m["f1"] for m in scored]), 3) if scored else 0.0,
        "macro_agreement": round(statistics.mean([m["agreement_present"] for m in scored]), 3) if scored else 0.0,
        "n_fields_scored": len(per_field),
        "n_fields_with_data": len(scored),
    }
    return EvalResult(
        per_field=per_field,
        overall=overall,
        n_reference=len(reference_rows),
        n_candidate=len(candidate_rows),
        n_matched=len(keys),
    )


def export_gold_template(
    records_rows: dict,
    fields: list[str],
    out_path: Path,
    *,
    key=DEFAULT_KEY,
    corpus_text: dict | None = None,
    n: int | None = None,
) -> int:
    """Write a blank gold-labeling sheet: key cols + source text + one blank
    column per field for a human to fill with the TRUE value.

    *corpus_text* optionally maps post_id -> source text (so the labeler can read
    the post inline).  Sampling is deterministic stride sampling for spread.
    Returns the number of rows written.
    """
    items = list(records_rows.items())
    if n and n < len(items):
        stride = len(items) / n
        items = [items[int(i * stride)] for i in range(n)]

    header = list(key) + (["source_text"] if corpus_text is not None else []) + list(fields)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for k, row in items:
            line = list(k)
            if corpus_text is not None:
                pid = row.get("post_id", "")
                line.append((corpus_text.get(pid, "") or "")[:2000])
            line += ["" for _ in fields]   # blank: human fills the truth
            w.writerow(line)
    return len(items)
