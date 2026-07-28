#!/usr/bin/env python3
"""Classify a run's mismatches into a failure taxonomy, so prompt work is aimed.

A results file says *that* 22 cells disagreed. It cannot say whether the model
hallucinated, or the pipeline's vocabulary map is missing an alias, or the gold
label is simply wrong -- three problems with three different fixes, only one of
which is the prompt. Before this script, that distinction was made by reading
mismatches by hand and remembering; the `me/cfs` DIFFs in TRACKER.md burned a
round of prompt speculation on what turned out to be a scoring artifact.

Each mismatch is shown to a judge model together with the source text and gets
one code from TAXONOMY. The output is a field x code matrix: the biggest
*actionable* cell is the next thing to fix.

Usage:
    python triage.py results/20260728T034411Z__baseline-v2.json
    python triage.py results/<run>.json --propose-gold-fixes    # emit a review file
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from eval_prompt_fixtures import RESULTS_DIR, REVIEW_DIR, ROOT
from patientpunk import llm_extract
from patientpunk._utils import get_llm_client, parse_json_response
from patientpunk.llm_extract import build_field_descriptions, call_haiku

PROJECT_ROOT = ROOT.parent
DEFAULT_JUDGE = "anthropic/claude-opus-5"

# code -> (what it means, where the fix belongs)
TAXONOMY = {
    "omission":         ("The value is stated in the text and in gold, and the candidate missed it.", "prompt/model"),
    "hallucination":    ("The candidate's value has no basis anywhere in the text.", "prompt"),
    "inference":        ("The candidate's value is a reasonable reading but is not explicitly stated.", "prompt"),
    "over_attribution": ("The candidate attributed to the author something the text ascribes to someone else.", "prompt"),
    "field_bleed":      ("The value is correct but belongs in a different field (symptom filed as condition, medication as alternative_treatment).", "prompt"),
    "format_violation": ("The value breaks a stated format rule: over 5 words, wrong 'drug: outcome: symptom' shape, a functional_status_tier outside the enum.", "prompt"),
    "vocab_variant":    ("Both sides mean the same thing in different words ('covid' vs 'covid-19', 'CFS' vs 'me/cfs').", "normalize.py"),
    "granularity":      ("Same fact at a different precision or unit ('4.5 mg' vs '4.5mg', '3 years' vs '36 months').", "normalize.py / scorer"),
    "gold_wrong":       ("The candidate is right and the gold label is wrong or incomplete for this field.", "fixture"),
    "unclear":          ("The text genuinely supports neither side over the other.", "none"),
}

JUDGE_PROMPT = """You are auditing a biomedical information extraction system.

You are given a patient-authored Reddit post, one extraction field, the GOLD label
for that field, and the CANDIDATE value the system produced. They disagree. Your job
is to say WHY, using exactly one of the codes below.

Judge only against what the text actually says. Gold is not authoritative: it was
itself produced by models and may be wrong or incomplete -- if the candidate is
right and gold is not, the code is gold_wrong.

CODES:
{codes}

Respond with valid JSON only:
{{"code": "<one code>", "reason": "<one sentence, under 20 words>"}}"""


def build_judge_prompt() -> str:
    codes = "\n".join(f"- {code}: {meaning}" for code, (meaning, _) in TAXONOMY.items())
    return JUDGE_PROMPT.format(codes=codes)


def judge_one(client, system_prompt: str, mismatch: dict, text: str,
              field_description: str) -> dict:
    user = (
        f"POST TEXT:\n{text}\n\n"
        f"FIELD: {mismatch['field']}\n"
        f"FIELD DEFINITION: {field_description}\n"
        f"GOLD: {mismatch['gold'] or '(empty)'}\n"
        f"CANDIDATE: {mismatch['candidate'] or '(empty)'}\n"
    )
    raw = call_haiku(client, system_prompt, user, label=f"{mismatch['post_id']}/{mismatch['field']}")
    parsed = parse_json_response(raw) or {}
    code = parsed.get("code")
    if code not in TAXONOMY:
        # An unrecognized code is a judge failure, not a finding; keep it visible
        # rather than silently folding it into a real category.
        return {**mismatch, "code": "unclassified", "reason": f"judge returned {code!r}"}
    return {**mismatch, "code": code, "reason": parsed.get("reason", "")}


def print_matrix(triaged: list[dict]) -> None:
    by_field: dict[str, Counter] = defaultdict(Counter)
    totals: Counter = Counter()
    for t in triaged:
        by_field[t["field"]][t["code"]] += 1
        totals[t["code"]] += 1

    codes = [c for c, _ in totals.most_common()]
    if not codes:
        print("No mismatches to triage.")
        return

    width = max(len(f) for f in by_field) + 2
    print("\n=== Field x failure code ===")
    print(" " * width + "".join(f"{c[:14]:>16}" for c in codes))
    for field in sorted(by_field, key=lambda f: -sum(by_field[f].values())):
        row = "".join(f"{by_field[field][c] or '':>16}" for c in codes)
        print(f"{field:<{width}}{row}")
    print(f"{'TOTAL':<{width}}" + "".join(f"{totals[c]:>16}" for c in codes))

    print("\n=== Where each code's fix belongs ===")
    for code, n in totals.most_common():
        where = TAXONOMY.get(code, ("", "judge failure"))[1]
        print(f"  {n:>3}  {code:<18} -> {where}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results", type=Path, help="A results/*.json file from eval_prompt_fixtures.py.")
    parser.add_argument("--judge", default=DEFAULT_JUDGE, help="Model used to classify mismatches.")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--propose-gold-fixes", action="store_true",
                        help="Write gold_wrong cells to a review file for label_fixture.py --apply.")
    args = parser.parse_args()

    run = json.loads(args.results.read_text())
    fixture = json.loads((ROOT / "fixtures" / run["fixture"]).read_text())
    by_id = {r["post_id"]: r for r in fixture["records"]}
    schema = json.loads((PROJECT_ROOT / fixture["schema"]).read_text())
    field_descriptions = build_field_descriptions(schema)

    mismatches = run["mismatches"]
    print(f"Triaging {len(mismatches)} mismatches from {args.results.name} with {args.judge}\n")

    llm_extract.MODEL = args.judge
    client = get_llm_client()
    system_prompt = build_judge_prompt()

    def work(m: dict) -> dict:
        record = by_id[m["post_id"]]
        return judge_one(client, system_prompt, m, "\n\n".join(record["texts"]),
                         field_descriptions.get(m["field"], m["field"]))

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        triaged = list(pool.map(work, mismatches))

    print_matrix(triaged)

    out_path = RESULTS_DIR / f"{args.results.stem}__triage.json"
    out_path.write_text(json.dumps({
        "results_file": args.results.name,
        "judge": args.judge,
        "counts": dict(Counter(t["code"] for t in triaged)),
        "triaged": triaged,
    }, indent=2, ensure_ascii=False) + "\n")
    print(f"\nSaved: {out_path.relative_to(ROOT)}")

    if args.propose_gold_fixes:
        proposals = [
            {"post_id": t["post_id"], "field": t["field"], "labeler": t["candidate"],
             "production": t["gold"], "resolved": t["candidate"], "_reason": t["reason"]}
            for t in triaged if t["code"] == "gold_wrong"
        ]
        review_path = REVIEW_DIR / f"review_{args.results.stem}_goldfix.json"
        review_path.write_text(json.dumps({
            "fixture": run["fixture"],
            "_instructions": (
                "Proposed gold corrections from triage. `resolved` is PRE-FILLED with the "
                "candidate value -- read each post and set it to null to reject, or edit it. "
                "Accepting a fix on faith lets the model rewrite its own exam. Then: "
                f"python label_fixture.py --fixture {run['fixture']} --apply {review_path.name}"
            ),
            "disagreements": proposals,
        }, indent=2, ensure_ascii=False) + "\n")
        print(f"{len(proposals)} proposed gold fixes -> {review_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
