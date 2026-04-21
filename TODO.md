# PatientPunk TODO

> Personal working list for Shaun. Feel free to just take things or offer suggestions.

---

## Checklist

**Data-transformation Pipeline Unification**

The drug sentiment pipeline (`src/`) and the demographic extraction pipeline (`Scrapers/`) were built independently by different contributors and have never been properly joined. They share a schema but the demographic pipeline outputs CSV that never reaches SQLite, `open_db()` silently skips schema initialization, the two branches have diverged significantly, and there is no single command to run the full pipeline end-to-end. The goal is a unified system with shared infrastructure, schema-driven extraction modules, and one orchestrator that a new contributor can run in a single step. Ideally we also want to run sentiment analysis on abstracted things:  a research question might be something like "How does ones sentiment towards motherhood effect abortion recovery" (NOTE: Polina might be better at doing this then I am, but I'm willing to take a shot.  Would love to at a minimum work on this with you nearby so I can bug you with questions)

- [ ] Right now we are organizing the pipeline 1 record:1 drug.  I want to explore what it would look like to have it 1 record:1 textblock, with drugs stored as a list or something similar. Right now the way we are storing the data nearly forces drugs as an independent variable and sentiment as a dependent variable, and I wonder if changing that structure might increase the range of questions we can answer with this and remove some assumptions of causality that are implied by this organization. Storing things in this way though (post:row) would be more computationally expensive than drug-sentiment-pair:row for a lot of reasons I think though.  Something to explore.
- [ ] `open_db()` does not apply `schema.sql`. Add `init_db()` using `executescript`. (`src/utilities/db.py`)
- [x] Delete old `database_creation/` scripts on `main` (duplicates of `src/scripts/`). Update README to point to `src/run_pipeline.py`. — **Done in PR #19 (merged to main).**
- [ ] Rewrite demographic pipeline to write directly to `user_profiles` and `conditions` in SQLite. CSV becomes an optional export, drawn from .db file. Evaluate `src/extract_demographics_conditions.py` for reuse or removal.
- [ ] Write `run_all.py`: single entry point sequencing init, import, demographics, sentiment. Calls importable functions, not subprocesses.
- [ ] I want to explore reapplying disease/subreddit specific schema to the variable extraction workflow?  Can be hand-written for now and will be eventually plugged into the inductive variable engine mentioned below.

**Analytics**

The analytics layer (branch:analytics-v2 , most code in the folder `app/analysis`) was built on top of the fragmented pipeline and picked up some of its inconsistencies. The most pressing is a silent data bug where `weak` (a signal strength value) is treated as a sentiment value in every scoring query, skewing results without raising any errors. The test suite compounds this by running against a hand-rolled schema that diverges from production, meaning tests pass against something that doesn't exist. The research assistant skill that drives all notebook generation is also overloaded at 253 lines, which degrades output quality and makes it hard to maintain. All three need attention before the analytics output can be trusted. Generally I(shaun) need to clean up this pipeline, make sure that it plays well with other parts of the project,  remove unnecessary things, remove unnecessary pipelines (I was testing 3 different approaches against each other), and make it so we can merge with main.

- [x] It looks like the sentiment/single strength classification handling is a bit inconsistent at some times in our code. Claude suggests the following, I want to look at things deeper obviously before implementing:  Remove `WHEN 'weak' THEN 0.25` from every CASE statement in `stats.py`. `weak` is a `signal_strength` value, not a sentiment value. Silent scoring bug. (`app/analysis/stats.py`) — **Investigated: the `WHEN 'weak'` bug exists in 8 locations in stats.py on analysis-v2. Added CHECK constraints to schema.sql and 19 validation tests in `tests/test_sentiment_validation.py`. CASE statement fix still pending.**
- [ ] Slim `test_stats.py`from 1161 lines to ~200-300. Possibly this should be a table(or other data structure?) of some kind instead of a python document.  Table entries should consist of the following: One minimal fixture, one test per function, explicit edge cases. Format should go: known-input → specific test in numpy/pandas/pangolin ->expected-output for each stat function-> edge case handling/warning (n=0, all-same sentiment)-> and warning behavior/limitation noting.
- [ ] Split research assistant skill into focused sub-agents: maybe `ra-explore`, `ra-analyze`, `ra-figures`, `ra-narrative`, `ra-qa`, plus a thin orchestrator skill. Each ~30-50 lines. (`.claude/skills/research-assistant.md`).  Right now there are over 250 lines with 120 rules in it and it is generating both python and SQL code:  it's way too much context for one skill and it is applying things inconsistently.


**Cleanup**

A handful of smaller issues accumulated during the hackathon: database files committed to version control (By Shaun: oops), an empty package directory left over from an abandoned extraction experiment, a broken logging call that silently swallows errors, and known canonicalization quality problems that will produce noisy results on a full corpus run. None of these block the pipeline work but they should be resolved before the repo is shared more broadly or run on real data.

- [ ] Clean up examples, remove intermediate json and .db etc files from GitHub.
- [x] `notebooks/patientpunk.db` and `notebooks/polina_onemonth.db` are committed to analytics-v2. Add `*.db` to `.gitignore`, purge from git history. — **Added `*.db` to `.gitignore` on `shaun/fix-logging-and-gitignore`. History purge still pending.**
- [ ] `variable_extraction/` has package structure but no source files. I'm assuming this got merged into something else in one of Paulina's passes, will investigate.
- [x] While looking through the code and I was making this list, Claude pointed out: `logging.log_error(...)` in `extract_demographics_conditions.py` does not exist. Change to `log.error(...)`. (`src/extract_demographics_conditions.py`) — **Fixed on `shaun/fix-logging-and-gitignore`.**
- [ ] Canonicalization code batch groups drugs in batches of 50:  will this overrun in large groups?  Want to test data quality on this further with edge cases/large data. 

**Query Interface** (blocked on pipeline unification)

The query interface is what turns the database into something a patient or researcher can actually use. The design is simple by intent: pure SQL against a static pre-built database, no LLM calls at query time. A CLI is the right starting point, with an optional web UI as a second step once the data layer is stable. Both are straightforward to build once the pipeline writes reliable data to the right tables.

- [ ] `query.py` CLI with `--drug`, `--condition`, `--sex`, `--age` filters
- [ ] Optional minimal web UI (FastAPI or Flask)

**Security:** 
- [ ]Reddit posts are untrusted LLM input — guard against prompt injection and sentiment bias via Pydantic enum gates, cross-model diffing, and input sanitization. See previous session notes for full threat model.

**Inductive Variable Finding** (low priority, blocked on pipeline unification)

The prototype in `Scrapers/demographic_extraction/discover_fields.py` scans a corpus without a predefined schema and proposes candidate variables. In the new architecture this becomes a schema authoring tool: run it on an unfamiliar community, get a draft schema JSON, a researcher curates it, then standard extraction runs. This is the piece that makes PatientPunk genuinely self-bootstrapping for new research questions. It is scientifically an incredibly interesting addition to our system, but it has no stable floor to stand on until the unified pipeline is working. Do not touch this until the unification work is done. (SHAUN!  LOOKING AT YOU!  DON'T PLAY WITH THE TOY UNTIL YOU HAVE FINISHED CLEANING OUR ROOM)

- [ ] Determine TODO's for this task.

---
