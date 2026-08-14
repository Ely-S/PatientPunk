# Second-pass extraction — design

Status: design agreed, not yet built. Supersedes the prototype in
`studies/psychedelics/extract_pharmacology.py`, which is a POC to be discarded.

---

## 1. The feature

Ask a follow-up question of a *filtered subset* of the corpus.

> For posters who mention psilocybin — what dose, what effect, how long, what
> adverse events?

> For posters who report POTS and tried LDN — what did they try first?

The first pass (`variable_extraction/`, `src/run_sentiment_pipeline.py`) reads the
whole corpus and produces per-author fields and per-post drug sentiment. A second
pass starts from a *cohort* — defined by the results of the first pass, or by an
earlier second pass — re-reads the raw source text for those authors, and produces
structured, source-anchored **claims**.

The unit of work is a **probe**: a declared question, scoped to a cohort, answered
against a schema, with its provenance and cost accounted for.

---

## 2. What the POC proved

`extract_pharmacology.py` is 2,360 lines. Roughly 300 are about psychedelics; the
rest is a hand-rolled second-pass engine. It ran a 25-pair pilot: 38 units, 271
events, $0.17.

It also stalled. Four sessions, 43 tests, a working pipeline — and zero validated
output, because the analyst-coding step ran through a CSV whose cells contained
embedded source text and a hand-authored `analyst_events_json` blob. The
extraction was never the bottleneck. The human loop was.

Both halves of that are inputs to this design.

---

## 3. Learnings ledger

### Carried forward

| # | Learning | Evidence | Lands as |
|---|---|---|---|
| L1 | Regex does keyword recall only. Whose experience it is, and whether the use happened, are model-labelled in the same LLM call. | A first-person regex gate silently destroyed 208 patient-drug pairs of recall. Three rounds of pattern narrowing moved groundability 29.8% → 36.5% and never resolved "I haven't tried ECT, but I have tried ketamine infusions." | Engine invariant |
| L2 | Extract the denominator. Plans, third-party reports, and unclear cases are emitted and labelled, not filtered at retrieval. | If nothing lands in `planned_or_considered`, the model isn't classifying — a signal you only get if those events exist. | Every claim schema declares an `included` predicate over its own labels |
| L3 | Per-field evidence anchors; paraphrase allowed. | Exact-substring validation was implemented and abandoned — models legitimately normalize. | Engine requires a non-empty quote per field, tied to a source window. No substring check. |
| L4 | Silence ≠ absence. | `reported` / `explicit_none` / `not_stated` — a boolean turns silence into a negative finding. | Provided base type probes compose |
| L5 | Split identity: *what work* (unit) vs *what work, judged how* (run). | A unit is the same work regardless of how its output is scored; the cache key is prompt-based, so the validator belongs to run identity and not to `unit_key`. | Engine |
| L6 | The cache key must cover everything that changes the answer. | A `**_ignored` kwarg swallow meant reasoning effort never reached the provider, and a max-effort call could be served a no-reasoning cached response. | Engine + a test that a dropped kwarg fails loudly |
| L7 | Log the provider response *before* validating it. | Otherwise truncations, malformed responses, and crash-before-commit vanish, and cost accounting under-reports. | Engine |
| L8 | `billing_uncertain` is a state. | A transport failure with no usage block is not free. | Engine |
| L9 | Sample at the analysis unit, never the compute unit. | Sampling batches made a reviewer code half of one person's history. | Engine samples cohort rows, returns all their units |
| L10 | Under reasoning models, cost is unknowable before a live call. | Pre-pilot projection was $1.18–$11.26; measured was 12,279 reasoning tokens/unit → ~$5.40. The estimate table was obsolete within a session of being written. | Lifecycle forces a *measured* re-projection. No cost tables in code. |
| L11 | Quotes plus hashed authors plus Reddit IDs are re-identifiable. | Study constraint. | Structural DB boundary, not a gitignore rule |
| L12 | Carrying a first-person anchor across sentences is a prompt problem, not a retrieval problem. | The POC's system prompt solves it in prose. | Prompt text survives the rewrite verbatim |
| L13 | Extraction is unstable: 36.5% field-set and 58.8% value agreement across two identical passes. | Corpus README. | Replication is a built-in measurement, not a checklist step. Cohort aggregates only; no per-person stories. |

### Discarded

| Prototype | Why |
|---|---|
| `EXPECTED_COHORT` hardcoded counts + drift assertion | A cohort hash detects drift better and needs no maintenance |
| Pinned price constants, three-row cost projection table | Obsolete within one session. Read pricing from provider metadata, record it, report measured spend |
| Provider routing pins, 65,536-token escalation ceiling | Chasing byte-determinism from a cheap reasoning endpoint that cannot provide it. Record what happened instead of pinning what should have |
| `source_units.json` *and* `.jsonl`; `cohort_status` *and* `cohort_status_final`; `finalize` rebuilding JSON from append-only ledgers | All of it is SQLite's job |
| Five CLI verbs with divergent guards | Three |
| `pilot_review.csv` — one row per unit, embedded source text, hand-authored JSON in a cell | The direct cause of the stall |

---

## 4. Architecture

### 4.1 A probe declares four things

```
probes/psychedelic_pharmacology/
  cohort.sql       SELECT author_hash, :target AS target FROM ... WHERE ...
  evidence.py      anchored(fts=..., term=...) | author_window(budget=...)
  claim.py         Pydantic model + `included` predicate + prompt body
  gates.toml       thresholds, review sample size, replication rate
```

Everything else belongs to the engine: identity, unit batching, cache, transport,
mechanical validation, ledger, cost accounting, sampling, gate scoring, promotion.

Target size: ~500 lines, against the POC's 2,360. Most of the difference is
SQLite absorbing the ledger, the artifact reconciliation, and `finalize`.

### 4.2 Cohort — SQL over `patientpunk.db`

The filters this feature exists to serve ("posters who mention X and report Y")
are joins across `treatment_reports`, `variables`, `conditions`, and `unified`.
A filter DSL would reimplement a fraction of SQL, worse.

Contract: a single `SELECT`, executed read-only, returning `author_hash` and
optionally `target`. The resolved row set is hashed into run identity, so cohort
drift is detected as a changed hash rather than a hand-maintained count.

This makes `load_db.py` (README Step 4) a prerequisite for every probe. The POC
filtered a records JSON directly; carrying that forward would mean maintaining two
filter surfaces permanently.

**Chaining is the point.** A cohort may select from a prior probe's claims:

```sql
SELECT author_hash FROM claim
WHERE probe = 'psychedelic_pharmacology' AND included = 1 AND ...
```

Upstream `run_id`s are recorded as `derived_from`, so a chain of passes is
traceable end to end.

### 4.3 Evidence — two retrieval modes, declared

- **`anchored`** — FTS candidates → term regex → paragraph ±1 windows around each
  mention, deduped, with a stable `source_window_id`. For questions keyed on a
  term.
- **`author_window`** — the author's text within a character budget, no keyword
  gate. For questions that aren't ("what was their exercise history?").

Declaring the mode is mandatory. The two produce different denominators, and
conflating them yields "share of reports mentioning X" figures that silently mean
different things.

Filtering before the LLM is limited to keyword recall and bot detection (L1).

### 4.4 Claim — Pydantic per probe

Cross-field invariants are the load-bearing part of a claim schema and cannot be
expressed in JSON Schema. In the POC these were
`outcomes_require_actual_self_use` and `adverse_fields_agree` — a plan or someone
else's report structurally cannot carry doses or outcomes.

Division of responsibility:

- **Engine — mechanical only.** JSON/schema validity, unknown keys, enum and range
  errors, duplicate claims, `source_window_id` belongs to the unit and its
  type/ID agree, every evidence quote non-empty, placeholder strings rejected
  outside quotes.
- **Probe — semantic.** Its own `model_validator`s, over its own labels.

The engine never second-guesses a model label. If the model says `subject=self`,
that stands, and the review pass measures whether it was right.

**Prompt composition.** The engine supplies an invariant preamble: source text is
untrusted data inside `<patient_text>`, evidence-quote discipline, no placeholder
values, emit the denominator. The probe supplies the domain body. The POC's
system prompt — anchor carrying, stacked-attribution rules, modal verbs not making
a use hypothetical — is the most valuable artifact it produced and is copied
forward verbatim into the psychedelics probe body.

### 4.5 Storage — SQLite, with a privacy boundary

Private, gitignored, one file per probe: `data/probes/<probe>.db`

```sql
unit(unit_key, run_id, author_hash, target, windows_json, character_count, ...)
attempt(run_id, unit_key, variant, transport_attempt, response_sha256,
        input_tokens, output_tokens, reasoning_tokens,
        estimated_cost, billing_uncertain, error, recorded_at)
claim(run_id, probe, author_hash, target, source_id, source_window_id,
      claim_type, included, payload_json, evidence_json)
review(run_id, claim_rowid, agree, note, coded_at)
```

Shared, committed: `patientpunk.db` gets `probe_run` (run identity, spec hashes,
cohort hash, `derived_from`) and de-quoted aggregates that `unified` can roll up.

Quotes never cross into `patientpunk.db`. L11 becomes a schema property rather
than a matter of discipline — a future analysis physically cannot join a quote
into a committed artifact.

The four indexed columns on `claim` (`author_hash`, `target`,
`source_window_id`, `included`) are what the engine and gate scoring need.
Per-probe nested structure stays in `payload_json`; there is no attempt at one
relational schema across all probes.

Using SQLite as the ledger removes `finalize` entirely: writes are transactional,
resume is a query, and there is no rebuild-from-JSONL step to reconcile.

### 4.6 Lifecycle — three verbs

```bash
uv run python -m probes plan   <probe>
uv run python -m probes run    <probe> --pilot --confirm-paid-run
uv run python -m probes review <probe> --export | --import <csv> | --score
```

- **`plan`** — resolve the cohort, build units, compute identity, project cost.
  Never calls an LLM.
- **`run`** — one code path; `--pilot` is a sampling flag, not a separate command.
  Always requires `--confirm-paid-run`. After a pilot it prints the *measured*
  cost re-projection, replacing the estimate rather than sitting beside it.
  `--replicate <frac>` re-runs a stratified subset under a fresh cache key and
  reports instability inline (L13).
- **`review`** — export a coding sample, import coded rows, score gates, and
  promote to `patientpunk.db` only on a pass.

### 4.7 Two tiers

The full apparatus is correct for a study you intend to publish and fatal to "I
just want to ask a follow-up question about these posters."

- **`probes ask <probe> --limit N`** — cached, no ledger, no gates, rows written
  with `provisional = 1`.
- **`probes run <probe>`** — full run identity, ledger, pilot, gates.

Hard rule: provisional rows are never promoted, and gate scoring refuses to read
them. Publishing means re-running under full identity. Exploration stays cheap and
the provenance guarantee stays absolute.

---

## 5. Review — scope decision

**An interactive review tool is out of scope.** The engine owns the export
format, the import format, gate scoring, and promotion; producing the coded data
is the analyst's own workflow.

The export must not reproduce the POC's failure:

- one row per **claim**, not per unit;
- source window text on the row;
- coding is `agree` / `disagree` columns filled with y/n;
- no JSON authoring in a spreadsheet cell.

**Consequence — recall degrades, deliberately.** Precision gates survive at
spreadsheet scale: y/n per emitted claim. Recall requires the analyst to
enumerate what the model *missed*, which is exactly what forced
`analyst_events_json` into a CSV cell. Two options, unresolved:

1. Measure recall on a much smaller window-level sample with a free-text "missed"
   column, and report it as a documented estimate rather than a hard gate.
   *(preferred)*
2. Gate on precision only, and state the limitation in the study.

Gate scoring stays bag-of-claims within a source window rather than
claim-to-claim alignment — model and analyst legitimately split a window into
different numbers of claims.

`--replicate` still supplies instability measurement without any human coding,
and for a corpus with 36.5% pass-to-pass field agreement that is the number that
matters most.

---

## 6. Build order

1. Probe DB schema + `plan` — cohort SQL → units → identity → cost projection. No
   LLM anywhere in this step.
2. `run` — transport, cache, mechanical validation, attempt/claim ledger, cost
   accounting. L6, L7, and L8 as explicit tests.
3. Review export/import + gate scoring + promotion to `patientpunk.db`.
4. Psychedelics rebuilt as a probe spec (~150 lines; prompt carried verbatim),
   pilot re-run, coded, gated. This is the first time the POC's question actually
   gets answered.
5. `ask` tier.
6. Chained cohorts — `derived_from` recorded, prior-probe claims selectable.

---

## 7. Open decisions

**Do the existing 271 pilot claims survive?** They live in
`data/psychedelics_pharmacology_pilot_coreweave_fp8_provider_workers10_evidence_quotes_20260807/`.
Under a new engine their run identity is meaningless, but they remain model output
over known source windows. Importing them as `provisional` gives step 3 a free
test corpus for the import path. The alternative is a clean $0.17 re-run.

**Are gates a house default with per-probe override, or fully per-probe?** The POC
declared 100% grounding, ≥95% attribution and self-report, ≥90% dose/duration/AE.
A probe author setting their own passing grade is a conflict of interest, which
argues for a house default — but then one probe can be blocked by a bar it never
needed.

**Recall gating** — option 1 or 2 in §5.

---

## 8. Constraints that carry over unchanged

From `studies/psychedelics/_handoff.txt` §2, and binding on every probe:

- Self-selected Reddit reporting cohort, not a clinical cohort.
- No efficacy, causal, incidence, or dose-response-over-time claims.
- No chronology inferred from timestamps; duration must be explicitly stated.
- A rate is "share of extractable reports mentioning X," never incidence. Always
  state the denominator.
- Silence is never "none."
- One person may report repeated or contradictory exposures; do not collapse them
  into one summary.
- No collective "stack" outcome assigned to a single component unless the source
  attributes it specifically.
- Quote-bearing artifacts stay private (§4.5) and are never committed.

---

## 9. V1 data-model and storage boundary

§4 describes the design in full. V1 builds a strict subset of it, so this section
records what `probes/models.py` and `probes/store.py` actually contain — the
sketch in §4.5 is the target, not the shipped schema.

### In V1

Six tables in the gitignored private `data/probes/<probe>.db`:

| Table | Holds |
|---|---|
| `probe_run` | immutable run identity: spec/cohort/source/unit-set hashes + `config_json` |
| `cohort_member` | the resolved SQL row set, one row per ordinal |
| `unit` | one bounded provider input, with its lifecycle status |
| `source_window` | private quote-bearing source text, checksummed |
| `attempt` | one provider response or transport failure, written before validation (L7) |
| `claim` | opaque `values_json` + `evidence_json`, keyed to a source window |

The models are deliberately domain-blind: `Claim.values` is a `dict` the engine
never interprets. A probe validates its own semantics and normalizes into that
field, which is what keeps one engine serving unrelated questions (§4.4).

Three differences from the §4.5 sketch, all intentional:

- **`probe_run` lives in the private DB, not `patientpunk.db`.** Nothing is
  promoted in V1, so a run identity in the shared database would have no reader.
- **`source_window` is its own table**, not a `windows_json` blob on `unit`. It is
  the FK target for `claim`, which is how "this claim's window belongs to this
  unit" becomes a database constraint instead of an engine check.
- **No `variant` column on `attempt`, and no `review` table.** Both belong to
  features V1 excludes.

`patientpunk.db` is an input to a probe and never an output. Quotes, raw
responses, source text, and hashed author IDs exist only behind
`data/probes/`, which satisfies L11 structurally.

### Not in V1

Review/export, gate scoring, promotion to `patientpunk.db`, `provisional` mode
and the `ask` tier, `--replicate`, chained cohorts and `derived_from`, public
de-quoted aggregates, and migration of the POC's 271 pilot claims. §7's open
decisions stay open — V1 does not answer them.

The engine (§4.6 `plan`/`run`) and the psychedelics probe (§4.1) follow in
later PRs on top of these contracts.
