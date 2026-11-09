# When creating Pull Requests
1. Use detailed commit messages
2. Every PR Needs a Description that has the following sections
- ## Why - Explaining the problem being solved, and why it is important
- ## Approach taken - Explaining the solution fully and the design
- ## User-facing changes  - Explain how this affects users
- ## Detailed test plan - A Test plan that an agent can follow, including end-to-end verification

The test plan must include exact commands to run and detailed steps to verify the output of the run

# Database provenance

Before a run that will produce a `.db` for handoff or upload, follow [docs/database-provenance.md](docs/database-provenance.md). Its `<database-stem>_provenance.yaml` records the exact inputs, code commit, commands, validation, and hashes the guide requires: `publish_db.py` writes it when you publish, keeping sections you add beside the database first, such as `validation`; for a database handed off without publishing, write it by hand. Upload a database to private S3 only when the user or the task asks, and only with `uv run python scripts/publish_db.py publish <db> --s3-uri <s3-uri> --label <label> --purpose <text> --input <input> --command <command>`, which finalizes the database, builds its YAML from `extraction_runs`, refuses to overwrite a published snapshot and rebuilds `s3://patientpunk/INDEX.md`. Never upload a `.db` with `aws s3` or another tool directly; a hook in Claude Code and Codex blocks it. `scripts/publish_db.py audit` lists S3 databases without a published provenance YAML. For an analysis combining databases, create the separate analysis provenance described there. Databases created by tests, and scratch databases deleted before handoff, are exempt. Keep databases, run-specific provenance, and patient data out of Git.
