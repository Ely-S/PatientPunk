#!/usr/bin/env python3
"""Export the FULL set of drug-mentioning posts (no sampling) into batch files
for a workflow census classification. Writes absolute-path batch JSONL files and
a manifest.json the orchestrator reads to fan out one agent per batch.

    .venv/bin/python scripts/export_full_for_classification.py --db data/phoenixrising.db --batch-size 60
"""
from __future__ import annotations
import argparse, json, re, sqlite3, datetime
from pathlib import Path

DRUG_FILES = {
    "ldn": Path("drugs/naltrexone.txt"),
    "mestinon": Path("drugs/pyridostigmine.txt"),
}


def alias_re(a): return re.compile(r"\b(?:" + "|".join(re.escape(x) for x in a) + r")\b", re.I)


def read_alias_file(path: Path) -> list[str]:
    aliases: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        aliases.append(line)
    return list(dict.fromkeys(aliases))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--batch-size", type=int, default=60)
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

    out_dir = (Path("outputs/manual/full")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []

    for name, alias_file in DRUG_FILES.items():
        aliases = read_alias_file(alias_file)
        rx = alias_re(aliases)
        cand = [r for r in rows if rx.search(recon(r))]
        recs = []
        for r in cand:
            pid, title, par, uid, body, date = r
            recs.append({
                "id": pid, "drug": name,
                "year": datetime.date.fromtimestamp(date).year if date else None,
                "thread": root_title(pid)[:120],
                "parent": (recon(byid[par])[:220] if par and par in byid else ""),
                "text": recon(r)[:600],
            })
        B = args.batch_size
        n_batches = (len(recs) + B - 1) // B
        for i in range(n_batches):
            chunk = recs[i * B:(i + 1) * B]
            in_path = out_dir / f"{name}_{i:03}.jsonl"
            out_path = out_dir / f"labels_{name}_{i:03}.json"
            with open(in_path, "w", encoding="utf-8") as f:
                for rec in chunk:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            manifest.append({"drug": name, "in": str(in_path), "out": str(out_path), "n": len(chunk)})
        print(f"{name}: {len(cand)} posts -> {n_batches} batches of {B}")

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Total batches: {len(manifest)}  |  manifest: {out_dir/'manifest.json'}")


if __name__ == "__main__":
    main()
