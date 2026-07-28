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
`cardiovascular_autonomic`, `pain`, `sleep`, `other_symptoms`). Some belong to more than
one: a migraine is both `pain` and `cognitive_neurological`; dizziness on standing is
both `cardiovascular_autonomic` and `cognitive_neurological`. The prompt instructs the
model to record those in every domain they belong to, with worked examples.

Measured on 300 r/covidlonghaulers posts (Haiku 4.5, temperature 0):

| Symptom | Both domains | One only |
|---|---|---|
| headache / migraine | 5 | 15 |
| nerve / burning pain | 0 | 5 |
| unrefreshing sleep | 1 | 2 |

28 record-symptom pairs: 6 placed in both domains, 22 in one. A small sample, and the
only one there is.

The problem is not *which* domain the model picks; for many symptoms there is no single
right answer, which is why cross-listing exists. It is that the same symptom is placed
differently on different posts with the same or similar language,
so a `pain` / `cognitive_neurological` split carries
variance that has nothing to do with the patient.

**Routing therefore happens during the run**, not in the prompt. The model finds the symptom
once, wherever it filed it, and `llm_extract.fan_out_cross_domain_symptoms` copies it
into the others from `CROSS_DOMAIN_SYMPTOMS`. Placement becomes deterministic through this
constructed lookup table.

- **Effect:** on the same 300 records, `pain` +1.7 points, `cognitive_neurological`
  +1.3, every other field unchanged, 24 values added. Records with at least one symptom
  domain filled stays at 57.7%, so nothing is invented — values are copied, not found.
- **Not configurable.** There is no reason to want inconsistent domain assignment, and
  raw model placement is preserved either way: `temp/llm_records_*.json` is written
  before normalisation, so diffing it against `records_*.json` shows exactly what the
  table added. A flag nobody would turn off is a code path nobody tests.
- **Which symptoms qualify:** only where the symptom is multi-domain *by definition*.
  This is a substring lookup on the value, so a rule that needs context to be correct
  will be wrong on every value that omits it. An earlier pass routed bare `insomnia`,
  `vertigo` and `chest pain`, which are multi-domain only in context — insomnia is sleep
  onset, not post-exertional malaise; vertigo is vestibular; chest pain is as often
  costochondral as cardiac. Those pushed invented signal into `fatigue_pem`, the ME/CFS
  cardinal criterion. Removed, and pinned by negative tests.
- **Limit:** four rules, because the by-definition bar excludes most candidates. Anything
  novel, or multi-domain only in context, still depends on the model. Dizziness with
  orthostatic context has no matching instances in this sample, so it is justified on
  definition and unvalidated on data.
- **How far that reaches:** across the same 300 posts the table matches 42 of 894 symptom
  mentions (4.7%) and 14 of 588 distinct strings (2.4%). Two of the four rules never fire.
  So placement is deterministic for about one mention in twenty; the rest is model
  judgement at an unmeasured consistency. The symptom vocabulary grows at roughly
  corpus^0.72 — about 9,800 distinct strings at 15,000 posts — so a longer hand-written
  table does not close this. Issue #105 tracks resolving each distinct string once and
  caching it instead.
- **Provenance:** the four rules and the by-definition bar are AI-authored and have had
  no clinical review. Freezing them into code makes application reproducible; it does not
  make the mapping correct.
- **Trade-off worth naming:** this moves a clinical-vocabulary decision from the prompt
  into code, so changing it needs a commit rather than a prompt edit. That is the right
  home for a mapping that must stay stable across runs, but the mapping is no longer
  visible to someone reading only the prompt.

## Field provenance

Almost every value in `records.csv` is LLM-produced (`llm_extract`, plus `discover`
for `llm_discovered` fields). The `confidence` column reflects the field's
schema-declared confidence tier. Self/other-sensitive fields (demographics,
conditions, medications) all go through the same SELF-REFERENCE ONLY guard described
above. The generated codebook lists each field's source (`base` / `base_optional` /
`extension` / `llm_discovered`).

**The one exception is the cross-domain fan-out.** Some symptom-domain values are copied
from another domain by a lookup table rather than found by the model. The record does not
mark which — a fanned-out value is indistinguishable from a model-placed one and carries
the same confidence. Raw model placement is still available: `temp/llm_records_*.json` is
written before normalisation, so diffing it against `records_*.json` shows exactly what
the table added.

## Run provenance

Each run writes `output/llm_provenance.json`:

| Key | Why it is there |
|---|---|
| `provider`, `model_fast`, `model_strong`, `base_url` | Which model answered |
| `temperature`, `service_tier` | Sampling settings |
| `schema_id`, `run_llm`, `discovery_mode` | Which phases ran against which schema |
| `git_commit` | The prompt, canonical maps, closed vocabularies and field list all live in code |

The commit matters more than it looks. Extraction is close to deterministic at
temperature 0 — field-level fill rates move about 0.1 points across identical runs — so
a larger difference between two runs is a real effect. But it is only *attributable* if
you know whether the code changed: prompt edits during this work moved `conditions` by 6
points and `medications` by 5.3, and nothing in the output said so.

**Two limits.** The commit is read from `.git` rather than by shelling out, because the
pipeline does not call `subprocess`. That means a modified working tree is not detected:
the record says which commit was *checked out*, not that the code matched it. And
nothing hashes the corpus, so the same commit and settings against a different input
slice look identical in the record.

Replay works for the deterministic half. `temp/llm_records_{schema_id}.json` holds raw
model output before normalization; re-running canonicalization, the closed-vocabulary
pass and the fan-out over that file reproduces `records_{schema_id}.json` exactly.

### What a run persists

| Artifact | Path | Survives the next run | Holds |
|---|---|---|---|
| API response cache | `cache/<provider>/<model>/…json` | **Yes** | One file per LLM call: response text, model, temperature, timestamp |
| Scraped corpus | `output/subreddit_posts.json` | **Yes** | The extractor's input |
| Flattened records | `output/records.csv` | **Yes** | One row per patient, values pipe-joined |
| Codebook | `output/codebook.csv` | **Yes** | Field list with source and confidence tier |
| Run provenance | `output/llm_provenance.json` | **Yes** | Provider, model, temperature, schema_id, git_commit |
| Raw model records | `output/temp/llm_records_{schema_id}.json` | No | Per-record extraction before normalization |
| Normalized records | `output/temp/records_{schema_id}.json` | No | Per-record extraction after normalization, with per-field confidence |

The cache is on by default (`LLM_CACHE=0` to disable) and nothing in the pipeline deletes
it, but it is gitignored — it lives only on the machine that ran the pipeline.

`_clean_temp()` empties `temp/` at the start of any full run with `--clean`. Its patterns
are schema-agnostic globs, so running one schema removes another schema's records too,
not just its own. Re-running with a warm cache costs no API calls, so those two files are
regenerable rather than lost, provided the corpus, schema and commit still match.

Three things that follow, and are easy to get wrong:

- **Per-field confidence exists only in the temp JSON.** `records.csv` carries values but
  no confidence columns. `export_csv --confidence` adds them, but that flag is not wired
  into `main.py run` (issue #94), so the durable CSV cannot currently carry confidence.
- **The cache records answers, not questions.** An entry stores `response_text` and the
  key, not the prompt behind it. Entries are interpretable only by regenerating the
  identical prompt — same corpus, schema and commit, which is what `git_commit` pins.
- **Analysis over symptom values does not need any of the temp files.** The domain columns
  are in `records.csv`, so post-processing that only reads symptom strings can run off the
  durable output long after the run.

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
