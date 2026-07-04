# Quote Ethics And Publication Policy

Date: 2026-07-04

This note defines how A4 should handle Reddit patient quotes, public summaries,
and methods transparency.

## Sources Checked

External sources:

- COREQ on EQUATOR: https://www.equator-network.org/reporting-guidelines/coreq/
- PRISMA-ScR project summary: https://knowledgetranslation.net/project/preferred-reporting-items-for-systematic-reviews-and-meta-analyses-extension-for-scoping-reviews/
- GRADE-CERQual home: https://www.cerqual.org/
- GRADE-CERQual introduction paper: https://link.springer.com/article/10.1186/s13012-017-0688-3
- AoIR ethics page: https://aoir.org/ethics/

Local sources:

- `README_AGENTS.md`
- `src/agents/_common/packet.py`
- `src/agents/_common/validate.py`
- `src/agents/TheTrialAgent/synthesize.py`
- `dev/analysis/a4_evidence_reporting/notes/reporting_guardrails.md`
- `dataset/covidlonghaulers_comments/derived/a3_result_analysis/runs/a3_openrouter_eval_20260704T190833Z_prompt_dev_3/quote_candidates.csv`

## How The External Sources Apply

COREQ is designed for interviews and focus groups, so it is not directly a
checklist for this Reddit-comment pipeline. Its useful lesson for A4 is
transparent reporting of context, analysis choices, and interpretation limits.

PRISMA-ScR is for scoping reviews, not model-extracted social-media corpora. Its
useful lesson for A4 is explicit eligibility criteria, source selection, search
scope, and item-level transparency.

GRADE-CERQual is closer conceptually because it separates confidence in a
qualitative synthesis finding from the finding itself. A4 should borrow the
discipline of finding-level confidence and explanation, but should not claim to
implement CERQual unless a formal qualitative evidence synthesis process is
added.

AoIR is directly relevant because this is internet research over public but
health-sensitive user text. A4 should treat public availability as insufficient
by itself for public quotation. Privacy, context collapse, searchability, and
re-identification risk still matter.

## Core Policy

A4 may create quote-bearing private review artifacts by default.

A4 must not create public quote-bearing reports until quote review and redaction
are implemented.

The current A3 quote candidates have:

```text
audit_status = unaudited
contains_sensitive_terms = unknown
redaction_status = not_reviewed
```

That means they are internal evidence-review inputs only.

## Output Modes

`private_review`:

- may include `comment_id`, `source_line`, `claim_id`, and evidence quotes
- may include quote candidates under ignored derived paths
- should not include usernames
- should not include direct Reddit permalinks unless there is an explicit
  reviewer-only need
- should mark all quotes with review status

`public_summary`:

- should not include raw comment IDs or source lines in the visible report
- should not include direct Reddit permalinks by default
- should not include unreviewed quotes
- should include denominator, methods, and limitations text
- should prefer aggregate summaries over quotations when quote risk is unclear

## Quote Review Statuses

A4 should use explicit review statuses:

```text
not_reviewed
needs_redaction
redacted_private_only
reviewed_public_ok
exclude_sensitive
exclude_not_representative
exclude_context_dependent
exclude_unsupported
```

Suggested quote fields:

```text
quote_id
run_id
claim_id
comment_id
source_line
quote_text_original
quote_text_redacted
claim_type
normalized_label_canonical
assertion
experiencer
audit_status
redaction_status
sensitivity_flags_json
public_allowed
reviewer
reviewed_at_utc
review_notes
source_a3_analysis_id
source_a2_run_id
```

`public_allowed` should be false unless:

- `audit_status` confirms the claim is supported
- `redaction_status=reviewed_public_ok`
- quote is representative of the finding
- quote is not uniquely identifying
- quote does not contain avoidable rare details
- finding itself is allowed in the target report mode

## Sensitivity Flags

Quote review should flag:

```text
medical_emergency
mental_health_crisis
self_harm
minors_or_children
pregnancy
location_or_workplace
rare_event_or_diagnosis
highly_specific_timeline
names_or_usernames
contact_information
third_party_private_information
legal_or_employment_issue
stigmatized_condition
sexual_or_reproductive_health
```

Flags do not automatically mean exclusion, but they should require human review
before public use.

## Quote Selection Rules

Quotes should be selected to represent a finding, not to persuade.

Rank candidates by:

1. audited supported claim
2. accepted normalization label
3. clear target-author attribution
4. high attribution confidence
5. readable length
6. low sensitivity after review
7. coverage of distinct findings, not repeated variants of the same dramatic
   language

Avoid:

- longest or most dramatic quote as the default
- quotes whose meaning depends heavily on missing parent/root-post context
- quotes that imply causality beyond the coded assertion
- repeated quotes from the same comment/finding when one is enough
- raw text that can be searched verbatim if public de-identification matters

## Redaction Rules

For public summaries, redaction should minimize identifiability while preserving
the analytic point.

Allowed redactions:

```text
[age]
[location]
[workplace]
[relative]
[date]
[condition detail]
...
```

Do not silently rewrite a quote into a paraphrase while presenting it as a quote.
If wording is materially changed, label it as a paraphrase and keep the original
only in private review artifacts.

## Methods Text Required For Public Reports

Every public A4 report should include:

- source community and date range
- comment-only or missing-root-post limitations
- extraction model and prompt/schema versions
- A2/A3 run IDs and analysis hashes
- denominator definitions
- audit sample sizes and error rates, if available
- normalization review status
- quote selection and redaction policy
- no clinical verification statement
- no patient-level denominator unless author/patient deduplication exists
- non-medical-advice statement

## Report Language

Preferred:

```text
In this extracted comment sample...
Among extracted claims...
Comment authors reported...
This is exploratory because...
```

Avoid:

```text
Patients have...
Prevalence was...
This treatment works...
This is safe...
Patients should...
```

## Public Quote Rule

For now, A4 should enforce:

```text
public_summary + quote.redaction_status != reviewed_public_ok -> fail validation
```

This can be relaxed only after quote review templates and tests exist.

## Research Takeaway

Quotes are evidence, not decoration. A4 should preserve them for review and
traceability, but public reports need a separate redaction/review gate before
any patient text leaves the private derived dataset.
