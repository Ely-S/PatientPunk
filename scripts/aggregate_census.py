#!/usr/bin/env python3
"""Aggregate the full-census workflow labels into per-drug stats.

Candidate denominator is DB-driven from the FINAL alias lists (so the alias
refinement is applied here, not baked into the classification). For each
candidate post we look up its census label; candidates without a label are
written out as 'stragglers' to classify. Also validates against the 400
hand-labels (gold set).

    .venv/bin/python scripts/aggregate_census.py --db data/phoenixrising.db
"""
from __future__ import annotations
import argparse, json, math, re, sqlite3
from collections import Counter
from pathlib import Path

MAN = Path("outputs/manual")
FULL = MAN / "full"
Z = 1.96

DEFAULT_ALIAS_FILES = {
    "low-dose naltrexone (LDN)": Path("drugs/naltrexone.txt"),
    "pyridostigmine / Mestinon": Path("drugs/pyridostigmine.txt"),
}
# Full-dose (NOT low-dose) signals for naltrexone — flagged, reported separately.
FULLDOSE_RE = re.compile(r"\b(revia|vivitrol|full[- ]?dose|50\s?mg|50 ?mg)\b", re.I)


def alias_re(a): return re.compile(r"\b(?:" + "|".join(re.escape(x) for x in a) + r")\b", re.I)


def read_alias_file(path: Path) -> list[str]:
    aliases: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        aliases.append(line)
    return list(dict.fromkeys(aliases))


def wilson(k, n):
    if not n: return (0.0, 0.0)
    p = k / n; d = 1 + Z**2 / n
    c = (p + Z**2 / (2*n)) / d
    h = Z * math.sqrt(p*(1-p)/n + Z**2/(4*n**2)) / d
    return (max(0, c-h), min(1, c+h))


def load_loose(path: Path):
    t = path.read_text(encoding="utf-8").strip()
    if "```" in t:
        m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
        if m: t = m.group(1).strip()
    s, e = t.find("["), t.rfind("]") + 1
    return json.loads(t[s:e])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    args = ap.parse_args()
    aliases_by_label = {label: read_alias_file(path) for label, path in DEFAULT_ALIAS_FILES.items()}
    conn = sqlite3.connect(args.db)
    rows = conn.execute("SELECT post_id,title,parent_id,user_id,body_text FROM posts").fetchall()
    conn.close()
    byid = {r[0]: r for r in rows}
    def recon(r):
        _, title, par, _, body = r
        return (f"{title or ''} {body or ''}".strip()) if par is None else (body or "")
    def root_title(pid):
        r = byid.get(pid)
        while r and r[2] is not None: r = byid.get(r[2])
        return (r[1] if r else "") or ""
    text_by_id = {r[0]: recon(r) for r in rows}

    # Load ALL census labels written by the workflow agents.
    labelmap = {}
    files = sorted(FULL.glob("labels_*.json"))
    bad = []
    for f in files:
        try:
            for r in load_loose(f):
                if r.get("id"): labelmap[r["id"]] = r
        except Exception as e:  # noqa: BLE001
            bad.append(f"{f.name}: {e}")
    print(f"Census label files: {len(files)}  | labeled posts: {len(labelmap)}  | unparseable files: {len(bad)}")
    for b in bad: print("   BAD:", b)
    print()

    summary = {}
    for label, aliases in aliases_by_label.items():
        rx = alias_re(aliases)
        cand_ids = [pid for pid, txt in text_by_id.items() if rx.search(txt)]
        labeled = [labelmap[i] for i in cand_ids if i in labelmap]
        stragglers = [i for i in cand_ids if i not in labelmap]
        # write stragglers for a follow-up classify pass
        if stragglers:
            drug_key = "ldn" if "naltrexone" in label else "mestinon"
            sp = FULL / f"stragglers_{drug_key}.jsonl"
            with open(sp, "w", encoding="utf-8") as fo:
                for i in stragglers:
                    r = byid[i]
                    fo.write(json.dumps({"id": i, "drug": drug_key, "thread": root_title(i)[:120],
                                         "parent": (recon(byid[r[2]])[:220] if r[2] and r[2] in byid else ""),
                                         "text": text_by_id[i][:600]}, ensure_ascii=False) + "\n")

        n = len(labeled)
        sent = Counter(r.get("sentiment", "neutral") for r in labeled)
        pos, neg, mix, neu = sent["positive"], sent["negative"], sent["mixed"], sent["neutral"]
        exp = pos + neg + mix
        fulldose = sum(1 for i in cand_ids if FULLDOSE_RE.search(text_by_id[i]))
        se = Counter()
        for r in labeled:
            for s in (r.get("side_effects") or []):
                if s and len(s) > 2: se[s.lower()] += 1
        cond = Counter()
        for r in labeled:
            for c in (r.get("conditions") or []): cond[c.lower()] += 1
        lo, hi = wilson(pos, exp)

        summary[label] = {
            "candidate_posts": len(cand_ids), "labeled": n, "stragglers_unlabeled": len(stragglers),
            "experiential": exp, "neutral": neu, "positive": pos, "negative": neg, "mixed": mix,
            "pos_pct_exp": round(100*pos/exp, 1) if exp else None,
            "neg_pct_exp": round(100*neg/exp, 1) if exp else None,
            "mixed_pct_exp": round(100*mix/exp, 1) if exp else None,
            "pos_or_mixed_pct_exp": round(100*(pos+mix)/exp, 1) if exp else None,
            "pos_95ci": [round(100*lo, 1), round(100*hi, 1)],
            "posts_mentioning_50mg_or_fulldose": fulldose,
        }
        print("=" * 70)
        print(f"{label}  —  FULL CENSUS (final aliases)")
        print("=" * 70)
        print(f"  Candidate posts (new aliases): {len(cand_ids)}   | labeled: {n}   | unlabeled stragglers: {len(stragglers)}")
        print(f"  Personal-experience posts    : {exp}  ({100*exp/n:.0f}% of labeled)")
        if exp:
            print(f"    Positive : {pos:>4}  ({100*pos/exp:.0f}%)  [95% CI {100*lo:.0f}-{100*hi:.0f}%]")
            print(f"    Mixed    : {mix:>4}  ({100*mix/exp:.0f}%)")
            print(f"    Negative : {neg:>4}  ({100*neg/exp:.0f}%)")
            print(f"    Positive-or-mixed     : {100*(pos+mix)/exp:.0f}%")
        print(f"  Posts mentioning 50mg/full-dose/Revia/Vivitrol (flagged, not excluded): {fulldose}")
        print(f"  Top side effects: " + ", ".join(f"{k} ({v})" for k, v in se.most_common(12)))
        print(f"  Conditions: " + ", ".join(f"{k} ({v})" for k, v in cond.most_common(8)))
        print()

    # Gold-set agreement
    gold = {}
    for f in ["labels_ldn_b1.json", "labels_ldn_b2.json", "labels_mestinon_b1.json", "labels_mestinon_b2.json"]:
        p = MAN / f
        if p.exists():
            for r in json.loads(p.read_text()): gold[r["id"]] = r["sentiment"]
    overlap = [(g, labelmap[i]["sentiment"]) for i, g in gold.items() if i in labelmap]
    if overlap:
        ex = sum(1 for g, c in overlap if g == c)
        ben = lambda x: x in ("positive", "mixed")
        bn = sum(1 for g, c in overlap if ben(g) == ben(c))
        pv = sum(1 for g, c in overlap if (g == "positive") == (c == "positive"))
        print("=" * 70); print("VERIFICATION — census vs 400 hand-labels (gold)"); print("=" * 70)
        print(f"  Overlap: {len(overlap)}  | exact 4-class: {100*ex/len(overlap):.0f}%  | "
              f"benefit-vs-not: {100*bn/len(overlap):.0f}%  | positive-vs-not: {100*pv/len(overlap):.0f}%")
        summary["_validation"] = {"overlap": len(overlap),
                                  "exact_4class_pct": round(100*ex/len(overlap), 1),
                                  "benefit_vs_not_pct": round(100*bn/len(overlap), 1),
                                  "positive_vs_not_pct": round(100*pv/len(overlap), 1)}
    (MAN / "census_summary.json").write_text(json.dumps(summary, indent=2))
    print("\nWrote", MAN / "census_summary.json")


if __name__ == "__main__":
    main()
