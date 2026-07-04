# A4 Evidence Reporting

A4 is the downstream evidence and reporting layer for the staged Reddit comment
analysis pipeline.

A0 extracts and indexes comments. A1 defines the coding instrument. A2 runs it
safely. A3 validates, scores, normalizes, and summarizes run outputs. A4 turns
that measured output into queryable evidence tables and human-readable reports
without losing provenance, uncertainty, or audit status.

A4 is meant to answer:

- what can a researcher safely say from the extracted comments?
- what denominators and caveats belong next to every count or percentage?
- what aggregate tables support questions about symptoms, treatments, outcomes,
  time, context, and patient subgroups?
- how should patient quotes be selected, redacted, and linked back to evidence?
- what confidence label should each finding carry?
- what A3 artifacts must exist before a finding can be reported?

Current research notes:

```text
notes/evidence_reporting_research.md
notes/a3_to_a4_contract.md
notes/query_and_aggregation_design.md
notes/reporting_guardrails.md
notes/a4_implementation_research.md
notes/finding_card_and_packet_design.md
notes/quote_ethics_and_publication_policy.md
notes/trial_agent_lessons_for_a4.md
```

Generated reports and marts should stay under ignored derived data paths, not
inside `dev/analysis/`.

## Main Commands

Build a complete private-review A4 report package from one A3 analysis run:

```powershell
python dev/analysis/a4_evidence_reporting/scripts/build_report.py `
  --a3 dataset/covidlonghaulers_comments/derived/a3_result_analysis/runs/<a3_run_id>
```

Build with an explicit report ID:

```powershell
python dev/analysis/a4_evidence_reporting/scripts/build_report.py `
  --a3 dataset/covidlonghaulers_comments/derived/a3_result_analysis/runs/<a3_run_id> `
  --report-id <report_id>
```

Validate an existing A4 report package:

```powershell
python dev/analysis/a4_evidence_reporting/scripts/validate_report.py `
  --report dataset/covidlonghaulers_comments/derived/a4_evidence_reporting/reports/<report_id>
```

The default output layout is:

```text
dataset/covidlonghaulers_comments/derived/a4_evidence_reporting/reports/<report_id>/
  report_manifest.json
  evidence_mart.sqlite
  finding_cards.jsonl
  finding_cards.csv
  evidence_packet.json
  tables/
  quotes/
  report.md
  methods.md
  limitations.md
  provenance.md
  validation_report.json
```

The first implementation is deterministic and private-review oriented. It does
not call an LLM, does not publish unreviewed quotes, and does not upgrade A3
reportability labels.
