# ADR-003: Two-pipeline architecture joined via SQLite

**Status:** Accepted
**Date:** 2026-04-07
**Deciders:** Shaun, Polina

## Context

PatientPunk has two independent extraction pipelines:

1. **Shaun's pipeline** (variable_extraction): Regex + LLM extraction of
   demographics, conditions, and clinical variables from Reddit posts.
2. **Polina's pipeline** (database_creation): Drug sentiment classification
   from the same Reddit corpus.

Both pipelines process the same subreddit_posts.json corpus and share
`author_hash` as a natural join key.

## Decision

Join the two pipelines via a SQLite database (schema.sql) using
`author_hash = user_id` as the foreign key.

Table ownership:

- **Shared:** `users`, `posts` (loaded by either pipeline first)
- **Shaun's pipeline:** `user_profiles`, `conditions`, `extraction_runs`
- **Polina's pipeline:** `treatment`, `treatment_reports`

The core product query ("which drugs help people like me?") joins
`treatment_reports` with `user_profiles` and `conditions` on `user_id`.

## Consequences

- Both pipelines must produce `author_hash` consistently.
- The composite key in sentiment_cache.json ("entry_id:drug_name") must
  split on the FIRST colon only (`split(":", 1)`) since drug names may
  contain colons.
- SQLite is the single source of truth for the query app; CSV outputs
  remain for exploratory use but are not canonical.
