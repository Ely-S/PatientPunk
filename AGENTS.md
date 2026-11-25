# GitHub

- Without asking: open draft PRs (`gh pr create --draft`) and push their branches.
- Everything else on GitHub needs a yes for that specific action, each time: close, merge, mark ready, edit, comment, anything with issues, force-push, deleting a remote branch. A yes to one action does not cover the next one it seems to imply.
- Check remote state (`gh pr view`) before writing to it. Checking does not authorize the write.
- Local git work (branch, commit, rebase, worktrees, tests) needs no permission.

# Secrets

Never read, print or quote `.env` or `variable_extraction/.env`. They hold live API keys, and one leak means rotating all of them. This holds even for harmless-sounding questions. Instead:

- Does it exist: `test -f .env && echo present`
- Model and provider: `grep -s -e '^LLM_PROVIDER=' -e '^MODEL_FAST=' -e '^MODEL_STRONG=' .env variable_extraction/.env`
- Which key is set: `python -c "from patientpunk._utils import resolve_llm_config as r; c=r(); print(c['provider'], '...' + (c['api_key'] or '')[-6:])"`
- Does the key work: call the provider with it, without printing it.

Never show more than a key's last six characters. If a key is exposed, say so at once and recommend rotating every key in that file.

# Paid runs and S3

- Before a run that calls a paid model or service, say what it will cost; an estimate is fine. If it is more than a few dollars, ask first.
- Never overwrite or delete an S3 object without a yes for that action that names each object that will go.

# When creating Pull Requests
1. Use detailed commit messages
2. Every PR Needs a Description that has the following sections
- ## Why - Explaining the problem being solved, and why it is important
- ## Approach taken - Explaining the solution fully and the design
- ## User-facing changes  - Explain how this affects users
- ## Detailed test plan - A Test plan that an agent can follow, including end-to-end verification

The test plan must include exact commands to run and detailed steps to verify the output of the run

# Database provenance

Before a run that will produce a `.db` for handoff or upload, follow [docs/database-provenance.md](docs/database-provenance.md). Its `<database-stem>_provenance.yaml` records the exact inputs, code commit, commands, validation, and hashes the guide requires: `publish_db.py` writes it when you publish, keeping sections you add beside the database first, such as `validation`; for a database handed off without publishing, write it by hand. Upload a database to private S3 only when the user or the task asks, and only with `uv run python scripts/publish_db.py publish <db> --s3-uri <s3-uri> --label <label> --purpose <text> --input <input> --command <command>`, which finalizes the database, builds its YAML from `extraction_runs`, refuses to overwrite a published snapshot and rebuilds `s3://patientpunk/INDEX.md`. Never upload a `.db` with `aws s3` or another tool directly. `scripts/publish_db.py audit` lists S3 databases without a published provenance YAML. For an analysis combining databases, create the separate analysis provenance described there. Databases created by tests, and scratch databases deleted before handoff, are exempt. Keep databases, run-specific provenance, and patient data out of Git.
