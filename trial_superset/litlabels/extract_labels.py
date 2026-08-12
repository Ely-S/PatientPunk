"""M3b - extract per-arm primary-endpoint outcomes from PMC full text (papers-as-labels).

For a completed trial that never posted CT.gov structured results, pull its OA full text,
and extract the PRIMARY endpoint value per arm in the shape her Experiment needs
(value + denom per non-placebo arm). LLM calls use Anthropic's OpenAI-compatible
endpoint; set `M3_MODEL` to override the default `claude-sonnet-4-6` model.

Output schema per trial:
  {extractable, primary_outcome_title, unit('count'|'percentage'), result_public_date,
   confidence, arms:[{title, is_placebo, n, value}], note}

Cached by (nct, pmcid, model). Run from the repo root:
  $env:PYTHONPATH = "trial_superset"
  trial_superset/.venv/Scripts/python.exe -m litlabels.extract_labels --n 15
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from lxml import etree

from . import cache, europe_pmc

cache.CACHE_DIR = Path("trial_superset/data/.cache")
MODEL = os.environ.get("M3_MODEL", "claude-sonnet-4-6")
_EXTRACT_TTL = 90 * 24 * 3600
MAX_CHARS = 55_000


_CLIENT = None


def _client():
    # Anthropic direct via the OpenAI-compatible endpoint (so we reuse the openai SDK).
    # Singleton so concurrent workers share one connection-pooled, thread-safe client.
    global _CLIENT
    if _CLIENT is None:
        from openai import OpenAI
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except Exception:
            pass
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise SystemExit("ANTHROPIC_API_KEY not set (in .env)")
        _CLIENT = OpenAI(base_url="https://api.anthropic.com/v1/", api_key=key, max_retries=4)
    return _CLIENT


def relevant_fulltext(xml: str) -> str:
    """Abstract + results sections + all tables from JATS XML, truncated."""
    try:
        root = etree.fromstring(xml.encode("utf-8"))
    except Exception:
        return re.sub(r"<[^>]+>", " ", xml)[:MAX_CHARS]
    def textof(els):
        return "\n".join("".join(e.itertext()) for e in els)
    abstract = textof(root.xpath("//*[local-name()='abstract']"))
    tables = textof(root.xpath("//*[local-name()='table-wrap']"))
    results = textof(root.xpath(
        "//*[local-name()='sec'][.//*[local-name()='title']"
        "[contains(translate(text(),'RESULT','result'),'result')]]"))
    parts = [p for p in (abstract, results, tables) if p.strip()]
    combined = "\n\n".join(parts) if parts else "".join(root.itertext())
    return combined[:MAX_CHARS]


PROMPT = """You are extracting a clinical trial's PRIMARY endpoint result from its publication.

REGISTERED PRIMARY OUTCOME(S) (from ClinicalTrials.gov):
{primary}

TRIAL ARMS (from ClinicalTrials.gov):
{arms}

PAPER TEXT (abstract + results + tables):
{text}

Return ONLY a JSON object (no prose) with this exact shape:
{{"extractable": true|false,
  "primary_outcome_title": "the primary outcome you found",
  "outcome_kind": "binary_count" | "percentage" | "continuous_mean",
  "unit_of_measure": "the result's unit, e.g. 'Participants', 'Percentage of Participants', 'Points (RAND-36 PF)', 'Meters'",
  "scale_min": <number or null>,
  "scale_max": <number or null>,
  "higher_is_better": true | false | null,
  "result_public_date": "YYYY-MM" or "YYYY",
  "confidence": "high" | "medium" | "low",
  "arms": [{{"title": "<arm name matching the trial arms>", "is_placebo": true|false,
             "n": <int participants analyzed in that arm>, "value": <number>}}],
  "note": "brief note / why not extractable"}}

Rules:
- Report the PRIMARY outcome only, per arm, at the primary timepoint.
- binary_count: value = number of participants with the event; unit_of_measure="Participants".
- percentage: value = the percent (0-100); unit_of_measure MUST contain "Percentage". Use this
  ONLY if the endpoint is literally a proportion/percent of participants.
- continuous_mean: value = the arm MEAN (or mean change) at the primary timepoint; n = participants
  analyzed; unit_of_measure = the score/measure unit (e.g. 'Points (FSS)', 'Meters') and must NOT
  contain 'percent'. A change in a questionnaire/scale score is continuous_mean, NOT a percentage.
- scale_min / scale_max: ONLY for continuous_mean on a BOUNDED instrument with a known fixed range
  (e.g. VAS 0-100, FIQ 0-100, Chalder Fatigue 0-33, SF-36 0-100). Give the instrument's full range.
  For UNBOUNDED measures (steps/day, meters walked, time, counts, lab values) OR if the value is a
  CHANGE-from-baseline (not an absolute score), set both to null. binary_count/percentage: null.
- higher_is_better: for continuous_mean, does a HIGHER score mean a BETTER patient outcome?
  (e.g. SF-36/RAND-36 physical function: true; FIQ / VAS pain / fatigue severity: false). Else null.
- Include every arm you can (treatment AND placebo). Match arm titles to the trial arms.
- If the paper does not report the primary endpoint per arm as numbers (only p-values, figures,
  or narrative), set extractable=false and explain in note.
- Output strictly valid JSON."""


def _parse_json(raw: str) -> dict | None:
    if "```" in raw:
        raw = raw.split("```")[1]
        raw = raw[4:] if raw.startswith("json") else raw
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        return json.loads(m.group()) if m else None


def _oa_pmcid(result: dict) -> str | None:
    return result["pmcid"] if result.get("pmcid") and result.get("isOpenAccess") == "Y" else None


def _is_review(result: dict) -> bool:
    pt = result.get("pubTypeList", {}).get("pubType", []) if isinstance(result.get("pubTypeList"), dict) else []
    blob = " ".join(pt).lower()
    return "review" in blob or "meta-analysis" in blob


def link_paper(nct: str, trial_json_path: str) -> dict | None:
    """Best OA paper to extract from. Prefer the trial's own CT.gov RESULT-type reference;
    fall back to an NCT search that EXCLUDES reviews/meta-analyses (which cite but don't report)."""
    trial = json.load(open(trial_json_path, encoding="utf-8"))
    refs = trial["protocolSection"].get("referencesModule", {}).get("references", []) or []
    result_pmids = [r["pmid"] for r in refs if r.get("type") == "RESULT" and r.get("pmid")]
    for pmid in result_pmids:  # the trial's declared results paper
        res = europe_pmc.search(f"EXT_ID:{pmid} AND SRC:MED", page_size=1).get("resultList", {}).get("result", [])
        if res and _oa_pmcid(res[0]):
            return {"pmcid": res[0]["pmcid"], "pmid": pmid, "via": "ct_result_ref"}
    # fallback: NCT search, skip reviews
    res = europe_pmc.search(nct, page_size=25).get("resultList", {}).get("result", [])
    for x in res:
        if _oa_pmcid(x) and not _is_review(x):
            return {"pmcid": x["pmcid"], "pmid": x.get("pmid"), "via": "nct_search"}
    return None


def candidate_papers(nct: str, trial_json_path: str, k: int = 5) -> list[tuple[str, str]]:
    """Ordered list of (pmcid, via) candidate OA papers - CT.gov RESULT refs first, then
    NCT-search hits excluding reviews. Lets us retry extraction across papers when the first
    linked paper is the wrong one (a review / protocol / secondary analysis)."""
    trial = json.load(open(trial_json_path, encoding="utf-8"))
    refs = trial["protocolSection"].get("referencesModule", {}).get("references", []) or []
    out: list[tuple[str, str]] = []
    seen = set()
    for pmid in [r["pmid"] for r in refs if r.get("type") == "RESULT" and r.get("pmid")]:
        res = europe_pmc.search(f"EXT_ID:{pmid} AND SRC:MED", page_size=1).get("resultList", {}).get("result", [])
        if res and _oa_pmcid(res[0]) and res[0]["pmcid"] not in seen:
            out.append((res[0]["pmcid"], "ct_result_ref")); seen.add(res[0]["pmcid"])
    for x in europe_pmc.search(nct, page_size=25).get("resultList", {}).get("result", []):
        pm = _oa_pmcid(x)
        if pm and not _is_review(x) and pm not in seen:
            out.append((pm, "nct_search")); seen.add(pm)
        if len(out) >= k:
            break
    return out


def extract_best(nct: str, trial_json_path: str) -> tuple[dict, str, str] | None:
    """Try each candidate paper until one yields an extractable result. Returns (schema, pmcid, via)."""
    for pmcid, via in candidate_papers(nct, trial_json_path):
        r = extract(nct, trial_json_path, pmcid)
        if r and r.get("extractable"):
            return r, pmcid, via
    return None


def extract(nct: str, trial_json_path: str, pmcid: str) -> dict | None:
    payload = {"nct": nct, "pmcid": pmcid, "model": MODEL, "v": 3}
    cached = cache.get("m3/extract", payload, _EXTRACT_TTL)
    if cached is not None:
        return cached

    trial = json.load(open(trial_json_path, encoding="utf-8"))
    ps = trial["protocolSection"]
    prim = ps.get("outcomesModule", {}).get("primaryOutcomes", []) or []
    primary = "\n".join(f"- {o.get('measure','')} [timeframe: {o.get('timeFrame','')}]"
                        f"{(' - ' + o['description']) if o.get('description') else ''}" for o in prim)
    arms = "\n".join(f"- {a.get('label','')} (type={a.get('type','')})"
                     for a in ps.get("armsInterventionsModule", {}).get("armGroups", []) or [])
    xml = europe_pmc.fulltext_xml("PMC", pmcid)
    if not xml:
        return None
    text = relevant_fulltext(xml)

    msg = PROMPT.format(primary=primary or "(none registered)", arms=arms or "(none)", text=text)
    resp = _client().chat.completions.create(
        model=MODEL, temperature=0, max_tokens=1500,
        messages=[{"role": "user", "content": msg}],
    )
    result = _parse_json(resp.choices[0].message.content or "")
    if result is not None:
        result["_pmcid"] = pmcid
        cache.put("m3/extract", payload, result)
    return result


# --- validation gate CLI ---
def _gate(n: int, only: str | None) -> None:
    import sys
    sys.path.insert(0, ".")
    from seed_terms import CLUSTER
    from m3_pool import POOL
    from run_study import build_cfg
    from build_improved import terms_of, classify
    from naturalv2.clinical_trial import ClinicalTrial
    from naturalv2.utils import check_trial
    from naturalv2.cli.create_study import resolve_trial_filters
    filters = resolve_trial_filters(build_cfg("x"))

    selected = list(CLUSTER) if not only else [only]
    per_cond = max(1, n // len(selected))  # spread across conditions for a representative read
    picked = []
    for slug in selected:
        tp = os.path.join(POOL, slug, "nct_reports_noresults")
        if not os.path.isdir(tp):
            continue
        taken = 0
        for fn in sorted(os.listdir(tp)):
            if not fn.endswith(".json") or taken >= per_cond:
                continue
            p = os.path.join(tp, fn)
            try:
                trial = ClinicalTrial.from_json_file(p)
            except Exception:
                continue
            if check_trial(trial, filters)[1] and classify(terms_of(trial), slug):
                link = link_paper(fn[:-5], p)
                if link:
                    picked.append((slug, fn[:-5], p, link["pmcid"]))
                    taken += 1

    ok = fail = 0
    for slug, nct, p, pmcid in picked:
        r = extract(nct, p, pmcid)
        if r and r.get("extractable"):
            ok += 1
            arms = "; ".join(f"{a['title']}={a.get('value')}(n={a.get('n')})" for a in r.get("arms", []))
            print(f"[{slug}] {nct} {pmcid} {r.get('outcome_kind')} conf={r.get('confidence')} "
                  f"date={r.get('result_public_date')}\n   outcome: {r.get('primary_outcome_title','')[:85]}\n   arms: {arms}")
        else:
            fail += 1
            print(f"[{slug}] {nct} {pmcid} NOT EXTRACTABLE: {(r or {}).get('note','(no result)')[:90]}")
    print(f"\nGate: {ok}/{len(picked)} extractable ({MODEL}). Spot-check the per-arm values vs the papers.")


JSONL = "trial_superset/data/m3_extractions.jsonl"


def run_all(jsonl: str = JSONL, workers: int = 8) -> None:
    """Extract ALL OA-linked candidates across the cluster, concurrently.
    Resumable (skips ncts already in the jsonl) + per-trial flush under a write lock."""
    import sys
    import threading
    from collections import Counter
    from concurrent.futures import ThreadPoolExecutor, as_completed
    sys.path.insert(0, ".")
    from seed_terms import CLUSTER
    from m3_pool import POOL
    from run_study import build_cfg
    from build_improved import terms_of, classify
    from naturalv2.clinical_trial import ClinicalTrial
    from naturalv2.utils import check_trial
    from naturalv2.cli.create_study import resolve_trial_filters
    filters = resolve_trial_filters(build_cfg("x"))

    done = set()
    if os.path.exists(jsonl):
        for line in open(jsonl, encoding="utf-8"):
            try:
                done.add(json.loads(line)["nct"])
            except Exception:
                pass

    # collect candidates first (fast, sequential)
    tasks = []
    for slug in CLUSTER:
        tp = os.path.join(POOL, slug, "nct_reports_noresults")
        if not os.path.isdir(tp):
            continue
        for fn in sorted(os.listdir(tp)):
            if not fn.endswith(".json"):
                continue
            nct, p = fn[:-5], os.path.join(tp, fn)
            if nct in done:
                continue
            try:
                trial = ClinicalTrial.from_json_file(p)
            except Exception:
                continue
            if check_trial(trial, filters)[1] and classify(terms_of(trial), slug):
                tasks.append((slug, nct, p))
    print(f"{len(tasks)} candidates to process ({len(done)} already cached), {workers} workers", flush=True)

    def work(t):
        slug, nct, p = t
        link = link_paper(nct, p)
        rec = {"nct": nct, "slug": slug, "linked": bool(link)}
        if link:
            try:
                r = extract(nct, p, link["pmcid"])
            except Exception as e:
                r = None
                rec["error"] = str(e)[:120]
            rec.update(pmcid=link["pmcid"], via=link["via"],
                       extractable=bool(r and r.get("extractable")), schema=r)
        return rec

    lock = threading.Lock()
    n = 0
    with open(jsonl, "a", encoding="utf-8") as out, ThreadPoolExecutor(max_workers=workers) as ex:
        for fut in as_completed([ex.submit(work, t) for t in tasks]):
            rec = fut.result()
            with lock:
                out.write(json.dumps(rec) + "\n")
                out.flush()
                n += 1
                if n % 25 == 0:
                    print(f"  {n}/{len(tasks)} processed", flush=True)

    # summary over the full jsonl
    by = Counter()
    for line in open(jsonl, encoding="utf-8"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        by["cand"] += 1
        by["linked"] += 1 if r.get("linked") else 0
        by["extractable"] += 1 if r.get("extractable") else 0
    print(f"\nTOTAL cand={by['cand']} linked={by['linked']} extractable={by['extractable']} -> {jsonl}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--n", type=int, default=15)
    ap.add_argument("--condition", default=None)
    args = ap.parse_args()
    if args.all:
        run_all()
    else:
        _gate(args.n, args.condition)
