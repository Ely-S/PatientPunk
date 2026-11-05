# Database provenance and S3 publication

Every PatientPunk/Lived Evidence database snapshot gets a `<stem>_provenance.yaml` beside it. A **snapshot** is a `.db` in the state it is handed off: read by a user, notebook, report, or another pipeline, or uploaded to S3. The runs and stages that wrote it are commands in its YAML, not separate snapshots. Databases created by tests, and scratch databases deleted before handoff, need no YAML. Other run outputs (CSV exports, notebooks, HTML reports) are out of scope here, except as outputs of an analysis record (see the end of this guide).

Create the YAML with `status: running` before the first command of a run expected to produce a snapshot. Close it as `completed` once its checks in [Finalizing and publishing](#finalizing-and-publishing) pass, or as `failed` or `interrupted` with any partial outputs listed. A resumed run keeps its YAML: set `status: running` again, append the new commands, and note the interruption in `comments`. Label backfills `record_method: retrospective` and separate observed from reconstructed facts. Use UTC ISO 8601 times and explain every `null`. Never invent provenance.

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
uv run python scripts/publish_db.py publish <db> --s3-uri s3://patientpunk/<prefix>/<stem>.db --label <label>     --purpose "<what the database holds>" --input "<input S3 URI or data: path>" --command "<command that built it>"
```

Repeat `--input` and `--command` for each one, in order. After the last writer exits, the script:

1. Runs `PRAGMA wal_checkpoint(TRUNCATE)`, confirms no non-empty `-wal` or `-journal` file remains, and runs the full `PRAGMA integrity_check`, which must be `ok`.
2. Refuses a database with no `extraction_runs`, or with a run whose `finished_at` is null.
3. Builds `<stem>_provenance.yaml` from the database: the commit, working-tree state, and each run's start and finish times and stored config (provider, model, reasoning mode, drug, depth, exclusions, workers), plus the SHA-256, bytes, table counts and run IDs. Sections already in a local YAML beside the database that the script does not generate, such as `processing`, `validation` and `comments`, are kept.
4. Refuses an S3 key that already holds a different database or any provenance YAML, uploads the database with its SHA-256 in object metadata, then uploads the YAML beside it.
5. Rebuilds `s3://patientpunk/INDEX.md`.

If it stops after the upload, run the same command again: a database already at the key with the same SHA-256 is treated as this publish's, and the script finishes it. Do not open the database for writing after publishing; a later write makes a new snapshot.

For a database already in S3 with no record, `publish <local copy> --s3-uri <existing URI> --label <label> --purpose "..." --record-only` writes a retrospective YAML beside it without uploading. The local copy must match the object's size (and its SHA-256, if the object has one in its metadata).

### Catalog

`s3://patientpunk/INDEX.md` lists every `.db` in the bucket outside `database_catalog/`. It is rebuilt from the bucket listing and each database's YAML, never edited by hand: on every publish, or with `uv run python scripts/publish_db.py audit --write-index`. A row's label comes from its YAML or its catalog copy's path, and a database whose successor's YAML names it under `database.supersedes` is marked superseded. `audit [--prefix <prefix>] [--strict]` lists each database and whether it has a published provenance YAML. A catalog copy is a second copy of the database under `s3://patientpunk/database_catalog/by-upload-date/uploaded-<YYYY-MM-DD>/<label>/<original key>`, for browsing by upload date and scope; make one only when asked. `publish_db.py` does not make catalog copies.

## YAML shape

Use observed values; explain `null` fields and add workflow-specific fields as needed. `publish_db.py` generates `database`, `code`, `extraction_runs`, `output` and `publication` from the database when it publishes, keeps the other sections, and drops YAML `#` comments, so put explanations in values or `comments`. Quote values that end in a colon, such as `'repo:'`.

```yaml
schema_version: 1
record_kind: database_provenance
record_method: contemporaneous  # or retrospective
database:
  filename: example.db
  purpose: "<what this database contains>"
  run_id: "<run identifier>"
  status: running  # completed, failed, or interrupted at close
  started_utc: "<ISO 8601>"
  completed_utc: null
  supersedes: null  # S3 URI and SHA-256 of the snapshot this corrects or reruns
code:
  repository: "https://github.com/<owner>/<repo>"
  branch: "<observed branch or detached HEAD>"
  commit_sha: "<full 40-character SHA>"
  commit_url: "<GitHub commit URL>"
  commit_on_github: true  # false if the commit was never pushed
  working_tree: "<clean or dirty>"
  code_outside_commit: []  # path from a named root, SHA-256, and S3 URI once published
environment:
  os: "<name and version>"
  runtime: "<Python and package-manager versions>"
  dependency_lockfile: "<GitHub URL and SHA-256>"
  schema: "<GitHub URL, version, and SHA-256>"
  config_and_prompts: []  # GitHub URLs, versions, and SHA-256 values
  model: null  # provider, exact model ID, effective settings, or reason N/A
  nonsecret_overrides: []
inputs:
  - name: "<source snapshot>"
    location: "s3://<private-bucket>/<exact-key>"  # or a path from a named root if never published
    s3_version_id: null
    sha256: "<SHA-256>"
    bytes: 0
    record_count: null
    source_window: null
    provenance: null  # the input database's YAML, if it has one
processing:
  unit_of_analysis: "<dose record, report, author-treatment, etc.>"
  selection_and_exclusions: "<exact rules>"
  joins_and_deduplication: "<exact rules>"
  missing_data_and_attribution: "<exact rules>"
  workers: null  # concurrency per stage
  random_seeds: []
commands:  # ordered commands actually run
  - stage: "<stage name>"
    cwd: "repo:"  # or "data:<path>"; other paths in the command start with a named root
    command: "<exact runnable command; redact secrets by argument name>"
    shell: "<shell and version>"
    started_utc: "<ISO 8601>"
    ended_utc: "<ISO 8601>"
    exit_code: 0
    log: null  # retained log, as a path from a named root or an S3 URI
output:
  location: "data:<path>/example.db"
  sha256: "<SHA-256 of the finalized database>"
  bytes: 0
  wal_checkpointed: true
  sqlite_integrity_check: "ok"
  schema_version: "<observed version>"
  table_row_counts: {}
  extraction_run_ids: []
validation:
  checks: []  # expected and observed results; commands are listed above
publication:
  status: local  # or published
  s3_uri: null
  s3_version_id: null
  uploaded_utc: null
  downloaded_sha256_matches: null
  catalog_copy_uri: null
  catalog_verified_utc: null
comments: []  # limitations and supplementary manifest references; required manifests go under inputs
```

## Analyses and merged databases

A database built by merging other databases is a `database_provenance` record like any other, with each source database under `inputs`.

An analysis that reads more than one database (a notebook, report, or set of figures) gets `<analysis-name>_provenance.yaml` with `record_kind: analysis_provenance`. List each input database's location, SHA-256, and provenance YAML under `inputs`; the join, filter, deduplication, and denominator rules under `processing`; and the report files under `outputs`. Note outcomes imported from another pipeline or linked only at author or report level.
