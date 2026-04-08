"""
.. deprecated::
    The ``old/`` package is **deprecated**.  Do not add new code here.
    Use ``main.py`` or the ``patientpunk`` library (``patientpunk/``) instead.

    Replacement classes:

    ==========================================  ====================================
    old/ script                                 patientpunk/ replacement
    ==========================================  ====================================
    extract_biomedical.py (Phase 1)             patientpunk.extractors.BiomedicalExtractor
    llm_extract.py (Phase 2)                    patientpunk.extractors.LLMExtractor
    discover_fields.py (Phase 3)                patientpunk.extractors.FieldDiscoveryExtractor
    records_to_csv.py (Phase 4)                 patientpunk.exporters.CSVExporter
    make_codebook.py (Phase 5)                  patientpunk.exporters.CodebookGenerator
    extract_demographics_llm.py                 patientpunk.extractors.DemographicsExtractor
    code_demographics_llm.py                    patientpunk.extractors.DemographicCoder
    run_pipeline.py                             patientpunk.Pipeline
    ==========================================  ====================================

patientpunk.old — DEPRECATED
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Archived reference copies of the original flat scripts.  **Do not modify
these files.** They will likely be deleted before the project ships.

The active, canonical versions of these scripts live in ``scripts/``.
Every class in ``patientpunk/extractors/`` and ``patientpunk/exporters/``
delegates to the ``scripts/`` copy via subprocess.

These ``old/`` copies are kept temporarily so that the originals can be
compared against the ``scripts/`` versions if regressions are suspected.

Script index
------------
extract_biomedical.py
    **Phase 1 — regex extraction.**
    Reads subreddit_posts.json and users/*.json; applies hand-crafted regex
    patterns for all 24+ schema fields; writes per-record JSON to temp/.
    Free, fast (~1–2 min for 300 records).  No API key required.

llm_extract.py
    **Phase 2 — LLM gap-filling.**
    Reads the Phase 1 output and sends records where regex left fields blank
    to Claude Haiku for structured extraction.  Merges LLM results back into
    the regex records.  Uses ``--skip-threshold`` (default 0.7) to skip
    records that regex already covered well.  Requires Anthropic API key.

discover_fields.py
    **Phase 3 — multi-model field discovery.**
    Four-stage pipeline: (1) Haiku scans corpus for new field candidates;
    (2) Sonnet writes and validates regex patterns; (3) regex runs validated
    patterns across the corpus; (4) Haiku fills gaps.  Updates the extension
    schema JSON in place.  Most expensive phase (~$1–3).  Requires API key.

records_to_csv.py
    **Phase 4 — CSV export.**
    Accepts one or more JSON record files and flattens them to a single
    records.csv, merging records that share the same author + post_id.
    Multi-value fields (e.g. conditions, medications) are joined with " | ".

make_codebook.py
    **Phase 5 — codebook.**
    Reads the schema JSON and records.csv and produces a data dictionary
    (codebook.csv or codebook.md) documenting every field: description,
    confidence tier, ICD-10 code, observed coverage %, and example values.

run_pipeline.py
    **Original pipeline orchestrator.**
    Runs all five phases in sequence via subprocess calls — mirrors the logic
    now encapsulated in ``patientpunk.pipeline.Pipeline``.  Kept here as a
    reference implementation.

extract_demographics_llm.py
    **Standalone LLM-only demographics.**
    Extracts only age, sex/gender, and location using Claude Haiku — no regex.
    A self-reference constraint instructs the model to extract only
    demographics the author states explicitly about themselves.  Works across
    both subreddit posts and full user posting histories.  Produces a
    standalone demographics.csv.  Wrapped by
    ``patientpunk.extractors.DemographicsExtractor``.

Environment
-----------
All LLM scripts load the API key from ``.env`` in this directory first, then
fall back to the parent ``variable_extraction/.env``.  The key is read from
the ``ANTHROPIC_API_KEY`` environment variable.
"""
