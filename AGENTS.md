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
| Which model / provider is configured? | `grep -sE '^(LLM_PROVIDER\|MODEL_FAST\|MODEL_STRONG)=' .env variable_extraction/.env` |
| Is a key set, and which one? | `python -c "from patientpunk._utils import resolve_llm_config as r; c=r(); print(c['provider'], '...' + (c['api_key'] or '')[-6:])"` |
| Does the key work / what is the balance? | call the provider with it; never echo it |

A six-character suffix distinguishes two keys and is useless to anyone who
finds it. That is the most that should ever reach a chat, a commit, or a log.

If a key does get exposed, say so plainly and immediately and recommend
rotating every key in the file — not only the one that was being asked about.

# When creating Pull Requests
1. Use detailed commit messages
2. Every PR Needs a Description that has the following sections
- ## Why - Explaining the problem being solved, and why it is important
- ## Approach taken - Explaining the solution fully and the design
- ## User-facing changes  - Explain how this affects users
- ## Detailed test plan - A Test plan that an agent can follow, including end-to-end verification

The test plan must include exact commands to run and detailed steps to verify the output of the run
