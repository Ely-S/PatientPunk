# ADR-004: Variable picker with explicit selection, no auto-merge

**Status:** Accepted
**Date:** 2026-04-07
**Deciders:** Shaun

## Context

The field discovery pipeline (Phase 3) finds new candidate variables
inductively from the corpus using LLM analysis. The original design
auto-merged all validated candidates into the schema.

This is problematic for qualitative research: the researcher should
decide which discovered categories are theoretically meaningful and
worth including. Auto-merging everything conflates "the LLM found a
pattern" with "this pattern matters for our research question."

## Decision

Split discovery into three steps with a human decision point:

1. **Batch run:** Pipeline produces a DiscoveryReport with candidate
   fields, regex hit rates, corpus coverage, and example extractions.
2. **Variable picker (apps/discover.py):** Marimo app shows a checkbox
   table of candidates with stats. Researcher checks which to keep.
3. **Selective merge:** `merge_selected()` writes only chosen fields
   into the schema JSON. Unchosen candidates are discarded.

## Consequences

- The discovery pipeline no longer modifies the schema directly.
- The Marimo app is the sole interface for field selection.
- `merge_selected()` takes a `selected_names: set[str]` parameter,
  never an "all" option.
- Rejected candidates can be re-evaluated in future runs without
  polluting the schema.
