# Arctic Shift Acquisition Provenance

This document records how the raw Reddit JSON underlying this paper's
analysis was acquired. It complements the SHA-256 hash and entry-count
information in [`README.md`](./README.md), which freeze the *result* of
the acquisition; this file freezes the *process*.

## Source

| Property | Value |
|---|---|
| Provider | Arctic Shift (Pushshift successor archive) |
| Download tool | <https://arctic-shift.photon-reddit.com/download-tool> |
| Subreddit | `r/covidlonghaulers` |
| Most recent scrape | **2026-05-02** (Saturday) |

The Arctic Shift download tool exports the full posting history of a
subreddit as bulk JSONL files (one for posts, one for comments). We
download those JSONL files and convert them to the per-paper JSON format
consumed by `src/import_posts.py`.

## Acquired files (raw JSONL, prior to conversion)

| File | Approx. size | What it contains |
|---|---|---|
| `r_covidlonghaulers_posts_all.jsonl` | ~404 MB | Every top-level post in `r/covidlonghaulers` from corpus inception through the scrape date |
| `r_covidlonghaulers_comments_all.jsonl` | ~3.3 GB | Every comment in `r/covidlonghaulers` over the same range |

Both files are stored in `~/OneDrive/Documents/Projects/PatientPunk_data/`
on the analyst's local machine; they are not redistributed in this
package because of size.

## Conversion to analysis JSON

The bulk JSONL files are filtered and reshaped into the
post-with-nested-comments JSON consumed by `src/import_posts.py`. The
canonical output is:

| File | Window | Size | SHA-256 |
|---|---|---|---|
| `historical_validation_2020-07_to_2022-12.json` | 2020-07-24 18:58 UTC → 2022-12-31 23:58 UTC | 378,221,044 bytes | `298d5bc719fb42b87169c28207ad509d17c94300d1c5e3b66370e98a79abfe6a` |

Conversion script: `scripts/convert_jsonl_to_source.py`. Re-running with
the same inputs and the same date range produces an identical JSON.

## Reproducing the acquisition

A reviewer who wants to rebuild the corpus from scratch would:

1. Visit <https://arctic-shift.photon-reddit.com/download-tool>.
2. Select subreddit `covidlonghaulers`, choose "all posts" and "all
   comments" downloads, save the resulting `.jsonl` files locally.
3. Run `scripts/convert_jsonl_to_source.py` to filter to the analysis
   window and produce `historical_validation_2020-07_to_2022-12.json`.
4. Verify SHA-256 matches `298d5bc7...abfe6a`.

Note that Reddit posts can be deleted between the original Arctic Shift
crawl and a re-acquisition, so the byte-identical reproduction is only
guaranteed against the snapshot Arctic Shift had on 2026-05-02. Earlier
or later Arctic Shift snapshots may differ.

## Why the date range stops at 2022-12-31

The full Arctic Shift archive scraped on 2026-05-02 covers
2020-07-24 through 2026-04-28. For this paper's historical-validation
analysis we cap at end-of-2022 (post_date < 2023-01-01 UTC) so the data
predates the publication of the comparator clinical trials for paxlovid
(2024) and colchicine (2025). See [`README.md`](./README.md), section
"Pre-publication cutoffs" for details.
