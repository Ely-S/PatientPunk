#!/usr/bin/env python3
"""Build the human review sheet for the v2 psychedelic extraction (GATE 4).

Reads the pinned v2 probe database READ-ONLY and writes a stratified sample of
extracted records, each with its cited quotes and full source window, plus
empty scoring columns for a human reviewer. The protocol and rubric are in
docs/validation_protocol.md.

The output is quote-bearing and belongs under data/ (gitignored). Author hashes
and Reddit IDs are used only in memory, to cap rows per account, and are never
written.

Usage:
    uv run python scripts/build_validation_sample.py
    uv run python scripts/build_validation_sample.py --db data/probes/psychedelic_pharmacology.db \
        --out data/validation/psychedelics_v2_sample.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "studies/psychedelics/v2"))
from psychedelics_v2 import classify_symptom, symptom_labels  # noqa: E402

V2_RUN_ID = "710567555e22b68c025d8ceb1c3373564d7f9b01dcc5fe94b02b7c3209ecbc05"
SEED = 20261002
MAX_PER_ACCOUNT = 2

# (name, size or None for "all eligible", eligibility predicate). Order matters:
# a record is assigned to the first stratum that samples it, so the sheet never
# asks a reviewer to score the same record twice.
FATIGUE = {"fatigue_general", "low_energy"}
STRATA = (
    ("fatigue_ketamine", 40,
     lambda r: r["record_type"] == "effect" and r["drug"] == "ketamine"
     and FATIGUE & set(r["labels"])),
    ("fatigue_psilocybin_lsd", 20,
     lambda r: r["record_type"] == "effect" and r["drug"] in ("psilocybin", "lsd")
     and FATIGUE & set(r["labels"])),
    ("pem_explicit", None,
     lambda r: r["record_type"] == "effect" and "pem_explicit" in r["labels"]),
    ("severe_adverse_event", 40,
     lambda r: r["record_type"] == "adverse_event" and r["ae_severity"] == "severe"),
    ("random_helped", 30,
     lambda r: r["record_type"] == "effect" and r["direction"] == "helped"),
    ("random_excluded", 30,
     lambda r: r["record_type"] == "claim" and not r["included"]),
)

SCORE_COLUMNS = (
    "quote_supports_field", "drug_attribution", "self_actual_use", "direction",
    "symptom_class_matches_meaning", "ae_category", "ae_severity", "dose", "duration",
)
# Not correct/incorrect: does the effect's target describe post-exertional
# malaise (yes / no / unclear)? Answers the PEM dilution and undercount questions.
PEM_COLUMN = "describes_pem"

COLUMNS = (
    "row_id", "stratum", "drug", "record_type", "claim_id", "record_index",
    "included", "subject", "exposure_status", "adverse_event_status",
    "direction", "confidence", "magnitude", "magnitude_basis",
    "symptom_target", "symptom_class", "symptom_labels",
    "ae_category", "ae_raw_event", "ae_severity",
    "duration_bin", "duration_raw", "doses",
    "field_quote", "subject_quote", "exposure_status_quote", "exposure_quote",
    "adverse_event_status_quote", "duration_quote", "dose_quotes",
    "source_type", "source_window_text",
    *SCORE_COLUMNS, PEM_COLUMN, "notes", "seed", "run_id",
)


def _dose_summary(doses: list[dict]) -> str:
    keys = ("raw_text", "amount_lower", "amount_upper", "unit", "route", "formulation",
            "frequency_schedule", "treatment_context", "author_stated_intent")
    return json.dumps([{k: d[k] for k in keys if d.get(k) is not None} for d in doses],
                      ensure_ascii=False) if doses else ""


def load_records(db: Path, run_id: str) -> list[dict]:
    """Every effect, adverse-event and claim record of one run, with its evidence."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        if not con.execute("SELECT 1 FROM probe_run WHERE run_id = ?", (run_id,)).fetchone():
            raise SystemExit(f"run {run_id} is not in {db}")
        rows = con.execute(
            """SELECT c.claim_id, c.included, c.values_json, c.evidence_json,
                      u.target, u.author_hash, w.source_type, w.text
               FROM claim c
               JOIN unit u ON u.run_id = c.run_id AND u.unit_key = c.unit_key
               JOIN source_window w ON w.run_id = c.run_id AND w.unit_key = c.unit_key
                    AND w.source_window_id = c.source_window_id
               WHERE c.run_id = ? ORDER BY c.claim_id""",
            (run_id,),
        ).fetchall()
    finally:
        con.close()

    records = []
    for claim_id, included, values_json, evidence_json, drug, author, source_type, text in rows:
        v = json.loads(values_json)
        quotes = {e["field_path"]: e["quote"] for e in json.loads(evidence_json)}
        base = {
            "claim_id": claim_id, "drug": drug, "author": author,
            "included": bool(included), "subject": v["subject"],
            "exposure_status": v["exposure_status"],
            "adverse_event_status": v["adverse_event_status"],
            "doses": _dose_summary(v["doses"]),
            "has_dose": bool(v["doses"]),
            "subject_quote": quotes.get("subject", ""),
            "exposure_status_quote": quotes.get("exposure_status", ""),
            "exposure_quote": quotes.get("exposure", ""),
            "adverse_event_status_quote": quotes.get("adverse_event_status", ""),
            "dose_quotes": json.dumps(
                [quotes[f"doses[{i}]"] for i in range(len(v["doses"]))], ensure_ascii=False
            ) if v["doses"] else "",
            "source_type": source_type, "source_window_text": text,
            "labels": (), "direction": None, "ae_severity": None,
        }
        records.append(base | {"record_type": "claim", "record_index": "",
                               "field_quote": quotes.get("exposure_status", "")})
        for i, e in enumerate(v["effects"]):
            duration = e.get("duration") or {}
            records.append(base | {
                "record_type": "effect", "record_index": i,
                "direction": e["direction"], "confidence": e["confidence"],
                "magnitude": e.get("magnitude_0_10"), "magnitude_basis": e.get("magnitude_basis"),
                "symptom_target": e.get("target", ""),
                "symptom_class": classify_symptom(e.get("target")),
                "labels": symptom_labels(e.get("target")),
                "duration_bin": duration.get("normalized"), "duration_raw": duration.get("raw_text"),
                "field_quote": quotes.get(f"effects[{i}]", ""),
                "duration_quote": quotes.get(f"effects[{i}].duration", ""),
            })
        for i, a in enumerate(v["adverse_events"]):
            duration = a.get("duration") or {}
            records.append(base | {
                "record_type": "adverse_event", "record_index": i,
                "confidence": a["confidence"], "ae_category": a["category"],
                "ae_raw_event": a["raw_event"], "ae_severity": a.get("severity"),
                "duration_bin": duration.get("normalized"), "duration_raw": duration.get("raw_text"),
                "field_quote": quotes.get(f"adverse_events[{i}]", ""),
                "duration_quote": quotes.get(f"adverse_events[{i}].duration", ""),
            })
    return records


def sample(records: list[dict], seed: int) -> list[dict]:
    """Stratified sample, at most MAX_PER_ACCOUNT rows per account per stratum."""
    rng = random.Random(seed)
    taken: set[tuple] = set()
    out = []
    for name, size, eligible in STRATA:
        pool = [r for r in records
                if eligible(r) and (r["claim_id"], r["record_type"], r["record_index"]) not in taken]
        rng.shuffle(pool)
        per_account: dict[str, int] = {}
        chosen = []
        for r in pool:
            if size is not None and len(chosen) >= size:
                break
            if per_account.get(r["author"], 0) >= MAX_PER_ACCOUNT:
                continue
            per_account[r["author"]] = per_account.get(r["author"], 0) + 1
            chosen.append(r)
        for r in chosen:
            taken.add((r["claim_id"], r["record_type"], r["record_index"]))
            out.append(r | {"stratum": name, "eligible_in_stratum": len(pool)})
    return out


def _prefill(r: dict) -> dict:
    """`n/a` where a scoring column cannot apply, so a blank always means unscored."""
    na = "n/a"
    effect, ae = r["record_type"] == "effect", r["record_type"] == "adverse_event"
    return {
        "quote_supports_field": "",
        "drug_attribution": "",
        "self_actual_use": "",
        "direction": "" if effect else na,
        "symptom_class_matches_meaning": "" if effect and r.get("symptom_target") else na,
        "ae_category": "" if ae else na,
        "ae_severity": "" if ae and r.get("ae_severity") else na,
        "dose": "" if r["has_dose"] and r["included"] else na,
        "duration": "" if r.get("duration_bin") else na,
        PEM_COLUMN: "" if effect else na,
    }


def write_sheet(rows: list[dict], out: Path, seed: int, run_id: str) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for n, r in enumerate(rows, 1):
            row = {k: r.get(k) for k in COLUMNS} | _prefill(r)
            row |= {"row_id": n, "symptom_labels": "|".join(r["labels"]),
                    "notes": "", "seed": seed, "run_id": run_id}
            w.writerow({k: "" if v is None else v for k, v in row.items()})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", type=Path, default=HERE / "data/probes/psychedelic_pharmacology.db")
    ap.add_argument("--run-id", default=V2_RUN_ID)
    ap.add_argument("--out", type=Path, default=HERE / "data/validation/psychedelics_v2_sample.csv")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    rows = sample(load_records(args.db, args.run_id), args.seed)
    write_sheet(rows, args.out, args.seed, args.run_id)

    counts: dict[str, list[int]] = {}
    for r in rows:
        counts.setdefault(r["stratum"], [0, r["eligible_in_stratum"]])[0] += 1
    manifest = {
        "run_id": args.run_id, "seed": args.seed, "max_per_account": MAX_PER_ACCOUNT,
        "db_sha256": hashlib.sha256(args.db.read_bytes()).hexdigest(),
        "rows": len(rows),
        "strata": {k: {"sampled": s, "eligible": e} for k, (s, e) in counts.items()},
    }
    args.out.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
