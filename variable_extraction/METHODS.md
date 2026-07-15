# Methods & Known Biases

This documents the extraction pipeline's **design decisions, self/other attribution
model, and known biases** — the things that determine how much you can trust an
extracted number and what you can tune. For *how to run* the pipeline, see
[`README.md`](./README.md); for per-field definitions, generate the codebook
(produced as Phase 5 of `main.py run`, or via `main.py export`).

Recommendations below are the maintainers' suggestions, not enforced defaults —
where a knob exists, the current default is stated explicitly.

## Two extraction paths

| Path | Command | Method | Output | Feeds analysis? |
|---|---|---|---|---|
| **Main pipeline** | `main.py run` | regex first pass (`biomedical`) + LLM gap-fill (`llm_extract`) + discovery | `records.csv` (all fields) | **Yes — authoritative.** Loaded into the DB (`load_extractions` / `load_variables`); consumed by `cluster-prep` and `validate`. |
| **Demographics** | `main.py demographics` | LLM only (Haiku), deductive + inductive | `demographics_deductive.csv` (+ inductive JSON) | Optional/supplementary — `load_extractions` also accepts `demographics_deductive.csv`. |

Per-drug and per-patient analysis reads `records.csv` from the **main pipeline**
unless you deliberately load the demographics output.

## Attribution model — only self-reported information

The pipeline extracts **only what the post author states about themselves.** This is
enforced in every LLM prompt (`llm_extract`, `demographics`, `discover`) and in the
shared `qualitative_standards` "SELF-REFERENCE ONLY" block — third-party mentions
("my mom has POTS") are ignored.

Two caveats to know:

- **Regex extraction (`biomedical`) has no self/other awareness.** It matches patterns
  anywhere in the text, so regex-produced demographic/condition values are the one
  *unguarded* surface. See *Regex vs LLM demographics* below.
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
- **Knob:** `PP_GROUP_GUARD=1` (env) — read by the LLM phase, so it takes effect with
  `main.py run`. (A `--group-guard` CLI flag exists on the standalone `llm_extract`
  entrypoint, but **`main.py run` does not accept it** — use the env var.) **Default: off**,
  to preserve reproducibility of prior runs.
- **Recommended:** enable for any analysis that reports per-drug `helped` rates; leave
  off to reproduce pre-guard numbers.

### Regex vs LLM demographics (age / sex / location)

The main pipeline extracts demographics with regex (unguarded) plus LLM gap-fill
(guarded). The LLM covers far more and is self/other-safe; regex's unique catches are
almost all false positives.

- **Measured** (100- and 220-record r/covidlonghaulers samples): LLM coverage is
  **2–5× regex**. The only value regex uniquely catches that the LLM misses is the
  compact `NNF`/`NNM` shorthand (~0.6% of records); every other regex-only demographic
  hit was a false positive (multi-person or packed garbage) the LLM correctly rejected.
- **Knob:** the demographic patterns in `biomedical.py`. **Default: regex on.**
- **Recommended:** treat the LLM as authoritative for age/sex/location; if keeping
  regex, keep only the `NNF`/`NNM` shorthand and drop the looser patterns.

## Field provenance

Every field in `records.csv` comes from regex, LLM, or both (regex first pass, LLM
gap-fill). The `confidence` column reflects the LLM's stated confidence. Self/other-
sensitive fields (demographics, conditions, medications) are only as reliable as the
guard on the path that produced them: **LLM-produced values are guarded; regex-produced
values are not.** The generated codebook lists each field's extraction method.

## Known limitations

- **`db.py`'s "other people" backstop is coarse.** When loading demographics it rejects
  *multi-valued* age/sex (assuming multiple values imply other people) but not single
  wrong-person values, and it does not filter conditions at all. It is a backstop, not
  the primary self/other guard — that lives in the extraction prompt.
- **`collect_texts_from_post` is duplicated and has diverged.** It should be title + body
  only everywhere, but `discover.py`'s copy currently also folds in commenters' text (a
  fix is proposed on the PR), and the copies differ on `[removed]`/`[deleted]` filtering
  (`biomedical` filters via `_keep_text`; `llm_extract` does not). A shared helper would
  prevent this.
