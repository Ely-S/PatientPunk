# GitHub

| | |
|---|---|
| allowed unprompted | `gh pr create --draft`, pushing that branch |
| needs a per-action yes | `gh pr close`, `gh pr merge`, `gh pr ready`, `gh pr edit`, `gh pr comment`, `gh issue` anything, `git push --force`, deleting a remote branch |

A per-action yes means *this* action, *now*. Approval to open a PR is not approval to
close it. Approval to close is not approval to delete its branch. Do not widen a
request into the adjacent action that seems implied.

NEVER MERGE TO MAIN WITHOUT EXPLICIT PERMISSION. 

Raw or processed data should never be put on the Github:  this is stored on the S3.

**Read remote state of a repo before writing to it** 

# When creating Pull Requests
1. Use detailed commit messages
2. Every PR Needs a Description that has the following sections
- ## Why - Explaining the problem being solved, and why it is important
- ## Approach taken - Explaining the solution fully and the design
- ## User-facing changes  - Explain how this affects users
- ## Detailed test plan - A Test plan that an agent can follow, including end-to-end verification
- ## Always start PR's as Drafts:  let the user mark them as ready to merge

The test plan must include exact commands to run and detailed steps to verify the output of the run



# Secrets

**Never read, print, or paste the contents of a `.env` file.** `.env` and
`variable_extraction/.env` hold live keys.

This applies to `cat`, `Read`, `head`, `type`.

Examples on how to check for keys and explore Secrets.
| Question | Command |
|---|---|
| Does the file exist? | `test -f .env && echo present` |
| Which model / provider is configured? | `grep -sE '^(LLM_PROVIDER\|MODEL_FAST\|MODEL_STRONG)=' .env variable_extraction/.env` |
| Is a key set, and which one? | `python -c "from patientpunk._utils import resolve_llm_config as r; c=r(); print(c['provider'], '...' + (c['api_key'] or '')[-6:])"` |
| Does the key work / what is the balance? | call the provider with it; never echo it |

A six-character suffix distinguishes two keys and is useless to anyone who
finds it. That is the most that should ever reach a chat, a commit, or a log.

If a key does get exposed, say so plainly.

