"""
run_j4_prefilter.py — Judgement ④ (prefilter) across the roster.

Prefilter is the binary keep/drop: does this (comment, drug) express the author's OWN personal experience?
Polina's `personal_use` column is the human reference — but it's degenerate (116 yes / 12 no ≈ 91% yes), so
recall is gameable by an always-yes model. So this is agreement + balanced-accuracy only, NOT accuracy: we
report cross-model α, per-model yes-rate, and balanced accuracy vs Polina with the base rate stated.

Output: data/validation/j4_prefilter_runs.json {manifest, results[], polina[]}
  result = {model, sample_id, drug, keep(bool), parse_failed}
"""
from __future__ import annotations
import argparse
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from utilities import get_client, LLM_TEMPERATURE, parse_json_array, LLMParseError
from roster_exec import parallel_map
from pipeline.classify import PREFILTER_PROMPT, _prefilter_block, _is_yes

IRR = ROOT / "data" / "irr_pilot"
OUT_DIR = ROOT / "data" / "validation"


def _bounded_prefilter(client, model, entry, drug, id_to_text, timeout=45.0):
    """Single-item prefilter call, returning (keep, parse_failed).

    PREFILTER_PROMPT asks for a JSON array, so a compliant model replies ["yes"] — which does NOT
    start with "yes". An earlier version applied _is_yes to the raw reply and so scored every
    model as dropping ~100% of pairs, invalidating the first ⑧ run of this judgement. Parse the
    array first; still accept a bare yes/no from a model that ignores the format.
    """
    msg = PREFILTER_PROMPT + "\nExpecting 1 answer.\n\n" + _prefilter_block(0, entry, drug, id_to_text)
    c = client.with_options(timeout=timeout, max_retries=1)
    try:
        try:
            m = c.messages.create(model=model, max_tokens=400, temperature=0,
                                  messages=[{"role": "user", "content": msg}])
        except anthropic.BadRequestError as e:
            if "temperature" in str(e).lower():
                m = c.messages.create(model=model, max_tokens=400, messages=[{"role": "user", "content": msg}])
            else:
                raise
        txt = "".join(getattr(b, "text", "") for b in m.content if getattr(b, "type", None) == "text")
        # An empty reply is a NON-ANSWER, not a "no". Reasoning models spend the token budget
        # internally and emit no text, which scored as a confident drop and made them look like
        # they rejected 100% of pairs. Count it as a parse failure so it can't masquerade as data.
        if not txt.strip():
            return None, True
        try:
            answers = parse_json_array(txt)
        except LLMParseError:
            stripped = txt.strip().lower()
            if stripped.startswith(("yes", "no")):
                return _is_yes(txt), False
            return None, True
        return (_is_yes(answers[0]) if answers else None), (not answers)
    except Exception:
        return None, True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--per-model", type=int, default=3)
    ap.add_argument("--out", type=Path, default=OUT_DIR / "j4_prefilter_runs.json")
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    client = get_client()
    pol = pd.read_csv(IRR / "human_coder_a.csv", dtype=str, keep_default_na=False)
    ci = pd.read_csv(IRR / "coding_input.csv", dtype=str, keep_default_na=False).set_index("sample_id")
    pol["pu"] = pol["personal_use"].str.strip().str.lower()
    lab = pol[pol.pu.str.startswith(("y", "n"))]   # any post with a personal_use judgement

    entries, pairs, polina = {}, [], []
    for _, r in lab.iterrows():
        s, drug = r["sample_id"], r["drug_mention_verbatim"].strip().lower()
        if s not in ci.index:
            continue
        row = ci.loc[s]
        if s not in entries:
            text = row["post_text"]
            if row["unit_type"] == "post" and str(row["title"]).strip():
                text = f"{row['title']}\n\n{text}"
            pid = None
            id_to_text = {}
            entries[s] = {"id": s, "text": text, "parent_id": pid, "author": "anon"}
        pairs.append((s, drug))
        polina.append({"sample_id": s, "drug": drug, "personal_use": r["pu"].startswith("y")})
    id_to_text = {s: e["text"] for s, e in entries.items()}
    print(f"{len(pairs)} (post,drug) pairs | {len(args.models)} models | temp={LLM_TEMPERATURE}", flush=True)

    partial = args.out.with_suffix(".partial.jsonl")
    if args.fresh and partial.exists():
        partial.unlink()
    done = set(); results = []
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line); results.append(r); done.add((r["model"], r["sample_id"], r["drug"]))
            except Exception:
                pass
    tasks = [(m, s, d) for m in args.models for (s, d) in pairs if (m, s, d) not in done]
    print(f"{len(done)} done; {len(tasks)} to run", flush=True)
    wlock = threading.Lock()

    def run_one(t):
        m, s, d = t
        keep, pf = _bounded_prefilter(client, m, entries[s], d, id_to_text)
        r = {"model": m, "sample_id": s, "drug": d, "keep": keep, "parse_failed": pf}
        with wlock, partial.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(r) + "\n")
        return r

    new = parallel_map(run_one, tasks, workers=args.workers, per_key=args.per_model,
                       key=lambda t: t[0], progress="prefilter", progress_every=100)
    results += [r for r in new if r]

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "judgement": "4_prefilter", "temperature": LLM_TEMPERATURE, "models": args.models,
        "n_pairs": len(pairs), "reference": "human_coder_a personal_use (degenerate: ~91% yes)",
    }
    args.out.write_text(json.dumps({"manifest": manifest, "results": results, "polina": polina}, indent=2),
                        encoding="utf-8")
    print(f"Wrote {args.out} ({len(results)} results)", flush=True)


if __name__ == "__main__":
    main()
