#!/usr/bin/env python3
"""Export a reproducible random sample of drug-mentioning posts for in-session
(no-API) sentiment classification. Each record carries the post text, its
immediate parent (for reply-chain context), and its thread title.

    .venv/bin/python scripts/export_for_manual_classification.py --db data/phoenixrising.db
"""
from __future__ import annotations
import argparse, json, random, re, sqlite3, datetime
from pathlib import Path

DRUGS = {
    "ldn":      (["naltrexone", "low dose naltrexone", "low-dose naltrexone", "ldn",
                  "naltrexona", "naltrexon", "naltrexene", "revia", "vivitrol"], 200),
    "mestinon": (["pyridostigmine", "mestinon", "pyridostigmine bromide",
                  "pyridostigmin", "regonol"], 200),
}
BATCH = 100
SEED = 42


def alias_re(aliases): return re.compile(r"\b(?:" + "|".join(re.escape(a) for a in aliases) + r")\b", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    args = ap.parse_args()
    conn = sqlite3.connect(args.db)
    rows = conn.execute("SELECT post_id,title,parent_id,user_id,body_text,post_date FROM posts").fetchall()
    conn.close()
    byid = {r[0]: r for r in rows}

    def recon(r):
        _, title, par, _, body, _ = r
        return (f"{title or ''} {body or ''}".strip()) if par is None else (body or "")

    def root_title(pid):
        r = byid.get(pid)
        while r and r[2] is not None:
            r = byid.get(r[2])
        return (r[1] if r else "") or ""

    out = Path("outputs/manual"); out.mkdir(parents=True, exist_ok=True)
    for name, (aliases, n) in DRUGS.items():
        rx = alias_re(aliases)
        cand = [r for r in rows if rx.search(recon(r))]
        random.seed(SEED)
        sample = cand if len(cand) <= n else random.sample(cand, n)
        recs = []
        for r in sample:
            pid, title, par, uid, body, date = r
            recs.append({
                "id": pid,
                "drug": name,
                "year": datetime.date.fromtimestamp(date).year if date else None,
                "thread": root_title(pid)[:120],
                "parent": (recon(byid[par])[:220] if par and par in byid else ""),
                "text": recon(r)[:600],
            })
        for i in range(0, len(recs), BATCH):
            bf = out / f"{name}_b{i // BATCH + 1}.jsonl"
            with open(bf, "w", encoding="utf-8") as f:
                for rec in recs[i:i + BATCH]:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"  wrote {bf}  ({len(recs[i:i+BATCH])} posts)")
        print(f"{name}: {len(cand)} direct-mention posts in corpus; sampled {len(sample)}.\n")


if __name__ == "__main__":
    main()
