"""
run_j1_alias.py — Judgement 1 (alias generation): roster run + dual-truth scoring.

This is the ARCHETYPE factual-judgement test — the template the other five factual
judgements (②③⑨⑩⑪) reuse. It does exactly what the Eli/Shaun design settled on:

  1. Run the judgement (alias generation, `drug_aliases_prompt`) across the model roster.
  2. Score each model's output for CORRECTNESS against TWO truth sources:
       - RxNorm  — external, objective, but only the FORMAL aliases (brand/generic).
       - Opus-as-judge — reads each alias and rules valid/invalid; catches the informal
         aliases (LDN, typos) RxNorm lacks AND the wrong-drug hallucinations RxNorm
         can't flag. Verification, not generation.
  3. Cross-check the judge itself: where RxNorm confirms an alias, Opus should agree —
     disagreement means the judge is suspect. (RxNorm validates Opus-as-truth.)
  4. Record every model's alias list (K repeats) so the notebook computes cross-model
     divergence (Jaccard) and within-model variability.

Opus is the source of truth, NEVER a candidate. Agreement between the cheap models is a
divergence diagnostic, never the correctness verdict (Eli's core correction).

Output: data/validation/j1_alias_runs.json  {manifest, generations[], judge[], rxnorm{}}

Usage:
    python scripts/run_j1_alias.py --k 5 --models claude-sonnet-4-6 claude-haiku-4-5-20251001
    (full roster once OpenRouter credits are restored — pass --models with the roster slugs)
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from utilities import get_client, llm_call, parse_json_array, LLMParseError, LLM_TEMPERATURE
from prompts.intervention_config import drug_aliases_prompt

OUT_DIR = ROOT / "data" / "validation"

# Corpus-grounded targets: real long-COVID / MCAS treatments with known brand names,
# plus one supplement (nattokinase) RxNorm does not cover — to expose the RxNorm gap
# that Opus-judge has to carry.
DRUGS = [
    "famotidine", "cetirizine", "loratadine", "fexofenadine", "levocetirizine",
    "naltrexone", "montelukast", "fluvoxamine", "propranolol", "gabapentin",
    "amitriptyline", "metformin", "sertraline", "duloxetine", "colchicine", "nattokinase",
]


# ── RxNorm (external truth source) ────────────────────────────────────────────
def _rx(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "patientpunk-validation"})
    return json.load(urllib.request.urlopen(req, timeout=20))


def rxnorm_names(drug: str) -> dict:
    """Return {all: [...], brand: [...]} of RxNorm names for a drug, or empty if uncovered."""
    try:
        j = _rx(f"https://rxnav.nlm.nih.gov/REST/rxcui.json?name={urllib.parse.quote(drug)}&search=1")
        ids = j.get("idGroup", {}).get("rxnormId", [])
        if not ids:
            return {"all": [], "brand": [], "covered": False}
        rel = _rx(f"https://rxnav.nlm.nih.gov/REST/rxcui/{ids[0]}/related.json?tty=IN+BN+PIN")
        all_names, brand = set(), set()
        for g in rel.get("relatedGroup", {}).get("conceptGroup", []):
            tty = g.get("tty", "")
            for cp in g.get("conceptProperties", []):
                nm = cp["name"].lower().strip()
                all_names.add(nm)
                if tty == "BN":
                    brand.add(nm)
        return {"all": sorted(all_names), "brand": sorted(brand), "covered": True}
    except Exception as e:
        return {"all": [], "brand": [], "covered": False, "error": f"{type(e).__name__}: {e}"}


# ── Alias generation (the judgement under test) ───────────────────────────────
def generate_aliases(client, model: str, drug: str) -> list[str]:
    """One alias-generation call for a model+drug (bypasses the on-disk cache)."""
    try:
        raw = llm_call(client, drug_aliases_prompt(drug), model=model, max_tokens=2000)
        return sorted({a.lower().strip() for a in parse_json_array(raw) if a and a.strip()})
    except LLMParseError:
        return []


# ── Opus-as-judge (truth source that grades informal aliases + hallucinations) ─
JUDGE_PROMPT = """You validate whether names are correct aliases for a specific drug or supplement.

Drug/supplement: {drug}

A model listed the following as aliases (generic name, brand names, standard abbreviations,
or plausible misspellings) for "{drug}":
{numbered}

For EACH, decide:
- "valid": a real, correct way to refer to {drug} — its generic name, a real brand name, a
  standard abbreviation (e.g. LDN for low-dose naltrexone), or a plausible misspelling of one.
- "invalid": NOT a correct reference to {drug} — a different drug, a drug class, an unrelated
  term, or an invented name.

Return ONLY a JSON array of {n} objects in the same order:
[{{"alias": "...", "verdict": "valid"}}, ...]"""


def opus_judge(client, judge_model: str, drug: str, aliases: list[str]) -> dict:
    """Ask the judge to rule valid/invalid on each alias. Returns {alias: verdict}."""
    if not aliases:
        return {}
    numbered = "\n".join(f"{i+1}. {a}" for i, a in enumerate(aliases))
    prompt = JUDGE_PROMPT.format(drug=drug, numbered=numbered, n=len(aliases))
    try:
        raw = llm_call(client, prompt, model=judge_model, max_tokens=40 * len(aliases) + 200)
        verdicts = parse_json_array(raw)
        out = {}
        for a, v in zip(aliases, verdicts):
            out[a] = "valid" if str(v.get("verdict", "")).lower().startswith("valid") else "invalid"
        # any aliases the judge dropped -> mark unknown->invalid conservatively
        for a in aliases:
            out.setdefault(a, "invalid")
        return out
    except (LLMParseError, Exception):
        # per-alias fallback would be costly; mark the whole set as ungraded
        return {a: "ungraded" for a in aliases}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drugs", nargs="+", default=DRUGS)
    ap.add_argument("--models", nargs="+",
                    default=["claude-sonnet-4-6", "claude-haiku-4-5-20251001"])
    ap.add_argument("--judge", default="claude-opus-4-8")
    ap.add_argument("--k", type=int, default=5, help="repeats per (model, drug) for variability")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", type=Path, default=OUT_DIR / "j1_alias_runs.json")
    args = ap.parse_args()

    client = get_client()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"{len(args.drugs)} drugs x {len(args.models)} models x k={args.k} generations "
          f"+ judge={args.judge} | temp={LLM_TEMPERATURE}")

    # 1) RxNorm truth (sequential; it's fast and we want to be polite to NIH)
    rxnorm = {d: rxnorm_names(d) for d in args.drugs}
    n_cov = sum(v["covered"] for v in rxnorm.values())
    print(f"RxNorm: {n_cov}/{len(args.drugs)} drugs covered")

    # 2) Generation across roster x drugs x k
    gen_tasks = [(m, d, r) for m in args.models for d in args.drugs for r in range(args.k)]

    def run_gen(t):
        m, d, r = t
        return {"model": m, "drug": d, "run": r, "aliases": generate_aliases(client, m, d)}

    generations = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(run_gen, t) for t in gen_tasks]
        for i, f in enumerate(as_completed(futs), 1):
            generations.append(f.result())
            if i % 40 == 0 or i == len(gen_tasks):
                print(f"  generation {i}/{len(gen_tasks)}")

    # 3) Opus-judge on the UNION of each (model, drug)'s aliases across runs
    union = {}
    for g in generations:
        union.setdefault((g["model"], g["drug"]), set()).update(g["aliases"])

    def run_judge(item):
        (m, d), al = item
        return {"model": m, "drug": d, "verdicts": opus_judge(client, args.judge, d, sorted(al))}

    judge = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(run_judge, it) for it in union.items()]
        for i, f in enumerate(as_completed(futs), 1):
            judge.append(f.result())
            if i % 10 == 0 or i == len(union):
                print(f"  judge {i}/{len(union)}")

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "judgement": "1_alias_generation",
        "temperature": LLM_TEMPERATURE,
        "candidate_models": args.models,
        "judge_model": args.judge,
        "k": args.k,
        "n_drugs": len(args.drugs),
        "truth_sources": ["rxnorm", "opus_judge"],
        "note": "candidate roster limited to Anthropic models — OpenRouter credits exhausted; "
                "pass --models with the full roster slugs when restored.",
    }
    args.out.write_text(json.dumps(
        {"manifest": manifest, "generations": generations, "judge": judge, "rxnorm": rxnorm},
        indent=2), encoding="utf-8")
    print(f"Wrote {args.out} ({len(generations)} generations, {len(judge)} judged)")


if __name__ == "__main__":
    main()
