#!/usr/bin/env python3
"""Label the fixture's unlabeled records by two-model adjudication.

Hand-labeling 21 fields x 30 records from source text is the gold standard and
was not affordable. This is the honest substitute:

    1. Label each record with a STRONG model (--labeler, default
       anthropic/claude-opus-5) using the live prompt and the fixture's schema.
    2. Take the PRODUCTION model's labels for the same post from the extraction
       run recorded in `baseline_extracted`.
    3. Both sides go through normalize_records, then per field:
         - identical value sets  -> `gold`, with gold_source "agreed"
         - anything else         -> left unlabeled, written to a review file

Two independent models landing on the same value set is weak evidence, but it is
*independent* evidence, and it concentrates the human effort on the cells where
the models actually disagree -- typically a fifth of them. What it cannot catch
is a value BOTH models missed, so recall against omissions stays the weakest
axis of any score computed from this fixture. Say so wherever the score is
reported; do not quietly call these labels gold.

Usage:
    # pass 1 -- label, write disagreements for review
    python label_fixture.py --fixture fixtures/eval_50.json

    # pass 2 -- fold reviewed decisions back in
    python label_fixture.py --fixture fixtures/eval_50.json --apply review/review_<ts>.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from eval_prompt_fixtures import SEP, normalize_cells, run_one
from patientpunk import llm_extract
from patientpunk._utils import get_llm_client
from patientpunk.llm_extract import build_field_descriptions, build_system_prompt

ROOT = Path(__file__).parent
PROJECT_ROOT = ROOT.parent
# Review files live outside fixtures/ so nothing globbing that directory for
# evaluation sets picks up a half-finished labeling worksheet.
REVIEW_DIR = ROOT / "review"
DEFAULT_LABELER = "anthropic/claude-opus-5"


def _values(cell: str) -> set[str]:
    return {v.strip().lower() for v in cell.split(SEP) if v.strip()}


def apply_review(fixture_path: Path, review_path: Path) -> None:
    """Fold a reviewed disagreement file back into the fixture as gold."""
    fixture = json.loads(fixture_path.read_text())
    review = json.loads(review_path.read_text())
    by_id = {r["post_id"]: r for r in fixture["records"]}

    applied = skipped = 0
    for item in review["disagreements"]:
        resolved = item.get("resolved")
        if resolved is None:
            skipped += 1
            continue
        rec = by_id[item["post_id"]]
        values = [v.strip() for v in resolved.split(SEP) if v.strip()]
        if values:
            rec["gold"][item["field"]] = values
        else:
            rec["gold"].pop(item["field"], None)
        rec["gold_source"][item["field"]] = "adjudicated"
        applied += 1

    fixture_path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n")
    print(f"Applied {applied} adjudicated cells; {skipped} still unresolved.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fixture", type=Path, default=ROOT / "fixtures" / "eval_50.json")
    parser.add_argument("--labeler", default=DEFAULT_LABELER,
                        help="Strong model used as the independent second opinion.")
    parser.add_argument("--apply", type=Path, default=None,
                        help="A review file whose `resolved` cells become adjudicated gold.")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if args.apply:
        apply_review(args.fixture, args.apply)
        return

    fixture = json.loads(args.fixture.read_text())
    schema = json.loads((PROJECT_ROOT / fixture["schema"]).read_text())
    field_descriptions = build_field_descriptions(schema)
    system_prompt = build_system_prompt(field_descriptions)

    todo = [r for r in fixture["records"] if not r["gold"]]
    if args.limit:
        todo = todo[: args.limit]
    print(f"Labeling {len(todo)} records with {args.labeler}\n")

    # call_haiku reads the module-level MODEL; point it at the strong labeler for
    # this script only. The cache key includes the model, so this cannot collide
    # with cached production-model replies for the same prompt.
    llm_extract.MODEL = args.labeler
    client = get_llm_client()

    disagreements: list[dict] = []
    n_agreed = 0
    for i, rec in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {rec['post_id']}...", flush=True)
        strong, status = run_one(client, system_prompt, rec["post_id"], rec["texts"])
        if status != "ok":
            print(f"    !! labeler {status} -- skipping record", flush=True)
            continue
        production = normalize_cells(rec["baseline_extracted"])

        for field in field_descriptions:
            s_cell, p_cell = strong.get(field, ""), production.get(field, "")
            if _values(s_cell) == _values(p_cell):
                if s_cell:
                    rec["gold"][field] = [v.strip() for v in s_cell.split(SEP) if v.strip()]
                    rec["gold_source"][field] = "agreed"
                    n_agreed += 1
                # Both empty: no label recorded. An agreed absence is exactly the
                # case two models are most likely to share a blind spot on, so it
                # is not evidence the field is genuinely absent.
            else:
                disagreements.append({
                    "post_id": rec["post_id"],
                    "field": field,
                    "labeler": s_cell,
                    "production": p_cell,
                    "resolved": None,   # reviewer fills: the correct cell, or "" for none
                })

    args.fixture.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    review_path = REVIEW_DIR / f"review_{timestamp}.json"
    review_path.write_text(json.dumps({
        "timestamp": timestamp,
        "fixture": args.fixture.name,
        "labeler": args.labeler,
        "_instructions": (
            "For each entry read the post's `texts` in the fixture and set `resolved` "
            "to the correct cell value (values joined with ' | '), or \"\" if the field "
            "should be empty. Leave null to skip. Then: "
            f"python label_fixture.py --fixture {args.fixture.name} --apply {review_path.name}"
        ),
        "disagreements": disagreements,
    }, indent=2, ensure_ascii=False) + "\n")

    print(f"\n{n_agreed} cells agreed -> gold")
    print(f"{len(disagreements)} disagreements -> {review_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
