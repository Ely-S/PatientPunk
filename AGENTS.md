# GitHub

**Draft PRs are the only state change you may make on your own.** Create them, push
the branch they need, and stop.

Everything else on a shared repo is the maintainers' decision, not yours:

| | |
|---|---|
| allowed unprompted | `gh pr create --draft`, pushing that branch |
| needs a per-action yes | `gh pr close`, `gh pr merge`, `gh pr ready`, `gh pr edit`, `gh pr comment`, `gh issue` anything, `git push --force`, deleting a remote branch |

A per-action yes means *this* action, *now*. Approval to open a PR is not approval to
close it. Approval to close is not approval to delete its branch. Do not widen a
request into the adjacent action that seems implied.

**Read remote state before writing to it** — `gh pr view` before any `gh pr` write.
But note the ordering: checking state does not license the action. If you would take
the action on finding it open, you needed permission before you looked.

Local work is unrestricted: fetch, checkout, branch, cherry-pick, commit, rebase,
worktrees, running tests. Do all of it, then name the exact remote actions required and
wait.

**Why this is written down:** a draft PR was created, the maintainer closed it, and the
agent then fired its own close at the already-closed PR and deleted the remote branch —
which nobody had asked for. The close was redundant; the branch deletion was not.

# Secrets

**Never read, print, or paste the contents of a `.env` file.** `.env` and
`variable_extraction/.env` hold live keys for OpenRouter, Anthropic, Brave and
Dispersed. Opening one puts every key in the transcript, and a transcript is not
a place a key can be un-shared from — it costs a rotation of all of them.

This applies to `cat`, `Read`, `head`, `type`, and to quoting a line back in
chat. It applies even when the question sounds harmless: "is the .env in the
right place", "did the key change", "which model is set". None of those need the
file's contents.

Answer them without opening it:

| Question | Command |
|---|---|
| Does the file exist? | `test -f .env && echo present` |
| Which model / provider is configured? | `grep -s -e '^LLM_PROVIDER=' -e '^MODEL_FAST=' -e '^MODEL_STRONG=' .env variable_extraction/.env` |
| Is a key set, and which one? | `python -c "from patientpunk._utils import resolve_llm_config as r; c=r(); print(c['provider'], '...' + (c['api_key'] or '')[-6:])"` |
| Does the key work / what is the balance? | call the provider with it; never echo it |

A six-character suffix distinguishes two keys and is useless to anyone who
finds it. That is the most that should ever reach a chat, a commit, or a log.

If a key does get exposed, say so plainly and immediately and recommend
rotating every key in the file — not only the one that was being asked about.

# Data lives outside the repo

**Corpora, databases and run outputs go in a `PatientPunk_data/` directory that sits
beside the checkout, not inside it.** The repo holds code and small text artifacts;
everything a pipeline generates or ingests stays out of version control.

Resolve it from the repo root, never from an absolute path:

```python
ROOT = Path(__file__).resolve().parents[2]      # repo root; count the levels
DATA = Path(os.environ.get("PATIENTPUNK_DATA") or ROOT.parent / "PatientPunk_data")
```

`studies/tropoflavin_nootropics/build_corpus.py` is the reference. Honour
`PATIENTPUNK_DATA` when it is set so a contributor who keeps data elsewhere — another
drive, a mounted share, no OneDrive at all — does not have to edit code to run anything.

**A path like `C:\Users\<you>\OneDrive\Documents\Projects\PatientPunk_data\...` must
never reach a committed file.** It works on exactly one machine. It also names a person,
which is worth avoiding in a repo that may be shared or published. That includes scripts,
notebooks, and the `output_dir` recorded inside a run manifest.

Absolute paths are fine in a throwaway shell command or a scratch file. The rule is about
what gets committed.

## Do not commit generated data

Extraction and canonicalisation outputs are large, regenerable, and diff as noise. Check
`git status` before committing, and add a pattern to `.gitignore` rather than selectively
staging around them.

`.gitignore` already covers several by name — `**/llm_records_*.json`,
`**/discovered_records_*.json`, `**/extraction_metadata_*.json`. Anything of the same
kind belongs there too.

**Why this is written down:** `tagged_mentions.json` and `canonicalized_mentions.json`
had no pattern, so a working tree accumulated 408,782 untracked lines across
`studies/noots_baseline/outputs_W`, `outputs_DHFcorpus` and
`studies/tropoflavin_nootropics/outputs_A`. Nothing was broken by it, but it made the
real diff impossible to see and made a five-file change look like a rewrite of the repo.

# When creating Pull Requests
1. Use detailed commit messages
2. Every PR Needs a Description that has the following sections
- ## Why - Explaining the problem being solved, and why it is important
- ## Approach taken - Explaining the solution fully and the design
- ## User-facing changes  - Explain how this affects users
- ## Detailed test plan - A Test plan that an agent can follow, including end-to-end verification

The test plan must include exact commands to run and detailed steps to verify the output of the run

# Database provenance

Before a run that will produce a `.db` for handoff or upload, follow [docs/database-provenance.md](docs/database-provenance.md). Create `<database-stem>_provenance.yaml` beside the database and record the exact inputs, code commit, commands, validation, and hashes the guide requires. Checkpoint the SQLite write-ahead log before hashing. Upload a database and its YAML to private S3 only when the user or the task asks; never overwrite a published snapshot, and finish publishing with a conditional update of `s3://patientpunk/INDEX.md`. For an analysis combining databases, create the separate analysis provenance described there. Databases created by tests, and scratch databases deleted before handoff, are exempt. Keep databases, run-specific provenance, and patient data out of Git.
