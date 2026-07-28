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
| insomnia | 0 | 16 | **0%** |
| neuropathy | 1 | 6 | 14% |
| headache / migraine | 5 | 19 | 21% |
| chest pain | 4 | 10 | 29% |
| unrefreshing sleep | 1 | 2 | 33% |
| dizziness | 8 | 8 | 50% |
| **overall** | **19** | **61** | **24%** |

Insomnia never once reached `fatigue_pem`, and the prompt's own first worked example
(migraine → `pain` + `cognitive_neurological`) lands at 21%.

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

- **Measured:** 24% → **100%** (81/81) re-normalising the same 300 records. The fan-out
  also rescues symptoms the model filed entirely outside a rule's domains — a "chest
  pain" left in `other_symptoms` still reaches `pain` and `cardiovascular_autonomic`,
  which is why the ON total is one pair higher than the OFF total.
- **Knob:** `--cross-domain-fanout` (on `main.py run` and `python -m patientpunk.llm_extract`)
  or `PP_CROSS_DOMAIN_FANOUT=1`. **Default: off** — chosen to keep a plain run
  comparable with earlier ones, matching the group-guard convention.
- **Recommended:** enable for any run feeding clustering.
- **Limit:** only symptoms listed in `CROSS_DOMAIN_SYMPTOMS` fan out. A novel
  cross-domain symptom still depends on the model, exactly as today — the knob closes
  a known gap, it does not close the general case. The table is plain data; extending
  it is a one-line edit.
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

## Known limitations

- **`db.py`'s "other people" backstop is coarse.** When loading demographics it rejects
  *multi-valued* age/sex (assuming multiple values imply other people) but not single
  wrong-person values, and it does not filter conditions at all. It is a backstop, not
  the primary self/other guard — that lives in the extraction prompt.
- **`collect_texts_from_post` is duplicated across modules.** The copies must stay
  identical (title + body only); a shared helper would prevent divergence.
