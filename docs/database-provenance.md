# Database provenance and S3 publication

Every PatientPunk/Lived Evidence database snapshot gets a `<stem>_provenance.yaml` beside it. A **snapshot** is a `.db` in the state it is handed off: read by a user, notebook, report, or another pipeline, or uploaded to S3. The runs and stages that wrote it are commands in its YAML, not separate snapshots. Databases created by tests, and scratch databases deleted before handoff, need no YAML. Other run outputs (CSV exports, notebooks, HTML reports) are out of scope here, except as outputs of an analysis record (see the end of this guide).

For a database you publish, `scripts/publish_db.py` writes the YAML from the database (see [YAML shape](#yaml-shape)). For a snapshot handed off without publishing, write it by hand: create it with `status: running` before the first command of a run expected to produce a snapshot. Close it as `completed` once its checks in [Finalizing and publishing](#finalizing-and-publishing) pass, or as `failed` or `interrupted` with any partial outputs listed. A resumed run keeps its YAML: set `status: running` again, append the new commands, and note the interruption in `comments`. Label backfills `record_method: retrospective` and separate observed from reconstructed facts. Use UTC ISO 8601 times and explain every `null`. Never invent provenance.

Publishing is a separate step. Upload a database to private S3 only when the user or the task asks for it; until then `publication.status` is `local`. Once a database and its YAML are uploaded and verified, both are frozen: never overwrite either object or edit the YAML again. A correction or rerun is a new snapshot under a new key, with a YAML whose `supersedes` names the earlier one.

## Required evidence

1. **Identity:** filename, purpose, run ID, status, dates, record method, and any snapshot it supersedes.
2. **Code:** repository, branch, full commit SHA, commit URL and whether that commit is on GitHub, and the pre-run clean/dirty state. List every file the run used that is not in that commit (local edits, study scripts outside Git) with its path from a named root and its SHA-256. When publishing, upload secret-free copies and add their S3 URIs.
3. **Inputs:** exact snapshots and required manifests, each with location, version ID if available, bytes, SHA-256, source window, and counts. A database input also names its provenance YAML, if it has one. Upload missing required inputs when authorized, or explain the reproduction limit.
4. **Commands:** one ordered list of the exact commands actually run, sufficient to rebuild this `.db` from the listed inputs and code. Give each command's working directory from a named root, `repo:` (the checked-out repository root) or `data:` (`PATIENTPUNK_DATA`, otherwise the checkout's sibling `PatientPunk_data/`), Write paths inside the working directory relative to it and any other path from a named root (`data:provenance_smoke/posts.db`), never as a machine-local absolute path. Include shell/runtime, non-secret overrides, times, exit codes, retained logs, retries, and resumes; cover acquisition through validation and any upload. If exact replay is impossible, say why.
5. **Methods:** dependency/schema/config/prompt hashes; exact model and effective settings; seeds, worker counts, selection, exclusions, analysis unit, joins, deduplication, missing values, and dose/route/effect attribution.
6. **Output:** location, bytes, SHA-256, integrity check, schema version, table counts, extraction run IDs, and validation results, all read from the finalized database.
7. **Comments:** errors, corrections, unresolved records, data gaps, eligibility, reproduction limits, supplementary manifest references, and whether effects link to treatment, report, or dose episode.
8. **Publication** (only when publishing): S3 URIs and version IDs, the result of the downloaded-copy hash check, and the catalog entry. Do not claim publication before verification.

Keep credentials, signed URLs, `.env` contents, patient text, identifiers, databases, and run YAML out of Git. Store data only in private S3. Preserve existing manifests and hand off the database and provenance locations.

## Finalizing and publishing

Publish only with `scripts/publish_db.py publish`. It needs S3 versioning on `s3://patientpunk`:

```bash
uv run python scripts/publish_db.py publish <db> --s3-uri s3://patientpunk/<prefix>/<stem>.db --label <label> \
    --purpose "<what the database holds>" --input "<input S3 URI or data: path>" --command "<command that built it>"
```

Give at least one `--input` and one `--command`, repeating each option for every input and command, in order. After the last writer exits, the script:

1. Runs `PRAGMA wal_checkpoint(TRUNCATE)`, confirms no non-empty `-wal` or `-journal` file remains, and runs the full `PRAGMA integrity_check`, which must be `ok`.
2. Refuses a database with no `extraction_runs`, or with a run whose `finished_at` is null, and a publish with no purpose, input or command (from the options or a local YAML).
3. Builds `<stem>_provenance.yaml` from the database: the commit, working-tree state, and each run's start and finish times and stored config (provider, model, reasoning mode, drug, depth, exclusions, workers), plus the SHA-256, bytes, table counts and run IDs. Sections already in a local YAML beside the database that the script does not generate, such as `processing`, `validation` and `comments`, are kept.
4. Refuses an S3 key that already holds a different database or any provenance YAML, uploads the database with its SHA-256 in object metadata, then uploads the YAML beside it.
5. Rebuilds `s3://patientpunk/INDEX.md`.

If it stops after the upload, run the same command again: a database already at the key with the same SHA-256 is treated as this publish's, and the script finishes it. Do not open the database for writing after publishing; a later write makes a new snapshot.

For a database already in S3 with no record, `publish <local copy> --s3-uri <existing URI> --label <label> --purpose "..." --record-only` writes a retrospective YAML beside it without uploading; `--input` and `--command` are optional there, since an old database's may be unknown. The local copy must match the object's size (and its SHA-256, if the object has one in its metadata).

A hook for Claude Code and Codex (`scripts/hooks/block_direct_db_upload.py`, registered in `.claude/settings.json` and `.codex/hooks.json`) blocks a shell command that uploads to S3 when any word on its line ends in `.db`, or when it uploads a folder (`sync`, `--recursive`) without `--exclude "*.db"`. It reads only the command's words, and downloads pass. With versioning on, an upload it misses is unrecorded rather than destructive, and `audit` lists it.

### Catalog

`s3://patientpunk/INDEX.md` lists every `.db` in the bucket outside `database_catalog/`. It is rebuilt from the bucket listing and each database's YAML, never edited by hand: on every publish, or with `uv run python scripts/publish_db.py audit --write-index`. A row's label comes from its YAML or its catalog copy's path, and a database whose successor's YAML names it under `database.supersedes` is marked superseded. `audit [--prefix <prefix>] [--strict]` lists each database and whether it has a published provenance YAML. A catalog copy is a second copy of the database under `s3://patientpunk/database_catalog/by-upload-date/uploaded-<YYYY-MM-DD>/<label>/<original key>`, for browsing by upload date and scope; make one only when asked. `publish_db.py` does not make catalog copies.

## YAML shape

`publish_db.py publish` writes the YAML. This is what it wrote for a one-run test database:

```yaml
schema_version: 1
record_kind: database_provenance
record_method: contemporaneous
generated_by: scripts/publish_db.py, from the database's extraction_runs table
database:
  filename: example.db
  purpose: LDN treatment reports from r/covidlonghaulers, one row per post and treatment
  status: completed
  started_utc: '2026-11-05T16:30:00Z'
  completed_utc: '2026-11-05T17:41:12Z'
  supersedes: null
code:
  repository: https://github.com/Ely-S/PatientPunk
  commit_shas:
  - 4b776d6e2f0c8a1d3b5e7f9a0c2d4e6f8a1b3c5d
  working_tree: clean
inputs:
- s3://patientpunk/corpora/covidlonghaulers_posts.db
commands:
- uv run python src/run_sentiment_pipeline.py --db data:ldn/example.db --output-dir data:ldn --drug LDN
extraction_runs:
- run_id: 1
  extraction_type: treatment_sentiment
  commit_sha: 4b776d6e2f0c8a1d3b5e7f9a0c2d4e6f8a1b3c5d
  started_utc: '2026-11-05T16:30:00Z'
  finished_utc: '2026-11-05T17:41:12Z'
  config:
    provider: openrouter
    reasoning_mode: disabled
    git_dirty: false
    models:
      fast: anthropic/claude-haiku-4.5
      strong: anthropic/claude-sonnet-4.6
    limit: 0
    drug: LDN
    workers: 8
output:
  sha256: 2475d4c6221592e470d6bcd65cae7ad03335483969b16772ca72ad4f15b25762
  bytes: 16384
  wal_checkpointed: true
  sqlite_integrity_check: ok
  table_row_counts:
    extraction_runs: 1
    treatment: 1
    treatment_reports: 3
  extraction_run_ids:
  - 1
publication:
  status: published
  s3_uri: s3://patientpunk/runs/ldn/example.db
  label: multi-treatment
  s3_version_id: Lx3t9kQe0rT2bV7mN4pW1sYc6uZa8dHf
  uploaded_utc: '2026-11-05T18:42:07Z'
  provenance_uri: s3://patientpunk/runs/ldn/example_provenance.yaml
```

The script generates all of these sections. `inputs` and `commands` come from `--input` and `--command`, and `extraction_runs[].config` is whatever each run stored, so its keys vary by pipeline. `code.working_tree` is `dirty` if any run recorded `git_dirty: true`, `clean` if every run recorded `false`, and `not recorded` otherwise. A `--record-only` record says `record_method: retrospective` and may have empty `inputs` and `commands`.

The script does not write `processing`, `validation` or `comments`. Put those in a `<stem>_provenance.yaml` beside the database before publishing and the script keeps them, along with any other section it does not generate; it also takes `database.purpose`, `database.supersedes`, `inputs` and `commands` from there when the matching option is not given. It drops YAML `#` comments, so put explanations in values or under `comments`. Quote values that end in a colon, such as `'repo:'`.

## Analyses and merged databases

A database built by merging other databases is a `database_provenance` record like any other, with each source database under `inputs`.

An analysis that reads more than one database (a notebook, report, or set of figures) gets `<analysis-name>_provenance.yaml` with `record_kind: analysis_provenance`. List each input database's location, SHA-256, and provenance YAML under `inputs`; the join, filter, deduplication, and denominator rules under `processing`; and the report files under `outputs`. Note outcomes imported from another pipeline or linked only at author or report level.
