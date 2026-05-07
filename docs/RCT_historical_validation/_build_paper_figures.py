"""
Reproducibility build script for RCT historical validation paper.

Generates Figure 1 (paired horizontal bar chart), Table 2 (data sources),
and Table 3 (per-drug response composition) from:

    "A Methodology for Gathering Real-World Evidence at Scale"

Methodology
-----------
For each of six drugs we extract treatment-sentiment reports from
r/covidlonghaulers posts dated *before* the relevant comparator paper was
publicly released (medRxiv preprint or journal online-first, whichever came
first). Pre-publication windows are capped at end of 2022 in this analysis.

Per-(user, drug) deduplication rule:
    1) Most recent report wins (full UTC timestamp, descending).
    2) Signal-strength is the tiebreaker on exact-timestamp ties
       (strong > moderate > weak > n/a). Such ties are rare, so this
       step acts as a near-vestigial tiebreaker — the rule reduces in
       practice to "most recent post wins."

We then test whether the proportion of responders (positive sentiment)
differs from a 50% null using a two-sided binomial test, and report the
proportion with a 95% Wilson score CI.

Usage
-----
    cd docs/RCT_historical_validation/
    python _build_paper_figures.py

Output
------
    output/paper_figures.ipynb            - source notebook
    output/paper_figures_executed.ipynb   - executed notebook
    output/paper_figures.html             - HTML export (code hidden)
    output/figure1.png                    - Figure 1 standalone image
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__) or ".")
from build_notebook import build_notebook, execute_and_export
import paths
from paths import db_path as resolve_db_path, output_dir as resolve_output_dir, find_package_root

# ────────────────────────────────────────────────────────────────────
# PROVENANCE MANIFEST HELPERS
# ────────────────────────────────────────────────────────────────────
# Used at the end of the build to write output/provenance.json — a
# machine-readable record of git commit, DB SHA-256, model names, and
# extraction-run metadata. This is the build-time freeze that ties a
# specific output artifact to a specific code revision and DB.
import hashlib
import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _compute_db_sha256(db_path):
    """SHA-256 of a SQLite DB file, streamed (works on multi-GB files)."""
    h = hashlib.sha256()
    with open(db_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_metadata():
    """Best-effort current commit hash + working-tree dirty flag.

    Anchored to the package root (this script's directory), and validated:
    we only return a commit hash if (a) git can resolve HEAD from inside
    the package root AND (b) this script file is tracked under that
    worktree. Otherwise we return 'outside-git' (or 'unknown' on
    git-not-available).

    Why so strict: if a reviewer extracts the package into an unrelated
    git checkout (e.g., a personal scratch repo) and runs the build
    there, an unanchored ``git rev-parse HEAD`` would silently record
    that *other* repo's commit in provenance.json — which is worse than
    no commit at all, because reviewers would trust it. We treat
    'package not tracked here' as a structural break and surface it.

    Returns a dict with 'commit' (sha, 'outside-git', or 'unknown') and
    'dirty' (bool or None if dirty state could not be determined). Loud
    warning whenever the chain breaks so we never silently mislead.
    """
    pkg_root = Path(__file__).resolve().parent
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(pkg_root),
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        # Verify this script file is actually tracked in the worktree git
        # found above. ls-files exits 1 if the path is not tracked.
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "_build_paper_figures.py"],
            cwd=str(pkg_root),
            capture_output=True, text=True,
        )
        if tracked.returncode != 0:
            print(f"WARN: package directory is inside a git checkout (HEAD {commit[:8]}) "
                  "but _build_paper_figures.py is NOT tracked there. The package was "
                  "likely extracted/copied into an unrelated repo. Recording "
                  "'outside-git' instead of the unrelated repo's commit — that "
                  "would be misleading provenance.")
            return {"commit": "outside-git", "dirty": None}
        try:
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(pkg_root),
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            dirty = bool(status)
        except Exception:
            dirty = None
        if dirty:
            print(f"WARN: git working tree DIRTY at build time (commit {commit[:8]} + "
                  "uncommitted changes). Provenance manifest records this; "
                  "commit before treating outputs as reproducible.")
        return {"commit": commit, "dirty": dirty}
    except subprocess.CalledProcessError:
        # git ran but returned non-zero — usually means pkg_root is not inside
        # any git worktree (e.g., extracted into a plain directory).
        print("WARN: package directory is not inside a git worktree; "
              "provenance manifest records 'outside-git' for git_commit. "
              "If you intend reproducible provenance, run from a checkout of "
              "the source repo.")
        return {"commit": "outside-git", "dirty": None}
    except FileNotFoundError:
        # git binary missing entirely.
        print("WARN: git not found on PATH; provenance manifest records "
              "'unknown' for git_commit. Install git and rerun from a clean "
              "checkout to capture the build commit.")
        return {"commit": "unknown", "dirty": None}


def _normalize_path_separators(value):
    """Convert Windows backslashes to forward slashes inside a config value.
    Path-like fields in extraction_runs.config get serialized with whatever
    separator the OS used at extraction time (typically Windows '\\'); we
    normalize for readability and cross-platform consistency. Non-path
    values pass through unchanged."""
    if isinstance(value, str) and "\\" in value:
        return value.replace("\\", "/")
    if isinstance(value, dict):
        return {k: _normalize_path_separators(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_path_separators(v) for v in value]
    return value


def _read_extraction_runs(db_path):
    """Pull all rows of the extraction_runs table; return None if absent."""
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='extraction_runs'"
        )
        if cur.fetchone() is None:
            return None
        cur = conn.execute(
            "SELECT run_id, run_at, commit_hash, extraction_type, config "
            "FROM extraction_runs ORDER BY run_id"
        )
        cols = [d[0] for d in cur.description]
        rows = []
        for r in cur.fetchall():
            row = dict(zip(cols, r))
            # config is stored as a JSON string; parse for readability
            try:
                row["config"] = json.loads(row["config"]) if row.get("config") else None
            except Exception:
                pass
            # Normalize Windows backslashes in any string values inside config
            # (typically config.output_dir from the original Windows extraction).
            row["config"] = _normalize_path_separators(row.get("config"))
            # run_at is unix epoch; add ISO for readability
            if isinstance(row.get("run_at"), int):
                row["run_at_iso"] = datetime.fromtimestamp(
                    row["run_at"], tz=timezone.utc
                ).isoformat()
            rows.append(row)
        return rows
    finally:
        conn.close()


def write_provenance_manifest(db_path, output_dir, package_root=None):
    """Write a machine-readable provenance manifest to output_dir/provenance.json.

    Captures the build-time freeze: git commit, DB SHA-256, model env, and the
    full extraction_runs table content from the analysis DB. Returns the path
    to the written manifest.

    The recorded DB path is package-relative (e.g. "data/historical_validation_*.db"),
    not absolute, so manifests don't leak machine-specific user paths.
    """
    db_path = Path(db_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if package_root is None:
        # Best-effort: walk up from db_path's parent
        package_root = find_package_root(start=db_path.parent)
    package_root = Path(package_root).resolve()
    try:
        rel_db = str(db_path.resolve().relative_to(package_root).as_posix())
    except ValueError:
        # DB lives outside the package (e.g. RCT_DB_PATH env var pointed elsewhere).
        # Record just the filename rather than a leaky absolute path.
        rel_db = db_path.name

    manifest = {
        "build_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "build_script": Path(__file__).name,
        "git": _git_metadata(),
        "db": {
            # Package-relative path. Absolute paths would leak personal info
            # (e.g. C:\Users\<name>\...) and aren't portable across reviewers.
            "path": rel_db,
            "filename": db_path.name,
            "sha256": _compute_db_sha256(db_path),
            "size_bytes": db_path.stat().st_size,
        },
        "models": {
            "fast": os.environ.get("MODEL_FAST", "anthropic/claude-haiku-4.5"),
            "strong": os.environ.get("MODEL_STRONG", "anthropic/claude-sonnet-4.6"),
        },
        "extraction_runs": _read_extraction_runs(db_path),
    }
    out = output_dir / "provenance.json"
    out.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(f"Wrote provenance manifest: {out}")
    return out


cells = []

# ────────────────────────────────────────────────────────────────────
# INTRODUCTION
# ────────────────────────────────────────────────────────────────────
cells.append(("md", """# RCT Historical Validation — Reproducibility Figures

This notebook reproduces **Figure 1**, **Table 2**, and **Table 3** from the paper.

- **Figure 1**: Pre-publication community sentiment — responders vs non-responders for 6 drugs
- **Table 2**: Data sources by drug (databases, window, post/user/report counts)
- **Table 3**: Per-drug response composition with Wilson 95% CIs and binomial test p-values

**Method.** For each drug, we extract all treatment-sentiment reports from
r/covidlonghaulers posts whose `post_date` is strictly before the
comparator paper's first public release (medRxiv preprint or journal
online-first, whichever came first). The SQL predicate is literally
`p.post_date < pub_date_in_unix_seconds`, where `pub_date` is the
midnight-UTC timestamp of the publication date — so any post on or
after the publication date is excluded by construction. The analysis
is additionally capped at end of 2022 (i.e., posts on or after
2023-01-01 are excluded) for paxlovid and colchicine. All classified
reports come from a single self-sufficient SQLite database
(`historical_validation_2020-07_to_2022-12.db`). Posts where the Reddit
author field was `[deleted]` or `[removed]` (mapped to the placeholder
user_id `"deleted"`) are excluded from per-user analysis: those posts come
from many distinct real users whose accounts no longer exist, and
collapsing them under one pseudo-user would give that whole population
one vote per drug. Each remaining user contributes exactly one data point
per drug after deduplication: the **most recent report** wins (by full
UTC timestamp), with **signal_strength** as the tiebreaker on exact
timestamp ties (strong > moderate > weak > n/a). Exact-timestamp ties
are rare, so the tiebreaker fires only occasionally — the rule
reduces in practice to "most recent post wins."
We then test whether the proportion of
responders (positive sentiment) differs from a 50% null using a two-sided
binomial test.
"""))

# ────────────────────────────────────────────────────────────────────
# SETUP CODE (produces zero visible output)
# ────────────────────────────────────────────────────────────────────
cells.append(("code", r"""
from pathlib import Path
from datetime import datetime, timezone
from scipy.stats import binomtest
from statsmodels.stats.proportion import proportion_confint as wilson

# ── Single self-sufficient analysis database ──
# Direct output of one master pipeline run covering 2020-07-24 to 2022-12-31
# across all six target drugs. See README "Provenance" section for details.
# The setup cell injected by build_notebook already opened `conn` against
# DB_PATH, which IS the combined DB; reuse that connection instead of
# opening a second one (Gemini review M3).
combined_conn = conn

# ── Integrity check: every treatment_report's user_id must match its post's ──
# An earlier (now-deleted) backfill script copied report rows from older DBs
# whose username-hashing differed from this DB's, producing report-level
# user_ids that did not match the same post's user_id. That breaks per-user
# dedup. We assert there are zero such mismatches; build fails loudly if any
# reappear.
_n_mismatch = combined_conn.execute(
    'SELECT COUNT(*) FROM treatment_reports tr '
    'JOIN posts p ON tr.post_id = p.post_id '
    'WHERE tr.user_id != p.user_id'
).fetchone()[0]
assert _n_mismatch == 0, (
    f"DB integrity check failed: {_n_mismatch} treatment_reports rows have "
    "user_id != posts.user_id for the same post_id. The DB has cross-DB "
    "backfill contamination and must be rebuilt from a clean pipeline run."
)
print(f"DB integrity check: {_n_mismatch} mismatched user_ids (must be 0). PASS.")

# ── Signal-strength rank for tiebreaking ──
# Higher = stronger evidence. 'n/a' is treated as lowest because it means the
# classifier wasn't sure; we'd rather pick a confident weak/moderate report
# over an uncertain one when dates tie.
SIG_RANK = {"strong": 3, "moderate": 2, "weak": 1, "n/a": 0, None: 0, "": 0}

def fetch_drug_reports(drug, window_end_exclusive_ts):
    '''Pull all reports for a canonical drug whose post_date is strictly
    before window_end_exclusive_ts. The exclusive upper bound is the
    publication date of the comparator paper (or 2023-01-01 if the
    end-of-2022 cap binds), so that "pre-publication" maps directly to
    p.post_date < publication_date_in_unix_seconds.

    Excludes posts where p.user_id = "deleted" (the placeholder assigned
    when the Reddit author field is "[deleted]" or "[removed]"). Those
    posts come from many distinct real users whose accounts no longer
    exist; collapsing them under one pseudo-user would give that whole
    population a single vote per drug, while treating each as its own
    user would inflate sample sizes with non-random ban/withdrawal
    artefacts. Excluding is the defensible compromise. See README,
    "Deleted-user exclusion policy" for details.'''
    return combined_conn.execute('''
        SELECT tr.user_id,
               lower(t.canonical_name) AS drug,
               tr.sentiment,
               tr.signal_strength      AS sig,
               p.post_date,
               tr.post_id
        FROM treatment_reports tr
        JOIN treatment t ON tr.drug_id = t.id
        JOIN posts     p ON tr.post_id = p.post_id
        WHERE lower(t.canonical_name) = ?
          AND p.post_date IS NOT NULL
          AND p.post_date < ?
          AND p.user_id != 'deleted'
    ''', (drug, window_end_exclusive_ts)).fetchall()

def dedup_recent_then_strength(rows):
    '''Per (user, drug): keep the most recent report (by full UTC
    timestamp); on exact-timestamp ties, keep the strongest signal.
    Such ties are rare, so the tiebreaker is near-vestigial.'''
    by_user = {}
    for row in rows:
        uid, drug, sent, sig, d, _pid = row
        date = d or 0
        sig_r = SIG_RANK.get(sig, 0)
        key = (uid, drug)
        if key not in by_user:
            by_user[key] = (date, sig_r, sent)
            continue
        cur_date, cur_sig, _ = by_user[key]
        if date > cur_date or (date == cur_date and sig_r > cur_sig):
            by_user[key] = (date, sig_r, sent)
    return [(uid_drug[0], uid_drug[1], v[2]) for uid_drug, v in by_user.items()]

def epoch_midnight(date_str):
    '''UTC-midnight Unix timestamp for the given YYYY-MM-DD.'''
    return int(datetime.strptime(date_str, '%Y-%m-%d').replace(
        tzinfo=timezone.utc).timestamp())

# Each drug's exclusive window upper bound is the publication date itself.
# The SQL predicate is "post_date < pub_date_midnight_utc", so any post on or
# after the publication date is excluded. The analysis additionally caps at
# end-of-2022 (i.e. excludes 2023-01-01 onward) for paxlovid and colchicine,
# whose comparator papers landed in 2024 and 2025.
END_2022_EXCLUSIVE = '2023-01-01'

DRUG_CUTOFFS = {
    # drug -> (publication_date_yyyy_mm_dd, paper_short, source_and_date)
    'famotidine':  ('2021-06-07', 'Glynne et al. 2021',           'medRxiv 2021-06-07'),
    'loratadine':  ('2021-06-07', 'Glynne et al. 2021',           'medRxiv 2021-06-07'),
    'prednisone':  ('2021-10-26', 'Utrero-Rico et al. 2021',      'Biomedicines 2021-10-26'),
    'naltrexone':  ('2022-07-03', "O'Kelly et al. 2022",          'BBI Health 2022-07-03'),
    'paxlovid':    ('2024-06-07', 'Geng et al. 2024 (STOP-PASC)', 'JAMA Intern Med 2024-06-07'),
    'colchicine':  ('2025-10-20', 'Bassi et al. 2025',            'JAMA Intern Med 2025-10-20'),
}

# Frozen expected outputs — used by the V10 build-time assertion below.
# Source of these values: dump_per_drug_csvs.py output against the canonical
# DB on 2026-05-04 (commit 1562239 era, pre-rebuild — re-verified
# unchanged after the rebuild). If the DB content changes legitimately, this
# dict and the README's "Expected Output" table must be updated together.
EXPECTED_OUTPUTS = {
    'famotidine': {'n': 232, 'pos': 179, 'pos_pct': 77.155, 'p': 3.565e-17},
    'loratadine': {'n':  90, 'pos':  73, 'pos_pct': 81.111, 'p': 1.948e-9 },
    'prednisone': {'n': 343, 'pos': 167, 'pos_pct': 48.688, 'p': 0.6658   },
    'naltrexone': {'n': 154, 'pos': 101, 'pos_pct': 65.584, 'p': 1.358e-4 },
    'paxlovid':   {'n': 196, 'pos': 106, 'pos_pct': 54.082, 'p': 0.2839   },
    'colchicine': {'n':  91, 'pos':  49, 'pos_pct': 53.846, 'p': 0.5296   },
}
"""))

# ────────────────────────────────────────────────────────────────────
# DATA EXTRACTION (produces resp_df used by Figure 0, Figure 1, Table 3)
# ────────────────────────────────────────────────────────────────────
cells.append(("code", r"""
def _sentiment_breakdown(drug_label, sentiments, trial_dir, paper_short, source_date):
    n = len(sentiments)
    pos = sum(1 for s in sentiments if s == 'positive')
    neg = sum(1 for s in sentiments if s == 'negative')
    neu = sum(1 for s in sentiments if s == 'neutral')
    mix = sum(1 for s in sentiments if s == 'mixed')
    nonr = neg + neu + mix
    pos_lo, pos_hi   = wilson(pos,  n, alpha=0.05, method='wilson') if n else (0, 0)
    nonr_lo, nonr_hi = wilson(nonr, n, alpha=0.05, method='wilson') if n else (0, 0)
    pval = binomtest(pos, n, 0.5, alternative='two-sided').pvalue if n else 1.0
    return {
        'drug': drug_label, 'n': n, 'trial_dir': trial_dir,
        'paper': paper_short, 'source_date': source_date,
        'pos': pos, 'neg': neg, 'neu': neu, 'mix': mix, 'nonr': nonr,
        'pos_pct': pos/n*100 if n else 0,
        'pos_lo': pos_lo*100, 'pos_hi': pos_hi*100,
        'nonr_pct': nonr/n*100 if n else 0,
        'nonr_lo': nonr_lo*100, 'nonr_hi': nonr_hi*100,
        'pval': pval,
    }

# Trial directions for each drug
TRIAL_DIRS = {
    'famotidine': '+',
    'loratadine': '+',
    'naltrexone': '+',
    'prednisone': '0',
    'paxlovid':   '0',
    'colchicine': '0',
}

resp_rows = []
for drug, (pub_date, paper_short, source_date) in DRUG_CUTOFFS.items():
    window_end_exclusive = min(pub_date, END_2022_EXCLUSIVE)
    cutoff_ts = epoch_midnight(window_end_exclusive)
    rows = fetch_drug_reports(drug, cutoff_ts)
    dedup = dedup_recent_then_strength(rows)
    sentiments = [s for _u, _d, s in dedup]
    resp_rows.append(_sentiment_breakdown(drug, sentiments, TRIAL_DIRS[drug], paper_short, source_date))

resp_df = (pd.DataFrame(resp_rows)
           .sort_values('pos_pct', ascending=False)
           .reset_index(drop=True))
"""))


# ────────────────────────────────────────────────────────────────────
# EXPECTED-OUTPUT ASSERTION — fail build on numerical drift
# ────────────────────────────────────────────────────────────────────
cells.append(("md", """## Expected-output assertion

The cell below compares the freshly-computed `resp_df` against a frozen
expected-output table (defined as `EXPECTED_OUTPUTS` in the setup cell).
Build fails on any drift outside rounding tolerance — so a future
analytical change that silently shifts a number can't slip through.

The check is intentionally strict on integer counts (`n`, `pos`) and
loose on rounding (`pos_pct` to 0.05pp, `p` relative tolerance 1e-3 for
non-tiny p-values; for p < 1e-4 we just check the order of magnitude
matches). Update `EXPECTED_OUTPUTS` *and* the README's "Expected Output"
table together if the analytical pipeline legitimately changes."""))

cells.append(("code", r"""
_violations = []
for _, _row in resp_df.iterrows():
    _drug = _row['drug']
    _exp = EXPECTED_OUTPUTS.get(_drug)
    if _exp is None:
        _violations.append(f"{_drug}: no entry in EXPECTED_OUTPUTS — extend the frozen table.")
        continue
    if int(_row['n']) != _exp['n']:
        _violations.append(f"{_drug}: n {int(_row['n'])} != expected {_exp['n']}")
    if int(_row['pos']) != _exp['pos']:
        _violations.append(f"{_drug}: pos {int(_row['pos'])} != expected {_exp['pos']}")
    if abs(_row['pos_pct'] - _exp['pos_pct']) > 0.05:
        _violations.append(
            f"{_drug}: pos_pct {_row['pos_pct']:.3f} differs from expected "
            f"{_exp['pos_pct']:.3f} by more than 0.05pp"
        )
    _p_actual = float(_row['pval'])
    _p_expected = _exp['p']
    if _p_expected < 1e-4:
        # Tiny p-values: just check actual is also small (within ~1 order of magnitude)
        if not (_p_actual < 10 * _p_expected):
            _violations.append(
                f"{_drug}: p {_p_actual:.3g} far from expected tiny {_p_expected:.3g}"
            )
    else:
        _rel = abs(_p_actual - _p_expected) / _p_expected
        if _rel > 1e-3:
            _violations.append(
                f"{_drug}: p {_p_actual:.4f} differs from expected {_p_expected:.4f} "
                f"(relative drift {_rel:.4f} > 0.001)"
            )

# Also assert no missing or unexpected drugs
_actual_drugs = set(resp_df['drug'])
_expected_drugs = set(EXPECTED_OUTPUTS)
_missing = _expected_drugs - _actual_drugs
_extra   = _actual_drugs - _expected_drugs
if _missing:
    _violations.append(f"missing drugs in resp_df: {sorted(_missing)}")
if _extra:
    _violations.append(f"unexpected drugs in resp_df not in EXPECTED_OUTPUTS: {sorted(_extra)}")

if _violations:
    raise AssertionError(
        "V10 expected-output drift FAILED:\n"
        + "\n".join("  - " + v for v in _violations)
        + "\n\nIf this drift is intentional, update EXPECTED_OUTPUTS in "
          "_build_paper_figures.py AND the README's \"Expected Output\" "
          "table together."
    )

print(f"V10 expected-output assertion: all {len(EXPECTED_OUTPUTS)} drugs match the frozen table. PASS.")
"""))


# ────────────────────────────────────────────────────────────────────
# FIGURE 0: Full sentiment breakdown per drug (stacked bar)
# ────────────────────────────────────────────────────────────────────
cells.append(("md", """## Figure 0 — Full sentiment breakdown per drug

Figure 1 collapses the four sentiment classes into a binary responder vs. non-responder split.
Figure 0 retains the full four-way breakdown (positive / mixed / neutral / negative) so the
shape of the non-responder bucket is visible. Per-segment labels show both the percentage and
the raw user count contributing to that segment."""))

cells.append(("code", r"""
# ── Figure 0: Stacked horizontal bar of full sentiment breakdown ──
cats   = ['positive', 'mixed', 'neutral', 'negative']
colors = ['#2ecc71',  '#f39c12', '#95a5a6', '#e74c3c']

pcts = pd.DataFrame({
    'drug':     resp_df['drug'],
    'trial':    resp_df['trial_dir'],
    'positive': resp_df['pos'] / resp_df['n'] * 100,
    'mixed':    resp_df['mix'] / resp_df['n'] * 100,
    'neutral':  resp_df['neu'] / resp_df['n'] * 100,
    'negative': resp_df['neg'] / resp_df['n'] * 100,
})
raw = {'positive': resp_df['pos'].values, 'mixed': resp_df['mix'].values,
       'neutral':  resp_df['neu'].values, 'negative': resp_df['neg'].values}

BAR_H          = 0.45
LABEL_Y_OFFSET = BAR_H / 2 + 0.05  # below each bar

fig, ax = plt.subplots(figsize=(16, 12))
y = np.arange(len(pcts))[::-1]

# Stacked horizontal bars
left = np.zeros(len(pcts))
for cat, color in zip(cats, colors):
    vals = pcts[cat].values
    ax.barh(y, vals, left=left, height=BAR_H, color=color, label=cat,
            edgecolor='white', linewidth=0.4)
    left += vals

# Per-segment labels (% and raw n) below each bar segment
for row_i, yi in enumerate(y):
    left_x = 0.0
    for cat in cats:
        pct = pcts[cat].values[row_i]
        n   = raw[cat][row_i]
        cx  = left_x + pct / 2
        if pct > 0:
            ax.text(cx, yi - LABEL_Y_OFFSET, f"{pct:.0f}%\n(n={n})",
                    ha='center', va='top', fontsize=15, color='#222',
                    linespacing=1.3)
        left_x += pct

# Y labels: drug + trial-direction tag
ax.set_yticks(y)
ax.set_yticklabels(
    [f"{r['drug']}  [{'+ trial' if r['trial'] == '+' else 'null trial'}]"
     for _, r in pcts.iterrows()],
    fontsize=18,
)
ax.set_xlabel('Patient-reported outcomes (% of users)', fontsize=18)
ax.set_xlim(0, 100)
ax.set_ylim(y.min() - 1.8, y.max() + 0.6)
ax.set_title('Figure 0 — Full sentiment breakdown per drug',
             fontsize=20, fontweight='bold')
ax.legend(loc='lower right', fontsize=14)
ax.tick_params(axis='x', labelsize=14)
ax.grid(axis='x', alpha=0.3)
plt.tight_layout()
plt.savefig('figure0.png', dpi=150, bbox_inches='tight')
plt.show()
"""))


# ────────────────────────────────────────────────────────────────────
# FIGURE 1: Paired horizontal bar chart (responders vs non-responders)
# ────────────────────────────────────────────────────────────────────
cells.append(("md", """## Figure 1 — Forest plot: responders and non-responders by drug

Figure 1 collapses the four-way sentiment breakdown into a binary split: responders
(positive sentiment) vs. non-responders (negative + neutral + mixed). Each drug
contributes two points to the forest plot — a green circle for the **responder**
rate and a red square for the **non-responder** rate — both with their 95% Wilson
confidence intervals. The row label gives the drug, the comparator trial outcome
(`[+ trial]` vs `[null trial]`), the paper citation, and the sample size."""))

cells.append(("code", r"""
# ── Figure 1: Forest plot of % responders + % non-responders with 95% Wilson CIs ──
from matplotlib.lines import Line2D

GREEN = '#27ae60'
RED   = '#c0392b'
OFFSET = 0.22  # vertical separation between responder and non-responder markers

fig, ax = plt.subplots(figsize=(13, 7.5))
y_center = np.arange(len(resp_df))[::-1].astype(float)
y_resp = y_center + OFFSET
y_nonr = y_center - OFFSET

# Responders: green circles + CI line
ax.errorbar(
    resp_df['pos_pct'], y_resp,
    xerr=[resp_df['pos_pct'] - resp_df['pos_lo'],
          resp_df['pos_hi'] - resp_df['pos_pct']],
    fmt='o', markersize=8, color=GREEN, ecolor=GREEN,
    elinewidth=1.6, capsize=0, label='% responders (positive)',
)

# Non-responders: red squares + CI line
ax.errorbar(
    resp_df['nonr_pct'], y_nonr,
    xerr=[resp_df['nonr_pct'] - resp_df['nonr_lo'],
          resp_df['nonr_hi'] - resp_df['nonr_pct']],
    fmt='s', markersize=8, color=RED, ecolor=RED,
    elinewidth=1.6, capsize=0, label='% non-responders (neg + neu + mix)',
)

# Value labels at the right end of each CI
for i, r in resp_df.iterrows():
    ax.text(r['pos_hi']  + 1.2, y_resp[i], f"{r['pos_pct']:.0f}%",
            color=GREEN, va='center', ha='left', fontsize=11)
    ax.text(r['nonr_hi'] + 1.2, y_nonr[i], f"{r['nonr_pct']:.0f}%",
            color=RED, va='center', ha='left', fontsize=11)

# Y-tick labels: drug + trial outcome tag (line 1), paper + n (line 2)
def _trial_tag(td):
    return '+ trial' if td == '+' else ('null trial' if td == '0' else f'{td} trial')

ax.set_yticks(y_center)
ax.set_yticklabels(
    [f"{r['drug']}  [{_trial_tag(r['trial_dir'])}]\n{r['paper']}  (n={r['n']})"
     for _, r in resp_df.iterrows()],
    fontsize=11,
)

# Visual separators between drug groups (horizontal lines at half-integer y positions)
for k in range(1, len(resp_df)):
    ax.axhline(len(resp_df) - 1 - k + 0.5, color='#dddddd', lw=0.7, zorder=0)

# Y range: leave half a row of padding top and bottom
ax.set_ylim(-0.6, len(resp_df) - 0.4)

# X axis
ax.set_xlim(0, 100)
ax.set_xlabel('% of users (95% Wilson CI)', fontsize=12)
ax.tick_params(axis='x', labelsize=11)
ax.set_xticks([0, 25, 50, 75, 100])

# Subtle null reference at 50%
ax.axvline(50, color='gray', ls=':', lw=0.8, zorder=0)

ax.set_title('Figure 1 — Forest plot: responders and non-responders by drug\n'
             '95% Wilson CIs. Trial outcome tagged in the row label.',
             fontsize=14, fontweight='bold', pad=12)

ax.grid(axis='x', alpha=0.3, zorder=0)
ax.set_axisbelow(True)
for spine in ('top', 'right'):
    ax.spines[spine].set_visible(False)

legend_elems = [
    Line2D([0], [0], marker='o', linestyle='-', color=GREEN, markersize=8,
           label='% responders (positive)'),
    Line2D([0], [0], marker='s', linestyle='-', color=RED, markersize=8,
           label='% non-responders (neg + neu + mix)'),
]
ax.legend(handles=legend_elems, loc='lower right', fontsize=10, frameon=True)

plt.tight_layout()
plt.savefig('figure1.png', dpi=150, bbox_inches='tight')
plt.show()
"""))

# ────────────────────────────────────────────────────────────────────
# TABLE 2: Data sources
# ────────────────────────────────────────────────────────────────────
cells.append(("md", """## Data sources and methodology

**Definitions:**
- **Responder**: user's selected report has `positive` sentiment.
- **Non-responder**: user's selected report has any other sentiment (negative, neutral, or mixed).

**Per-(user, drug) deduplication rule:**
- Most recent post wins (full UTC timestamp, descending).
- On exact-timestamp ties, the report with stronger `signal_strength`
  wins (strong > moderate > weak > n/a). Such ties are rare, so this
  step is a near-vestigial tiebreaker — the rule reduces in practice
  to "most recent post wins."

**Window cap:** all data is restricted to posts from the corpus inception
(2020-07-24) through end of 2022 (2022-12-31). For famotidine, loratadine,
prednisone, and naltrexone the comparator publication date is the binding
cutoff. For paxlovid (publication June 2024) and colchicine (December 2025),
the end-2022 cap is the binding cutoff."""))

cells.append(("code", r"""
# ── Table 2: Data sources by drug ──
# Pulls user/report counts directly from the merged data so the table
# auto-updates if the underlying DBs change.
def _last_included_date(window_end_exclusive_str):
    '''Return the last date (YYYY-MM-DD) actually included given a strict-<
    upper bound at midnight on the given date, e.g. "2021-06-07" -> "2021-06-06".'''
    from datetime import timedelta
    d = datetime.strptime(window_end_exclusive_str, '%Y-%m-%d') - timedelta(days=1)
    return d.strftime('%Y-%m-%d')

def _count_posts_in_window(cutoff_ts):
    '''Total posts in the corpus that pass the same baseline filter the
    per-drug analysis applies (post_date present, non-deleted user). This
    is the denominator the substring + LLM extraction was actually run
    against, not raw row count.'''
    return combined_conn.execute(
        "SELECT COUNT(*) FROM posts "
        "WHERE post_date IS NOT NULL AND post_date < ? AND user_id != 'deleted'",
        (cutoff_ts,),
    ).fetchone()[0]

src_rows = []
for drug, (pub_date, paper_short, source_date) in DRUG_CUTOFFS.items():
    window_end_exclusive = min(pub_date, END_2022_EXCLUSIVE)
    cutoff_ts = epoch_midnight(window_end_exclusive)
    rows = fetch_drug_reports(drug, cutoff_ts)
    n_reports = len(rows)
    n_users = len({(uid, dr) for uid, dr, _s, _sg, _d, _p in rows})
    n_total_posts = _count_posts_in_window(cutoff_ts)
    src_rows.append({
        'drug': drug,
        'databases': 'historical_validation_2020-07_to_2022-12.db',
        'window_start': '2020-07-24',
        'window_end': _last_included_date(window_end_exclusive),
        'total_posts': n_total_posts,
        'unique_users': n_users,
        'treatment_reports': n_reports,
        'comparator': f"{paper_short} ({source_date})",
    })
src_df = pd.DataFrame(src_rows)

src_html = "<table style='border-collapse:collapse; width:100%; font-size:0.85em; margin:12px 0;'>"
src_html += ("<tr style='background:#34495e; color:white;'>"
             "<th style='padding:6px 10px;'>Drug</th>"
             "<th style='padding:6px 10px;'>Window</th>"
             "<th style='padding:6px 10px;'>Total posts</th>"
             "<th style='padding:6px 10px;'>Unique users</th>"
             "<th style='padding:6px 10px;'>Treatment reports</th>"
             "<th style='padding:6px 10px;'>Comparator paper</th></tr>")
for i, (_, r) in enumerate(src_df.iterrows()):
    bg = '#fff' if i % 2 == 0 else '#f8f9fa'
    src_html += (f"<tr style='background:{bg};'>"
                 f"<td style='padding:6px 10px; font-weight:bold;'>{r['drug']}</td>"
                 f"<td style='padding:6px 10px;'>{r['window_start']} → {r['window_end']}</td>"
                 f"<td style='padding:6px 10px; text-align:right;'>{r['total_posts']:,}</td>"
                 f"<td style='padding:6px 10px; text-align:right;'>{r['unique_users']:,}</td>"
                 f"<td style='padding:6px 10px; text-align:right;'>{r['treatment_reports']:,}</td>"
                 f"<td style='padding:6px 10px; font-size:0.85em;'>{r['comparator']}</td></tr>")
src_html += "</table>"
src_html += ("<p style='font-size:0.85em; color:#777; margin-top:4px;'>"
             "All counts are drawn from a single SQLite database "
             "(<code>historical_validation_2020-07_to_2022-12.db</code>) constructed for this paper. "
             "<b>Total posts:</b> all r/covidlonghaulers posts in the drug's window with non-NULL "
             "<code>post_date</code> and non-deleted <code>user_id</code> — the denominator the "
             "substring + LLM extraction ran against. "
             "<b>Unique users:</b> distinct users with at least one classified report for the drug "
             "(after deleted-user exclusion). "
             "<b>Treatment reports:</b> total post-level classified reports before per-user dedup. "
             "Window cap at end of 2022 applies to paxlovid and colchicine; for the other four drugs the "
             "comparator publication date is the binding cutoff.</p>")

display(HTML("<h3>Table 2 &mdash; Data sources by drug</h3>" + src_html))
"""))

# ────────────────────────────────────────────────────────────────────
# TABLE 3: Per-drug response composition
# ────────────────────────────────────────────────────────────────────
cells.append(("code", r"""
# ── Table 3: Response composition ──
table_df = resp_df[['drug', 'paper', 'source_date', 'n', 'pos', 'pos_pct',
                    'pos_lo', 'pos_hi', 'nonr', 'nonr_pct',
                    'nonr_lo', 'nonr_hi', 'pval']].copy()

def _fmt_pct(v): return f"{v:.1f}%"
def _fmt_ci(lo, hi): return f"[{lo:.1f}%, {hi:.1f}%]"
def _fmt_p(v):
    # Scientific notation for p < 0.001 (e.g. 3.57e-17), three decimal
    # places otherwise (e.g. 0.284). Normalize exponent to drop the
    # leading zero on single-digit exponents (1.95e-9 not 1.95e-09).
    if v < 0.001:
        import re as _re
        return _re.sub(r'e([+-])0(\d)$', r'e\1\2', f"{v:.2e}")
    return f"{v:.3f}"

table_df['% responders']      = table_df['pos_pct'].apply(_fmt_pct)
table_df['responders 95% CI'] = [_fmt_ci(lo, hi) for lo, hi in zip(table_df['pos_lo'], table_df['pos_hi'])]
table_df['% non-resp']        = table_df['nonr_pct'].apply(_fmt_pct)
table_df['non-resp 95% CI']   = [_fmt_ci(lo, hi) for lo, hi in zip(table_df['nonr_lo'], table_df['nonr_hi'])]
table_df['p (vs 50%)']        = table_df['pval'].apply(_fmt_p)

display_table = table_df[['drug', 'paper', 'source_date', 'n',
                          '% responders', 'responders 95% CI',
                          'nonr', '% non-resp', 'non-resp 95% CI',
                          'p (vs 50%)']].rename(columns={
                              'paper':        'Comparator paper',
                              'source_date':  'Source / first public date',
                              'nonr':         '-/0/~',
                          })

display(HTML("<h3>Table 3 &mdash; Per-drug response composition (pre-publication data only)</h3>"
             "<p style='font-size:0.9em; color:#555;'>Each row: one (user, drug) per cell after the "
             "<i>most recent + signal-strength tiebreaker</i> dedup rule. "
             "Responders = positive sentiment; non-responders = negative + neutral + mixed. "
             "<i>p</i> values from a two-sided binomial test against the 50% null "
             "(H&#8320;: P(responder) = 0.5). The 'Source / first public date' column gives the "
             "earliest publicly available release of the comparator paper "
             "(medRxiv preprint where available, otherwise journal online-first).</p>"
             + display_table.to_html(index=False)))
"""))

# ────────────────────────────────────────────────────────────────────
# DEDUP AUDIT — raw vs unique-user counts + class-change sensitivity
# ────────────────────────────────────────────────────────────────────
cells.append(("md", """## Dedup audit

For each drug we report:

- **Raw reports**: total `treatment_reports` rows in-window (pre-dedup).
- **Unique users**: `COUNT(DISTINCT user_id)` over the same set — this is
  the `n` that appears in Figure 1 / Table 3 after dedup.
- **Multi-report users**: users with ≥2 in-window reports for this drug.
  Dedup only matters for these.
- **Mixed-signal users**: multi-report users whose reports contain *both*
  positive and non-positive labels — the population where the dedup rule
  choice actually changes the class assignment.
- **Flipped under alternative rules**: how many users would land in a
  different responder/non-responder bucket if we used "majority sentiment"
  or "any-positive ⇒ positive" instead of our "most-recent + signal-strength
  tiebreaker" rule. This is the dedup-rule sensitivity check.

A small flip count (relative to total users) means the headline numbers
are robust to the choice of dedup rule. A large flip count would mean the
analysis is sensitive to dedup methodology and we should be more careful
about justifying the rule."""))

cells.append(("code", r"""
import collections as _coll

_audit_rows = []
for _drug, (_pub_date, _paper_short, _source_date) in DRUG_CUTOFFS.items():
    _win_end_excl = min(_pub_date, END_2022_EXCLUSIVE)
    _cutoff_ts = epoch_midnight(_win_end_excl)
    _rows = fetch_drug_reports(_drug, _cutoff_ts)
    _n_raw = len(_rows)

    # Group by user
    _by_user = _coll.defaultdict(list)
    for _uid, _d, _sent, _sig, _date, _pid in _rows:
        _by_user[_uid].append({'sent': _sent, 'sig': _sig, 'date': _date or 0})

    _n_users = len(_by_user)
    _multi = {u: rs for u, rs in _by_user.items() if len(rs) > 1}
    _n_multi = len(_multi)
    _n_mixed = sum(
        1 for rs in _multi.values()
        if any(r['sent'] == 'positive' for r in rs)
        and any(r['sent'] != 'positive' for r in rs)
    )

    # Apply our dedup rule and count flips against alternatives
    _n_pos_dedup = 0
    _flip_majority = 0
    _flip_any_pos = 0
    for _uid, _rs in _by_user.items():
        _rs_sorted = sorted(
            _rs,
            key=lambda r: (r['date'], SIG_RANK.get(r['sig'], 0)),
            reverse=True,
        )
        _chosen_pos = (_rs_sorted[0]['sent'] == 'positive')
        if _chosen_pos:
            _n_pos_dedup += 1
        if len(_rs) > 1:
            _n_pos = sum(1 for r in _rs if r['sent'] == 'positive')
            _majority_pos = _n_pos > len(_rs) / 2
            _any_pos = _n_pos > 0
            if _majority_pos != _chosen_pos:
                _flip_majority += 1
            if _any_pos != _chosen_pos:
                _flip_any_pos += 1

    _audit_rows.append({
        'drug': _drug,
        'raw_reports': _n_raw,
        'unique_users': _n_users,
        'multi_report_users': _n_multi,
        'mixed_signal_users': _n_mixed,
        'final_n_pos': _n_pos_dedup,
        'final_n_nonpos': _n_users - _n_pos_dedup,
        'flip_majority': _flip_majority,
        'flip_any_pos': _flip_any_pos,
    })

_rows_html = []
for _r in _audit_rows:
    _flip_pct_maj = (100 * _r['flip_majority'] / _r['unique_users']) if _r['unique_users'] else 0
    _flip_pct_any = (100 * _r['flip_any_pos'] / _r['unique_users']) if _r['unique_users'] else 0
    _rows_html.append(
        f"<tr>"
        f"<td style='padding:4px 8px; font-weight:bold;'>{_r['drug']}</td>"
        f"<td style='padding:4px 8px; text-align:right;'>{_r['raw_reports']:,}</td>"
        f"<td style='padding:4px 8px; text-align:right;'>{_r['unique_users']:,}</td>"
        f"<td style='padding:4px 8px; text-align:right;'>{_r['multi_report_users']:,}</td>"
        f"<td style='padding:4px 8px; text-align:right;'>{_r['mixed_signal_users']:,}</td>"
        f"<td style='padding:4px 8px; text-align:right;'>{_r['final_n_pos']:,}</td>"
        f"<td style='padding:4px 8px; text-align:right;'>{_r['flip_majority']} "
            f"<span style='color:#777;'>({_flip_pct_maj:.1f}%)</span></td>"
        f"<td style='padding:4px 8px; text-align:right;'>{_r['flip_any_pos']} "
            f"<span style='color:#777;'>({_flip_pct_any:.1f}%)</span></td>"
        f"</tr>"
    )
_table = (
    "<table style='border-collapse:collapse; width:100%; font-size:0.9em; margin:8px 0;'>"
    "<tr style='background:#34495e; color:white;'>"
    "<th style='padding:6px 10px;'>drug</th>"
    "<th style='padding:6px 10px;'>raw reports</th>"
    "<th style='padding:6px 10px;'>unique users</th>"
    "<th style='padding:6px 10px;'>multi-report users</th>"
    "<th style='padding:6px 10px;'>mixed-signal users</th>"
    "<th style='padding:6px 10px;'>final n (pos)</th>"
    "<th style='padding:6px 10px;'>flips: majority rule</th>"
    "<th style='padding:6px 10px;'>flips: any-positive rule</th>"
    "</tr>"
    + "".join(_rows_html)
    + "</table>"
    + "<p style='font-size:0.85em; color:#777; margin-top:4px;'>"
      "<i>flips: majority rule</i> = users who would have landed in a different "
      "responder bucket under the rule \"majority of reports\" instead of "
      "\"most recent + signal-strength tiebreaker.\" "
      "<i>flips: any-positive rule</i> = same but under the rule \"any positive "
      "report → responder.\" Smaller is more robust.</p>"
)
display(HTML("<h3>Dedup audit &mdash; raw vs unique counts + rule sensitivity</h3>" + _table))

# Print to stdout for build-log visibility
print(f"Dedup audit: {len(_audit_rows)} drugs audited.")
for _r in _audit_rows:
    print(f"  {_r['drug']:<12} raw={_r['raw_reports']:>4} users={_r['unique_users']:>4} "
          f"multi={_r['multi_report_users']:>3} mixed={_r['mixed_signal_users']:>3} "
          f"flip(maj)={_r['flip_majority']:>3} flip(any+)={_r['flip_any_pos']:>3}")
"""))


# ────────────────────────────────────────────────────────────────────
# WINDOW VERIFICATION — actual MIN/MAX(post_date) per drug + assert
# ────────────────────────────────────────────────────────────────────
cells.append(("md", """## Window verification

For each drug we report the actual `MIN(p.post_date)` and `MAX(p.post_date)`
of the classified reports the analysis includes. The `MAX` must be strictly
before `window_end_exclusive` (the publication-date midnight, or 2023-01-01
for the end-of-2022 cap); the cell below asserts this and fails the build
if any drug includes an out-of-window report. We also confirm zero
`post_date IS NULL` rows enter the per-drug analysis.

This complements the SQL predicate `p.post_date < window_end_exclusive_ts`
in `fetch_drug_reports()` — that predicate *prevents* leakage; this audit
*proves* it didn't leak."""))

cells.append(("code", r"""
from datetime import datetime as _dt, timezone as _tz

_audit_rows = []
_violations = []
for _drug, (_pub_date, _paper_short, _source_date) in DRUG_CUTOFFS.items():
    _win_end_excl = min(_pub_date, END_2022_EXCLUSIVE)
    _cutoff_ts = epoch_midnight(_win_end_excl)
    _row = combined_conn.execute('''
        SELECT MIN(p.post_date), MAX(p.post_date), COUNT(*),
               SUM(CASE WHEN p.post_date IS NULL THEN 1 ELSE 0 END)
        FROM treatment_reports tr
        JOIN treatment t ON tr.drug_id = t.id
        JOIN posts p ON tr.post_id = p.post_id
        WHERE lower(t.canonical_name) = ?
          AND p.post_date IS NOT NULL
          AND p.post_date < ?
          AND p.user_id != 'deleted'
    ''', (_drug, _cutoff_ts)).fetchone()
    _mn, _mx, _n, _n_null = _row
    # Also check rows that the IS NOT NULL filter excluded — should be 0
    _null_check = combined_conn.execute('''
        SELECT SUM(CASE WHEN p.post_date IS NULL THEN 1 ELSE 0 END)
        FROM treatment_reports tr
        JOIN treatment t ON tr.drug_id = t.id
        JOIN posts p ON tr.post_id = p.post_id
        WHERE lower(t.canonical_name) = ?
          AND p.user_id != 'deleted'
    ''', (_drug,)).fetchone()
    _n_null_unfiltered = _null_check[0] or 0

    # Assertions: max must be strictly < cutoff_ts; zero nulls
    if _mx is not None and _mx >= _cutoff_ts:
        _violations.append(
            f"{_drug}: MAX(post_date) = {_dt.fromtimestamp(_mx, tz=_tz.utc).isoformat()} "
            f">= window_end_exclusive ({_win_end_excl} 00:00 UTC). LEAKAGE."
        )
    if _n_null_unfiltered:
        _violations.append(
            f"{_drug}: {_n_null_unfiltered} treatment_reports rows have post_date IS NULL "
            "(silently excluded by the IS NOT NULL filter). Investigate."
        )

    _audit_rows.append({
        'drug': _drug,
        'pub_date': _pub_date,
        'win_end_excl': _win_end_excl,
        'min_post_date': _dt.fromtimestamp(_mn, tz=_tz.utc).strftime('%Y-%m-%d %H:%M UTC') if _mn else '-',
        'max_post_date': _dt.fromtimestamp(_mx, tz=_tz.utc).strftime('%Y-%m-%d %H:%M UTC') if _mx else '-',
        'n_reports_pre_dedup': _n,
        'n_post_date_null': _n_null_unfiltered,
        'in_window': _mx is None or _mx < _cutoff_ts,
    })

# Render
_rows_html = []
for _r in _audit_rows:
    _check = '&#10003;' if _r['in_window'] and _r['n_post_date_null'] == 0 else '&#10007;'
    _color = '#27ae60' if _r['in_window'] and _r['n_post_date_null'] == 0 else '#c0392b'
    _rows_html.append(
        f"<tr>"
        f"<td style='padding:4px 8px; font-weight:bold;'>{_r['drug']}</td>"
        f"<td style='padding:4px 8px;'>{_r['pub_date']}</td>"
        f"<td style='padding:4px 8px;'>{_r['win_end_excl']}</td>"
        f"<td style='padding:4px 8px;'>{_r['min_post_date']}</td>"
        f"<td style='padding:4px 8px;'>{_r['max_post_date']}</td>"
        f"<td style='padding:4px 8px; text-align:center;'>{_r['n_reports_pre_dedup']:,}</td>"
        f"<td style='padding:4px 8px; text-align:center;'>{_r['n_post_date_null']}</td>"
        f"<td style='padding:4px 8px; text-align:center; color:{_color}; font-size:1.2em;'>{_check}</td>"
        f"</tr>"
    )
_table = (
    "<table style='border-collapse:collapse; width:100%; font-size:0.9em; margin:8px 0;'>"
    "<tr style='background:#34495e; color:white;'>"
    "<th style='padding:6px 10px;'>drug</th>"
    "<th style='padding:6px 10px;'>pub_date</th>"
    "<th style='padding:6px 10px;'>win_end_excl</th>"
    "<th style='padding:6px 10px;'>actual min</th>"
    "<th style='padding:6px 10px;'>actual max</th>"
    "<th style='padding:6px 10px;'>n (pre-dedup)</th>"
    "<th style='padding:6px 10px;'>nulls</th>"
    "<th style='padding:6px 10px;'>in window?</th>"
    "</tr>"
    + "".join(_rows_html)
    + "</table>"
)
display(HTML(_table))

# Fail loud if anything escaped the window
if _violations:
    raise AssertionError(
        "Window verification FAILED:\n" + "\n".join("  - " + v for v in _violations)
    )
print("Window verification: all 6 drugs in-window, 0 NULL post_dates. PASS.")
"""))


# ────────────────────────────────────────────────────────────────────
# PROVENANCE — display extraction_runs in the executed notebook
# ────────────────────────────────────────────────────────────────────
cells.append(("md", """## Pipeline provenance — `extraction_runs`

This table is the build-DB's record of *which pipeline run produced every
classified report it contains*. Each row links a `run_id` to the git commit
that ran it, the run timestamp, and the run config (models used, target
drug, etc.). The same `run_id` is foreign-keyed onto every
`treatment_reports` row, so any number in Figure 1 / Table 3 can be traced
back to the exact pipeline invocation that produced it.

A machine-readable copy of this table — together with the build-time git
commit, DB SHA-256, and model env — is also written to
`output/provenance.json` at the end of the build."""))

cells.append(("code", r"""
import json as _json
from datetime import datetime as _dt, timezone as _tz

_runs = combined_conn.execute(
    "SELECT run_id, run_at, commit_hash, extraction_type, config "
    "FROM extraction_runs ORDER BY run_id"
).fetchall()

_rows_html = []
for run_id, run_at, commit_hash, extraction_type, config in _runs:
    run_at_iso = _dt.fromtimestamp(int(run_at), tz=_tz.utc).strftime("%Y-%m-%d %H:%M UTC") if run_at else ""
    try:
        cfg = _json.loads(config) if config else {}
    except Exception:
        cfg = {}
    drug = cfg.get("drug") or "(all)"
    fast = (cfg.get("models") or {}).get("fast", "")
    strong = (cfg.get("models") or {}).get("strong", "")
    _rows_html.append(
        f"<tr>"
        f"<td style='padding:4px 8px; text-align:center;'>{run_id}</td>"
        f"<td style='padding:4px 8px;'>{run_at_iso}</td>"
        f"<td style='padding:4px 8px; font-family:monospace; font-size:0.85em;'>{commit_hash[:10] if commit_hash else ''}</td>"
        f"<td style='padding:4px 8px;'>{extraction_type or ''}</td>"
        f"<td style='padding:4px 8px;'>{drug}</td>"
        f"<td style='padding:4px 8px; font-size:0.85em;'>{fast}</td>"
        f"<td style='padding:4px 8px; font-size:0.85em;'>{strong}</td>"
        f"</tr>"
    )

_table = (
    "<table style='border-collapse:collapse; width:100%; font-size:0.9em; margin:8px 0;'>"
    "<tr style='background:#34495e; color:white;'>"
    "<th style='padding:6px 10px;'>run_id</th>"
    "<th style='padding:6px 10px;'>run_at</th>"
    "<th style='padding:6px 10px;'>commit</th>"
    "<th style='padding:6px 10px;'>type</th>"
    "<th style='padding:6px 10px;'>drug</th>"
    "<th style='padding:6px 10px;'>fast model</th>"
    "<th style='padding:6px 10px;'>strong model</th>"
    "</tr>"
    + "".join(_rows_html)
    + "</table>"
    + f"<p style='font-size:0.85em; color:#777; margin-top:4px;'>"
      f"{len(_runs)} pipeline run(s) in this DB. Every classified "
      f"<code>treatment_report</code> row is foreign-keyed to one of these <code>run_id</code>s.</p>"
)
display(HTML("<h3>extraction_runs &mdash; pipeline provenance for this DB</h3>" + _table))
"""))


# ────────────────────────────────────────────────────────────────────
# BUILD + EXECUTE
# ────────────────────────────────────────────────────────────────────
# DB-resolver code embedded in the notebook's setup cell. The notebook
# is a built artifact that may be opened from any cwd (workspace root in
# VS Code, notebook dir in Jupyter Lab, repo root via nbconvert), so the
# path can't be a static literal. This snippet is a self-contained
# inlining of paths.py's resolution logic — anchored on PACKAGE_MARKERS,
# with the RCT_DB_PATH env var as escape hatch. Reviewers see exactly
# how the path is found rather than having to chase imports.
#
# The constants below are read FROM paths.py (DB_FILENAME, PACKAGE_MARKERS,
# ENV_VAR) and interpolated into the template at build time, so any change
# to those constants in paths.py automatically flows through to the
# notebook's inlined resolver — no risk of the two drifting apart.
NOTEBOOK_DB_RESOLVER = '''import os
from pathlib import Path

_DB_FILENAME = "{db_filename}"
_PACKAGE_MARKERS = {package_markers}
_ENV_VAR = "{env_var}"'''.format(
    db_filename=paths.DB_FILENAME,
    package_markers=tuple(paths.PACKAGE_MARKERS),
    env_var=paths.ENV_VAR,
) + '''


def _resolve_db_path():
    """Locate the analysis DB. Order: RCT_DB_PATH env var, then anchor walk
    up from cwd looking for a directory containing both PACKAGE_MARKERS.
    Mirrors paths.py:db_path() so behaviour is identical inside and outside
    the notebook."""
    env = os.environ.get(_ENV_VAR)
    if env:
        p = Path(env).expanduser().resolve()
        if not p.is_file():
            raise RuntimeError(
                f"{_ENV_VAR}={env!r} is set but does not point to an existing file. "
                f"Resolved to: {p}"
            )
        return p
    p = Path.cwd().resolve()
    searched = []
    while True:
        searched.append(str(p))
        if all((p / m).is_file() for m in _PACKAGE_MARKERS):
            db = p / "data" / _DB_FILENAME
            if db.is_file():
                return db
            raise RuntimeError(
                f"Found package root at {p} but DB is missing.\\n"
                f"Expected: {db}\\n"
                f"Set {_ENV_VAR}=/absolute/path/to/{_DB_FILENAME} to override."
            )
        if p.parent == p:
            break
        p = p.parent
    raise RuntimeError(
        "Could not locate the RCT historical validation package root.\\n"
        f"Searched: {searched}\\n"
        f"Set {_ENV_VAR}=/absolute/path/to/{_DB_FILENAME} or cd into "
        f"docs/RCT_historical_validation/."
    )


DB_PATH = str(_resolve_db_path())
conn = sqlite3.connect(DB_PATH)
print(f"DB_PATH resolved to: {DB_PATH}")'''


if __name__ == "__main__":
    # Both the build script and the notebook find the DB via paths.py logic.
    # Anchored on the script's own location, so it works no matter what cwd
    # the user invokes us from.
    SCRIPT_DIR  = Path(__file__).resolve().parent
    DB_PATH     = resolve_db_path(start=SCRIPT_DIR)
    PKG_ROOT    = find_package_root(start=SCRIPT_DIR)
    OUTPUT_DIR  = resolve_output_dir(start=SCRIPT_DIR)

    nb = build_notebook(cells=cells, db_path_block=NOTEBOOK_DB_RESOLVER)
    html_path = execute_and_export(nb, str(OUTPUT_DIR / "paper_figures"))

    # Provenance: write machine-readable manifest tying this output to a
    # specific code revision, DB SHA-256, model env, and pipeline-run set.
    write_provenance_manifest(DB_PATH, OUTPUT_DIR, package_root=PKG_ROOT)

    print(f"\nDone. Open {html_path} to view the results.")
