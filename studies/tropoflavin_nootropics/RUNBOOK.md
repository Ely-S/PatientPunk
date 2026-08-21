# Running the 7,8-DHF study

Exact steps to rebuild this study from raw dumps. `NOTES.md` in this directory holds
the findings and the reasoning behind each choice; this file is just the procedure.

Everything here assumes the branch this file arrived on — it sits on top of the
pipeline stack (#121 → #119 → #122 → #118 → #120). On `main` alone the classify
stage dies on its first batch.

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
  --subreddit Nootropics --workers 12 --max-upstream-chars 1500
```

`--drug-file` is targeted mode: extract becomes a regex over the alias list, so no
tokens are spent finding mentions. Expect 4,603 pairs → prefilter keeps 988 → **661
records from 301 users**.

`--max-upstream-chars 1500` bounds the classify input. Without it the run dies part-way
on large corpora.

## 3. Pipeline B — variable extraction

```bash
uv run python variable_extraction/main.py \
  --corpus studies/tropoflavin_nootropics/source_B \
  --schema variable_extraction/schemas/nootropics_schema.json \
  --out studies/tropoflavin_nootropics/source_B
```

There is **no `--drug` flag in pipeline B** — its unit is the patient, not the drug,
which is why targeting means the pre-filtered corpus from step 1.

## 4. Analyses

Each reads the database or `source_B/records.csv` and prints to stdout.

```bash
python studies/tropoflavin_nootropics/analyze_purpose.py      # what people take it for
python studies/tropoflavin_nootropics/analyze_B.py            # the two compounds, separated
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

## 5. What you should get

| | |
|---|---|
| positive | 214/301 = **71.1%** (95% Wilson 65.7–75.9) |
| negative | 77 = 25.6% |

Read that with NOTES.md's caveats attached — positives are over-called 10–20% on this
pipeline, the alias blends 7,8-DHF with its 4'-DMA derivative (quote pipeline B for
per-compound claims), and r/Nootropics is a healthy-user population.

## 6. Reproducing the original numbers exactly

The figures above were produced with **reasoning enabled** on `deepseek-v4-flash`. This
stack suppresses reasoning by default (#121), which makes the model a different
classifier — cheaper and more reliable, but not the same one.

Reasoning-on runs additionally need `REASONING_HEADROOM` and `MAX_TOKENS_PER_ITEM`,
which are **not in this stack**. Without them, `LLM_REASONING=1` truncates on the first
prefilter batch.

Two further hazards if you go that route:

- The on-disk LLM cache keys on model, prompt, temperature and `max_tokens` — **not** on
  the reasoning flag. A reasoning-off run will silently return reasoning-on cached
  answers, mixing regimes with nothing in the output to show it. Point `LLM_CACHE_DIR`
  at a fresh directory, or set `LLM_CACHE=0`.
- `extraction_runs.config` does not record the flag either, so a database cannot say
  which regime produced it.

Treat any comparison across the two regimes as invalid until both are fixed.
