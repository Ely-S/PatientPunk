# Finding Card And Evidence Packet Design

Date: 2026-07-04

This note defines the A4 unit of reporting and the frozen evidence packet that
should feed any human-readable report.

## Design Goal

A4 should make it structurally hard to produce an unsupported sentence.

Every rendered report should be backed by a frozen packet:

```text
finding cards -> evidence packet -> deterministic renderer -> report.md
```

The report renderer should never compute counts directly from raw rows. It
should render from already-created finding cards and packet claims.

## Finding Card

A finding card is one aggregate claim A4 might show to a researcher or reader.
It should carry both the result and the reason it is or is not reportable.

Recommended fields:

```text
finding_id
report_id
finding_type
title
plain_language_summary
claim_type
normalized_label_canonical
analysis_bucket
cohort_filter_json
time_filter_json
n_claims
n_comments
n_source_runs
n_audited_claims
n_audited_comments
denominator_name
denominator_value
percentage
wilson_interval_json
normalization_review_status
audit_status
reportability_label
reportability_reason
gate_decision
representative_quote_ids_json
source_claim_ids_json
source_comment_ids_json
source_a3_analysis_ids_json
source_a2_run_ids_json
limitations_json
created_at_utc
```

`plain_language_summary` should be deterministic for the first implementation.
Example:

```text
17 normalized claims were extracted from 3 selected comments in this A3 run.
This finding is exploratory because audit labels are missing and normalization
is unreviewed.
```

That sentence is boring, but it is auditable.

## Stable Finding IDs

Finding IDs should be deterministic and content-addressable enough to survive
rerenders:

```text
finding:<report_id>:<finding_type>:<hash_of_scope_and_key>
```

Hash inputs should include:

```text
source_a3_analysis_ids
finding_type
claim_type
normalized_label_canonical
analysis_bucket
cohort_filter_json
time_filter_json
normalization_version
```

Do not include generated timestamps in finding ID hashes.

## Evidence Packet

The evidence packet is the A4 equivalent of The Trial's `EvidencePacket`.
It should be JSON and should be the only source for rendered narrative reports.

Suggested shape:

```json
{
  "packet_id": "packet:<report_id>",
  "report_id": "<report_id>",
  "generated_at_utc": "...",
  "mode": "private_review",
  "source_manifests": [],
  "denominators": {},
  "findings": {},
  "quotes": {},
  "caveats": {},
  "provenance": {},
  "render_policy": {}
}
```

Each `findings` entry should include a `render` string and structured `value`.
This mirrors the Trial packet pattern:

```json
{
  "F1": {
    "kind": "finding",
    "finding_id": "...",
    "render": "17 normalized claims across 3 selected comments.",
    "value": {
      "n_claims": 17,
      "n_comments": 3,
      "denominator_name": "n_work_items_selected"
    }
  }
}
```

Quote entries should be keyed separately:

```json
{
  "Q1": {
    "kind": "quote",
    "quote_id": "...",
    "render": "\"short quote\"",
    "source_claim_id": "...",
    "redaction_status": "not_reviewed",
    "public_allowed": false
  }
}
```

Caveats should be first-class:

```text
C1 source_scope
C2 platform_selection_bias
C3 comment_only_or_missing_root_posts
C4 model_extraction_error
C5 audit_sample_size
C6 no_patient_denominator
C7 no_clinical_verification
C8 quote_redaction_status
```

## Citation Discipline

The Trial uses `cite("S2")` and `quote("Q-pos-1")` against a frozen packet.
A4 should reuse that idea in a quieter form.

For machine-generated or LLM-assisted text, require one of:

```text
cite("F1")
quote("Q1")
caveat("C3")
```

For deterministic Markdown, the renderer can avoid inline citation syntax by
inserting packet renders directly. The validation step should still know which
packet IDs backed each paragraph.

## Renderer Policy

First implementation:

- deterministic renderer only
- no public quotes
- no generative bottom line
- no "advice" sentence beyond a fixed non-medical-use disclaimer

Later implementation:

- optional LLM-assisted plain-language summary
- LLM receives only the evidence packet, not raw A3 tables
- every numeric and quote-bearing sentence must cite packet IDs
- report validation rejects orphan numbers, orphan quotes, and unsupported
  confidence language

## A4 No-Fabrication Gate

The existing Trial gate checks numbers, quotes, caveats, prescription language,
silent-drop safety framing, and phantom citations. A4 should adapt it for
reports.

Initial A4 gates:

```text
R1 number_trace
  Every rendered number or percentage must appear in a cited finding,
  denominator, or provenance item.

R2 quote_trace
  Every direct patient quote must come from a quote packet entry with
  public_allowed=true for public summaries, or private mode for internal review.

R3 caveat_presence
  Every report must include the required caveats for its mode and source data.

R4 confidence_cap
  Report language must not exceed the finding's reportability label.

R5 no_medical_advice
  No start, stop, dose, prescribe, safety, or efficacy directive.

R6 phantom_reference
  Every cited finding, quote, caveat, denominator, and source manifest ID must
  exist in the packet.
```

## Evidence Mart Relationship

The mart is for queries and tables. The packet is for report rendering.

Pipeline:

```text
A3 files
  -> evidence_mart.sqlite
  -> finding_cards.csv/jsonl
  -> evidence_packet.json
  -> report.md/methods.md/limitations.md/provenance.md
  -> validation_report.json
```

The packet should include only the subset of mart-derived facts used in the
report. This keeps rendered reports compact and reviewable.

## Confidence Labels In Cards

Use A4 labels, not clinical certainty labels:

```text
not_reportable
exploratory
weak_signal
suggestive_signal
stable_descriptive_pattern
```

Mapping should remain conservative:

- unaudited finding: `exploratory`
- unreviewed normalization: `exploratory`
- no clear denominator: `not_reportable`
- public quote requested but redaction not reviewed: `not_reportable` for that
  quote, even if the aggregate finding remains exploratory
- repeated audited pattern with accepted labels: may become `suggestive_signal`
- `stable_descriptive_pattern`: later only, after A4 has repeated-run logic and
  enough audit evidence

## Trial-Agent Lessons Applied

Relevant Trial patterns:

- build a frozen packet before any prose generation
- stamp every fact with a stable ID
- render headline numbers by code, not by LLM
- let the model react only to the packet, if a model is used at all
- validate the narrative after generation
- include a fixed safety coda and provenance footer

What not to copy:

- the debate framing
- treatment-sentiment percentages over patient/user denominators
- old treatment-specific side-effect assumptions
- public quote display before A4 redaction review exists

## Research Takeaway

A4's durable abstraction should be the finding card plus the frozen evidence
packet. The report is a rendering of packet facts, not an independent analytic
object.
