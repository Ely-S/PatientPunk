# ADR: keep dual-judge audit outside extraction databases

## Decision

Use a post-pipeline, read-only audit over persisted latest decisions. Run two
subscription-backed CLI judges independently before any discussion. Relay their
structured verdicts for at most 10 rounds, then mark unresolved if needed. Never
apply judge corrections directly to extraction tables. Store audit records in an
external SQLite database and resume by a source-and-value-derived decision ID.

## Rationale

The source pipelines append results and can be rerun. An audit that mutates their
tables would obscure provenance and confound comparisons. Separate records preserve
the original decision, both judges' evidence, prompt template hashes, model identities,
and disagreement history. The original prompts can be reconstructed from the saved
task and verdict sequence with the versioned templates. CLI failures pause work rather than being interpreted as
patient evidence or silently falling back to API billing.

## Limitation

The current database has no durable rows for every rejected prefilter or discarded
model candidate. Those decisions cannot be audited until their producers persist
them. Agreement between two models requires calibration against human adjudication.
