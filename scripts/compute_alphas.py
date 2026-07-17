"""
Compute intercoder reliability for the IRR pilot.

Reads every ai_coder_*.csv and human_coder_*.csv in data/irr_pilot/,
canonicalizes drug names against the pipeline's treatment table, pivots
into a (unit × coder) matrix, and computes Krippendorff's α for each of
the four comparison fields:
    - personal_use    (binary: yes/no)
    - sentiment       (nominal, on personal_use=yes subset)
    - signal_strength (nominal, on personal_use=yes subset)
    - drug_extracted  (nominal: for each sample, what canonical drug set
                       did the coder extract? — extraction agreement)

Outputs:
    - data/irr_pilot/alpha_report.txt  (human-readable summary)
    - data/irr_pilot/alpha_pairwise.csv (pairwise α matrix per field)
    - data/irr_pilot/merged_long.csv (all coders in long format, for audit)

Usage:
    python scripts/compute_alphas.py
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

# --- encoding hygiene for Windows consoles ---
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

IRR_DIR = Path("data/irr_pilot")
DB_PATH = Path("data/patientpunk.db")


# ── Label + identity normalization (canonical / reconciled — prereq P4) ───────
# This is the single canonical α implementation. It supersedes
# scripts/compute_irr_all_pairs.py: that script's typo-normalization is folded in
# below, and its plaintext human-coder names ("Polina", "Shaun") are dropped in
# favour of the pseudonymous coder_ids already in the CSVs ("Coder A"/"Coder B").
#
# Human coders and models share the same free-text typos, so the scorer must
# normalise the reference exactly as it normalises model output — otherwise
# "postive" vs "positive" reads as disagreement and deflates α (plan §1).
SENT_FIX = {"postive": "positive", "positve": "positive", "posistive": "positive",
            "negaive": "negative", "mixe": "mixed"}
SIG_FIX = {"week": "weak", "wek": "weak", "medium": "moderate", "mod": "moderate"}
PU_FIX = {"y": "yes", "n": "no", "true": "yes", "false": "no"}

# Signal strength is ordinal — declare the ordering once (weak < moderate < strong).
SIGNAL_ORDER = ["weak", "moderate", "strong"]

_DEID_SALT = "patientpunk-irr"  # stable within-project salt; not a secret


def deidentify_coder_id(coder_id: str) -> str:
    """Map a coder label to a non-identifying token.

    Model slugs (contain '/'), already-pseudonymous 'Coder X' labels, and
    'ai_*' tokens pass through unchanged; anything that looks like a real name
    is hashed to a stable 'human-<hash8>' so no committed artifact carries a
    person's name (prereq P4 — the plaintext-coder-name fix)."""
    s = str(coder_id).strip()
    low = s.lower()
    if "/" in s or low.startswith("coder ") or low.startswith("ai_") or low.startswith("human-"):
        return s
    return "human-" + hashlib.sha256((_DEID_SALT + low).encode()).hexdigest()[:8]


def hash_post_id(post_id: str) -> str:
    """Stable, non-reversible hash of a raw post/comment id — for any artifact
    that would otherwise carry Reddit ids (e.g. the P2 audit-sink output).
    The unhashed-post-id fix: notebooks persist hash_post_id(id), never the id."""
    return hashlib.sha256((_DEID_SALT + str(post_id)).encode()).hexdigest()[:12]


# ── Canonicalization ────────────────────────────────────────────────────────


def build_canonical_lookup(db_path: Path) -> dict[str, str]:
    """Return {lowercase_verbatim_or_alias: canonical_name} from treatment table."""
    if not db_path.exists():
        print(f"WARN: {db_path} not found — skipping canonicalization; using verbatim.")
        return {}
    conn = sqlite3.connect(str(db_path))
    lookup: dict[str, str] = {}
    for canonical, aliases_json in conn.execute(
        "SELECT canonical_name, aliases FROM treatment"
    ).fetchall():
        if canonical:
            lookup[canonical.lower()] = canonical
        if aliases_json:
            try:
                for a in json.loads(aliases_json):
                    if a:
                        lookup[a.lower()] = canonical
            except (json.JSONDecodeError, TypeError):
                pass
    conn.close()
    return lookup


def canonicalize(s: str | None, lookup: dict[str, str]) -> str | None:
    """Map a verbatim drug string to a canonical name, or pass through lowercase."""
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    if s.upper() == "NONE":
        return "__NONE__"
    key = s.lower()
    return lookup.get(key, key)


# ── Loading coder data ──────────────────────────────────────────────────────


def load_coder_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    # Normalize column types
    df = df.fillna("")
    for col in ["personal_use", "sentiment", "signal_strength"]:
        if col in df.columns:
            df[col] = df[col].str.strip().str.lower().replace({"nan": ""})
    # Typo/vocabulary normalization — applied to every coder (models AND humans)
    # so shared typos don't count as disagreement (prereq P4 / plan §1).
    if "sentiment" in df.columns:
        df["sentiment"] = df["sentiment"].map(lambda v: SENT_FIX.get(v, v))
    if "signal_strength" in df.columns:
        df["signal_strength"] = df["signal_strength"].map(lambda v: SIG_FIX.get(v, v))
    if "personal_use" in df.columns:
        df["personal_use"] = df["personal_use"].map(lambda v: PU_FIX.get(v, v))
    df["drug_mention_verbatim"] = df["drug_mention_verbatim"].str.strip()
    # De-identify the coder label (models pass through; real names are hashed).
    df["coder_id"] = df["coder_id"].str.strip().map(deidentify_coder_id)
    return df


def load_all_coders(irr_dir: Path) -> pd.DataFrame:
    """Merge every ai_coder_*.csv and human_coder_*.csv into one long DataFrame."""
    files = list(irr_dir.glob("ai_coder_*.csv")) + list(irr_dir.glob("human_coder_*.csv"))
    # Exclude the production pipeline's first-20 reformat if it's lying around
    files = [f for f in files if f.name != "ai_coder_first20.csv"]
    if not files:
        raise SystemExit(f"No coder CSVs found in {irr_dir}")
    print(f"Loading {len(files)} coder files:")
    frames = []
    for f in files:
        df = load_coder_csv(f)
        if df.empty:
            print(f"  {f.name:60s} (empty — skipped)")
            continue
        print(f"  {f.name:60s} {len(df):>5} rows, "
              f"{df['coder_id'].nunique()} coder_id(s)")
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


# ── Long-format merged table ────────────────────────────────────────────────


def build_merged(df: pd.DataFrame, lookup: dict[str, str]) -> pd.DataFrame:
    """Add canonical_drug column, drop error/empty rows, return the tidy frame."""
    df = df.copy()
    df["canonical_drug"] = df["drug_mention_verbatim"].apply(
        lambda s: canonicalize(s, lookup)
    )
    # Drop rows where the coder errored out (notes contain [API/PARSE ERROR])
    if "notes" in df.columns:
        err_mask = df["notes"].str.contains(r"\[(?:API|PARSE).*ERROR", regex=True, na=False)
        n_err = err_mask.sum()
        if n_err:
            print(f"\nDropping {n_err} error rows (API/parse failures) from merged frame.")
        df = df[~err_mask]
    # Drop rows with no canonical drug (rare; usually means both verbatim was empty)
    df = df[df["canonical_drug"].notna()]
    return df


# ── Krippendorff's α ────────────────────────────────────────────────────────


def _krippendorff_alpha(matrix: np.ndarray, metric) -> float | None:
    """General Krippendorff's α. matrix: rows=coders, cols=units; None/''/NaN = missing.

    `metric(a, b)` is the squared difference between two labels (0 if identical).
    With the 0/1 nominal metric this reduces to the standard nominal α; with a
    squared-rank metric it gives the ordinal/interval α. Returns None if there
    are too few paired observations."""
    from collections import Counter
    # Per-unit ratings; only units rated by ≥2 coders contribute.
    unit_ratings = []
    for col in range(matrix.shape[1]):
        valid = [v for v in matrix[:, col] if v is not None and v == v and v != ""]
        if len(valid) >= 2:
            unit_ratings.append(valid)
    if not unit_ratings:
        return None

    # Coincidence: all ordered within-unit pairs, weighted 1/(m_u - 1).
    coincidence: Counter = Counter()
    for ratings in unit_ratings:
        m = len(ratings)
        for i in range(m):
            for j in range(m):
                if i != j:
                    coincidence[(ratings[i], ratings[j])] += 1 / (m - 1)

    total = sum(coincidence.values())
    if total == 0:
        return None
    n_c: dict = {}
    for (a, _b), v in coincidence.items():
        n_c[a] = n_c.get(a, 0.0) + v
    N = sum(n_c.values())
    if N <= 1:
        return None

    # Observed vs expected disagreement, weighted by the metric.
    D_o = sum(v * metric(a, b) for (a, b), v in coincidence.items()) / total
    labels = list(n_c.keys())
    D_e = sum(n_c[a] * n_c[b] * metric(a, b) for a in labels for b in labels)
    D_e = D_e / (N * (N - 1))

    if D_e == 0:
        return 1.0 if D_o == 0 else None
    return 1 - (D_o / D_e)


def krippendorff_alpha_nominal(matrix: np.ndarray) -> float | None:
    """Krippendorff's α for nominal data (labels equal or not)."""
    return _krippendorff_alpha(matrix, lambda a, b: 0.0 if a == b else 1.0)


def krippendorff_alpha_ordinal(matrix: np.ndarray, order: list[str] | None = None) -> float | None:
    """Krippendorff's α for ordinal data, using squared rank distance (interval
    weights on the ordered categories). Labels outside `order` fall back to a
    nominal 0/1 distance. Default order = SIGNAL_ORDER (weak < moderate < strong)."""
    order = order or SIGNAL_ORDER
    rank = {c: i for i, c in enumerate(order)}

    def metric(a, b):
        if a in rank and b in rank:
            return float((rank[a] - rank[b]) ** 2)
        return 0.0 if a == b else 1.0  # off-scale label → nominal fallback

    return _krippendorff_alpha(matrix, metric)


def pivot_field(long_df: pd.DataFrame, field: str,
                mask: pd.Series | None = None) -> tuple[np.ndarray, list[str]]:
    """Pivot long-format into (coder × unit) array with '' for missing.

    unit = (sample_id, canonical_drug). Returns (matrix, coder_ids)."""
    df = long_df if mask is None else long_df[mask]
    if df.empty:
        return np.array([]).reshape(0, 0), []
    pivot = df.pivot_table(
        index=["sample_id", "canonical_drug"],
        columns="coder_id",
        values=field,
        aggfunc="first",
    )
    coders = list(pivot.columns)
    matrix = pivot.T.to_numpy()
    # Replace NaN with None so our α function skips missing
    out = np.empty(matrix.shape, dtype=object)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            v = matrix[i, j]
            if isinstance(v, float) and np.isnan(v):
                out[i, j] = None
            elif v == "":
                out[i, j] = None
            else:
                out[i, j] = v
    return out, coders


# ── Main analysis ───────────────────────────────────────────────────────────


def compute_all_alphas(long_df: pd.DataFrame) -> dict:
    """Compute α for each of 4 comparison fields, n-way across all coders."""
    results = {}

    # 1) Extraction agreement — nominal: what drug-set did each coder extract per sample?
    # For each sample, each coder's value is the sorted pipe-delimited canonical drug set.
    coders = sorted(long_df["coder_id"].unique())
    samples = sorted(long_df["sample_id"].unique())
    drug_sets = (long_df.groupby(["sample_id", "coder_id"])["canonical_drug"]
                 .apply(lambda x: "|".join(sorted(set(x))))
                 .reset_index()
                 .rename(columns={"canonical_drug": "drug_set"}))
    pivot_ext = drug_sets.pivot_table(
        index="sample_id", columns="coder_id",
        values="drug_set", aggfunc="first",
    )
    pivot_ext = pivot_ext.reindex(samples).fillna("__NONE__")
    ext_matrix = pivot_ext[coders].to_numpy().astype(object).T
    results["drug_extracted"] = {
        "alpha": krippendorff_alpha_nominal(ext_matrix),
        "n_units": ext_matrix.shape[1],
        "n_coders": ext_matrix.shape[0],
    }

    # 2) personal_use — over rows where at least one coder emitted the (sample, drug)
    m, c = pivot_field(long_df, "personal_use")
    results["personal_use"] = {
        "alpha": krippendorff_alpha_nominal(m) if m.size else None,
        "n_units": m.shape[1] if m.size else 0,
        "n_coders": len(c),
    }

    # 3) sentiment — only on rows where personal_use=yes
    yes_mask = long_df["personal_use"] == "yes"
    m, c = pivot_field(long_df[yes_mask], "sentiment")
    results["sentiment"] = {
        "alpha": krippendorff_alpha_nominal(m) if m.size else None,
        "n_units": m.shape[1] if m.size else 0,
        "n_coders": len(c),
    }

    # 4) signal_strength — same filter, but ORDINAL (weak < moderate < strong)
    m, c = pivot_field(long_df[yes_mask], "signal_strength")
    results["signal_strength"] = {
        "alpha": krippendorff_alpha_ordinal(m) if m.size else None,
        "n_units": m.shape[1] if m.size else 0,
        "n_coders": len(c),
    }
    return results


def pairwise_alphas(long_df: pd.DataFrame, field: str,
                    filter_mask: pd.Series | None = None,
                    ordinal: bool = False) -> pd.DataFrame:
    """Compute α for every coder pair, return DataFrame matrix.

    ordinal=True uses the ordinal (squared-rank) α — pass it for signal_strength."""
    alpha_fn = krippendorff_alpha_ordinal if ordinal else krippendorff_alpha_nominal
    df = long_df if filter_mask is None else long_df[filter_mask]
    coders = sorted(df["coder_id"].unique())
    matrix = pd.DataFrame(index=coders, columns=coders, dtype=float)
    for a, b in combinations(coders, 2):
        sub = df[df["coder_id"].isin([a, b])]
        m, _ = pivot_field(sub, field)
        alpha = alpha_fn(m) if m.size else None
        matrix.loc[a, b] = alpha
        matrix.loc[b, a] = alpha
    for c in coders:
        matrix.loc[c, c] = 1.0
    return matrix


def pairwise_extraction_alpha(long_df: pd.DataFrame) -> pd.DataFrame:
    """Pairwise α on drug extraction (nominal).

    For each sample, each coder's extraction is represented as the sorted,
    pipe-delimited set of canonical drugs they identified. Alpha measures
    whether coders agree on WHICH drugs they found per sample.

    Samples where a coder found no drugs (or no overlapping drugs in a
    filtered universe) are coded as '__NONE__'.
    """
    coders = sorted(long_df["coder_id"].unique())
    samples = sorted(long_df["sample_id"].unique())
    matrix = pd.DataFrame(index=coders, columns=coders, dtype=float)

    # Build per-(sample, coder) drug-set string
    drug_sets = (long_df.groupby(["sample_id", "coder_id"])["canonical_drug"]
                 .apply(lambda x: "|".join(sorted(set(x))))
                 .reset_index()
                 .rename(columns={"canonical_drug": "drug_set"}))

    for a, b in combinations(coders, 2):
        sub = drug_sets[drug_sets["coder_id"].isin([a, b])]
        if sub.empty:
            continue
        pivot = sub.pivot_table(
            index="sample_id", columns="coder_id",
            values="drug_set", aggfunc="first",
        )
        # Reindex to all samples so missing = no-drugs-found
        pivot = pivot.reindex(samples).fillna("__NONE__")
        if a not in pivot.columns or b not in pivot.columns:
            continue
        mat = pivot[[a, b]].to_numpy().astype(object).T
        alpha = krippendorff_alpha_nominal(mat)
        matrix.loc[a, b] = alpha
        matrix.loc[b, a] = alpha
    for c in coders:
        matrix.loc[c, c] = 1.0
    return matrix


# ── Report rendering ────────────────────────────────────────────────────────


def render_report(overall: dict, pair_ext: pd.DataFrame, pair_pu: pd.DataFrame,
                  pair_sent: pd.DataFrame, pair_sig: pd.DataFrame,
                  n_coders: int, n_samples: int) -> str:
    lines = []
    lines.append("# IRR Pilot — Krippendorff's α report")
    lines.append("")
    lines.append(f"Coders: {n_coders} | Samples in pilot: {n_samples}")
    lines.append("")
    lines.append("## Overall (n-way) Krippendorff's α")
    lines.append("")
    lines.append(f"| Field | α | n units | n coders |")
    lines.append(f"|---|---|---|---|")
    for field in ["drug_extracted", "personal_use", "sentiment", "signal_strength"]:
        r = overall[field]
        alpha_str = f"{r['alpha']:.3f}" if r["alpha"] is not None else "n/a"
        lines.append(f"| {field} | {alpha_str} | {r['n_units']} | {r['n_coders']} |")
    lines.append("")

    for name, matrix in [
        ("drug_extracted", pair_ext),
        ("personal_use", pair_pu),
        ("sentiment (personal_use=yes only)", pair_sent),
        ("signal_strength (personal_use=yes only)", pair_sig),
    ]:
        lines.append(f"## Pairwise α — {name}")
        lines.append("")
        lines.append("```")
        lines.append(matrix.round(3).to_string())
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--irr-dir", type=Path, default=IRR_DIR)
    ap.add_argument("--db", type=Path, default=DB_PATH)
    args = ap.parse_args()

    print(f"Reading coder CSVs from {args.irr_dir}")
    raw = load_all_coders(args.irr_dir)
    print(f"\nRaw total: {len(raw):,} rows from {raw['coder_id'].nunique()} coders")

    print(f"\nBuilding canonical lookup from {args.db}...")
    lookup = build_canonical_lookup(args.db)
    print(f"  {len(lookup):,} verbatim/alias → canonical mappings")

    long_df = build_merged(raw, lookup)
    print(f"After canonicalization + error-row drop: {len(long_df):,} rows")

    # Persist the merged frame for audit
    merged_path = args.irr_dir / "merged_long.csv"
    long_df.to_csv(merged_path, index=False, encoding="utf-8")
    print(f"Wrote {merged_path}")

    print("\nComputing n-way Krippendorff's α on 4 fields...")
    overall = compute_all_alphas(long_df)
    for field, r in overall.items():
        a = f"{r['alpha']:.3f}" if r["alpha"] is not None else "n/a"
        print(f"  {field:20s}  α = {a}  (n units = {r['n_units']}, "
              f"n coders = {r['n_coders']})")

    print("\nComputing pairwise α matrices...")
    pair_ext = pairwise_extraction_alpha(long_df)
    pair_pu = pairwise_alphas(long_df, "personal_use")
    yes = long_df["personal_use"] == "yes"
    pair_sent = pairwise_alphas(long_df, "sentiment", filter_mask=yes)
    pair_sig = pairwise_alphas(long_df, "signal_strength", filter_mask=yes, ordinal=True)

    # Save pairwise matrices as CSV (one per field)
    for name, m in [
        ("drug_extracted", pair_ext),
        ("personal_use", pair_pu),
        ("sentiment", pair_sent),
        ("signal_strength", pair_sig),
    ]:
        p = args.irr_dir / f"alpha_pairwise_{name}.csv"
        m.to_csv(p, encoding="utf-8")
    print(f"Wrote alpha_pairwise_*.csv (4 files)")

    report = render_report(
        overall, pair_ext, pair_pu, pair_sent, pair_sig,
        n_coders=long_df["coder_id"].nunique(),
        n_samples=long_df["sample_id"].nunique(),
    )
    report_path = args.irr_dir / "alpha_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Wrote {report_path}")
    print()
    print(report)


if __name__ == "__main__":
    main()
