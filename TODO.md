# PatientPunk TODO

> Personal working list. Team suggestions welcome via GitHub Issues.

---

## Checklist

**Pipeline Unification**

The drug sentiment pipeline (`src/`) and the demographic extraction pipeline (`Scrapers/`) were built independently by different contributors and have never been properly joined. They share a schema but the demographic pipeline outputs CSV that never reaches SQLite, `open_db()` silently skips schema initialization, the two branches have diverged significantly, and there is no single command to run the full pipeline end-to-end. The goal is a unified system with shared infrastructure, schema-driven extraction modules, and one orchestrator that a new contributor can run in a single step. Ideally we also want to run sentiment analysis on abstracted things:  a research question might be something like "How does ones sentiment towards motherhood effect abortion recovery"

- [ ] `open_db()` does not apply `schema.sql`. Add `init_db()` using `executescript`. (`src/utilities/db.py`)
- [ ] Delete old `database_creation/` scripts on `main` (duplicates of `src/scripts/`). Update README to point to `src/run_pipeline.py`.
- [ ] Rewrite demographic pipeline to write directly to `user_profiles` and `conditions` in SQLite. CSV becomes an optional export. Evaluate `src/extract_demographics_conditions.py` for reuse or removal.
- [ ] Add `extraction_quality` table to `schema.sql` (see schema below).
- [ ] Write `run_all.py`: single entry point sequencing init, import, demographics, sentiment. Calls importable functions, not subprocesses.

**Analytics**

The analytics layer (branch:analytics-v2 , most code in the folder `app/analysis/stats.py`) was built on top of the fragmented pipeline and picked up some of its inconsistencies. The most pressing is a silent data bug where `weak` (a signal strength value) is treated as a sentiment value in every scoring query, skewing results without raising any errors. The test suite compounds this by running against a hand-rolled schema that diverges from production, meaning tests pass against something that doesn't exist. The research assistant skill that drives all notebook generation is also overloaded at 253 lines, which degrades output quality and makes it hard to maintain. All three need attention before the analytics output can be trusted. Generally I(shaun) need to clean up this pipeline, make sure that it plays well with other parts of the project,  remove unnecessary things, remove unnecessary pipelines (I was testing 3 different approaches against each other), and make it so we can merge with main.

- [ ] Remove `WHEN 'weak' THEN 0.25` from every CASE statement in `stats.py`. `weak` is a `signal_strength` value, not a sentiment value. Silent scoring bug. (`app/analysis/stats.py`)
- [ ] `test_stats.py` uses a hand-rolled `extraction_runs` schema missing `commit_hash` and `extraction_type`. Replace with `schema.sql` read from disk. (`tests/test_stats.py`)
- [ ] Slim `test_stats.py` from 1161 lines to ~200-300. One minimal fixture, one test per function, explicit edge cases. Format should go: known-input → specific test in numpy/pandas/pangolin ->expected-output for each stat function, edge case handling (n=0, all-same sentiment), and warning behavior
- [ ] Split research assistant skill into focused sub-agents: maybe `ra-explore`, `ra-analyze`, `ra-figures`, `ra-narrative`, `ra-qa`, plus a thin orchestrator skill. Each ~30-50 lines. (`.claude/skills/research-assistant.md`).  Right now there are over 250 lines with 120 rules in it and it is generating both python and SQL code:  it's too much context for one skill and it is applying things inconsistently.


**Cleanup**

A handful of smaller issues accumulated during the hackathon: database files committed to version control (By Shaun: oops), an empty package directory left over from an abandoned extraction experiment, a broken logging call that silently swallows errors, and known canonicalization quality problems that will produce noisy results on a full corpus run. None of these block the pipeline work but they should be resolved before the repo is shared more broadly or run on real data.

- [ ] `notebooks/patientpunk.db` and `notebooks/polina_onemonth.db` are committed to analytics-v2. Add `*.db` to `.gitignore`, purge from git history.
- [ ] `variable_extraction/` has package structure but no source files. Delete or spec it out.
- [ ] `logging.log_error(...)` in `extract_demographics_conditions.py` does not exist. Change to `log.error(...)`. (`src/extract_demographics_conditions.py`)
- [ ] Canonicalization has known quality issues (cross-batch synonym misses, non-drug entities leaking in). Needs regex-first approach before full corpus run. (`src/pipeline/canonicalize.py`)

**Query Interface** (blocked on pipeline unification)

The query interface is what turns the database into something a patient or researcher can actually use. The design is simple by intent: pure SQL against a static pre-built database, no LLM calls at query time. A CLI is the right starting point, with an optional web UI as a second step once the data layer is stable. Both are straightforward to build once the pipeline writes reliable data to the right tables.

- [ ] `query.py` CLI with `--drug`, `--condition`, `--sex`, `--age` filters
- [ ] Optional minimal web UI (FastAPI or Flask)

**Inductive Variable Finding** (low priority, blocked on pipeline unification)

The prototype in `Scrapers/demographic_extraction/discover_fields.py` scans a corpus without a predefined schema and proposes candidate variables. In the new architecture this becomes a schema authoring tool: run it on an unfamiliar community, get a draft schema JSON, a researcher curates it, then standard extraction runs. This is the piece that makes PatientPunk genuinely self-bootstrapping for new research questions. It is scientifically an incredibly interesting part of the system, but it has no stable floor to stand on until the unified pipeline is working. Do not touch this until the unification work is done. (SHAUN!  LOOKING AT YOU!  DON'T PLAY WITH THE TOY UNTIL YOU HAVE FINISHED CLEANING OUR ROOM)

- [ ] Decouple `discover_fields.py` from Scrapers so it runs against any SQLite DB
- [ ] Change output to candidate schema JSON format for human review
- [ ] Tag discovered fields with `"provenance": "discovered"` for prioritized validation

---

## Reference: `extraction_quality` Table

```sql
CREATE TABLE extraction_quality (
    quality_id    INTEGER PRIMARY KEY,
    run_id        INTEGER NOT NULL REFERENCES extraction_runs(run_id),
    record_id     TEXT NOT NULL,
    field_name    TEXT,
    validated_by  TEXT NOT NULL,   -- 'llm_strong', 'human', etc.
    confidence    REAL,            -- 0.0-1.0
    flag          TEXT,            -- 'ok', 'uncertain', 'wrong'
    notes         TEXT,
    validated_at  INTEGER NOT NULL
);
```

---

## Open Questions

- Should canonical drug names map to RxNorm CUIs for long-term interoperability?
- Store sentiment as categorical strings or convert to floats at write time?
- How often to re-run the pipeline on a fresh scrape?
