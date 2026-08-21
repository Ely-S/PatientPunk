"""Extract one subreddit from Arctic Shift monthly all-Reddit dumps.

The monthly dumps (RC_YYYY-MM.zst = comments, RS_YYYY-MM.zst = submissions) hold
every subreddit, so a single subreddit is ~0.01% of the bytes. This streams each
archive, keeps only the matching lines, and never holds a decompressed month on
disk -- so peak usage is one compressed archive, not the whole run.

    pip install zstandard
    python Scrapers/filter_monthly_dumps.py --dumps D:/dumps --out r_nootropics_comments_2019on.jsonl
    python Scrapers/filter_monthly_dumps.py --dumps D:/dumps --out noots.jsonl --delete-after

Filters on subreddit_id by default (t5_2r81c = r/Nootropics). The id survives
renames and capitalisation changes; the name does not.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def open_zst(path: Path):
    """Line iterator over a .zst archive.

    max_window_size must be raised: these dumps are written with a long-distance
    window and the default ceiling raises "frame requires too much memory".
    """
    import zstandard as zstd

    fh = path.open("rb")
    dctx = zstd.ZstdDecompressor(max_window_size=2**31)
    return io.BufferedReader(dctx.stream_reader(fh), buffer_size=2**24)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dumps", required=True, type=Path,
                    help="Directory holding RC_*.zst / RS_*.zst monthly archives")
    ap.add_argument("--out", required=True, type=Path, help="Output .jsonl")
    ap.add_argument("--subreddit-id", default="t5_2r81c",
                    help="Reddit fullname of the target sub (default: r/Nootropics)")
    ap.add_argument("--subreddit-name", default="Nootropics",
                    help="Fallback match for archives predating subreddit_id")
    ap.add_argument("--kind", choices=["RC", "RS", "both"], default="RC",
                    help="RC=comments, RS=submissions (default: RC)")
    ap.add_argument("--delete-after", action="store_true",
                    help="Delete each archive once filtered. Frees disk as you go; "
                         "you cannot re-run without re-downloading.")
    args = ap.parse_args()

    prefixes = ("RC_", "RS_") if args.kind == "both" else (args.kind + "_",)
    archives = sorted(p for p in args.dumps.glob("*.zst")
                      if p.name.startswith(prefixes))
    if not archives:
        sys.exit(f"No {'/'.join(prefixes)}*.zst found in {args.dumps}")

    # Cheap bytes test before JSON parsing: ~99.99% of lines fail it, and
    # json.loads on every line of a 50 GB month is the whole runtime.
    needles = [f'"subreddit_id":"{args.subreddit_id}"'.encode(),
               f'"subreddit":"{args.subreddit_name}"'.encode()]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with args.out.open("wb") as out:
        for arc in archives:
            kept = seen = 0
            try:
                for line in open_zst(arc):
                    seen += 1
                    if not any(n in line for n in needles):
                        continue
                    try:
                        o = json.loads(line)
                    except Exception:
                        continue
                    if (o.get("subreddit_id") == args.subreddit_id
                            or o.get("subreddit") == args.subreddit_name):
                        out.write(line if line.endswith(b"\n") else line + b"\n")
                        kept += 1
            except Exception as e:
                print(f"  !! {arc.name}: {type(e).__name__}: {e}", flush=True)
                continue
            total += kept
            out.flush()
            print(f"  {arc.name:20s} {seen:>12,} scanned  {kept:>7,} kept  "
                  f"(running total {total:,})", flush=True)
            if args.delete_after:
                arc.unlink()

    print(f"\nWrote {total:,} records to {args.out}")


if __name__ == "__main__":
    main()
