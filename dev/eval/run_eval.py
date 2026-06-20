#!/usr/bin/env python3
"""Faithful eval harness for PatientPunk's drug-sentiment LLM prompts.

dr-hiro MEASURED methodology: every prompt change is judged against a grounded
bank (dev/eval/bank.json) of real r/covidlonghaulers posts with hand-read
expected drugs + classify labels. We run the REAL prompts (imported from
src/, never hand-copied) against the model N reps, score four metrics, pool
reps (sum k,n — never average per-rep), exclude errored cases from denominators,
and print a Wilson-CI table.

Metrics
-------
  json_valid_rate     : did the classify-batch output parse as a JSON array on
                        the FIRST try, with NO per-item retry? (catches OBSERVED
                        FAILURE #1 — model narrates prose instead of returning JSON)
  extract_recall      : of the drugs a correct extract should find, how many did it?
  extract_precision   : of the drugs it found, how many were expected?
  sentiment_accuracy  : on labeled drugs, did the classifier's sentiment match?
  side_effect_correct : on labeled drugs, did side_effects match (catches
                        OBSERVED FAILURE #2 — over-attribution of one drug's
                        side effect to others in the same stack)?

Usage
-----
  uv run python dev/eval/run_eval.py --selftest          # offline, no LLM
  uv run python dev/eval/run_eval.py --live --n 5        # 5 reps against the model
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ── Make the REAL PatientPunk code importable ────────────────────────────────
# load_dotenv FIRST (utilities resolves the LLM provider/models at import time),
# then put 'src' on sys.path so `prompts.*` and `utilities` resolve to the real
# pipeline modules — we never hand-copy a prompt.
_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"
try:
    from dotenv import load_dotenv
    load_dotenv(_REPO / ".env", override=False)
except Exception:  # dotenv is a dep; if missing, env must already be set
    pass
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from wilson import wilson, contrast, rule_of_three  # noqa: E402  (local sibling)

BANK_PATH = Path(__file__).resolve().parent / "bank.json"
SUBREDDIT = "covidlonghaulers"  # matches data/posts.db users.source_subreddit


# ── Bank loading ─────────────────────────────────────────────────────────────
def load_bank(path: Path = BANK_PATH) -> list[dict]:
    items = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError("bank.json must be a JSON array")
    for it in items:
        for key in ("id", "text", "expected_drugs", "labels"):
            if key not in it:
                raise ValueError(f"bank item {it.get('id', '?')} missing key {key!r}")
        if not isinstance(it["expected_drugs"], list):
            raise ValueError(f"{it['id']}: expected_drugs must be a list")
        if not isinstance(it["labels"], dict):
            raise ValueError(f"{it['id']}: labels must be an object")
    return items


# ── Normalization helpers (lenient matching for extract recall/precision) ────
def _norm(s: str) -> str:
    return str(s).strip().lower()


# A few documented synonym families so extract recall isn't punished for the
# canonical-name choice the bank made vs. an equally-correct surface form the
# model emits. Kept deliberately small and explicit — this is matching, not a
# second canonicalizer. Each line is a set of interchangeable surface forms.
_SYNONYM_GROUPS = [
    {"ldn", "low dose naltrexone", "low-dose naltrexone", "naltrexone"},
    {"lda", "low dose abilify", "low-dose abilify", "abilify", "aripiprazole"},
    {"hbot", "hyperbaric oxygen", "hyperbaric oxygen therapy"},
    {"nicotine patches", "nicotine patch", "nicotine"},
    {"red light mat", "red light therapy", "red light", "red light therapy mat"},
    {"antihistamines", "antihistamine", "h1 antihistamines", "h1 antihistamine"},
    {"h1 blockers", "h1 blocker", "h1 antihistamines"},
    {"famotidine", "pepcid", "famitodine", "pepsid"},
    {"betaine hcl", "betaine", "betaine hydrochloride", "betaine hydrochloric acid"},
    {"lisdexamfetamine", "lisdex", "vyvanse", "elvanse", "lisdexamphetamine"},
    {"nattokinase", "natto"},
    {"lumbrokinase", "lumbro"},
    {"beta blockers", "beta blocker", "beta-blocker", "beta-blockers"},
    {"iron", "iron supplements", "iron supplement", "iron supplementation"},
    {"ferrous sulfate", "ferrous sulphate", "iron sulfate"},
    {"iron glycinate", "iron bisglycinate", "ferrous glycinate"},
    {"b12", "vitamin b12", "b-12", "cobalamin", "methylcobalamin"},
    {"b1", "vitamin b1", "thiamine"},
    {"b6", "vitamin b6", "pyridoxine"},
    {"d3", "vitamin d3", "vitamin d", "d"},
    {"omega 3", "omega-3", "fish oil", "omega 3s"},
    {"probiotics", "probiotic"},
    {"creatine", "creatine monohydrate"},
    {"magnesium", "mag"},
    {"epipen", "epipens", "epinephrine", "adrenaline"},
    {"hydroxyzine", "atarax", "vistaril"},
    {"gaviscon", "gaviscon advance"},
    {"ketotifen", "zaditen"},
    {"desloratadine", "aerius"},
    {"zyrtec", "cetirizine"},
    {"guanfacine", "intuniv"},
    {"mitochondrial support supplement", "mitochondrial support", "mitothera", "sfi mitothera"},
    {"amifampridine", "3,4-dap", "firdapse"},
    {"fluvoxamine", "luvox"},
    {"tollovid", "tollovid daily"},
]


def _match_set(name: str) -> frozenset[str]:
    """Return the synonym family for a name (or just {name})."""
    n = _norm(name)
    for grp in _SYNONYM_GROUPS:
        if n in grp:
            return frozenset(grp)
    return frozenset({n})


def _drug_in(found: set[str], target: str) -> bool:
    """True if `target` (or any of its synonyms) appears in `found`."""
    fam = _match_set(target)
    return any(_norm(f) in fam for f in found)


# ── Side-effect comparison ───────────────────────────────────────────────────
# Function words ignored when comparing side-effect phrases by content tokens.
_SE_STOPWORDS = frozenset({
    "the", "a", "an", "my", "me", "got", "was", "were", "is", "are", "of",
    "to", "and", "had", "have", "it", "i", "really", "very", "much", "more",
    "bit", "little", "so", "feel", "feeling", "felt", "been", "being",
})


def _content_tokens(phrase: str) -> frozenset[str]:
    toks = [w for w in _norm(phrase).replace("-", " ").split() if w and w not in _SE_STOPWORDS]
    return frozenset(toks)


def _se_phrase_match(a: str, b: str) -> bool:
    """Two side-effect phrases match if one contains the other OR they share a
    content token (so 'worse sleep' ~ 'sleep got worse', 'anxiety' ~ 'bad anxiety')."""
    na, nb = _norm(a), _norm(b)
    if na in nb or nb in na:
        return True
    return bool(_content_tokens(a) & _content_tokens(b))


def side_effects_match(expected: list[str], got: list[str]) -> bool:
    """Order-insensitive, lenient match on side-effect lists.

    Empty-vs-empty is the load-bearing case (OBSERVED FAILURE #2): the bank
    asserts side_effects==[] for drugs that should carry NO side effect, and we
    require the model to also return [] (any spurious effect = mismatch).
    For non-empty expected sets we require each expected phrase to be matched
    1:1 by a got phrase (containment or shared content token, so "worse sleep"
    matches "sleep got worse"), and forbid leftover spurious got phrases.
    """
    exp = [_norm(e) for e in expected]
    g = [_norm(x) for x in got]
    if not exp:
        return len(g) == 0
    used = [False] * len(g)
    for e in exp:
        hit = False
        for i, x in enumerate(g):
            if used[i]:
                continue
            if _se_phrase_match(e, x):
                used[i] = True
                hit = True
                break
        if not hit:
            return False
    # No leftover spurious got phrases (catches over-attribution / hallucination).
    return all(used)


# ── Tally container ──────────────────────────────────────────────────────────
class Tally:
    """Pooled (k, n) counter. Pool reps by summing k and n — never average."""

    def __init__(self) -> None:
        self.k = 0
        self.n = 0

    def add(self, success: bool) -> None:
        self.n += 1
        if success:
            self.k += 1

    def add_kn(self, k: int, n: int) -> None:
        self.k += k
        self.n += n


# ── Scorers (pure; unit-tested by --selftest) ────────────────────────────────
def score_extract(expected: list[str], found: list[str]) -> tuple[int, int, int, int]:
    """Return (recall_k, recall_n, prec_k, prec_n) for one item.

    recall: of expected drugs, how many are present in `found` (synonym-aware).
    precision: of found drugs, how many map to an expected drug.
    """
    found_set = {_norm(f) for f in found}
    rec_k = sum(1 for d in expected if _drug_in(found_set, d))
    rec_n = len(expected)
    prec_k = sum(1 for f in found_set if any(_drug_in({f}, e) for e in expected))
    prec_n = len(found_set)
    return rec_k, rec_n, prec_k, prec_n


def score_sentiment(label: dict, result: dict) -> bool | None:
    """True/False if sentiment is labeled, else None (skip — not in denominator)."""
    if "sentiment" not in label:
        return None
    return _norm(result.get("sentiment", "")) == _norm(label["sentiment"])


def score_side_effects(label: dict, result: dict) -> bool | None:
    """True/False if side_effects is labeled, else None (skip)."""
    if "side_effects" not in label:
        return None
    return side_effects_match(label["side_effects"], result.get("side_effects", []))


# ── Faithful prompt composition (mirrors src/pipeline exactly) ───────────────
def _build_classify_msg(items: list[tuple[dict, str]]) -> str:
    """Use the REAL classify-batch composition (imported, never hand-copied) so the eval
    measures the shipped prompt verbatim. `items` is a list of (entry, drug), same drug."""
    from pipeline.classify import build_classify_batch_msg  # the real composer

    id_to_text = {e["id"]: e.get("_upstream", "") for e, _ in items}
    return build_classify_batch_msg(items, id_to_text)


# ── Live run ─────────────────────────────────────────────────────────────────
def run_live(bank: list[dict], n_reps: int) -> dict:
    """Run the real prompts against the model n_reps times; return pooled tallies."""
    from prompts.intervention_config import EXTRACT_PROMPT, system_prompt
    from utilities import (
        MODEL_FAST, MODEL_STRONG, LLMParseError, get_client,
        llm_call, parse_json_array,
    )

    client = get_client()

    t = {
        "json_valid": Tally(),
        "recall": Tally(),
        "precision": Tally(),
        "sentiment": Tally(),
        "side_effect": Tally(),
    }
    errored = {"extract": 0, "classify": 0}

    for rep in range(n_reps):
        print(f"\n=== rep {rep+1}/{n_reps} ===", file=sys.stderr)
        for item in bank:
            text = item["text"]
            # ---- EXTRACT (faithful single-text batch, mirrors extract_batch) ----
            ex_msg = EXTRACT_PROMPT + "\n" + f"--- 1 ---\n{text}\n\n"
            try:
                raw = llm_call(client, ex_msg, model=MODEL_FAST, max_tokens=1 * 80)
                arr = parse_json_array(raw)
                # extract returns list-of-lists; flatten the first (only) inner list
                inner = arr[0] if arr and isinstance(arr[0], list) else arr
                found = [str(d).lower().strip() for d in inner if isinstance(d, (str,)) and str(d).strip()]
                rk, rn, pk, pn = score_extract(item["expected_drugs"], found)
                t["recall"].add_kn(rk, rn)
                t["precision"].add_kn(pk, pn)
            except (LLMParseError, Exception) as e:  # noqa: BLE001
                errored["extract"] += 1
                print(f"  [extract ERROR {item['id']}] {type(e).__name__}: {e}", file=sys.stderr)

            # ---- CLASSIFY (one labeled drug per call; faithful batch composition) ----
            for drug, label in item["labels"].items():
                entry = {
                    "id": item["id"],
                    "text": text,
                    "_upstream": item.get("upstream", "") or "",
                }
                # mirror classify: synonyms hint + subreddit injected into system prompt
                sys_prompt = system_prompt(drug, None, SUBREDDIT)
                msg = _build_classify_msg([(entry, drug)])
                try:
                    raw = llm_call(
                        client, msg, model=MODEL_STRONG, system=sys_prompt, max_tokens=80 * 1,
                    )
                    # json_valid_rate: did the BATCH array parse on the FIRST try?
                    try:
                        results = parse_json_array(raw)
                        t["json_valid"].add(True)
                    except LLMParseError as pe:
                        t["json_valid"].add(False)
                        print(f"  [json FAIL {item['id']}:{drug}] {pe}", file=sys.stderr)
                        # observed-failure path: prose instead of array -> count, skip scoring
                        errored["classify"] += 1
                        continue
                    if not results or not isinstance(results[0], dict):
                        errored["classify"] += 1
                        continue
                    result = results[0]
                    sm = score_sentiment(label, result)
                    if sm is not None:
                        t["sentiment"].add(sm)
                    se = score_side_effects(label, result)
                    if se is not None:
                        t["side_effect"].add(se)
                except Exception as e:  # noqa: BLE001  (network/SDK errors)
                    errored["classify"] += 1
                    print(f"  [classify ERROR {item['id']}:{drug}] {type(e).__name__}: {e}", file=sys.stderr)

    return {"tallies": t, "errored": errored}


# ── Reporting ────────────────────────────────────────────────────────────────
def print_table(tallies: dict, errored: dict) -> None:
    print("\n" + "=" * 72)
    print(f"{'metric':<22}{'k':>6}{'n':>6}{'p̂':>8}{'  95% Wilson CI':>22}")
    print("-" * 72)
    order = [
        ("json_valid_rate", "json_valid"),
        ("extract_recall", "recall"),
        ("extract_precision", "precision"),
        ("sentiment_accuracy", "sentiment"),
        ("side_effect_correct", "side_effect"),
    ]
    for label, key in order:
        tl = tallies[key]
        p, lo, hi = wilson(tl.k, tl.n)
        ci = f"[{lo:.3f}, {hi:.3f}]"
        print(f"{label:<22}{tl.k:>6}{tl.n:>6}{p:>8.3f}{ci:>22}")
    print("-" * 72)
    print(f"errored (excluded from denominators): extract={errored['extract']} classify={errored['classify']}")
    # Rule-of-three note when a metric saw zero failures.
    for label, key in order:
        tl = tallies[key]
        if tl.n and tl.k == tl.n:
            print(f"note: {label} had 0 failures in n={tl.n}; rule-of-three upper bound on failure rate ≈ {rule_of_three(tl.n):.3f}")
    print("=" * 72)


# ── Selftest (offline, no LLM) ───────────────────────────────────────────────
def selftest() -> bool:
    ok = True

    def check(cond: bool, msg: str) -> None:
        nonlocal ok
        status = "PASS" if cond else "FAIL"
        print(f"  [{status}] {msg}")
        if not cond:
            ok = False

    print("--- selftest: bank loads ---")
    bank = load_bank()
    by_id = {b["id"]: b for b in bank}
    check(len(bank) >= 5, f"bank has >=5 items (got {len(bank)})")
    check(all("id" in b and "text" in b for b in bank), "every item has id+text")
    p1 = by_id.get("p1")
    check(p1 is not None, "item p1 present")
    check(p1 and p1["labels"]["fluvoxamine"]["side_effects"] == ["worse sleep"], "p1 fluvoxamine carries 'worse sleep'")
    check(p1 and p1["labels"]["red light mat"]["side_effects"] == [], "p1 red light mat side_effects == [] (over-attribution guard)")
    # true-negative items must have expected_drugs == [] and no labels
    tn = [b for b in bank if not b["expected_drugs"] and not b["labels"]]
    check(len(tn) >= 1, f"bank has >=1 true-negative (empty drugs+labels) item (got {len(tn)})")
    # every label's drug must appear in that item's expected_drugs (synonym-aware)
    for b in bank:
        for drug in b["labels"]:
            exp_set = {_norm(d) for d in b["expected_drugs"]}
            check(_drug_in(exp_set, drug), f"{b['id']}: labeled drug {drug!r} is in expected_drugs")

    print("--- selftest: wilson ---")
    p, lo, hi = wilson(0, 0)
    check((p, lo, hi) == (0.0, 0.0, 1.0), "wilson(0,0) == (0,0,1)")
    p, lo, hi = wilson(5, 10)
    check(abs(p - 0.5) < 1e-9, "wilson(5,10) p̂ == 0.5")
    check(lo < 0.5 < hi and lo > 0.18 and hi < 0.82, f"wilson(5,10) CI ~[.24,.76] (got [{lo:.3f},{hi:.3f}])")
    p, lo, hi = wilson(10, 10)
    check(p == 1.0 and hi == 1.0 and lo < 1.0, "wilson(10,10) p̂==1, lo<1, hi==1")
    check(abs(rule_of_three(10) - 0.3) < 1e-9, "rule_of_three(10) == 0.3")
    check(rule_of_three(0) == 1.0, "rule_of_three(0) == 1.0")

    print("--- selftest: contrast ---")
    check(contrast(0, 20, 20, 20) == "SEPARATED", "0/20 vs 20/20 -> SEPARATED")
    check(contrast(5, 10, 6, 10) == "overlap", "5/10 vs 6/10 -> overlap")

    print("--- selftest: score_extract ---")
    # exact match
    rk, rn, pk, pn = score_extract(["ldn", "lda"], ["ldn", "lda"])
    check((rk, rn, pk, pn) == (2, 2, 2, 2), f"exact match -> 2,2,2,2 (got {rk,rn,pk,pn})")
    # synonym recall: expected 'ldn' found via 'low dose naltrexone'
    rk, rn, pk, pn = score_extract(["ldn"], ["low dose naltrexone"])
    check((rk, rn) == (1, 1), f"synonym recall ldn<-low dose naltrexone (got {rk},{rn})")
    # missed one
    rk, rn, pk, pn = score_extract(["ldn", "lda", "hbot"], ["ldn"])
    check((rk, rn) == (1, 3), f"recall 1/3 when 2 missed (got {rk},{rn})")
    # spurious found -> precision penalty
    rk, rn, pk, pn = score_extract(["ldn"], ["ldn", "aspirin"])
    check((pk, pn) == (1, 2), f"precision 1/2 with 1 spurious (got {pk},{pn})")
    # empty expected -> precision 0/n
    rk, rn, pk, pn = score_extract([], ["aspirin"])
    check((rk, rn, pk, pn) == (0, 0, 0, 1), f"empty expected (got {rk,rn,pk,pn})")

    print("--- selftest: score_sentiment ---")
    check(score_sentiment({"sentiment": "positive"}, {"sentiment": "positive"}) is True, "sentiment match -> True")
    check(score_sentiment({"sentiment": "positive"}, {"sentiment": "negative"}) is False, "sentiment mismatch -> False")
    check(score_sentiment({"side_effects": []}, {"sentiment": "x"}) is None, "no sentiment label -> None (skipped)")

    print("--- selftest: score_side_effects ---")
    check(score_side_effects({"side_effects": []}, {"side_effects": []}) is True, "[] vs [] -> True")
    check(score_side_effects({"side_effects": []}, {"side_effects": ["worse sleep"]}) is False, "[] vs ['worse sleep'] -> False (over-attribution)")
    check(score_side_effects({"side_effects": ["worse sleep"]}, {"side_effects": ["sleep got worse"]}) is True, "fuzzy se match -> True")
    check(score_side_effects({"side_effects": ["worse sleep"]}, {"side_effects": []}) is False, "missed se -> False")
    check(score_side_effects({"side_effects": ["worse sleep"]}, {"side_effects": ["worse sleep", "nausea"]}) is False, "spurious extra se -> False")
    check(score_side_effects({"sentiment": "x"}, {"side_effects": []}) is None, "no se label -> None (skipped)")

    print("--- selftest: Tally pooling ---")
    tl = Tally()
    tl.add_kn(3, 5)
    tl.add_kn(4, 5)
    check((tl.k, tl.n) == (7, 10), "pooling sums k and n (7/10)")

    print("--- selftest: prompt composition imports the REAL code ---")
    try:
        from pipeline.classify import format_entry as _fe  # noqa: F401
        from prompts.intervention_config import EXTRACT_PROMPT as _ep, system_prompt as _sp  # noqa: F401
        sp = _sp("ldn", None, SUBREDDIT)
        check("r/covidlonghaulers" in sp, "system_prompt injects the subreddit")
        check("LDN" in sp, "system_prompt title-cases the drug name")
        msg = _build_classify_msg([({"id": "x", "text": "hi", "_upstream": ""}, "ldn")])
        check(msg.startswith("Classify each entry separately."), "classify msg matches real composition")
        check("Text:\nhi" in msg, "classify msg embeds entry text via real format_entry")
    except Exception as e:  # noqa: BLE001
        check(False, f"real-code import/composition raised {type(e).__name__}: {e}")

    print()
    print("SELFTEST:", "PASS" if ok else "FAIL")
    return ok


# ── CLI ──────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true", help="offline self-test of scorers + bank (no LLM)")
    ap.add_argument("--live", action="store_true", help="run the real prompts against the model")
    ap.add_argument("--n", type=int, default=3, help="reps per bank item for --live (default 3)")
    args = ap.parse_args()

    if args.selftest:
        return 0 if selftest() else 1

    if args.live:
        bank = load_bank()
        print(f"Loaded {len(bank)} bank items; running {args.n} rep(s) each against the model...")
        out = run_live(bank, args.n)
        print_table(out["tallies"], out["errored"])
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
