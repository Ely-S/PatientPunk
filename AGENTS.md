# PatientPunk — project agent guide

PatientPunk extracts real-world evidence (RWE) from patient-authored Reddit
(r/covidlonghaulers via Arctic Shift): emergent biomedical variables + per-drug
sentiment, fused per-patient into `patientpunk.db`. Two pipelines:
- `variable_extraction/` — extraction toolchain (`python variable_extraction/main.py <cmd>`).
- `src/` — drug-sentiment, the *dependent variable* (`python src/run_sentiment_pipeline.py`),
  loaded into the DB by `load_db.py`.

## Start every session here
**Read `CONTINUITY.md` (repo root, git-ignored) first if it's present.** It holds the current
project state: branch/HEAD, what the last session produced, the full pipeline + exact commands,
env setup (LLM = DeepSeek via OpenRouter), open next steps, and landmines (path doubling, `.env`
override, buffered output, the per-patient FK fix). **Update `CONTINUITY.md` at the end of your session.**

Data (`output*/`, `*.db`, `**/temp/`, `subreddit_posts.json`) is git-ignored — keep it in
`PatientPunk_data/` + `s3://patientpunk/`, never commit data.
