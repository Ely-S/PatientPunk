"""
build_f1_vocab.py — Build the F1 multi-treatment vocabulary fixture (prereq F1).

Judgement 5 (attribution) needs to know which posts mention >=2 treatments — that
is where group-attribution bias can inflate the "helped" rate, by crediting one
post's outcome to every drug in a stack. The production pipeline only tagged the 6
target RCT drugs, so "post with >=2 targets" (419 posts) undercounts the real
multi-treatment population ~13.6x.

F1 replaces that with the FULL per-post treatment set, anchored on Opus's IRR
extraction and cross-checked by the other 17 coders (2 humans + 15 other models):
a treatment is in a post's vocabulary if >=2 coders independently found it after
canonicalization — so a single coder's hallucination is dropped, and Opus's finding
counts as one corroborating vote. This is the "Opus's extraction, model-checked"
fixture the plan calls for, built from data already on disk (no new API spend).

Output: data/irr_pilot/f1_treatment_vocab.json
  { sample_id: { treatments: [...], n_treatments, is_multi_treatment,
                 opus_terms: [...], n_coders } }

Usage:
    python scripts/build_f1_vocab.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import compute_alphas as ca  # canonical loaders + canonicalization + de-id

# Opus is one of the IRR coders; its slug passes through de-identification unchanged.
OPUS_CODER = "anthropic/claude-opus-4.1"
MIN_CORROBORATION = 2  # a treatment must be found by >=2 coders to enter the vocab


def build_vocab(irr_dir: Path, db_path: Path) -> dict:
    raw = ca.load_all_coders(irr_dir)          # de-identified coder_ids
    lookup = ca.build_canonical_lookup(db_path)
    df = ca.build_merged(raw, lookup)          # + canonical_drug, drops error/empty rows
    df = df[df["canonical_drug"] != "__NONE__"]  # "__NONE__" = coder found no treatment

    vocab: dict = {}
    for sample_id, grp in df.groupby("sample_id"):
        by_coder = grp.groupby("coder_id")["canonical_drug"].apply(lambda s: set(s))
        opus = set(by_coder.get(OPUS_CODER, set()))
        counts: Counter = Counter()
        for coder_set in by_coder:
            counts.update(coder_set)
        # Corroborated treatments (Opus's vote counts as one of the >=2).
        terms = sorted(t for t, n in counts.items() if n >= MIN_CORROBORATION)
        vocab[str(sample_id)] = {
            "treatments": terms,
            "n_treatments": len(terms),
            "is_multi_treatment": len(terms) >= 2,
            "opus_terms": sorted(opus),
            "n_coders": int(len(by_coder)),
        }
    return vocab


def main():
    irr_dir, db_path = ca.IRR_DIR, ca.DB_PATH
    vocab = build_vocab(irr_dir, db_path)

    out = irr_dir / "f1_treatment_vocab.json"
    out.write_text(json.dumps(vocab, indent=2), encoding="utf-8")

    n_multi = sum(v["is_multi_treatment"] for v in vocab.values())
    total_mentions = sum(v["n_treatments"] for v in vocab.values())
    dist = Counter(v["n_treatments"] for v in vocab.values())
    print(f"Wrote {out}")
    print(f"{len(vocab)} samples with >=1 corroborated treatment")
    print(f"{n_multi} multi-treatment posts (>=2 treatments) — the judgement-5 universe")
    print(f"{total_mentions} corroborated treatment-mentions total")
    print("n_treatments distribution:", dict(sorted(dist.items())))


if __name__ == "__main__":
    main()
