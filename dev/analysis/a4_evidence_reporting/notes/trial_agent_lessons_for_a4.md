# Trial Agent Lessons For A4

Date: 2026-07-04

This note extracts implementation lessons from the existing `src/agents`
Trial system for A4 evidence reporting.

## Sources Read

- `README_AGENTS.md`
- `src/agents/_common/packet.py`
- `src/agents/_common/validate.py`
- `src/agents/TheTrialAgent/main.py`
- `src/agents/TheTrialAgent/synthesize.py`
- `eval/trial/rubric.py`
- `tests/trial_test.py`
- `dev/_trial_claude_check.json`

## What The Trial Gets Right

The strongest design pattern is not the courtroom UI or the agent personas. It
is the evidence architecture:

```text
deterministic resolver
  -> frozen EvidencePacket
  -> claim_id-stamped facts
  -> agents may cite only packet IDs
  -> deterministic final briefing for numbers/quotes
  -> no-fabrication gate
```

A4 should copy this structure.

## Frozen Packet Pattern

`src/agents/_common/packet.py` builds an `EvidencePacket` before any debate.
Every number, quote, caveat, and provenance item gets an ID. The agents only see
the packet's prompt block.

A4 equivalent:

```text
A3 analysis package
  -> evidence_mart.sqlite
  -> finding_cards
  -> evidence_packet.json
  -> report renderer
```

The report renderer should read the packet, not the raw A3 files.

## Deterministic Briefing Pattern

`src/agents/TheTrialAgent/synthesize.py` code-renders the headline counts,
confidence tier, side effects, quotes, caveats, safety coda, and provenance
footer. Only a short bottom line is generative.

A4 first implementation should be stricter:

- render all public-facing text deterministically
- use no LLM for report generation
- add LLM summaries only after report validation exists

If A4 later adds LLM language, the model should receive only packet facts and
its output should be validated against the packet.

## No-Fabrication Gate Pattern

`src/agents/_common/validate.py` catches:

```text
G1 orphan numbers
G2 fabricated long quotes
G3 unsupported methodology caveats or wrong n
G4 prescription directives
G5 no-negatives-means-safe framing
G6 phantom citations
```

A4 should adapt these to reports:

```text
R1 orphan numbers
R2 unreviewed or fabricated quotes
R3 missing required caveats
R4 confidence label exceeded
R5 medical advice or efficacy/safety claims
R6 phantom packet IDs
```

This should run on `report.md` and any LLM-assisted summary.

## Provenance Footer Pattern

The Trial always appends provenance. A4 should do the same, but richer:

```text
source A3 analysis IDs
source A2 run IDs
A1 prompt/schema versions
A2 model IDs
A3 analysis/normalization/audit versions
source file hashes
generated_at_utc
report package hash
```

Put the full form in `provenance.md` and a compact version in `report.md`.

## Safety Coda Pattern

The Trial has a fixed non-medical-advice coda. A4 should use fixed caveat text
rather than ask a model to invent caveats.

Suggested A4 fixed language:

```text
These are self-reported comments from one Reddit community. They are useful for
hypothesis generation and lived-experience mapping, not for estimating clinical
prevalence, treatment efficacy, treatment safety, or medical advice.
```

Use this in public reports and in private reports that may be copied elsewhere.

## What A4 Should Not Copy

Do not copy the current Trial denominator:

- The Trial uses deduplicated `user_id` from `treatment_reports`.
- A3 comment-coding outputs currently do not export stable author hashes.
- A4 must not claim "patients" or patient-level percentages until A2/A3 expose
  author/patient identifiers and a dedup policy.

Do not copy treatment sentiment assumptions:

- The old treatment pipeline has positive/negative/mixed/neutral sentiment.
- The A1 comment-coding schema currently emits claim types, assertions,
  experiencers, evidence quotes, and labels.
- A4 can summarize symptom/treatment claim frequencies now, but treatment
  outcome percentages need a new relation.

Do not copy quote behavior directly:

- The Trial prints patient quotes in its briefing.
- A4 should keep quotes private until redaction/review exists.

Do not copy the debate format as the first A4 product:

- The debate is useful for patient-facing engagement.
- A4 first needs a reliable mart, finding cards, and validation.

## A4 Agent Use Later

If A4 later gets Rumi agents, use them only after deterministic packet building:

```text
ReportBuilderAgent
  input: evidence_packet.json
  output: draft prose with cite("F1") / quote("Q1") / caveat("C1")
  validation: R1-R6 gate
```

Potential roles:

```text
MethodsWriterAgent
  Converts provenance and run metadata into clear methods text.

PlainLanguageAgent
  Converts accepted finding cards into cautious summaries.

SkepticAgent
  Reviews report language for overclaiming before public export.
```

None of these agents should be allowed to query raw comments or invent facts.

## A4 Eval Lessons

The Trial eval separates hard gates from quality axes. A4 should do the same.

Hard gates:

- report package validates
- source hashes match
- no orphan numbers
- no unreviewed public quotes
- no medical advice
- no confidence overrun

Quality axes after hard gates:

```text
usefulness
traceability
calibration
methods_transparency
quote_ethics
```

Do not grade usefulness if the hard evidence gate fails.

## Research Takeaway

A4 should inherit The Trial's grounded packet and validation architecture, not
its theatrical presentation or old treatment-specific denominator model. The
main reusable idea is structural: reports should cite a frozen evidence packet,
and validation should make unsupported numbers and quotes impossible to miss.
