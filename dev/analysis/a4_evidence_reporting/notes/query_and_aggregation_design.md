# Query And Aggregation Design

Date: 2026-07-04

This note designs the A4 query layer over A3-normalized outputs.

## Design Goal

A4 should make PatientPunk's core question easy to ask:

```text
Among patient self-reports matching a cohort or topic, what patterns are
reported, how often, and with what evidence quality?
```

The query layer should be reproducible and inspectable. Prefer SQLite marts and
CSV exports before dashboards.

## Evidence Mart

A4 should build:

```text
evidence_mart.sqlite
```

Recommended tables:

```text
report_manifest
source_runs
comments
claims
claim_labels
claim_label_frequency
monthly_claim_counts
context_quality
audit_quality
finding_cards
quote_bank
```

The mart is downstream and disposable. It should be fully regenerable from A3
artifacts.

## Grain Rules

Keep grains explicit:

```text
comments: one row per target comment
claims: one row per extracted claim
claim_labels: one row per canonical claim label per run/report
finding_cards: one row per reportable aggregate finding
quote_bank: one row per quote candidate or selected quote
```

Do not mix comment counts and claim counts in the same percentage without naming
the denominator.

## Denominator Policy

A4 should expose denominator columns directly:

```text
n_claims
n_comments_with_claim
n_unique_threads
n_source_runs
n_audited_claims
n_audited_comments
```

Future work may add `n_authors`, but the current split comments dataset does
not have stable hashed author IDs in A2 outputs. A4 should not claim patient
counts until author hashing and deduplication are explicitly implemented.

## Useful First Queries

Claim label frequencies:

```sql
SELECT
  claim_type,
  normalized_label_canonical,
  analysis_bucket,
  COUNT(*) AS n_claims,
  COUNT(DISTINCT comment_id) AS n_comments
FROM claims
GROUP BY claim_type, normalized_label_canonical, analysis_bucket
ORDER BY n_claims DESC;
```

Monthly trend:

```sql
SELECT
  year_month,
  claim_type,
  normalized_label_canonical,
  COUNT(*) AS n_claims,
  COUNT(DISTINCT comment_id) AS n_comments
FROM claims
GROUP BY year_month, claim_type, normalized_label_canonical;
```

Context-sensitive rows:

```sql
SELECT *
FROM claims
WHERE used_context = 1
   OR attribution_confidence != 'high';
```

High-risk report rows:

```sql
SELECT *
FROM claims
WHERE evidence_source != 'target_comment'
   OR normalization_review_status != 'accepted'
   OR confidence = 'low';
```

## Aggregation Patterns

First A4 aggregates:

```text
claim_type x canonical_label
claim_type x assertion
claim_type x experiencer
analysis_bucket x year_month
parent_kind x claim_type
used_context x attribution_confidence
selection_bucket x error/audit rates
```

Treatment-specific aggregates should wait until A3 normalization can reliably
separate:

```text
treatment entity
outcome direction
symptom target
timeline
side effect
```

The current A1 schema has `claim_type=medication_or_treatment`, but it does not
yet model treatment-outcome triples as a first-class relation. A4 should not
pretend it can produce the exact old "64% positive / 20% negative" treatment
report until A1/A3 define that relation.

## Quote Selection

A4 quote selection should be deterministic and auditable.

Quote candidate ranking:

1. audited correct claim
2. high attribution confidence
3. evidence quote length in a readable range
4. non-sensitive after redaction review
5. representative of a high-frequency canonical label
6. not duplicate or near-duplicate of another selected quote

Never select quotes only because they are dramatic. Quote selection should
represent the finding, not maximize persuasion.

## Public And Private Modes

A4 should support two output modes:

```text
private_review
public_summary
```

`private_review` can include source lines, comment IDs, evidence quotes, and
rendered context snippets under ignored local paths.

`public_summary` should use minimized quotes, no Reddit usernames, no direct
permalinks by default, and stronger caveat language.

## Later Dashboard Layer

An interactive dashboard should consume `evidence_mart.sqlite` or exported CSVs.
It should not contain exclusive analysis logic.

Possible dashboard views:

- run quality overview
- claim label frequency explorer
- time trend explorer
- context-sensitive claims queue
- audit disagreement queue
- finding-card builder

## Research Takeaway

A4 should make aggregates easy to compute but difficult to overinterpret. The
query layer must preserve grain, denominator, source-run, normalization, and
audit fields all the way into every finding.

