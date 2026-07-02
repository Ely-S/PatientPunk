"""Convert our LC Reddit JSONL dumps -> the hive-partitioned Parquet NATURAL's source pipeline ingests.

NATURAL's `sources/reddit/processing/contextualize.py` globs `source_dir/**/*.parquet`, parsing
`content_type={submissions|comments}` and `bucket={id}` from the path, and scans these exact schemas
(extra columns ignored):
  submissions: id:str, created_utc:int64, subreddit:str, title:str, selftext:str, author:str, score:f64
  comments:    id:str, link_id:str, created_utc:int64, subreddit:str, body:str, author:str, score:f64

Our JSONL already has all these fields (link_id is the `t3_<post>` form contextualize strips). We stream
line-by-line and write batched Parquet with pyarrow (polars binary is missing in this venv). bucket =
subreddit, so each subreddit's posts+comments share a bucket (the author-reply join is within a bucket).

Run: trial_superset/.venv/Scripts/python.exe trial_superset/convert_corpus.py
Output: <PatientPunk_data>/natural_corpus_parquet/content_type=*/bucket=*/part-0.parquet
"""

from __future__ import annotations

import json
import os

import pyarrow as pa
import pyarrow.parquet as pq

SRC = r"C:\Users\scgee\OneDrive\Documents\Projects\PatientPunk_data"
DEST = os.path.join(SRC, "natural_corpus_parquet")
BATCH = 100_000

# subreddit -> (posts jsonl, comments jsonl)
SUBREDDITS = {
    "covidlonghaulers": ("r_covidlonghaulers_posts_all.jsonl", "r_covidlonghaulers_comments_all.jsonl"),
    "LongCovid": ("r_LongCovid_posts.jsonl", "r_LongCovid_comments.jsonl"),
    "LongHaulersRecovery": ("r_LongHaulersRecovery_posts.jsonl", "r_LongHaulersRecovery_comments.jsonl"),
}

SUB_SCHEMA = pa.schema([("id", pa.string()), ("created_utc", pa.int64()), ("subreddit", pa.string()),
                        ("title", pa.string()), ("selftext", pa.string()), ("author", pa.string()),
                        ("score", pa.float64())])
COM_SCHEMA = pa.schema([("id", pa.string()), ("link_id", pa.string()), ("created_utc", pa.int64()),
                        ("subreddit", pa.string()), ("body", pa.string()), ("author", pa.string()),
                        ("score", pa.float64())])


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _str(v):
    return v if isinstance(v, str) else (None if v is None else str(v))


CASTERS = {"created_utc": _int, "score": _float}


def convert(jsonl_path: str, out_dir: str, schema: pa.Schema) -> int:
    cols = schema.names
    os.makedirs(out_dir, exist_ok=True)
    writer = pq.ParquetWriter(os.path.join(out_dir, "part-0.parquet"), schema)
    batch = {c: [] for c in cols}
    n = total = 0

    def flush():
        table = pa.table({c: pa.array(batch[c], type=schema.field(c).type) for c in cols}, schema=schema)
        writer.write_table(table)
        for c in cols:
            batch[c].clear()

    with open(jsonl_path, encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except Exception:
                continue
            for c in cols:
                batch[c].append(CASTERS.get(c, _str)(d.get(c)))
            n += 1
            total += 1
            if n >= BATCH:
                flush()
                n = 0
    if n:
        flush()
    writer.close()
    return total


def verify() -> None:
    """Confirm the output matches what contextualize.py globs + scans (schema + partition structure)."""
    from pathlib import Path
    found = {"submissions": 0, "comments": 0}
    buckets = set()
    ok = True
    for fp in Path(DEST).glob("**/*.parquet"):
        parts = dict(p.split("=") for p in str(fp).replace("\\", "/").split("/") if "=" in p)
        ct = parts.get("content_type")
        buckets.add(parts.get("bucket"))
        found[ct] = found.get(ct, 0) + pq.ParquetFile(fp).metadata.num_rows
        want = SUB_SCHEMA if ct == "submissions" else COM_SCHEMA
        got = pq.ParquetFile(fp).schema_arrow
        if [f.name for f in want] != [got.field(i).name for i in range(len(want))]:
            print(f"  SCHEMA MISMATCH in {fp}: {got.names}")
            ok = False
    print(f"\nverify: partitions parsed OK; buckets={sorted(buckets)}")
    print(f"  submissions rows={found['submissions']:,}  comments rows={found['comments']:,}")
    print(f"  schema matches NATURAL scan: {'YES' if ok else 'NO'}")


def main() -> None:
    for sub, (posts, comments) in SUBREDDITS.items():
        for jsonl, ct, schema in ((posts, "submissions", SUB_SCHEMA), (comments, "comments", COM_SCHEMA)):
            src = os.path.join(SRC, jsonl)
            if not os.path.exists(src):
                print(f"  [skip] {jsonl}")
                continue
            out = os.path.join(DEST, f"content_type={ct}", f"bucket={sub}")
            print(f"  {sub}/{ct}: {jsonl} ...")
            n = convert(src, out, schema)
            print(f"     wrote {n:,} rows -> {out}")
    verify()
    print(f"\n-> {DEST}  (point contextualize.py source_dir here)")


if __name__ == "__main__":
    main()
