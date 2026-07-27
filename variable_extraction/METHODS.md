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

## Known limitations

- **`db.py`'s "other people" backstop is coarse.** When loading demographics it rejects
  *multi-valued* age/sex (assuming multiple values imply other people) but not single
  wrong-person values, and it does not filter conditions at all. It is a backstop, not
  the primary self/other guard — that lives in the extraction prompt.
- **`collect_texts_from_post` is duplicated across modules.** The copies must stay
  identical (title + body only); a shared helper would prevent divergence.
