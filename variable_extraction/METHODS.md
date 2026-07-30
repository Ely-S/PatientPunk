# Methods & Known Biases

This documents the extraction pipeline's **design decisions, self/other attribution
model, and known biases** — the things that determine how much you can trust an
extracted number and what you can tune. For *how to run* the pipeline, see
[`README.md`](./README.md); for per-field definitions, generate the codebook
(`main.py make-codebook` / the codebook exporter).

Recommendations below are the maintainers' suggestions, not enforced defaults —
where a knob exists, the current default is stated explicitly.

## Two extraction paths

| Path | Command | Method | Output | Feeds analysis? |
|---|---|---|---|---|
| **Main pipeline** | `main.py run` | LLM extraction (`llm_extract`) + optional discovery (`discover`) | `records.csv` (all fields) | **Yes — authoritative.** Loaded into the DB (`load_extractions` / `load_variables`); consumed by `cluster-prep` and `validate`. |
| **Demographics** | `main.py demographics` | LLM only (Haiku), deductive + inductive | `demographics.csv` | Optional/supplementary — `load_extractions` also accepts it. |

Per-drug and per-patient analysis reads `records.csv` from the **main pipeline**
unless you deliberately load the demographics output.

## Attribution model — only self-reported information

The pipeline extracts **only what the post author states about themselves.** This is
enforced in every LLM prompt (`llm_extract`, `demographics`, `discover`) and in the
shared `qualitative_standards` "SELF-REFERENCE ONLY" block — third-party mentions
("my mom has POTS") are ignored. Every field is LLM-produced, so every field goes
through this guard — there is no unguarded regex surface (the old regex first pass
was removed; see [issue #86](https://github.com/Ely-S/PatientPunk/issues/86)).

One caveat to know:

- **Post extraction uses title + body only.** Comments are written by other users, so
  they are excluded from the post-author record; commenters are captured as their own
  patients via the aggregate path.

## Known biases & tunable guards

Each entry is a *measured* effect with a knob and a default.

### Group-attribution (`helped` inflation)

In "stack" posts — several treatments named together with a single **collective**
outcome ("this stack helped") — the model can copy that outcome onto every named
treatment, inflating per-drug `helped` rates.

- **Measured:** on a 3-arm test, enabling the guard moved `helped` share **47% → 43%**
  (~6% `helped`→`unknown` vs a 1% noise floor).
- **Knob:** `PP_GROUP_GUARD=1` (env var only — no CLI flag). **Default: off** — chosen
  to preserve reproducibility of prior runs.
- **Recommended:** enable for any analysis that reports per-drug `helped` rates; leave
  off to reproduce pre-guard numbers.

## Field provenance

Every field in `records.csv` is LLM-produced (`llm_extract`, plus `discover` for
`llm_discovered` fields). The `confidence` column reflects the field's schema-declared
confidence tier. Self/other-sensitive fields (demographics, conditions, medications)
all go through the same SELF-REFERENCE ONLY guard described above. The generated
codebook lists each field's source (`base` / `base_optional` / `extension` /
`llm_discovered`).

The `subreddits` column is metadata, not an extracted field. It counts which
communities a record's text came from, as `name:count` pairs — `covidlonghaulers:3
cfs:1` for an aggregated patient, `covidlonghaulers:1` for a single post.

Aggregation merges a patient's posts across communities on purpose: one person is
one patient wherever they wrote. This column is what tells you afterwards how mixed
a record is. It does not say which *value* came from which community — a merged
record carries no per-value provenance.

## Base field selection

Fields were kept or cut on measured fill rate. The rates come from 1,177 records
extracted from one month of r/covidlonghaulers under an earlier pipeline version, so
they justify this cut but are not a baseline any current run can be compared against.

35 fields went in (23 base, 12 optional) and 24 came out (19 base, 5 optional). Every
retained field fills at 10.4% or better and every cut field fell below that, so no
field was ever kept on clinical grounds against a low rate — the framework column
below records where a field is grounded, it did not decide anything.

| Field | Fill rate | Frameworks |
|---|---|---|
| `age` | 22.7% | demographic standard |
| `sex_gender` | 20.5% | demographic standard |
| `location_country` | — | demographic standard |
| `conditions` | 52.3% | RECOVER, PC-COS |
| `onset_trigger` | 35.3% | RECOVER |
| `medications` | 44.4% | clinical standard |
| `dosage` | — | clinical standard |
| `treatment_outcome` | 38.7% | PC-COS |
| `procedures` | 12.2% | clinical standard |
| `work_disability_status` | 16.5% | SF-36 |
| `mental_health` | 21.3% | EQ-5D, SF-36, PROMIS, RECOVER, PC-COS |
| `prior_infections` | 11.3% | RECOVER |
| `functional_status_tier` | 30.2% | EQ-5D, SF-36, PROMIS |
| `social_impact` | 33.5% | EQ-5D, SF-36, PROMIS |
| `alternative_treatments` | 20.0% | — |
| `dietary_interventions` | 13.8% | — |
| `misdiagnosis` | 10.4% | — |
| `illness_duration` | 18.3% | RECOVER |
| `illness_trajectory` | 17.2% | RECOVER |

`location_country` and `dosage` were not measured separately.

**Cut:** `activity_level`, `age_at_onset`, `diagnosis_source`, `diagnostic_odyssey`,
`doctor_dismissal`, `ethnicity`, `family_history`, `healthcare_costs`,
`healthcare_system`, `hormonal_events`, `location_us_state`, `time_to_diagnosis`.
Their individual rates were not retained; only `age_at_onset` is recorded, at 0.7%.

**Frameworks.** Retained fields are cross-referenced against the outcome instruments
used in post-viral illness research, so the variable set is legible outside this
project:

| Tag | Instrument |
|---|---|
| EQ-5D | EuroQol 5-dimension health status measure |
| SF-36 | 36-Item Short Form Health Survey |
| PROMIS | Patient-Reported Outcomes Measurement Information System |
| RECOVER | NIH RECOVER Initiative long-COVID cohort protocol |
| PC-COS | Post-COVID Core Outcome Set (Lancet Respiratory Medicine) |
| ME/CFS CCC | Myalgic Encephalomyelitis Canadian Consensus Criteria |

`demographic standard` and `clinical standard` are not instruments; they mark fields
any patient-record schema carries.

## Known limitations

- **`db.py`'s "other people" backstop is coarse.** When loading demographics it rejects
  *multi-valued* age/sex (assuming multiple values imply other people) but not single
  wrong-person values, and it does not filter conditions at all. It is a backstop, not
  the primary self/other guard — that lives in the extraction prompt.
- **`collect_texts_from_post` is duplicated across modules.** The copies must stay
  identical (title + body only); a shared helper would prevent divergence.
