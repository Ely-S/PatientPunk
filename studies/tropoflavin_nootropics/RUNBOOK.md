# Running the 7,8-DHF study

Exact steps to rebuild this study from raw dumps. `NOTES.md` in this directory holds
the findings and the reasoning behind each choice; this file is just the procedure.

Everything here assumes the branch this file arrived on. The complete stack is
#121 -> #119 -> #122 -> #118 -> #120 -> #142 -> #141 -> #140. The final three
changes add treatment-linked doses, treatment-linked administration routes, and
this study. On `main` alone the classify stage dies on its first batch.

## 0. Prerequisites

`.env` at the repo root with `LLM_PROVIDER` and a key. Never open it; to check what is
configured see the table in `AGENTS.md`.

Raw dumps go in `PatientPunk_data/`, a **sibling of the repo** — the builders resolve
`ROOT.parent / "PatientPunk_data"` from their own location, so no path editing is needed
as long as that layout holds.

```bash
aws s3 cp s3://patientpunk/raw_data/arctic_shift_ndjson/r_nootropics_comments.jsonl ../PatientPunk_data/
aws s3 cp s3://patientpunk/raw_data/arctic_shift_ndjson/r_nootropics_posts.jsonl ../../
```

Comments 2.25 GB (1,827,221 lines, 2009-09-25 → 2026-08-18); posts 416 MB (184,321
lines). The posts dump still lives two directories above the repo rather than beside the
comments — `DOCS` in the builders. Moving it into `PatientPunk_data/` and repointing
`DOCS` is a small cleanup nobody has done.

**Check the last timestamp, not the file size.** An earlier comments download looked
healthy — no month gaps, last line parsed — and was truncated at 2019-05-02, missing
7¼ years.

```bash
tail -1 ../PatientPunk_data/r_nootropics_comments.jsonl | python -c "import sys,json,datetime as d; print(d.datetime.utcfromtimestamp(int(json.loads(sys.stdin.read())['created_utc'])))"
```

If a subreddit needs re-pulling from Arctic Shift monthly dumps rather than S3, use
`Scrapers/filter_monthly_dumps.py`.

## 1. Build the two corpora

The pipelines take different inputs, so both are built.

```bash
python studies/tropoflavin_nootropics/build_corpus.py     # -> source/subreddit_posts.json
python studies/tropoflavin_nootropics/build_corpus_B.py   # -> source_B/users/*.json
```

Expect `1,047 posts + 44,620 comments = 45,667 items`, 99.9% parent-chain survival,
13,568 distinct authors; then `752` user files.

`build_corpus.py` pulls whole threads containing a mention so reply context survives.
`build_corpus_B.py` is separate because pipeline B reads title+body only and would
silently drop every comment mention — see NOTES.md §4.

**Neither output is committable.** `source/` and `source_B/` are patient text.

## 2. Pipeline A — drug sentiment

```bash
uv run python src/run_sentiment_pipeline.py \
  --db studies/tropoflavin_nootropics/noots.db \
  --output-dir studies/tropoflavin_nootropics/outputs_A \
  --drug-file studies/tropoflavin_nootropics/aliases_78dhf.txt \
  --workers 12 --max-upstream-chars 1500
```

`--drug-file` is targeted mode: extract becomes a regex over the alias list, so no
tokens are spent finding mentions. Expect 4,603 pairs → prefilter keeps 988 → **661
records from 301 users**.

`--max-upstream-chars 1500` bounds the classify input. Without it the run dies part-way
on large corpora.

## 3. Pipeline B — variable extraction

Create a versioned run directory so the historical extraction is not overwritten.
The group guard is enabled because this study reports per-compound outcomes and
should not assign a statement about a group to every treatment in that group.

```powershell
$runDir = "../PatientPunk_data/studies/tropoflavin_nootropics/runs/2026-08-27-linked-dose-route"
New-Item -ItemType Directory -Force "$runDir/corpus/users", "$runDir/cache" | Out-Null
Copy-Item "studies/tropoflavin_nootropics/source_B/users/*.json" "$runDir/corpus/users/"
$env:LLM_CACHE = "1"
$env:LLM_CACHE_DIR = "$runDir/cache"
$env:LLM_MAX_TOKENS = "16384"
$env:PP_GROUP_GUARD = "1"
uv run python variable_extraction/main.py run `
  --schema schemas/nootropics_schema.json `
  --input-dir "$runDir/corpus" `
  --temp-dir "$runDir/temp" `
  --workers 12
```

There is **no `--drug` flag in pipeline B** — its unit is the patient, not the drug,
which is why targeting means the pre-filtered corpus from step 1.

Require the phase summary to report 752 records and zero failures. The default
8,192-token ceiling failed on two unusually dense histories in the 2026-08-27
run; 16,384 completed both. Do not analyze a partial CSV.

The extraction CSV contains linked raw values. Run normalization to add the
decomposed analysis columns:

```powershell
uv run python variable_extraction/main.py normalize `
  --records "$runDir/corpus/records.csv" `
  --out "$runDir/corpus/records_normalized.csv"
```

Expect 752 rows in `$runDir/corpus/records_normalized.csv`. The derived columns
`dosage_treatment`, `dosage_value`, `administration_route_treatment`, and
`administration_route_value` must all be present. Use a fresh cache whenever a
prompt rule or reasoning mode changes.

## 4. Analyses

Each resolves its inputs relative to this study directory, so these commands work
from the repository root. To analyze a versioned pipeline B run, set
`TROPOFLAVIN_RECORDS` first.

```powershell
$env:TROPOFLAVIN_RECORDS = "$runDir/corpus/records_normalized.csv"
python studies/tropoflavin_nootropics/analyze_purpose.py      # what people take it for
python studies/tropoflavin_nootropics/analyze_B.py            # outcomes, linked doses, and routes
python studies/tropoflavin_nootropics/analyze_followups.py    # no_effect gap, use-case splits
python studies/tropoflavin_nootropics/analyze_se.py           # side effects
python studies/tropoflavin_nootropics/analyze_dose2.py        # dose-stratified (strict binding)
python studies/tropoflavin_nootropics/sample_quotes.py        # first-person quotes, seed=7
python studies/tropoflavin_nootropics/make_sheet.py           # results_workbook.xlsx
```

The `audit_*.py` scripts exist to check the analyses, and each one found a real problem:

- `audit_dose.py` — shows why a proximity window mis-attributes doses in stack posts
- `audit_diag.py` — shows the side-effect-by-indication diagonal is a tagging artifact
- `audit_fatigue.py` — prints the six records behind the fatigue cell so they can be read

Run them before quoting anything from the dose or side-effect-by-indication tables.

## 5. Build the combined Pipeline A and B database

Copy Pipeline A through SQLite's backup API, then add the normalized Pipeline B
records and analysis tables. The source `noots.db` is opened read-only and is not
modified.

```powershell
$outputDir = "$runDir/outputs/pr140-linked-dose-route"
$combinedDb = "$outputDir/nootropics_pipeline_a_b.db"
$studyReport = "$outputDir/study_design_analysis.md"

uv run python -m studies.tropoflavin_nootropics.build_combined_db `
  --source-db "studies/tropoflavin_nootropics/noots.db" `
  --pipeline-b-records "$runDir/corpus/records_normalized.csv" `
  --output "$combinedDb" `
  --expected-records 752 `
  --run-name "2026-08-27-linked-dose-route"

uv run python -m studies.tropoflavin_nootropics.analyze_study_design `
  --database "$combinedDb" `
  --output "$studyReport"
```

The combined database retains every Pipeline A table and adds:

- `pipeline_b_records`: the exact 752-row, 41-column normalized export
- `pipeline_b_dosages`: one linked dose per row, with raw value, normalized mass,
  and stable milligram band
- `pipeline_b_administration_routes`: one linked route per row, with exact route
  and pharmacologic route family
- `pipeline_b_treatment_outcomes`: treatment-specific outcome, symptom, and
  desired-result domain
- `pipeline_b_compound_exposures`: one row per author and target compound with
  dose, route, efficacy, and explicit dose-route ambiguity in the same table
- `pipeline_a_side_effects`: treatment-linked canonical side-effect terms and
  safety-domain buckets
- `combined_pipeline_manifest`: completion status and source provenance

The completed run should contain 661 Pipeline A reports, 752 Pipeline B records,
643 linked dosage pairs, 231 linked route pairs, 1,482 outcome entries, 202 target
author-compound exposure rows, and 216 side-effect mentions. Validate the artifact:

```powershell
@'
import sqlite3
from pathlib import Path

path = Path(r"REPLACE_WITH_COMBINED_DB_PATH")
connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
print(connection.execute("PRAGMA integrity_check").fetchone()[0])
print(connection.execute("PRAGMA foreign_key_check").fetchall())
print(connection.execute("SELECT pipeline, status, record_count FROM combined_pipeline_manifest").fetchall())
connection.close()
'@ | uv run python -
```

Require `ok`, an empty foreign-key result, and complete manifest rows for both
pipelines before analysis.

## 6. Comparator cohort

The cohort is versioned in `comparator_cohort.json`. It keeps the parent compound and
4'-DMA derivative separate, then applies one pipeline configuration to Semax,
Cerebrolysin, Selank, NSI-189, Dihexa, lion's mane, 9-MBC, and the BPC-157 control.

Build the private union of every thread containing a configured compound. Usernames
are hashed before the corpus is written. Source text, the generated corpus, SQLite
database, cache, and manifests remain outside Git.

```powershell
$comparatorRun = "../PatientPunk_data/studies/tropoflavin_nootropics/runs/2026-08-31-comparator-cohort"
$comparatorCorpus = "$comparatorRun/corpus/subreddit_posts.json"
$comparatorDb = "$comparatorRun/sentiment/comparators.db"
$comparatorOutput = "$comparatorRun/sentiment/outputs"
$comparatorReport = "studies/tropoflavin_nootropics/comparator_analysis.md"

uv run python -m studies.tropoflavin_nootropics.build_comparator_corpus `
  --comments "../PatientPunk_data/r_nootropics_comments.jsonl" `
  --posts "../../r_nootropics_posts.jsonl" `
  --output "$comparatorCorpus"

$env:LLM_CACHE = "1"
$env:LLM_CACHE_DIR = "$comparatorRun/cache"
$env:LLM_REASONING = "0"
uv run python -m studies.tropoflavin_nootropics.run_comparator_pipeline `
  --corpus "$comparatorCorpus" `
  --database "$comparatorDb" `
  --output-dir "$comparatorOutput" `
  --workers 8 `
  --max-upstream-chars 1500

uv run python -m studies.tropoflavin_nootropics.analyze_comparator_cohort `
  --sentiment-database "$comparatorDb" `
  --study-database "$combinedDb" `
  --output "$comparatorReport"
```

The corpus is shared, but each target gets its own alias and enclosing-compound
exclusion rules. This matters for `7,8-DHF`, whose text span must not be counted when
it occurs only inside `4'-DMA-7,8-DHF`. The analysis uses one most-recent report per
author and compound, Wilson intervals, Fisher tests with Benjamini-Hochberg correction,
and a matched-author exact sensitivity analysis. Side effects are joined through the
classified treatment ID. Dose, route, and symptom outcomes come from the linked
Pipeline B tables and do not invent administration-level pairings.

The committed report contains aggregate tables and SHA-256 hashes only. Before using
it, require a nonzero report count for every cohort member in
`comparator_pipeline_manifest.json`, `PRAGMA integrity_check = ok`, and an empty
foreign-key check.

The completed 2026-08-31 run produced the following private-database counts. These
counts are safe aggregates; the corpus, cache, database, and manifest are not committed.

| Compound | Reports | Authors |
|---|---:|---:|
| 7,8-DHF | 653 | 279 |
| 4'-DMA-7,8-DHF | 159 | 88 |
| Semax | 5,904 | 2,133 |
| Cerebrolysin | 1,472 | 572 |
| Selank | 2,170 | 992 |
| NSI-189 | 2,673 | 879 |
| Dihexa | 635 | 272 |
| Lion's mane | 10,459 | 5,215 |
| 9-MBC | 348 | 177 |
| BPC-157 | 1,270 | 515 |

Use eight workers for the OpenRouter run unless the configured provider has been load
tested at higher concurrency. The pipeline writes report rows incrementally and caches
prefilter and classification responses, so a transport interruption can be resumed with
the same command.

## 7. What you should get

| | |
|---|---|
| positive | 214/301 = **71.1%** (95% Wilson 65.7–75.9) |
| negative | 77 = 25.6% |

Read that with NOTES.md's caveats attached — positives are over-called 10–20% on this
pipeline, the alias blends 7,8-DHF with its 4'-DMA derivative (quote pipeline B for
per-compound claims), and r/Nootropics is a healthy-user population.

## 8. Reproducing the original numbers exactly

The historical figures above were produced with **reasoning enabled** on
`deepseek-v4-flash`. This stack suppresses reasoning by default (#121), which makes
the model a different classifier: cheaper and more reliable, but not the same one.

The stack now includes bounded output-budget growth for reasoning responses. For a
new baseline, leave reasoning off. Set `LLM_REASONING=1` only when reproducing the
historical model regime, and still use a fresh cache.

The cache key now includes the effective reasoning mode, and
`extraction_runs.config` records it. A reasoning-off run therefore cannot reuse a
reasoning-on response. Still use a fresh cache when changing prompts, model behavior,
or study definitions so the artifact boundary remains obvious.
