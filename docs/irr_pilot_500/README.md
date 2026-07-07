# IRR Pilot — 500 samples

A second inter-coder reliability (IRR) sample pack, drawn from the
**Nov–Dec 2021 window** of r/covidlonghaulers — the same window the
historical-validation paper analyses for famotidine, loratadine, and
prednisone. 500 stratified samples (50% AI-found-drug / 30% keyword
match / 20% random) so per-drug agreement statistics have meaningful
sample size.

## Status — ⚠️ NOT YET CODED

Samples are drawn and ready, but no human or AI coder has run against
this set yet. There is no α report, no `human_coder_*.csv`, no
`ai_coder_*.csv` — just the inputs.

When the 500-pilot is run, results (per-coder CSVs, α report) will live
in `data/irr_pilot_500/` (gitignored), parallel to the 300-pilot's
`data/irr_pilot/` outputs.

## Files

- [`SAMPLING_METHODOLOGY.md`](./SAMPLING_METHODOLOGY.md) — how the 500
  samples were drawn (corpus, codable pool, 50/30/20 stratification,
  seed)
- `coding_input.csv` *(not tracked in git)* — the 500 sampled units
  (sample_id, subreddit, post_date, unit_type, title, parent_context,
  post_text), one row per sample. Contains verbatim patient text, so it
  lives in gitignored `data/irr_pilot_500/` and is distributed to coders
  privately (and via S3), not committed here. Regenerable from the seed
  (see [`SAMPLING_METHODOLOGY.md`](./SAMPLING_METHODOLOGY.md)).
- `ai_labels.csv` *(not tracked in git)* — analyst-only stratum labels +
  AI-pipeline output per sample. This is the answer key; publishing it
  would break coder blinding, so it stays in the same private location as
  `coding_input.csv`.
- [`coder_output_template.csv`](./coder_output_template.csv) — blank
  form coders fill in (one row per sample, one row added per additional
  drug for multi-drug samples).

The codebook used by this pilot is the same as the one used by the
300-sample pilot. See
[`../irr_pilot/CODING_INSTRUCTIONS.md`](../irr_pilot/CODING_INSTRUCTIONS.md).
It is **not** duplicated in this folder.
