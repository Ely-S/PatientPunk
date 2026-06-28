"""LEVER #2 — mine SYSTEMATIC REVIEWS / meta-analyses for Long-COVID trial labels.

Standalone explorer, deliberately separate from both the CT.gov pipeline and the registry miner.
A good Long-COVID-interventions review ships an evidence table that already lists every included
RCT *and* extracts its per-arm primary result — curated by domain experts. That is strictly better
signal than scraping individual papers: it finds the trials and hands us vetted outcomes in one pass.

Pipeline:
  1. find OA Long-COVID *intervention* systematic reviews / meta-analyses in Europe PMC
  2. fetch each review's full text, LLM-extract its included-RCT evidence table
  3. emit one row per (review, included trial) with trial id, intervention, outcome, reported result
  4. flag which trial ids we already have (CT.gov) vs are NEW

Output is a *candidate* CSV for review — it does NOT auto-inject into the training set (a human
should confirm the review's extraction before these become labels).

Run: PYTHONPATH=trial_superset trial_superset/.venv/Scripts/python.exe -m mine_reviews
Output: data/mined_reviews.csv
"""

from __future__ import annotations

import csv
import glob
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

from litlabels import europe_pmc
from litlabels.extract_labels import _client, MODEL, relevant_fulltext, _parse_json

OUT = "trial_superset/data/mined_reviews.csv"
MAX_REVIEWS = 15

PROMPT = """You are reading the full text of a systematic review / meta-analysis of interventions for \
Long COVID (post-acute sequelae of COVID-19). Extract its evidence table: every INCLUDED randomized \
controlled trial and the primary result the review reports for it.

Return ONLY a JSON object: {"is_long_covid_intervention_review": true/false, "trials": [ ... ]}.
Each trial: {
  "trial_id": "registry id if given (NCT.../ISRCTN.../EudraCT...) else ''",
  "study_label": "first author + year, e.g. 'Smith 2023'",
  "intervention": "the experimental treatment",
  "comparator": "control/comparator",
  "primary_outcome": "the outcome the review reports for this trial",
  "result": "the reported effect — direction + number if given (e.g. 'MD -1.2 fatigue', 'OR 0.6', 'no difference')",
  "n_total": integer or null,
  "favors": "intervention" | "comparator" | "no_difference" | "unclear"
}
Only INCLUDED primary RCTs (not other reviews they cite, not observational studies). If this is not a \
Long-COVID intervention review, return is_long_covid_intervention_review=false and an empty trials list."""


def find_reviews() -> list[tuple[str, str]]:
    q = ('"long covid" AND (intervention OR treatment OR therapy OR rehabilitation) '
         'AND (PUB_TYPE:"systematic-review" OR PUB_TYPE:"Meta-Analysis") AND OPEN_ACCESS:y AND IN_EPMC:y')
    res = europe_pmc.search(q, page_size=MAX_REVIEWS).get("resultList", {}).get("result", [])
    return [(x["pmcid"], x.get("title", "")[:90]) for x in res if x.get("pmcid")]


def mine_review(item: tuple[str, str]) -> list[dict]:
    pmcid, title = item
    xml = europe_pmc.fulltext_xml("PMC", pmcid)
    if not xml:
        return []
    # systematic reviews mostly cite included trials by author-year, not registry id; capture the
    # few that ARE embedded in the full text so they aren't lost (they're directly linkable).
    embedded = ";".join(sorted(set(re.findall(r"NCT\d{8}|ISRCTN\d{8}", xml))))
    text = relevant_fulltext(xml)[:45000]
    try:
        resp = _client().chat.completions.create(
            model=MODEL, temperature=0,
            messages=[{"role": "user", "content": PROMPT + "\n\n=== REVIEW FULL TEXT ===\n" + text}],
        )
        data = _parse_json(resp.choices[0].message.content)
    except Exception as e:
        print(f"   {pmcid}: error {str(e)[:70]}")
        return []
    if not data or not data.get("is_long_covid_intervention_review"):
        return []
    rows = []
    for t in data.get("trials", []):
        if not isinstance(t, dict):
            continue
        rows.append({"review_pmcid": pmcid, "review_title": title,
                     "trial_id": (t.get("trial_id") or "").strip(),
                     "study_label": (t.get("study_label") or "")[:40],
                     "intervention": (t.get("intervention") or "")[:50],
                     "comparator": (t.get("comparator") or "")[:40],
                     "primary_outcome": (t.get("primary_outcome") or "")[:70],
                     "result": (t.get("result") or "")[:70],
                     "n_total": t.get("n_total"), "favors": (t.get("favors") or "")[:14],
                     "review_embedded_ids": embedded})
    return rows


def main() -> None:
    reviews = find_reviews()
    print(f"found {len(reviews)} OA Long-COVID intervention reviews; mining evidence tables ({MODEL})")
    all_rows = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        for rows in ex.map(mine_review, reviews):
            all_rows.extend(rows)

    # which referenced trial ids do we already have? (any locally downloaded NCT)
    have = {os.path.basename(p)[:-5] for p in glob.glob("trial_superset/data/**/NCT*.json", recursive=True)}
    for r in all_rows:
        tid = r["trial_id"].upper()
        r["already_have"] = tid in have if tid.startswith("NCT") else ""
        r["registry"] = ("CT.gov" if tid.startswith("NCT") else "ISRCTN" if tid.startswith("ISRCTN")
                         else "EudraCT" if re.match(r"20\d\d-\d{6}", tid) else "none/unlinked")

    cols = ["review_pmcid", "registry", "trial_id", "already_have", "study_label", "intervention",
            "comparator", "primary_outcome", "result", "favors", "n_total", "review_embedded_ids",
            "review_title"]
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader(); w.writerows(all_rows)

    with_id = [r for r in all_rows if r["trial_id"]]
    embedded = set()
    for r in all_rows:
        embedded |= {i for i in (r.get("review_embedded_ids") or "").split(";") if i}
    new_embedded = {i for i in embedded if i.startswith("NCT") and i not in have}
    print(f"\nextracted {len(all_rows)} included-trial rows from {len({r['review_pmcid'] for r in all_rows})} usable reviews")
    print(f"   rows the LLM tagged with a registry id: {len(with_id)} (reviews mostly cite by author-year)")
    print(f"   registry ids embedded anywhere in review full text: {len(embedded)} | NEW vs our set: {sorted(new_embedded)}")
    print(f"   -> rows without a linkable id are WEAK LABELS (intervention -> outcome direction), not structured trials")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
