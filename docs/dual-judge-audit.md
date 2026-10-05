# Dual-judge audit of pipeline decisions

This optional, read-only step audits the latest persisted sentiment, dose, and effect
decisions after those pipelines complete. It uses two fresh CLI sessions per decision:
Claude Opus 5.5 and GPT-6 Astra, with GPT-6.1 Sol selectable. The first verdicts are
independent. When they disagree, each sees the prior round's two verdicts and rechecks
the original report. Discussion stops at agreement or 10 rounds. Agreement on an
unsupported decision requires the same issue code and exact evidence quote. The audit
never changes the pipeline database. It writes all verdicts, exchanges, and provenance
to a separate SQLite database outside the checkout.

## Coverage

One task is created for each latest stored treatment report, dose row, and effect row.
A completed dose or effect run with no rows creates a `no_dose` or `no_effect` task for
that report. A response is `supported`, `flagged`, or `unresolved`. Invalid evidence,
unclear cases, and disagreement after 10 rounds remain unresolved. A CLI failure stops
the run; completed decisions are retained and skipped on restart. This is model
agreement, not ground truth. Calibrate both judges against a human-reviewed sample
before treating aggregate audit rates as validation metrics.

The existing pipeline does **not** persist all upstream negative decisions, such as
prefilter rejections and model candidates dropped before storage. This audit cannot
verify those invisible decisions. It also audits the latest version of each stored
report, rather than every historical run. Future coverage of upstream decisions needs
their provenance to be recorded by the producing pipeline.

## Subscription-only setup

Install the project and ensure `claude` and `codex` are on `PATH`. Sign both CLIs in
with their subscription accounts. Claude must show `authMethod: claude.ai` in
`claude auth status`; Codex must report ChatGPT login in `codex login status`.
`claude auth status` may still show a cached login after its OAuth session expires, so
a first live call is the definitive check. If that happens, use `claude auth login`.
No `.env` file is read by the audit. Pay-as-you-go API-key and alternate-provider
environment variables are removed from each judge process.
The Claude judge uses `--safe-mode` to disable customizations while retaining OAuth
authentication. Do not replace it with `--bare`: bare mode does not read OAuth or
keychain credentials and cannot use this subscription-only setup.

With `PATIENTPUNK_DATA` set to the external data directory, an unattended command is:

```powershell
python src/run_pipeline_audit.py --db "$env:PATIENTPUNK_DATA\runs\pipeline.sqlite" --drug "7,8-DHF" --max-rounds 10
```

Omit `--drug` to cover all treatments, add `--kind dose` to audit only doses, or use
`--limit 10` for a small pilot or resumable batch. `--codex-model gpt-6.1-sol` switches the second judge
explicitly. `--output-db` sets the separate audit database; otherwise the default is
`PATIENTPUNK_DATA/audits/<source-stem>-dual-judge.sqlite`. Rerun the same command to
resume. Do not commit or publicly upload either source or audit database: both contain
patient-authored text.

## Verification

```powershell
python -m pytest tests/test_pipeline_audit.py -q
python src/run_pipeline_audit.py --preflight-only
python src/run_pipeline_audit.py --db "$env:PATIENTPUNK_DATA\runs\pipeline.sqlite" --drug "7,8-DHF" --limit 1
```

The last command should create one result outside the repository. Query
`audit_results.status` and `result_json` in that database and confirm the source
database row counts are unchanged. If Claude says its session expired, reauthenticate
before retrying; the first failed decision is not recorded as a scientific verdict.
