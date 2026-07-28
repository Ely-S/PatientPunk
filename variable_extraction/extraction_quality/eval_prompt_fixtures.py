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
(see that file's `_description` for provenance/caveats).

Each record carries `texts`: the post's title/body segments exactly as the
production pipeline collects them (include_comments=False). Feeding anything
else -- comments included, or the segments pre-joined -- scores the model on
input the gold labels were never derived from.

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
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from patientpunk._utils import MODEL_FAST, get_llm_client, parse_json_response
from patientpunk.evaluate import score_field
from patientpunk.llm_cache import set_cache_enabled
from patientpunk.llm_extract import (
    build_field_descriptions, build_system_prompt, build_user_message, call_haiku,
    normalize_records,
)
from patientpunk.llm_schema import parse_extraction

ROOT = Path(__file__).parent
PROJECT_ROOT = ROOT.parent          # variable_extraction/ -- fixture paths are relative to it
FIXTURE_PATH = ROOT / "fixtures" / "eval_50.json"
RESULTS_DIR = ROOT / "results"
PROMPTS_DIR = ROOT / "prompts"
# Review worksheets live outside fixtures/ so nothing globbing that directory for
# evaluation sets picks up a half-finished labeling file.
REVIEW_DIR = ROOT / "review"
SEP = " | "


def _to_cell(values: list[str] | str | None) -> str:
    """Match records.csv cell format: multi-values joined with SEP."""
    if values is None:
        return ""
    if isinstance(values, str):
        return values
    return SEP.join(str(v) for v in values)


def load_variant(name: str) -> str:
    """Read a prompts/<name>.md rule overlay, dropping its markdown headings.

    A variant is an additive rule block, so an experiment is a file plus a flag
    rather than an edit to build_system_prompt -- which means two variants can be
    compared as two runs instead of two working trees.
    """
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise SystemExit(f"No such prompt variant: {path}")
    return "\n".join(
        line for line in path.read_text().splitlines() if not line.startswith("#")
    ).strip()


def _as_values(value: list[str] | str | None) -> list[str] | None:
    """A field value from either source (parsed model output, or a CSV cell)."""
    if value is None or isinstance(value, list):
        return value
    return [v.strip() for v in str(value).split(SEP) if v.strip()]


def normalize_cells(fields: dict[str, list[str] | str | None]) -> dict[str, str]:
    """Run one record's fields through the production normalization pass.

    Applies the same lowercase/dedupe/_CANONICAL_MAPS treatment a real run does,
    so scoring compares production-shaped output on both sides -- otherwise
    vocabulary variants the pipeline already canonicalizes (e.g. "CFS" ->
    "me/cfs") show up as false disagreements. Returns {field: cell}.
    """
    record = {"fields": {name: _as_values(value) for name, value in fields.items()}}
    normalize_records([record])
    return {
        name: _to_cell(data["values"])
        for name, data in record["fields"].items()
        if data.get("values")
    }


def run_one(client, system_prompt: str, post_id: str,
            texts: list[str]) -> tuple[dict[str, str], str]:
    """Call the model on one fixture post; return ({field: cell}, status).

    *texts* is the post's title/body segments as the production pipeline collects
    them; they go through build_user_message exactly as in a real run.

    Runs the same normalize_records pass (lowercase/dedupe/_CANONICAL_MAPS) that
    a real extraction run applies, so scoring reflects production output rather
    than raw model text -- otherwise vocabulary variants the pipeline already
    canonicalizes (e.g. "CFS" -> "me/cfs") show up as false DIFFs.

    A failed parse returns no cells, which scores identically to a model that
    genuinely found nothing -- hence the status, so the run can report parse
    failures separately instead of silently logging them as recall loss.
    """
    raw = call_haiku(client, system_prompt, build_user_message(texts), label=post_id)
    parsed = parse_json_response(raw)
    if parsed is None:
        return {}, "json_parse_failed"
    validated = parse_extraction(parsed)
    if validated is None:
        return {}, "schema_validation_failed"
    extraction, _dropped = validated
    return normalize_cells(dict(extraction.fields)), "ok"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fixture", type=Path, default=FIXTURE_PATH, help="Fixture JSON to evaluate against.")
    parser.add_argument("--schema", type=Path, default=None, help="Extension schema JSON; defaults to the fixture's own schema.")
    parser.add_argument("--limit", type=int, default=None, help="Only run the first N fixture records.")
    parser.add_argument("--group-guard", action="store_true", help="Enable the group-attribution guard.")
    parser.add_argument("--prompt-variant", default="", help="Comma-separated names of prompts/<name>.md rule overlays to append.")
    parser.add_argument("--no-cache", action="store_true", help="Bypass the LLM response cache (for measuring run-to-run noise).")
    parser.add_argument("--verbose", action="store_true", help="Print every field, not just mismatches.")
    parser.add_argument("--label", type=str, default="run", help="Short name for this run, used in the results filename.")
    args = parser.parse_args()

    if args.no_cache:
        set_cache_enabled(False)

    fixture = json.loads(args.fixture.read_text())
    records = fixture["records"]
    if args.limit:
        records = records[: args.limit]

    # The fixture's gold labels came from a run under a specific schema; scoring
    # under a narrower one silently drops every gold value in the extra fields.
    schema_path = args.schema or (
        PROJECT_ROOT / fixture["schema"] if fixture.get("schema") else None
    )
    schema = json.loads(schema_path.read_text()) if schema_path else None
    field_descriptions = build_field_descriptions(schema)
    variants = [v.strip() for v in args.prompt_variant.split(",") if v.strip()]
    system_prompt = build_system_prompt(
        field_descriptions,
        group_guard=args.group_guard,
        extra_rules=[load_variant(v) for v in variants],
    )
    prompt_sha = hashlib.sha256(system_prompt.encode()).hexdigest()[:12]

    print(f"Model: {MODEL_FAST}   Label: {args.label}")
    print(f"Fixture: {args.fixture.name} ({len(records)} records)   "
          f"Schema: {schema_path.name if schema_path else 'base fields only'}   "
          f"Prompt: {prompt_sha}"
          f"{'   Variants: ' + ','.join(variants) if variants else ''}\n")

    client = get_llm_client()

    all_fields = sorted(field_descriptions)
    pairs_by_field: dict[str, list[tuple[str, str]]] = {f: [] for f in all_fields}
    mismatches: list[tuple[str, str, str, str, str]] = []  # post_id, field, gold, candidate, kind

    parse_failures: list[dict[str, str]] = []

    for i, rec in enumerate(records, 1):
        post_id, gold = rec["post_id"], rec["gold"]
        print(f"[{i}/{len(records)}] {post_id}...", flush=True)
        candidate, status = run_one(client, system_prompt, post_id, rec["texts"])
        if status != "ok":
            print(f"    !! {status} -- scored as empty", flush=True)
            parse_failures.append({"post_id": post_id, "status": status})

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

    if parse_failures:
        print(f"\n=== Parse failures ({len(parse_failures)}) ===")
        for pf in parse_failures:
            print(f"  {pf['post_id']}: {pf['status']}")

    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"{timestamp}__{args.label}.json"
    out_path.write_text(json.dumps({
        "timestamp": timestamp,
        "label": args.label,
        "model": MODEL_FAST,
        "fixture": args.fixture.name,
        "schema": str(schema_path) if schema_path else None,
        "group_guard": args.group_guard,
        "prompt_variants": variants,
        "cache": not args.no_cache,
        "prompt_sha": prompt_sha,
        "system_prompt": system_prompt,
        "n_records": len(records),
        "parse_failures": parse_failures,
        "field_scores": field_scores,
        "mismatches": [
            {"post_id": p, "field": f, "gold": g, "candidate": c, "kind": k}
            for p, f, g, c, k in mismatches
        ],
    }, indent=2, ensure_ascii=False))
    print(f"\nSaved: {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
