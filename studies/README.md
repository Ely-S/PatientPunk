# Studies

Methodology and documentation for every PatientPunk study, in one place. Each
study is a subfolder here; nesting reflects dependency (a sub-study lives inside
the study it supports).

Large data — corpora, sample packs, model outputs — is **not** kept in git. Each
study's own README says where its data lives (gitignored `data/` locally, and S3
under `s3://patientpunk/scientific_validation/`).

## Index

| Study | Folder | Status |
|---|---|---|
| RCT historical validation | `rct_validation/` | on `main` (being relocated from `docs/RCT_historical_validation/`) |
| &nbsp;&nbsp;└ IRR pilot (inter-coder reliability) | `rct_validation/irr_pilot/` | PR #39 |
| FDA letter analysis (LDN / Mestinon RWE) | `fda_letter/` | PR #52 |
| &nbsp;&nbsp;└ Phoenix Rising corpus | `fda_letter/phoenix_rising/` | PR #41 |
| Clustering study (long COVID / ME-CFS) | `clustering/` | PR #110 — corpus ready, no run yet |
| NATURAL exploration — TrialScout (U of Toronto) | `natural_exploration/` | **not ready to merge** |

## Why these are nested

- **`rct_validation/irr_pilot/`** — the IRR pilot measures how reliably the
  pipeline's drug-extraction and sentiment labels reproduce human coding; it
  validates the pipeline behind the RCT historical-validation study.
- **`fda_letter/phoenix_rising/`** — the Phoenix Rising ME/CFS forum corpus is a
  data source feeding the FDA letter real-world-evidence analysis.
- **`natural_exploration/`** — TrialScout is part of the NATURAL prospective
  trial-prediction exploration with the University of Toronto. It is **not yet
  ready to merge** and is listed here only to reserve its place in the structure.

> This table is the source of truth for where each study belongs. Studies live on
> separate branches today; each lands in its folder here as its PR merges.
