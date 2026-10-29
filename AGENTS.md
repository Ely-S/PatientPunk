# When creating Pull Requests
1. Use detailed commit messages
2. Every PR Needs a Description that has the following sections
- ## Why - Explaining the problem being solved, and why it is important
- ## Approach taken - Explaining the solution fully and the design
- ## User-facing changes  - Explain how this affects users
- ## Detailed test plan - A Test plan that an agent can follow, including end-to-end verification

The test plan must include exact commands to run and detailed steps to verify the output of the run

# Database provenance

Before a run that will produce a `.db` for handoff or upload, follow [docs/database-provenance.md](docs/database-provenance.md). Create `<database-stem>_provenance.yaml` beside the database and record the exact inputs, code commit, commands, validation, and hashes the guide requires. Finalize the database with `uv run python scripts/publish_db.py finalize <db>`, which checkpoints the SQLite write-ahead log, checks integrity and writes the hashes and counts into the YAML. Upload a database to private S3 only when the user or the task asks, and only with `uv run python scripts/publish_db.py publish <db> --s3-uri <s3-uri> --label <label>`, which refuses to overwrite a published snapshot, verifies the upload and updates `s3://patientpunk/INDEX.md`. Never upload a `.db` with `aws s3` or another tool directly; a Claude Code hook blocks it. `scripts/publish_db.py audit` lists S3 databases missing provenance or a catalog row. For an analysis combining databases, create the separate analysis provenance described there. Databases created by tests, and scratch databases deleted before handoff, are exempt. Keep databases, run-specific provenance, and patient data out of Git.
