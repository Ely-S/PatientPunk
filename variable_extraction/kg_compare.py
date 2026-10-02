"""Compare a claim-graph run against the flat extraction of the same posts.

    python kg_compare.py --db output_kg/kg.db
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from kg_prompts import CLAIM_TYPES
from kg_store import open_db

_ROOT = Path(__file__).parent.parent
DEFAULT_BASELINE = _ROOT / "output_deepseek_1000" / "records.csv"
DEFAULT_DB = _ROOT / "output_kg" / "kg.db"

META_COLS = {"author_hash", "source", "post_id", "text_count", "schema_id",
             "extraction_method", "extracted_at"}

_STOP = {"the", "a", "an", "of", "and", "or", "to", "in", "for", "with", "my", "i",
         "was", "is", "it", "on", "at", "no", "not", "yes", "unknown", "none", "n/a"}
_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> set[str]:
    # Numbers are kept at any length: ages ("34") and durations ("18") are exactly
    # the values a length filter would silently delete, faking a retention miss.
    return {t for t in _TOKEN.findall(text.lower())
            if (len(t) > 2 or t.isdigit()) and t not in _STOP}


def matches(value: str, haystack: set[str]) -> bool:
    """True if most content tokens of *value* appear in *haystack*."""
    tv = tokens(value)
    if not tv:
        return False
    return len(tv & haystack) / len(tv) >= 0.6


def cmd_compare(args: argparse.Namespace) -> None:
    conn = open_db(args.db)
    run_id = args.run_id or conn.execute(
        "SELECT run_id FROM runs ORDER BY run_at DESC LIMIT 1").fetchone()[0]

    baseline = {r["post_id"]: r for r in csv.DictReader(
        args.baseline.open(encoding="utf-8"))}
    fields = [c for c in next(iter(baseline.values())) if c not in META_COLS]

    # KG side, restricted to posts the baseline also covers.
    claims_by_post: dict[str, list[dict]] = defaultdict(list)
    for pid, ctype, span, payload_json in conn.execute(
            "SELECT post_id, claim_type, source_span, payload FROM claims"
            " WHERE run_id = ?", (run_id,)):
        if pid not in baseline:
            continue
        payload = json.loads(payload_json)
        primary = CLAIM_TYPES[ctype].primary_field()
        claims_by_post[pid].append({
            "type": ctype,
            "text": span + " " + " ".join(str(v) for v in payload.values()),
            "primary": str(payload.get(primary, "")),
        })
    processed = [r[0] for r in conn.execute(
        "SELECT post_id FROM post_status WHERE run_id = ? AND status = 'ok'", (run_id,))]
    posts = [p for p in processed if p in baseline]
    n = len(posts)
    if not n:
        sys.exit("No overlap between kg.db posts and the baseline records.csv.")

    # --- 1/2. yield + coverage ---
    kg_counts = [len(claims_by_post.get(p, [])) for p in posts]
    flat_counts = [sum(1 for f in fields if (baseline[p].get(f) or "").strip()) for p in posts]
    type_dist = Counter(c["type"] for p in posts for c in claims_by_post.get(p, []))

    # --- 3. per-field retention, split by whether the KG made any claim at all ---
    # A post where the KG abstained is not the same failure as a post where it
    # produced claims but dropped a value: abstention is usually the KG refusing to
    # attribute a study abstract / news repost to the author, which the flat schema does.
    retention: dict[str, list[int]] = defaultdict(list)   # engaged posts only
    abstain_cells: Counter = Counter()                    # field -> cells on abstained posts
    abstained = [p for p in posts if not claims_by_post.get(p)]
    for p in posts:
        claims = claims_by_post.get(p, [])
        # Scored against every claim on the post, not just the claim types a field
        # "should" land in: a hand-maintained field->type table has to be revisited
        # for every new claim type, and the match is lexical anyway.
        scope: set[str] = set()
        for c in claims:
            scope |= tokens(c["text"])
        for f in fields:
            cell = (baseline[p].get(f) or "").strip()
            if not cell:
                continue
            if not claims:
                abstain_cells[f] += 1
                continue
            retention[f].append(
                int(any(matches(v, scope) for v in cell.split(" | ") if v.strip())))

    # --- 4. new signal: claims with no counterpart in the baseline row ---
    novel: list[tuple[str, str, str]] = []
    n_novel = 0
    for p in posts:
        flat_tokens = tokens(" ".join(
            (baseline[p].get(f) or "") for f in fields))
        for c in claims_by_post.get(p, []):
            if c["primary"] and not matches(c["primary"], flat_tokens):
                n_novel += 1
                if len(novel) < 15:
                    novel.append((p, c["type"], c["primary"]))

    # --- 5/6/7. grounding, graph, cost ---
    grounded = conn.execute(
        "SELECT AVG(span_grounded) FROM claims WHERE run_id=?", (run_id,)).fetchone()[0] or 0
    rels = Counter(dict(conn.execute(
        "SELECT relation, COUNT(*) FROM claim_edges WHERE run_id=? GROUP BY 1", (run_id,))))
    n_edges = sum(rels.values())
    linked = conn.execute(
        "SELECT COUNT(DISTINCT c) FROM (SELECT from_claim AS c FROM claim_edges WHERE run_id=?"
        " UNION SELECT to_claim FROM claim_edges WHERE run_id=?)", (run_id, run_id)).fetchone()[0]
    n_claims = sum(kg_counts)
    n_facts = conn.execute(
        "SELECT COUNT(*) FROM claim_facts WHERE run_id=?", (run_id,)).fetchone()[0]
    failed = conn.execute(
        "SELECT COUNT(*) FROM post_status WHERE run_id=? AND status='failed'",
        (run_id,)).fetchone()[0]

    ret_rows = sorted(
        ((f, sum(v) / len(v), len(v)) for f, v in retention.items() if v),
        key=lambda r: r[1])

    lines = []
    add = lines.append
    add(f"# Knowledge graph vs flat extraction (run_id={run_id})\n")
    add(f"- posts compared: **{n}** (baseline `{args.baseline.name}`, same posts, same model)")
    add(f"- failed posts: {failed}\n")
    add("## 1. Yield per post\n")
    add("| | claims / filled cells per post |")
    add("|---|---|")
    add(f"| KG claims   | mean **{statistics.mean(kg_counts):.2f}**, "
        f"median {statistics.median(kg_counts):.0f}, max {max(kg_counts)} |")
    add(f"| flat fields | mean **{statistics.mean(flat_counts):.2f}**, "
        f"median {statistics.median(flat_counts):.0f}, max {max(flat_counts)} "
        f"(of {len(fields)} possible) |")
    add(f"\nTuples in the store: **{n_facts}** facts across {n_claims} claims "
        f"({n_facts / max(n, 1):.2f} per post).\n")
    add("Claims by type:\n")
    for t, c in type_dist.most_common():
        add(f"- `{t}`: {c} ({c / max(n_claims, 1) * 100:.0f}%)")
    add("\n## 2. Post coverage\n")
    add(f"- posts with >=1 claim: **{sum(1 for c in kg_counts if c) / n * 100:.1f}%**")
    add(f"- posts with >=1 filled flat field: {sum(1 for c in flat_counts if c) / n * 100:.1f}%")
    add(f"- posts where the KG abstained entirely: {len(abstained)} "
        f"({len(abstained) / n * 100:.1f}%), carrying {sum(abstain_cells.values())} "
        f"baseline cells\n")
    add("## 3. Baseline retention per flat field, on posts where the KG engaged (worst first)\n")
    add("Does the value the flat schema recorded still exist somewhere in the claims for that"
        " post? Restricted to the "
        f"{n - len(abstained)} posts with >=1 claim -- abstentions are counted separately in"
        " section 3b, because the KG is instructed to claim only about the AUTHOR and refuses"
        " posts (study abstracts, news reposts) the flat schema attributes anyway.\n")
    add("Retention is a LOWER BOUND: the match is lexical (>=60% of the cell's content"
        " tokens present in the claim), so a claim that says the same thing in the author's"
        " words ('couldn't leave the house' vs `social_impact: isolation`) scores as a miss.\n")
    add("| field | retained | n non-empty |")
    add("|---|---|---|")
    for f, rate, cnt in ret_rows:
        add(f"| {f} | {rate * 100:.0f}% | {cnt} |")
    overall = sum(sum(v) for v in retention.values()) / max(
        sum(len(v) for v in retention.values()), 1)
    add(f"\n**Overall retention: {overall * 100:.1f}%** of non-empty baseline cells on"
        " engaged posts.\n")
    add("### 3b. Baseline cells on posts the KG abstained from\n")
    add("Each of these is either a real KG miss or a baseline over-attribution."
        " Sample the posts before deciding.\n")
    add("| field | cells lost to abstention |")
    add("|---|---|")
    for f, c in abstain_cells.most_common(15):
        add(f"| {f} | {c} |")
    add("\nAbstained posts to eyeball: "
        + ", ".join(f"`{p}`" for p in abstained[:10]) + "\n")
    add("## 4. New signal\n")
    add(f"- claims with no counterpart anywhere in the baseline row: **{n_novel}** "
        f"({n_novel / max(n_claims, 1) * 100:.0f}% of claims, {n_novel / n:.2f} per post)\n")
    add("Samples:\n")
    for p, t, txt in novel:
        add(f"- `{p}` [{t}] {txt[:180]}")
    add("\n## 5. Grounding\n")
    add(f"- claims whose `source_span` is verbatim in the post: **{grounded * 100:.1f}%**\n")
    add("## 6. Graph\n")
    add(f"- edges: {n_edges} ({n_edges / n:.2f} per post); "
        f"claims in >=1 edge: {linked / max(n_claims, 1) * 100:.0f}%")
    for r, c in rels.most_common():
        add(f"  - `{r}`: {c}")
    add("")

    report = "\n".join(lines)
    print("\n" + report)
    out_md = args.out or args.db.parent / "kg_vs_flat.md"
    out_md.write_text(report, encoding="utf-8")
    out_csv = out_md.with_suffix(".csv")
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["field", "retention", "n_nonempty", "baseline_fill_rate"])
        for f, rate, cnt in ret_rows:
            w.writerow([f, round(rate, 3), cnt, round(cnt / n, 3)])
    print(f"  Wrote {out_md}\n  Wrote {out_csv}")



def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    ap.add_argument("--run-id", type=int, default=None)
    ap.add_argument("--out", type=Path, default=None)
    cmd_compare(ap.parse_args())


if __name__ == "__main__":
    main()
