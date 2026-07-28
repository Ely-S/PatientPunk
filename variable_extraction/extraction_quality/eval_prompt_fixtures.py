#!/usr/bin/env python3
"""Prompt-iteration harness: run the real extraction prompt against a fixed
20-post fixture set and score it against hand-corrected gold labels.

This makes real LLM API calls (via patientpunk.llm_extract), so it's a script,
not a pytest test. The loop it supports:

    1. Edit BASE_FIELD_DESCRIPTIONS / build_system_prompt in llm_extract.py
    2. python eval_prompt_fixtures.py
    3. Check per-field precision/recall and the printed mismatches
    4. Repeat

Fixture: fixtures/spotcheck_20.json -- 20 real posts sampled from the
deepseek-v4-flash 10k run reviewed in PR #92, with a `gold` field per record
that corrects the baseline extraction where a spot-check found it wrong
(see that file's `_description` and inline comments for provenance/caveats).

Model/config selection: this always calls patientpunk.llm_extract with
whatever prompt/model is currently active there, controlled by the same env
vars as a real run (MODEL_FAST, LLM_PROVIDER, LLM_TEMPERATURE, ...; see
patientpunk/_utils.py). To compare models or configs, set the env var and
pass a distinct --label; to compare prompts, edit build_system_prompt in
llm_extract.py directly -- there's one live prompt, not forked copies of it.

Usage:
    python eval_prompt_fixtures.py --label baseline           # base fields
    python eval_prompt_fixtures.py --schema schemas/covidlonghaulers_schema.json
    python eval_prompt_fixtures.py --limit 5                  # first 5 fixture records
    MODEL_FAST=deepseek/deepseek-v3.2 python eval_prompt_fixtures.py --label deepseek-v3.2

Each run is saved to results/<timestamp>__<label>.json so TRACKER.md rows can
reference the exact scores and mismatches later.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from patientpunk._utils import MODEL_FAST, get_llm_client, parse_json_response
from patientpunk.evaluate import score_field
from patientpunk.llm_extract import (
    build_field_descriptions, build_system_prompt, build_user_message, call_haiku,
    normalize_records,
)
from patientpunk.llm_schema import parse_extraction

ROOT = Path(__file__).parent
FIXTURE_PATH = ROOT / "fixtures" / "spotcheck_20.json"
RESULTS_DIR = ROOT / "results"
SEP = " | "


def _to_cell(values: list[str] | str | None) -> str:
    """Match records.csv cell format: multi-values joined with SEP."""
    if values is None:
        return ""
    if isinstance(values, str):
        return values
    return SEP.join(str(v) for v in values)


def run_one(client, system_prompt: str, post_id: str, text: str) -> dict[str, str]:
    """Call the model on one fixture post; return {field: cell} like a CSV row.

    Runs the same normalize_records pass (lowercase/dedupe/_CANONICAL_MAPS) that
    a real extraction run applies, so scoring reflects production output rather
    than raw model text -- otherwise vocabulary variants the pipeline already
    canonicalizes (e.g. "CFS" -> "me/cfs") show up as false DIFFs.
    """
    raw = call_haiku(client, system_prompt, build_user_message([text]), label=post_id)
    parsed = parse_json_response(raw)
    if parsed is None:
        return {}
    validated = parse_extraction(parsed)
    if validated is None:
        return {}
    extraction, _dropped = validated
    fake_record = {"fields": dict(extraction.fields)}
    normalize_records([fake_record])
    return {
        name: _to_cell(field_data["values"])
        for name, field_data in fake_record["fields"].items()
        if field_data.get("values")
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--schema", type=Path, default=None, help="Extension schema JSON (as in llm_extract.py).")
    parser.add_argument("--limit", type=int, default=None, help="Only run the first N fixture records.")
    parser.add_argument("--group-guard", action="store_true", help="Enable the group-attribution guard.")
    parser.add_argument("--verbose", action="store_true", help="Print every field, not just mismatches.")
    parser.add_argument("--label", type=str, default="run", help="Short name for this run, used in the results filename.")
    args = parser.parse_args()

    print(f"Model: {MODEL_FAST}   Label: {args.label}\n")

    schema = json.loads(args.schema.read_text()) if args.schema else None
    field_descriptions = build_field_descriptions(schema)
    system_prompt = build_system_prompt(field_descriptions, group_guard=args.group_guard)

    fixture = json.loads(FIXTURE_PATH.read_text())
    records = fixture["records"]
    if args.limit:
        records = records[: args.limit]

    client = get_llm_client()

    all_fields = sorted(field_descriptions)
    pairs_by_field: dict[str, list[tuple[str, str]]] = {f: [] for f in all_fields}
    mismatches: list[tuple[str, str, str, str, str]] = []  # post_id, field, gold, candidate, kind

    for i, rec in enumerate(records, 1):
        post_id, text, gold = rec["post_id"], rec["text"], rec["gold"]
        print(f"[{i}/{len(records)}] {post_id}...", flush=True)
        candidate = run_one(client, system_prompt, post_id, text)

        for field in all_fields:
            gold_cell = _to_cell(gold.get(field))
            cand_cell = candidate.get(field, "")
            pairs_by_field[field].append((gold_cell, cand_cell))
            gold_set = {v.strip().lower() for v in gold_cell.split(SEP) if v.strip()}
            cand_set = {v.strip().lower() for v in cand_cell.split(SEP) if v.strip()}
            if gold_set != cand_set:
                if not gold_set:
                    kind = "EXTRA"  # gold has nothing here -- may be a real find, not a bug
                elif not cand_set:
                    kind = "MISS"   # candidate dropped something gold has
                else:
                    kind = "DIFF"   # both non-empty, values disagree
                mismatches.append((post_id, field, gold_cell, cand_cell, kind))
            elif args.verbose and gold_set:
                print(f"    OK  {field}: {gold_cell}")

    print("\n=== Per-field scores (candidate vs gold) ===")
    header = f"{'field':<28}{'precision':>10}{'recall':>10}{'f1':>8}{'agreement':>11}{'gold_fill':>11}{'cand_fill':>11}"
    print(header)
    field_scores: dict[str, dict] = {}
    for field in all_fields:
        pairs = pairs_by_field[field]
        if not any(g or c for g, c in pairs):
            continue
        s = score_field(pairs, SEP)
        field_scores[field] = s
        print(
            f"{field:<28}{s['precision']:>10.3f}{s['recall']:>10.3f}{s['f1']:>8.3f}"
            f"{s['agreement_present']:>11.3f}{s['ref_fill']:>11}{s['cand_fill']:>11}"
        )

    print(f"\n=== Mismatches ({len(mismatches)}) ===")
    print(
        "MISS = gold has a value the candidate dropped (regression). "
        "DIFF = both have a value but disagree (check which is right). "
        "EXTRA = candidate found something gold doesn't have -- gold is only "
        "corrected on 7/20 records' flagged fields, so this may be a genuine "
        "improvement rather than a bug; verify against the source text before "
        "treating it as wrong.\n"
    )
    for post_id, field, gold_cell, cand_cell, kind in mismatches:
        print(f"  [{kind}] {post_id} / {field}")
        print(f"      gold:      {gold_cell or '(empty)'}")
        print(f"      candidate: {cand_cell or '(empty)'}")

    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"{timestamp}__{args.label}.json"
    out_path.write_text(json.dumps({
        "timestamp": timestamp,
        "label": args.label,
        "model": MODEL_FAST,
        "schema": str(args.schema) if args.schema else None,
        "group_guard": args.group_guard,
        "n_records": len(records),
        "field_scores": field_scores,
        "mismatches": [
            {"post_id": p, "field": f, "gold": g, "candidate": c, "kind": k}
            for p, f, g, c, k in mismatches
        ],
    }, indent=2, ensure_ascii=False))
    print(f"\nSaved: {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
