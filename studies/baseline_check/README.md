# Baseline Check

Evidence behind the Baseline Check weekly questionnaire (page: `docs/baseline_check/index.html`).
The scripts were written during exploratory sessions and are kept as they ran, so each one reads and
writes files in its own folder.

Corpus: `reddit_2026-06-13.db` (long COVID / ME/CFS subreddits).

## Folders

| Folder | Page version | What it holds |
|---|---|---|
| `v02_analysis/` | v0.2 | Corpus scans (`fts_counts.py`, `patterns.py`, `scan.py`, `level_rx.py`), LLM coding of a 900-post sample plus a 150-post repeat (`code_llm.py`, `analyze_*.py`), activity ladder (`ladder*.py`), self-rating test–retest (`longit.py`), coder agreement (`quality/agree.py`), first coverage pass (`coverage/`) |
| `v03_rechecks/b_matters/` | v0.3, item 1 | Blind recode of what change matters most (242 posts, 3 coders); `CODEBOOK.md`, `analyze.py` |
| `v03_rechecks/c_coverage/` | v0.3, item 4 | Blind coverage regrade (114 posts); `CODEBOOK.md`, `analyze.py` |
| `v03_rechecks/d_checks/` | v0.3, items 2, 3, 5, 6 | Crash-delay scan (`delay.py`); results for all four in `RESULTS.md` |
| `v03_rechecks/a_instrument/t/` | v0.3 | jsdom tests for the form (12 checks) |

## Data stays out of Git

Post batches, coded rows (`*.jsonl`, and the `b*.py` / `c*.py` files that write coded rows as Python),
samples and page drafts contain post text, so `.gitignore` excludes them. They exist only in the local copy of
this folder. Back them up to private S3 before deleting the local copy.

## Reproduce

Use the project Python (3.10+; `longit.py` needs `statistics.correlation`):

```sh
cd studies/baseline_check
(cd v03_rechecks/b_matters && uv run python analyze.py)                        # item 1: 43% symptom, 23% trajectory, 8% activity
(cd v03_rechecks/c_coverage && uv run python analyze.py ../../v02_analysis/coverage/coded.jsonl)  # item 4: blind 57% fully
(cd v02_analysis && uv run python longit.py)                                   # item 6: r=0.63, SDC ~30 points
(cd v03_rechecks/d_checks && uv run python delay.py /path/to/reddit_2026-06-13.db)  # item 2
(cd v03_rechecks/a_instrument/t && npm ci && node test.js ../../../../../docs/baseline_check/index.html)
```
