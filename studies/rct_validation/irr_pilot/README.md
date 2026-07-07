# IRR Pilot — 300 samples

The original inter-coder reliability (IRR) sample pack used to compare
the PatientPunk pipeline's drug-extraction and sentiment classifications
against human coders. 300 stratified samples drawn from a 1-month
r/covidlonghaulers corpus (2026-03-11 → 2026-04-10), distributed to
11 coders (2 human, 9 AI models).

## Files

- [`SAMPLING_METHODOLOGY.md`](./SAMPLING_METHODOLOGY.md) — how the 300
  samples were drawn (corpus, codable pool, stratification, seed)
- [`CODING_INSTRUCTIONS.md`](./CODING_INSTRUCTIONS.md) /
  [`.pdf`](./CODING_INSTRUCTIONS.pdf) — codebook (v1.4) distributed to
  coders. Defines the `personal_use` / `sentiment` / `signal_strength` /
  `confidence` schema and the per-drug-row decision tree.
- `coding_input.csv` *(not tracked in git)* — the 300 sampled units
  (sample_id, subreddit, post_date, unit_type, title, parent_context,
  post_text), one row per sample. Contains verbatim patient text, so it
  lives in gitignored `data/irr_pilot/` and is distributed to coders
  privately (and via S3), not committed here. Regenerable from the seed
  (see [`SAMPLING_METHODOLOGY.md`](./SAMPLING_METHODOLOGY.md)).
- `ai_labels.csv` *(not tracked in git)* — analyst-only stratum labels +
  AI-pipeline output per sample. This is the answer key; publishing it
  would break coder blinding, so it stays in the same private location as
  `coding_input.csv`.
- [`coder_output_template.csv`](./coder_output_template.csv) — blank
  form coders fill in (one row per sample, one row added per additional
  drug for multi-drug samples).

## Status

**Coded.** All 11 coders (2 human + 9 AI panel) returned outputs;
Krippendorff's α was computed on `personal_use`, `sentiment`,
`signal_strength`, and `drug_extracted`. The α report and per-coder
output CSVs (`human_coder_*.csv`, `ai_coder_*.csv`, `merged_long.csv`,
`alpha_report.md`, `alpha_pairwise_*.csv`) live outside this docs folder
in `data/irr_pilot/`, which is gitignored at the repo level.
**Per-coder outputs are intentionally not redistributed** in this
repo — coder identity is paired with coding decisions in those files,
and we treat that pairing as private to the team.
