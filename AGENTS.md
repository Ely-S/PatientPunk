# When creating Pull Requests
1. Use detailed commit messages
2. Every PR Needs a Description that has the following sections
- ## Why - Explaining the problem being solved, and why it is important
- ## Approach taken - Explaining the solution fully and the design
- ## User-facing changes  - Explain how this affects users
- ## Detailed test plan - A Test plan that an agent can follow, including end-to-end verification

The test plan must include exact commands to run and detailed steps to verify the output of the run

# Corpus data

**Never commit corpus data.** Scraped posts and comments, per-user files, extracted
records, databases and any workbook carrying quote tabs stay out of git. They belong
in `PatientPunk_data/` locally and `s3://patientpunk/raw_data/` remotely.

`.gitignore` is not the safety net. It names a handful of specific paths and covers
one study, so `git add studies/<name>` sweeps the corpus in beside the scripts. **Add
files by name.**

| commit | never commit |
|---|---|
| `*.py`, `*.sh`, alias lists, `NOTES.md` | `source*/`, `outputs*/`, `*.db`, `*.db-shm`, `*.db-wal`, `*.jsonl`, workbooks with quotes |

**Why this is written down:** `chore/purge-committed-data` exists because corpus files
reached the repo once already. A later agent proposed committing a study directory
holding 752 per-author text files, having assumed `.gitignore` covered them; it covered
four files out of 788.

**Verify a download by its last timestamp, not its size.** An r/Nootropics comments
dump looked healthy — no month gaps, last line parsed clean, plausible size — and was
truncated at 2019-05-02, missing 7¼ years.

**A study is not reproducible from its notes alone.** If a run depended on uncommitted
changes, the notes describe a procedure the committed code cannot execute. Commit the
code the numbers came from, or say in the notes that they are not reproducible yet.

# Corpus analysis

**Match body text, never the raw JSON line.** Reddit base36 ids contain strings like
`i78dhf6` and score as drug mentions.

**`\b` does not fire after a digit.** `\bdhf\b` misses `7,8DHF`. FTS5 misses it too —
the tokenizer never emits a bare `dhf`. Use FTS to narrow, regex to confirm.

**An alias matches inside longer names.** `7,8-dhf` matches within `4'-DMA-7,8-DHF`,
blending a parent compound and its derivative into one rate — worth ~9 points where it
was measured.

**Never derive a category from the text the classifier read.** Tagging an indication by
keyword and then reporting sentiment or side effects per indication is circular: the
words that assign the category are the words being measured. Tried twice on one corpus,
it produced every category above baseline once, and a self-inflating diagonal the other
time — 13% of a fatigue cohort "reporting fatigue" collapsed to 3% when outcome
sentences were excluded from the tagging. Categories must come from an extracted field.

**Positive sentiment is over-called by 10–20% on this pipeline; negatives are reliable.**
Prefer a negative rate, or a category-vs-category comparison, over a positive rate
against baseline.

**Stacked treatments inherit the collective outcome**, which inflates `helped`. Run the
monotherapy sensitivity check before quoting any rate.

**One vote per user** — most recent record, ties broken by signal strength.

**Match the indication before comparing communities.** ME/CFS and Long COVID discuss the
same drug for different symptoms, so an unmatched comparison measures the symptom mix,
not the drug. Negative controls must match indication too.
