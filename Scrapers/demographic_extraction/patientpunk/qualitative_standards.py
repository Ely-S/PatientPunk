"""
patientpunk.qualitative_standards
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Qualitative coding standards injected as context into every LLM prompt
in the PatientPunk pipeline.

Background
----------
Qualitative content analysis requires the same rigour as quantitative research.
These principles — drawn from graduate-level research methods texts (Strauss &
Corbin, Miles & Huberman, Krippendorff) — are given to the model as explicit
instructions so that extracted values behave as valid, reliable, and
reproducible measurements rather than informal paraphrases.

Usage
-----
Each script that calls an LLM imports the appropriate constant from here and
appends it to the system prompt:

    from patientpunk.qualitative_standards import EXTRACTION_STANDARDS
    system_prompt = base_prompt + "\\n\\n" + EXTRACTION_STANDARDS

Three variants are provided depending on the task the model is performing:

FIELD_DESIGN_STANDARDS
    For agents that are *defining new fields* (Phase 3 — field discovery).
    Full seven-principle block covering levels of measurement, MEE,
    operationalization, parsimony, double-barreling, construct validity, and
    unit of observation.  Also includes worked examples and anti-patterns.

EXTRACTION_STANDARDS
    For agents that are *coding text against existing fields* (Phase 2 — LLM
    gap-filling).  A condensed four-principle block: operationalization,
    construct validity, MEE in value selection, and unit of observation.
    Enough to keep extraction decisions disciplined without overwhelming the
    prompt with field-design guidance that isn't relevant here.

DEMOGRAPHIC_STANDARDS
    For agents doing *demographic-only coding* (standalone demographics
    extractor).  Minimal — focused on self-reference, operationalization of
    demographic concepts, confidence calibration, and evidence citation.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# FIELD DESIGN STANDARDS
# Injected when the model is discovering / defining new fields (Phase 3).
# ---------------------------------------------------------------------------

FIELD_DESIGN_STANDARDS: str = """
CODEBOOK BEST PRACTICES — graduate research methods level
---------------------------------------------------------
You are acting as a qualitative research methodologist, not just a text
scanner.  Every field you propose must meet the standards a peer reviewer
would expect in a social-science or medical informatics journal.

1. LEVELS OF MEASUREMENT — choose the right one:
   - Nominal: unordered categories. e.g. vaccine brand (Pfizer, Moderna, AstraZeneca).
     Use when categories have no natural order. Each value is just a label.
   - Ordinal: ordered categories. e.g. severity (mild < moderate < severe < bedbound).
     Use when rank matters but the intervals between ranks are unequal.
   - Avoid interval/ratio for text extraction — you cannot reliably extract
     "pain = 7.3" from patient narrative.
   Rule of thumb: if you cannot sort the values meaningfully, it is nominal.
   If you can sort but cannot do arithmetic on them, it is ordinal.

2. MUTUALLY EXCLUSIVE AND EXHAUSTIVE (MEE):
   Every observation must fit into exactly ONE category, and every possible
   observation must fit into SOME category.
   - Bad: categories "mild" and "moderate" overlap if "mildly moderate" is possible.
   - Bad: categories that don't cover "unknown" or "not mentioned" leave gaps.
   - Fix: design categories so no value could reasonably belong to two of them,
     and add a catch-all option for edge cases where needed.

3. OPERATIONALIZATION — the bridge between concept and measurement:
   A field is only useful if you can define exactly what text evidence counts
   as an instance of it. Ask: "Would two independent coders agree on whether
   this sentence belongs in this field?"  If not, the definition is too loose.
   - Bad: "supplement_efficacy" — too vague; coders will disagree.
   - Good: "supplement_reported_helpful" with values (helped / no_effect /
     worsened / mixed) — coders will agree because the coding rule is explicit.

4. PARSIMONY — fewer, cleaner categories beat many overlapping ones:
   3–7 categories per field is a good target.  More than 10 usually means the
   field is actually two separate fields, or the categories are not truly
   distinct.
   - Bad: 15 different specialist types with overlapping scope.
   - Good: 6–8 core specialist types with an "other" catch-all.

5. AVOID DOUBLE-BARRELED FIELDS — one field, one concept:
   If a field tries to capture two things at once, split it.
   - Bad: "medication_and_outcome" (two concepts in one field).
   - Good: separate "medication_tried" and "treatment_outcome" fields.
   A signal that a field is double-barreled: the extracted_value needs
   punctuation (→, ;, :) to hold it together.

6. CONSTRUCT VALIDITY — does the extracted value actually measure the concept?
   The text evidence must be a reliable indicator of the underlying construct,
   not just a surface-level linguistic match.
   - Bad: capturing "worked" as treatment_outcome — "it worked out that I
     couldn't go" is not a treatment outcome.
   - Good: require "worked" adjacent to a medication name or procedure.

7. UNIT OF OBSERVATION — what does one extracted value represent?
   Be explicit: is one value per sentence? Per post? Per medication? Per patient?
   Most fields here are per-patient. If a field is per-medication, the value
   should be just the medication name — not a sentence about it.
""".strip()


# ---------------------------------------------------------------------------
# EXTRACTION STANDARDS
# Injected when the model is coding text against existing schema fields
# (Phase 2 — LLM gap-filling).
# ---------------------------------------------------------------------------

EXTRACTION_STANDARDS: str = """
QUALITATIVE CODING STANDARDS
-----------------------------
You are performing structured qualitative content analysis, not free-form
summarisation.  Apply these principles to every value you extract:

1. OPERATIONALIZATION — use the field definition as your coding rule:
   Extract a value only when the text contains evidence that clearly satisfies
   the field's definition.  Ask: "Would a second coder reading the same text
   make the same extraction decision?"  If there is reasonable doubt, set null.

2. CONSTRUCT VALIDITY — match the concept, not just the surface words:
   The extracted value must reflect the underlying construct the field measures.
   Words that look relevant can be false positives.
   - "it worked out" ≠ treatment outcome.
   - "I stayed home" ≠ housebound status.
   - "my sister has POTS" ≠ patient's own condition.
   Always verify the author is describing themselves and that the context
   matches the field's intended meaning.

3. MUTUALLY EXCLUSIVE VALUE SELECTION — when a field is categorical:
   Pick the single best-fitting category.  If two categories seem to apply,
   choose the more specific one, or return both only if the field semantics
   genuinely allow multiple values (e.g. a list field like "conditions").

4. UNIT OF OBSERVATION — extract at the right granularity:
   Most fields are per-patient (one value describing the author's overall
   situation).  For list fields (conditions, medications), extract one entry
   per distinct item.  Do not merge two separate items into a single value.
""".strip()


# ---------------------------------------------------------------------------
# DEMOGRAPHIC STANDARDS
# Injected for demographic-only coding tasks (age / sex / location).
# ---------------------------------------------------------------------------

DEMOGRAPHIC_STANDARDS: str = """
DEMOGRAPHIC CODING STANDARDS
-----------------------------
You are performing structured demographic coding at the standard expected in
epidemiological and social-science research.  Apply these rules strictly:

1. SELF-REFERENCE ONLY — operationalize "the author" precisely:
   Extract ONLY information the post author states directly about themselves.
   Ignore all third-party mentions regardless of how prominent they are.
   - "my 65-year-old father" → do not extract age.
   - "she mentioned she's from Texas" → do not extract location.
   - "25M here" → extract age=25, sex_gender="male".
   If the author's own demographics are ambiguous, return null.

2. CONSTRUCT VALIDITY — explicit statement, not inference:
   Do not infer demographics from indirect signals (username, writing style,
   pronouns used by other commenters, community norms).  The author must
   have stated the value explicitly.
   - "he/him flair" set by someone else → not valid evidence.
   - "I am a 34-year-old woman living in Ohio" → valid evidence for all four fields.

3. CONFIDENCE CALIBRATION — use the scale consistently:
   - high:   Author states the value explicitly and unambiguously in their own words.
   - medium: Value can be inferred from a clear but indirect self-statement
             (e.g. "diagnosed post-partum" implies female, but not stated directly).
   - low:    Only a weak contextual signal exists; another coder might disagree.
   When in doubt, return a lower confidence level rather than a higher one.

4. EVIDENCE CITATION — cite the minimal sufficient quote:
   The evidence field must contain the shortest quote from the source text that
   a second coder could use to verify your extraction.  Do not paraphrase —
   use the author's exact words.  Maximum 120 characters.
""".strip()
