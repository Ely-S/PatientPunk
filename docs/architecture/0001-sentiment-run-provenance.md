# ADR 0001: Version sentiment run provenance

## Status

Accepted

## Context

Sentiment runs stored a small unvalidated configuration dictionary. It omitted
prompt identity, provider, reasoning mode, dirty checkout state, and several
behavior-affecting options. Comparing two run records could not establish
whether they used the same run definition.

## Decision

Each sentiment run stores one validated provenance record with:

- a schema identifier;
- Git commit and dirty state;
- provider, fast model, strong model, and reasoning mode;
- one SHA-256 identity for the complete prompt bundle;
- behavior-affecting pipeline options; and
- a SHA-256 fingerprint of the canonical provenance record.

The existing `extraction_runs.commit_hash` column remains populated for
backward compatibility. The full record is stored in `extraction_runs.config`.

The fingerprint is traceability metadata. This decision does not change cache
keys, resume behavior, or classification behavior.

## Consequences

Runs with the same recorded definition have the same fingerprint. Prompt,
model, code, reasoning, or option changes produce a different fingerprint.
Dirty runs are identifiable but cannot be reproduced from their commit alone.
