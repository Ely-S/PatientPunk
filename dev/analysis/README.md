# Analysis Development

This directory is the working home for local analysis pipeline development.
Code can be exploratory here, but it should still be reproducible, documented,
and safe to rerun.

The current focus is the `r/covidlonghaulers` Reddit comments corpus:

- split the large source JSONL export into smaller structured files
- build a derived reply-context database
- support later classification, extraction, labeling, and audit workflows

Generated data lives under `dataset/` and is intentionally ignored by git.
Do not commit raw Reddit exports, generated JSONL chunks, SQLite databases, or
large derived artifacts.

## Directory Contents

```text
dev/analysis/
  README.md
  helpers.py                     # user-facing helper for getting/iterating comments
  build_comment_dataset.py       # compatibility wrapper for A0 dataset CLI
  build_comment_context_db.py    # compatibility wrapper for A0 context DB CLI
  a0_extraction/
    __init__.py
    build_comment_dataset.py     # CLI for splitting/verifying the raw JSONL export
    comment_dataset.py           # implementation for dataset build/verify
    build_comment_context_db.py  # CLI for building/querying the context SQLite DB
    comment_context.py           # implementation for context DB and CommentStore API
```

Additional compatibility wrapper:

```text
scripts/build_covidlonghaulers_comment_dataset.py
```

The wrappers delegate to `dev.analysis.a0_extraction`. Older commands continue
to work, but new implementation code should live under `a0_extraction/`.
Most analysis notebooks and scripts should import only `dev.analysis.helpers`.

## Generated Dataset Layout

Default dataset root:

```text
dataset/covidlonghaulers_comments/
```

Expected structure:

```text
dataset/covidlonghaulers_comments/
  README.md
  comments_jsonl/
    year=YYYY/
      month=MM/
        comments_YYYY-MM_part-0001.jsonl
        ...
  index/
    comments_index_part-0001.csv
    ...
  metadata/
    manifest.json
    chunks.csv
    index_files.csv
    summary_by_month.csv
    field_counts.csv
    malformed_lines.jsonl
  derived/
    comments.sqlite
```

The `comments_jsonl/` files are the canonical local split of the source export.
They preserve each valid source Reddit comment object as JSONL.

The `index/` CSV files are for browsing and quick lookup. They include compact
fields such as `source_line`, `date_utc`, `author`, `score`, `body_preview`,
`permalink`, and `chunk_file`.

The `metadata/` files are used for validation, checksums, field discovery, and
monthly counts.

The `derived/` directory is for analysis-oriented files created from the
canonical split dataset. Today this contains `comments.sqlite`. Future derived
files may include Parquet exports, context-window JSONL, labels, embeddings, or
audit samples.

## Current Dataset Snapshot

The current local build was verified with these totals:

```text
source lines: 1,950,192
valid comments: 1,950,192
blank lines: 0
malformed lines: 0
JSONL chunk files: 231
CSV index files: 40
date span UTC: 2020-07-24T19:58:29+00:00 to 2026-06-09T05:10:23+00:00
source SHA-256: 6511221575c20d5d07eab03a26e2e4af2bbb34543fee2a59ecc260bc2cc88ebe
```

The context database currently verifies as:

```text
comments: 1,950,192
comments with body: 1,950,192
distinct source lines: 1,950,192
top-level comments: 766,962
reply comments: 1,183,230
reply comments with available parent: 1,183,155
reply comments with missing parent: 75
removed/deleted comments: 52,710
```

These numbers are local build facts, not hardcoded assumptions for future code.
Use the manifest and verification commands when correctness matters.

## Build The Split Dataset

Default source:

```text
C:\Users\leech\Downloads\r_covidlonghaulers_comments_all.jsonl
```

Default output:

```text
dataset/covidlonghaulers_comments/
```

Verify the existing split dataset:

```powershell
python dev/analysis/a0_extraction/build_comment_dataset.py --verify-only
```

Rebuild the split dataset from the source JSONL:

```powershell
python dev/analysis/a0_extraction/build_comment_dataset.py --replace
```

Use explicit paths if needed:

```powershell
python dev/analysis/a0_extraction/build_comment_dataset.py `
  --source "C:\Users\leech\Downloads\r_covidlonghaulers_comments_all.jsonl" `
  --output "dataset\covidlonghaulers_comments" `
  --replace
```

Useful build options:

```text
--max-rows-per-jsonl   rows per full-record JSONL chunk, default 10000
--max-rows-per-index   rows per browsing CSV, default 50000
--preview-chars        characters retained in CSV body_preview, default 500
--progress-every       progress logging interval, default 100000
--replace              replace existing output directory
--verify-only          verify existing output without rebuilding
```

The splitter uses streaming reads. It does not load the full source JSONL into
memory.

## Build The Reply Context Database

The context database is a derived SQLite file:

```text
dataset/covidlonghaulers_comments/derived/comments.sqlite
```

Build or rebuild it:

```powershell
python dev/analysis/a0_extraction/build_comment_context_db.py --replace
```

Verify it:

```powershell
python dev/analysis/a0_extraction/build_comment_context_db.py --verify-only
```

Render a context window by source line:

```powershell
python dev/analysis/a0_extraction/build_comment_context_db.py `
  --sample-source-line 11 `
  --ancestor-depth 3 `
  --previous-sibling-limit 2 `
  --previous-thread-limit 3
```

Render a context window by comment ID:

```powershell
python dev/analysis/a0_extraction/build_comment_context_db.py `
  --sample-id fz5axid `
  --ancestor-depth 3
```

Useful context DB options:

```text
--dataset                  dataset root, default dataset/covidlonghaulers_comments
--db                       SQLite DB path, default dataset/.../derived/comments.sqlite
--replace                  replace existing context DB
--verify-only              verify existing context DB
--sample-id                render a context window for a comment id or t1_ name
--sample-source-line       render a context window for a source line
--ancestor-depth           number of parent-chain comments to include
--previous-sibling-limit   earlier replies under the same parent
--previous-thread-limit    earlier comments in the same thread
--progress-every           progress logging interval, default 100000
```

## Context Database Schema

Main table:

```text
comments
```

Key columns:

```text
id                     bare Reddit comment id, for example fz4iv4x
name                   full thing id, for example t1_fz4iv4x
link_id                thread/post id, usually t3_<post_id>
post_id                bare post id derived from link_id or parent_id
parent_id              Reddit parent id, t1_<comment_id> or t3_<post_id>
parent_kind            comment, post, or unknown
parent_comment_id      bare parent comment id when parent_kind = comment
created_utc            integer timestamp
date_utc               ISO UTC timestamp
author                 Reddit username as present in export
score                  comment score
is_submitter           1 if the comment author is the original poster
stickied               1 if stickied
body                   full comment body
body_length            length of body
body_sha256            SHA-256 hash of body text
is_removed_or_deleted  1 for [removed] or [deleted]
permalink              Reddit permalink
source_line            original source JSONL line number
source_chunk           split JSONL chunk containing the full source record
has_body               1 after body text has been loaded from JSONL chunks
```

Indexes are created for:

```text
link_id + created_utc
parent_id + created_utc
parent_comment_id
created_utc
author + created_utc
source_chunk
is_removed_or_deleted
```

This supports fast lookups for:

- direct parent comments
- child comments
- ancestor chains
- previous sibling comments
- previous comments in the same thread
- author timelines
- chronological corpus scans

## Programmatic API

Use `dev.analysis.helpers.comments` for normal analysis code. It is the one
helper intended for getting one comment or iterating many comments.

Get one comment with context by source line:

```python
from dev.analysis.helpers import comments

item = comments(
    source_line=11,
    ancestor_depth=3,
    previous_sibling_limit=2,
    previous_thread_limit=3,
)

print(item.target.body)
print([ancestor.body for ancestor in item.ancestors])
```

Get one bare comment without context:

```python
from dev.analysis.helpers import comments

comment = comments(source_line=11, with_context=False)
print(comment.body)
```

Iterate through comments with context:

```python
from dev.analysis.helpers import comments

for item in comments(
    ancestor_depth=2,
    previous_sibling_limit=2,
    previous_thread_limit=0,
    order="created_utc, id",
    limit=100,
):
    target = item.target
    ancestors = item.ancestors
    previous_siblings = item.previous_siblings
    missing = item.missing
```

Iterate through bare comments:

```python
from dev.analysis.helpers import comments

for comment in comments(with_context=False, limit=100):
    print(comment.id, comment.body[:80])
```

Advanced code can still use the lower-level context implementation:

```python
from dev.analysis.a0_extraction.comment_context import CommentStore, render_context

with CommentStore() as store:
    context = store.get_context("fz5axid", ancestor_depth=3)
    print(render_context(context))
```

## What "Before This Comment" Means

Reddit threads are trees, not flat conversations. The context API keeps these
concepts separate:

```text
ancestors
  The direct parent, grandparent, and higher parent-chain comments.

previous_siblings
  Earlier comments under the same parent_id.

previous_thread_comments
  Earlier comments in the same link_id/thread, ordered chronologically.

target
  The one comment being classified or extracted.
```

Default classification context should usually be conservative:

```text
ancestor_depth = 2
previous_sibling_limit = 0 or 2
previous_thread_limit = 0
```

Use broader thread context mainly for manual audit, conversation-flow analysis,
or specialized models that are explicitly designed for thread-level evidence.

## Attribution Rule

For extraction and classification, treat `context.target` as the only comment
being classified.

Use ancestor, sibling, and previous-thread context only to resolve references
such as:

```text
same
that
it
this medication
that crash
your symptoms
```

Do not copy claims from context authors into the target author's record unless
the target comment itself endorses, repeats, or clearly adopts the claim.

Bad extraction:

```text
Parent: "LDN helped my fatigue."
Target: "How long did it take?"

Wrong label: target author took LDN and improved.
```

Better extraction:

```text
Target is asking about LDN timing.
No target-author treatment claim is present.
```

This distinction is central to keeping downstream biomedical analysis clean.

## Known Limitations

The current dataset is comments-only. It does not include submission titles,
submission bodies, flair, post score, or root post author text.

For top-level comments:

```text
parent_id = t3_<post_id>
```

the context DB knows the comment replied to a post, but it cannot provide the
post title or body. `CommentContext.missing` marks this as:

```python
{"root_post": "not_available_in_comments_jsonl"}
```

If a future posts/submissions dataset is added, extend the context DB with a
`posts` table and include root post context in `CommentContext`.

There are also a small number of reply comments whose parent comments are not
present in the export. Those are preserved and reported during verification.

## Verification Expectations

Run these after changing analysis code:

```powershell
python -m py_compile dev/analysis/helpers.py dev/analysis/a0_extraction/comment_dataset.py dev/analysis/a0_extraction/build_comment_dataset.py
python -m py_compile dev/analysis/a0_extraction/comment_context.py dev/analysis/a0_extraction/build_comment_context_db.py
python -m ruff check dev/analysis/helpers.py dev/analysis/a0_extraction/comment_dataset.py dev/analysis/a0_extraction/build_comment_dataset.py dev/analysis/a0_extraction/comment_context.py dev/analysis/a0_extraction/build_comment_context_db.py
python dev/analysis/a0_extraction/build_comment_dataset.py --verify-only
python dev/analysis/a0_extraction/build_comment_context_db.py --verify-only
```

The dataset verification re-reads all split JSONL chunks and CSV index files.
The context DB verification checks row counts, body loading, source-line
uniqueness, date bounds, parent availability, and removed/deleted counts.

## Suggested Future Pipeline Shape

Keep the pipeline layered:

```text
1. Canonical local split
   comments_jsonl/, index/, metadata/

2. Context index
   derived/comments.sqlite

3. Candidate selection
   keyword search, date windows, high-score samples, thread samples

4. Context-window export
   target comment plus controlled context

5. Classification and extraction
   target-only attribution, context for disambiguation

6. Audit and evaluation
   manually review samples, compare context-free vs context-aware labels

7. Final derived tables
   symptoms, treatments, outcomes, doctor experiences, support/crisis labels
```

Likely future derived artifacts:

```text
dataset/covidlonghaulers_comments/derived/
  comments.sqlite
  context_windows_sample.jsonl
  labels.sqlite
  comments.parquet/
  treatment_mentions.parquet
  symptom_mentions.parquet
  audit_samples/
```

Do not overwrite canonical split JSONL files to support an analysis idea.
Instead, create a derived file or table that can be regenerated.

## Development Conventions

- Keep raw and derived data out of git.
- Prefer streaming reads for large JSONL files.
- Prefer SQLite/DuckDB/Parquet over repeated full JSONL scans.
- Keep context roles explicit: target, ancestor, sibling, previous-thread.
- Keep target-author attribution separate from context-author claims.
- Add verification commands for every new derived artifact.
- Write manual-render helpers for anything a classifier will see.
- Make generated outputs reproducible from CLI commands.
- Avoid hidden notebook-only state for pipeline-critical steps.

## Troubleshooting

If the split dataset is missing:

```powershell
python dev/analysis/a0_extraction/build_comment_dataset.py --replace
```

If `comments.sqlite` is missing:

```powershell
python dev/analysis/a0_extraction/build_comment_context_db.py --replace
```

If verification fails after a partial build, rebuild with `--replace`.

If a context sample has no root post text, that is expected for top-level
comments until a submissions dataset is added.

If a reply has no parent comment, check verification output for the count of
missing reply parents. A small number are currently expected.

If a command is slow, check whether it is re-reading the full JSONL split or
building SQLite indexes. Those phases are expected to take longer than ordinary
context queries.
