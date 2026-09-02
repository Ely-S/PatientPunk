# ADR 0001: Keep subreddit cohorts independent

## Status

Accepted

## Context

The 7,8-DHF study now analyzes nine Reddit communities. A person may post in more
than one community, and each community has a different selection mechanism. Adding
records or denominators across communities would therefore risk double counting and
would blur source-specific reporting patterns.

## Decision

Each subreddit has its own source corpus, author corpus, sentiment database, variable
extraction output, combined database, and report. Author votes are deduplicated only
within a compound and subreddit. Cross-subreddit outputs show independent rows and an
aggregate overlap-count matrix. They do not calculate pooled counts, rates, or tests.

All cohorts use the same deterministic author-hash algorithm. Deleted and unidentified
authors are excluded from overlap claims. Raw corpora, hashes, databases, caches, and
run outputs remain in the external `PatientPunk_data` directory. Only privacy-safe
aggregate reports and reproducible code may be committed.

Dose and route summaries use source-corroborated Pipeline B rows. The stricter
post-level analysis requires the compound, one quantitative dose, and the
treatment-specific outcome to occur in the same report.

## Consequences

Subreddit results can be compared descriptively but cannot be treated as independent
patient samples without consulting the overlap matrix. Sparse cohorts remain visible
with explicit warnings rather than being enlarged through pooling. Regeneration takes
longer because each model pipeline runs independently, but provenance and source
boundaries remain auditable.
