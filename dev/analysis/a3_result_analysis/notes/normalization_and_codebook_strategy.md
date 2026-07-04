# Normalization And Codebook Strategy

Date: 2026-07-04

This note designs A3 normalization and codebook generation for A2 claim rows.

## Local Lessons

`patientpunk.normalize` establishes the right rule:

```text
preserve raw values
add derived canonical values
version the normalization logic
report cardinality before and after
```

`patientpunk.cluster_prep` shows why this matters. High-cardinality free text
fragments analyses and clustering. A2 `normalized_label` is useful, but it is
still model text and will drift across prompts/models.

`scripts/make_codebook.py` shows the right output shape:

```text
field
source
description
coverage
example values
allowed values
```

For A3, the "fields" are both table columns and controlled values such as
`claim_type`, `assertion`, `experiencer`, `confidence`, and canonical claim
labels.

## Normalization Boundary

A3 should never overwrite model output.

Keep:

```text
normalized_label
raw_text
evidence_quote
```

Add:

```text
normalized_label_clean
normalized_label_canonical
analysis_bucket
normalization_version
normalization_rule
normalization_notes
```

`claim_rows_normalized.csv` should be a derived A3 export, not an A2 primary
table in the first slice.

## First Label Inventory

Before writing rules, A3 should generate frequency tables:

```text
claim_label_frequency.csv
claim_type_label_frequency.csv
claim_type_assertion_frequency.csv
claim_type_experiencer_frequency.csv
claim_type_confidence_frequency.csv
```

Minimum columns for label frequency:

```text
claim_type
normalized_label
normalized_label_clean
n_claims
n_comments
n_runs
first_seen_run_id
example_raw_text
example_evidence_quote
```

This lets a human decide whether a label is already canonical, a synonym, too
broad, too narrow, or not useful.

## Mapping File

A3 should use an editable CSV mapping file:

```text
dev/analysis/a3_result_analysis/normalization_maps/comment_coding_v0.1_claim_labels.csv
```

Suggested columns:

```text
schema_version
prompt_version
claim_type
raw_label_clean
canonical_label
analysis_bucket
rule_type
rule_version
review_status
notes
```

`rule_type` values:

```text
exact
synonym
regex
manual
passthrough
drop
```

`review_status` values:

```text
unreviewed
accepted
needs_review
deprecated
```

The default behavior for unmapped labels should be cleaned passthrough, not
blanking. A3 can flag high-frequency passthroughs for review.

## Initial Cleaning

A3 can safely apply deterministic surface cleaning before mapping:

- lowercase
- strip whitespace
- normalize punctuation to spaces
- collapse repeated spaces
- remove wrapping quotes
- preserve medically meaningful characters such as `/`, `+`, `%`, and `-`

Do not stem or aggressively lemmatize in the first slice; that can collapse
clinically different labels.

## Analysis Buckets

A3 should start with modest buckets, not a large ontology.

Potential symptom buckets:

```text
cardiovascular
respiratory
neurological
fatigue_energy
pain
gastrointestinal
immune_inflammatory
sleep
mental_health
functional
other
unclear
```

Potential treatment buckets:

```text
medication
supplement
diet_lifestyle
rehabilitation_exercise
medical_procedure
device_monitoring
healthcare_access
other
unclear
```

These should be optional derived buckets. The canonical label remains the more
specific value.

## Codebook Generation

A3 should generate both:

```text
codebook.csv
codebook.md
```

Column-level codebook rows:

```text
table
column
description
type
allowed_values
source
nullable
contains_text
derived
coverage_pct
example_values
```

Controlled-value sections:

```text
claim_type allowed values
experiencer allowed values
assertion allowed values
confidence allowed values
skip_reason allowed values
analysis_bucket values
```

For each canonical label in the normalization map:

```text
claim_type
canonical_label
analysis_bucket
raw_label_examples
n_claims
n_comments
review_status
```

## Versioning

A3 should have an explicit normalization version:

```text
claim_label_normalization_v0.1
```

Every normalized output should record:

```text
normalization_version
normalization_map_sha256
source_claim_rows_sha256
generated_at_utc
```

If the map changes, A3 should generate a new normalized export instead of
silently mutating older outputs.

## A4 Reportability Needs

A4 will build evidence marts from normalized claim rows. To avoid overclaiming,
A3 should expose normalization review state directly.

Add these columns to `claim_rows_normalized.csv`:

```text
normalized_label_clean
normalization_review_status
normalization_notes
```

Allowed `normalization_review_status` values:

```text
unreviewed
accepted
needs_review
deprecated
```

A4 can use unreviewed labels in exploratory frequency tables, but stable
finding cards should require `accepted` canonical labels or an explicit override
in the report manifest.

## What Not To Normalize Yet

Do not normalize these in the first slice:

- `raw_text`
- `evidence_quote`
- full context strings
- `ambiguity_notes`

Those are evidence and audit materials, not categorical variables.

Do not force all `normalized_label` values into a finite ontology until enough
claim rows have been reviewed. The first job is measuring cardinality and
identifying high-impact label groups.

## Research Takeaway

A3 normalization should begin as an auditable mapping layer over A2
`claim_rows.csv`. The key design is preserving raw model labels while adding
canonical analysis columns with explicit map versions and coverage/cardinality
reports. For A4, A3 also needs to expose whether each canonical label has been
reviewed enough to support reportable findings.
