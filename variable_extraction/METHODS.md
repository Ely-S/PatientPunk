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

### Cross-domain symptoms (inconsistent domain assignment)

Symptoms are split across six domains (`fatigue_pem`, `cognitive_neurological`,
`cardiovascular_autonomic`, `pain`, `sleep`, `other_symptoms`). Some symptoms belong to
more than one: a migraine is both `pain` and `cognitive_neurological`, dizziness on
standing is both `cardiovascular_autonomic` and `cognitive_neurological`. The extraction
prompt instructs the model to record those in **every** domain they belong to, with
worked examples.

**The model largely does not comply.** Measured on 300 r/covidlonghaulers posts
(Haiku 4.5, temperature 0), counting each record where a rule's symptom appears in at
least one of its domains:

| Symptom | Both domains | One only | Compliance |
|---|---|---|---|
| nerve / burning pain | 0 | 5 | **0%** |
| headache / migraine | 5 | 15 | 25% |
| unrefreshing sleep | 1 | 2 | 33% |
| orthostatic dizziness | 0 | 0 | — (no instances) |
| **overall** | **6** | **22** | **21%** |

The prompt's own first worked example (migraine → `pain` + `cognitive_neurological`)
lands at 25%. Orthostatic dizziness did not occur in this sample in a form the rule
matches, so that rule is justified on definition but unvalidated on data.

**Which symptoms qualify is a separate question, and an earlier version of this table
got it wrong.** A first pass also routed bare `insomnia` into `fatigue_pem`, bare
`vertigo` and `dizziness` into `cardiovascular_autonomic`, and bare `chest pain` into
`cardiovascular_autonomic`. Those are not multi-domain by definition — insomnia is sleep
onset, vertigo is vestibular, chest pain is as often musculoskeletal as cardiac — and
routing them was a diagnosis dressed up as a lookup. The insomnia case is the instructive
one: the model filed it under `sleep` alone in **16/16** records, which read as 0%
compliance but was the model being *right*. Perfect consistency against a rule is
evidence the rule is wrong, not that the model is. `CROSS_DOMAIN_SYMPTOMS` now admits a
trigger only if it is multi-domain by definition, and the negative cases are pinned by
tests.

**Why this matters more than the raw miss rate.** The problem is not that the model
picks the "wrong" domain — for many symptoms there is no single right answer, which is
why cross-listing exists. The problem is that the choice is **inconsistent**: the same
symptom lands in one domain on one post and two on the next, for reasons that have
nothing to do with the patient. Any clustering feature built on the `pain` /
`cognitive_neurological` split then encodes model variance as if it were patient
variance. Either policy applied *uniformly* — always one domain, or always both —
would be more analysable than 28% compliance. Inconsistency is the defect, not
under-fanning.

**The fix is to stop asking the model.** Routing a known symptom to known domains is a
lookup, not a judgement. With the knob enabled, the model only has to find the symptom
once — in whichever domain it chose — and `llm_extract.fan_out_cross_domain_symptoms`
copies it into the others from `CROSS_DOMAIN_SYMPTOMS`. That is 100% consistent by
construction, reproducible across model versions, and independent of temperature.

- **Measured:** 21% → **100%** (28/28) re-normalising the same 300 records, adding 24
  values. The fan-out also rescues symptoms the model filed entirely outside a rule's
  domains — a migraine left in `other_symptoms` still reaches `pain` and
  `cognitive_neurological`. Effect on fill: `pain` +1.7pt, `cognitive_neurological`
  +1.3pt, everything else unchanged. Records with at least one symptom domain filled
  stays at 57.7%, because the fan-out redistributes rather than invents.
- **Knob:** `--no-cross-domain-fanout` (on `main.py run` and
  `python -m patientpunk.llm_extract`) or `PP_CROSS_DOMAIN_FANOUT=0` to disable.
  **Default: on.** This is the opposite of the group-attribution guard above, and
  deliberately so: that guard defaults off to reproduce *published pre-guard runs*,
  and no such runs exist for the symptom domains — they ship in this schema version.
  Defaulting off would make 24%-consistent domain assignment what anyone gets
  without knowing to ask for better.
- **Disable when:** you specifically want raw model placement, e.g. to re-measure
  compliance or to study how the model routes symptoms on its own.
- **Limit:** only symptoms listed in `CROSS_DOMAIN_SYMPTOMS` fan out, and the list is
  deliberately short — four rules, because the by-definition bar excludes most
  candidates. A novel or context-dependent cross-domain symptom still depends on the
  model. The knob closes a known gap; it does not close the general case. Extending the
  table is a one-line edit, but each addition has to clear the same bar.
- **Trade-off worth naming:** this moves a clinical-vocabulary decision from the prompt
  into code, so changing it needs a commit rather than a prompt edit. That is the right
  home for a mapping that must stay stable across runs, but it does mean the mapping is
  no longer visible to someone reading only the prompt.

## Field provenance

Every field in `records.csv` is LLM-produced (`llm_extract`, plus `discover` for
`llm_discovered` fields). The `confidence` column reflects the field's schema-declared
confidence tier. Self/other-sensitive fields (demographics, conditions, medications)
all go through the same SELF-REFERENCE ONLY guard described above. The generated
codebook lists each field's source (`base` / `base_optional` / `extension` /
`llm_discovered`).

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
