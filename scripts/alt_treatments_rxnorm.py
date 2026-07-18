"""
alt_treatments_rxnorm.py — the Tier-2 TOOL for `alternative_treatments`, backed by RxNorm (keyless RxNav).

This is the real ontology tool the conditions prototype showed was load-bearing — but pointed at the field
where it is both feasible and high-ROI. Every therapeutic substance is linked to an RxNorm concept (RxCUI)
and canonicalized to that concept's name, so surface variants collapse: `coq10` = `coenzyme q10`,
`magnesium` = `magnesium supplementation`, `b12` = `vitamin b12`. Non-substance interventions (`pacing`,
`vestibular therapy`) don't link and are kept verbatim. RxNorm/RxNav is the NLM's drug terminology; no
API key, no install — the drug analogue of the UMLS the `conditions` boundary needed.

Build the cache once (links every unique term in the corpus, ~minutes, saved to disk); apply is then offline.
"""
from __future__ import annotations
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "validation" / "rxnorm_cache.json"

# supplement/abbreviation expansions so the linker hits the right concept
EXPAND = {
    "b12": "vitamin b12", "b-12": "vitamin b12", "vit b12": "vitamin b12", "b6": "vitamin b6",
    "d3": "vitamin d3", "vit d": "vitamin d", "vitamin d": "vitamin d", "coq10": "coenzyme q10",
    "co q10": "coenzyme q10", "ldn": "naltrexone", "nac": "acetylcysteine", "alcar": "acetyl-l-carnitine",
    "l-carnitine": "levocarnitine", "fish oil": "omega-3", "omega 3": "omega-3",
}
_STRIP = re.compile(r"\b(supplementation|supplements?|powder|capsules?|tablets?|daily|oral|"
                    r"high[- ]?dose|low[- ]?dose|extended[- ]?release|therapy|complex)\b")


def _clean(term: str) -> str:
    t = term.lower().strip()
    t = re.sub(r"\([^)]*\)", " ", t)              # drop parentheticals
    t = _STRIP.sub(" ", t)
    t = re.sub(r"[^a-z0-9+\-/ ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _get(url, tries=4):
    """GET with retry+backoff — RxNav rate-limits bursts, and a silent failure would look like a
    missed link. Returns None only after all retries fail."""
    for i in range(tries):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "pp"}), timeout=12))
        except Exception:
            time.sleep(0.4 * (i + 1))
    return None


def _link(term: str):
    """Return (rxcui, canonical_name) or (None, None). Exact first, then approximate >= 60."""
    t = _clean(term)
    t = EXPAND.get(t, t)
    if not t:
        return None, None
    cui = None
    d = _get("https://rxnav.nlm.nih.gov/REST/rxcui.json?name=" + urllib.request.quote(t))
    if d:
        ids = d.get("idGroup", {}).get("rxnormId", [])
        cui = ids[0] if ids else None
    if not cui:
        d = _get("https://rxnav.nlm.nih.gov/REST/approximateTerm.json?maxEntries=1&term=" + urllib.request.quote(t))
        if d:
            cand = d.get("approximateGroup", {}).get("candidate", [])
            try:
                if cand and float(cand[0].get("score", 0)) >= 60:
                    cui = cand[0]["rxcui"]
            except (TypeError, ValueError):
                pass
    if not cui:
        return None, None
    p = _get(f"https://rxnav.nlm.nih.gov/REST/rxcui/{cui}/property.json?propName=RxNorm%20Name")
    name = None
    if p:
        pc = p.get("propConceptGroup", {}).get("propConcept", [])
        name = pc[0].get("propValue") if pc else None
    return cui, (name.lower() if name else t)


def load_cache() -> dict:
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def _split(value) -> list:
    items = [value] if isinstance(value, str) else list(value or [])
    out = []
    for it in items:
        out.extend(re.split(r"[;,]", str(it)))
    return [x.strip() for x in out if x.strip()]


def canonical(term: str, cache: dict) -> str:
    """RxNorm concept name if the term links to a substance, else the cleaned surface form."""
    rec = cache.get(term.lower().strip())
    if rec and rec.get("name"):
        return rec["name"]
    return _clean(term) or term.lower().strip()


def fix_alt(value, cache: dict) -> list:
    out, seen = [], []
    for it in _split(value):
        c = canonical(it, cache)
        if c and c not in seen:
            seen.append(c); out.append(c)
    return out


def build_cache(terms):
    """Link every unique term and persist {term: {rxcui, name}}. Resumable."""
    cache = load_cache()
    # (re)link new terms AND any prior nulls (transient rate-limit failures look identical to real misses)
    todo = [t for t in terms if not cache.get(t.lower().strip(), {}).get("rxcui")]
    print(f"{len(cache)} cached; (re)linking {len(todo)} terms", flush=True)
    for i, t in enumerate(todo, 1):
        cui, name = _link(t)
        cache[t.lower().strip()] = {"rxcui": cui, "name": name}
        time.sleep(0.05)
        if i % 40 == 0:
            CACHE.write_text(json.dumps(cache, indent=0), encoding="utf-8")
            print(f"  linked {i}/{len(todo)}", flush=True)
    CACHE.write_text(json.dumps(cache, indent=0), encoding="utf-8")
    linked = sum(1 for v in cache.values() if v.get("rxcui"))
    print(f"done: {linked}/{len(cache)} terms linked to RxNorm", flush=True)
    return cache


if __name__ == "__main__":
    # build the cache from the corpus alt_treatments vocabulary
    cod = json.loads((ROOT / "data" / "validation" / "j11_coding_runs.json").read_text(encoding="utf-8"))
    uniq = set()
    for g in cod["gold"]:
        uniq.update(x.lower() for x in _split(g["fields"].get("alternative_treatments")))
    for c in cod["codings"]:
        uniq.update(x.lower() for x in _split(c["fields"].get("alternative_treatments")))
    build_cache(sorted(uniq))
