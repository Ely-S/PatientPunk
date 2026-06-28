"""LEVER #1 — mine NON-CT.gov registries (ISRCTN, EudraCT) for Long-COVID RCTs.

Standalone explorer, deliberately separate from the CT.gov pipeline. NATURAL is CT.gov-only;
this finds Long-COVID randomized trials registered elsewhere (the UK runs many on ISRCTN) that
the literature references but our NCT-only harvest ignored. Output is a *candidate* CSV for review
— it does NOT inject into the training set (these records aren't CT.gov JSON; wiring them into her
Study would need a schema adapter, a separate decision).

Pipeline:
  1. harvest ISRCTN + EudraCT ids from Europe PMC Long-COVID RCT papers (tracking which paper cites each)
  2. fetch each ISRCTN record from the ISRCTN API (structured XML — no LLM needed)
  3. keep interventional + randomized + patient + genuinely-Long-COVID; tag intervention type
  4. EudraCT ids are recorded but NOT fetched (EU CTR has no clean API — HTML scrape, future work)

Run: PYTHONPATH=trial_superset trial_superset/.venv/Scripts/python.exe -m mine_registries
Output: data/mined_registries.csv
"""

from __future__ import annotations

import csv
import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests

OUT = "trial_superset/data/mined_registries.csv"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
ISRCTN_API = "https://www.isrctn.com/api/query/format/default"
LC_TOKENS = ("long covid", "long-covid", "post-covid", "post covid", "postcovid", "pasc",
             "post-acute covid", "post-acute sequelae", "long-haul", "long haul", "post-acute sars")
HEADERS = {"accept": "application/xml", "user-agent": "trial_superset-research/1.0"}


def is_long_covid(text: str) -> bool:
    t = (text or "").lower()
    return any(tok in t for tok in LC_TOKENS)


def harvest_ids() -> tuple[dict[str, set], dict[str, set]]:
    """{ISRCTN id -> {citing pmcids}}, {EudraCT id -> {citing pmcids}} from LC RCT papers."""
    isrctn: dict[str, set] = {}
    eudract: dict[str, set] = {}
    for query in ['"long covid" AND (randomized OR randomised OR placebo)',
                  '("post-covid" OR "post-acute covid" OR PASC) AND (randomized OR randomised)']:
        cur = "*"
        for _ in range(3):
            d = requests.get(EPMC, params={"query": query, "format": "json", "pageSize": "1000",
                                           "cursorMark": cur, "resultType": "core"}, timeout=120).json()
            for x in d.get("resultList", {}).get("result", []):
                pmcid = x.get("pmcid") or x.get("id")
                blob = (x.get("abstractText", "") or "") + " " + (x.get("title", "") or "")
                for m in re.findall(r"ISRCTN\d{8}", blob):
                    isrctn.setdefault(m, set()).add(pmcid)
                for m in re.findall(r"\b20\d\d-\d{6}-\d\d\b", blob):
                    eudract.setdefault(m, set()).add(pmcid)
            nc = d.get("nextCursorMark")
            if not nc or nc == cur:
                break
            cur = nc
    return isrctn, eudract


def _tag(xml: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, re.S)
    return re.sub(r"<[^>]+>", " ", m.group(1)).strip() if m else ""


def fetch_isrctn(trial_id: str) -> dict | None:
    """Fetch + parse one ISRCTN record. Returns structured fields, or None on failure."""
    for attempt in range(3):
        try:
            r = requests.get(ISRCTN_API, params={"q": trial_id}, headers=HEADERS, timeout=60)
            if r.status_code == 200 and "<title" in r.text:
                xml = r.text
                title = _tag(xml, "title")
                cond = _tag(xml, "condition")
                interv = _tag(xml, "intervention")
                return {
                    "trial_id": trial_id, "registry": "ISRCTN",
                    "title": title[:140],
                    "interventional": "interventional" in _tag(xml, "primaryStudyDesign").lower(),
                    "randomized": "randomi" in _tag(xml, "studyDesign").lower(),
                    "participant_type": _tag(xml, "participantType")[:40],
                    "intervention_type": _tag(xml, "interventionType")[:40],
                    "condition": cond[:80],
                    "looks_long_covid": is_long_covid(title + " " + cond + " " + interv),
                }
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return None


def main() -> None:
    isrctn, eudract = harvest_ids()
    print(f"harvested from LC RCT papers: {len(isrctn)} ISRCTN ids, {len(eudract)} EudraCT ids")

    records = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for rec, (tid, papers) in zip(ex.map(fetch_isrctn, isrctn), isrctn.items()):
            if rec is None:
                records.append({"trial_id": tid, "registry": "ISRCTN", "fetch_ok": False,
                                "source_papers": ";".join(sorted(p for p in papers if p))})
                continue
            rec["fetch_ok"] = True
            rec["source_papers"] = ";".join(sorted(p for p in papers if p))
            rec["usable"] = bool(rec["interventional"] and rec["randomized"]
                                 and rec["looks_long_covid"]
                                 and "healthy" not in rec["participant_type"].lower())
            records.append(rec)
    # EudraCT: recorded only (no clean API)
    for tid, papers in eudract.items():
        records.append({"trial_id": tid, "registry": "EudraCT", "fetch_ok": False,
                        "note": "EU CTR has no API — HTML scrape / WHO ICTRP lookup needed (future)",
                        "source_papers": ";".join(sorted(p for p in papers if p))})

    cols = ["trial_id", "registry", "fetch_ok", "usable", "looks_long_covid", "interventional",
            "randomized", "participant_type", "intervention_type", "condition", "title",
            "source_papers", "note"]
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in sorted(records, key=lambda r: (not r.get("usable", False), r["registry"])):
            w.writerow(r)

    usable = [r for r in records if r.get("usable")]
    drugs = [r for r in usable if "drug" in (r.get("intervention_type", "") or "").lower()]
    print(f"\nISRCTN fetched ok: {sum(1 for r in records if r.get('fetch_ok'))}/{len(isrctn)}")
    print(f"USABLE (interventional + randomized + patient + Long-COVID): {len(usable)}  (of which drug: {len(drugs)})")
    print(f"EudraCT ids recorded (not fetched): {len(eudract)}")
    print(f"-> {OUT}")
    print("\nusable ISRCTN drug trials (corpus-relevant):")
    for r in drugs[:15]:
        print(f"   {r['trial_id']}  {r['intervention_type']:14s} {r['title'][:55]}")


if __name__ == "__main__":
    main()
