# Baseline Check

The evidence behind **Baseline Check**, a short weekly questionnaire for Long COVID and ME/CFS trials, drawn
from how patients describe their own health changing on Reddit.

The [v0.3.1 questionnaire](../../docs/baseline_check/index.html) and its rationale are maintained in
`docs/baseline_check/`. The three product pages share `style.css`:

| Page | File | For |
|---|---|---|
| The Quiz | `index.html` | Patients and carers: the working form, with live scores |
| Methodology and Data | `methodology.html` | Trialists and reviewers: scoring rules, the evidence, limitations, validation plan |
| Blog post | `blog.html` | General readers: the story of how the check was built |

The product uses aggregate findings and thematic summaries. The analysis scripts and codebooks are here,
with the source of each finding identified on the Methodology and Data page.

Claude Sonnet agents coded the main samples for this exploratory study. Patient validation is pending.
The [next-version design and validation plan](next_version/README.md) includes a reproducible audit of the current
evidence and specifies what to test in the next instrument.

---

## Contents

1. [The questionnaire in brief](#the-questionnaire-in-brief)
2. [Inputs](#inputs)
3. [Folder layout](#folder-layout)
4. [How the work was done](#how-the-work-was-done)
5. [Findings and where they come from](#findings-and-where-they-come-from)
6. [Corrections made along the way](#corrections-made-along-the-way)
7. [Limitations](#limitations)
8. [Reproducing the results](#reproducing-the-results)
9. [Script reference](#script-reference)
10. [Data that is not in Git](#data-that-is-not-in-git)
11. [Cost](#cost)
12. [Next version](#next-version)

---

## The questionnaire in brief

Version 0.3.1 asks about the past 7 days.

| Q | Asks | Scored as |
|---|---|---|
| Q1 | Days in a crash or flare, whatever set it off. Setting Q1 to zero clears the optional trigger list | 0–7 |
| Q2 | Activities done **without paying for it later**, counting only those done at least two days before the check so a delayed crash has time to show. 23 items in 4 groups: *Within the home*, *Everyday basics*, *Getting out and keeping up*, *Full days and beyond*. Each group has "All of these" and "None of these this week" buttons | Group scores as answered. Total 0–23 once all four groups are answered |
| Q3 | Overall symptoms on a typical day | 0–10 |
| Q4 | Percent of your old self (**optional**), on a slider with a Clear answer button | 0–100 in steps of 5 |
| Q5 | Change since the last check (with a "No earlier check" choice) | 7-point scale |
| Q6 | What changed this week (**optional**) | Free text |
| — | Patient answering directly, patient answering with help, or carer answering for the patient | Reporter mode |

The methodology describes a candidate win-ratio endpoint and a responder definition. Both thresholds are
provisional. When the reporter switches between self-report and proxy, the quiz asks whether to start a
fresh check. Direct and assisted self-report share the patient wording and answers.

## Inputs

| Input | Location | Size | SHA-256 |
|---|---|---|---|
| Reddit corpus | `reddit_2026-06-13.db` (repo root, not in Git) | 2.5 GB | `6641928b5ea4e2971b8018d596ff2cc80f9a55ad98fac687f28e1feb2d5e9c72` |
| Per-author extraction records | `data/full_corpus_2026-07-31/records.csv` (not in Git; see that folder's README) | 45 MB | `056e03735f1a4202be04ea3aae4fbb530f8bc2fc337922ebbfa5549a24ff1fdc` |

The corpus holds 243,289 posts and 3,602,691 comments, dated 2009-10-09 to 2026-06-11, from Long COVID and
ME/CFS subreddits. The largest are r/covidlonghaulers (118,675 posts), r/cfs (87,220) and r/LongCovid (26,615).
It has full-text indexes (`posts_fts`, `comments_fts`) that the scan scripts use.

`records.csv` is used only for its `author_hash`, `functional_status_tier` and `illness_trajectory` columns.
These give each author a severity tier (bedbound … mostly functional) for the activity ladder and the
self-rating-by-severity analysis. Authors with more than one tier are skipped.

## Folder layout

The v0.2 and v0.3 scripts were written during two exploratory sessions and are kept as they ran. Run those
scripts from their own folders. Run the next-version audit from the repository root.

```
baseline_check/
├── README.md
├── v02_analysis/            Session 1 (2026-11-16): evidence for page v0.1–v0.2
│   ├── fts_counts.py        vocabulary and instrument-name counts
│   ├── patterns.py          regex scan for how patients quantify change
│   ├── level_rx.py          strict "N% of my old self" pattern (shared)
│   ├── scan.py              extracts self-ratings and "I can now / I can't" phrases
│   ├── domains.py, domains_v2.py      life domains in improvement vs other posts
│   ├── pct_vs_tier.py       self-rating by severity tier and trajectory
│   ├── milestones.py, ladder.py, ladder_ci.py   activity ladder
│   ├── tradeoff.py          "fine as long as I rest" statements
│   ├── longit.py            repeat self-ratings by the same author (test-retest)
│   ├── sample_change.py     draws the improve/worsen post sample
│   ├── code_llm.py          LLM coding via OpenRouter (mostly failed; see below)
│   ├── analyze_llm.py       analysis of the LLM coding
│   ├── analyze_coded.py     analysis of the 450 agent-coded posts  ← main v0.2 numbers
│   ├── analyze_ex2.py       same analysis on a second copy (coded_ex2/)
│   ├── review_checks.py     keyword split of "what matters most" (the withdrawn 48%)
│   ├── fmt.py, coded/hdr.py helpers the coding agents used to write rows
│   ├── page.js              v0.2 form script
│   ├── quality/             coder agreement: agree.py, rec.py
│   └── coverage/            first coverage test: add.py, analyze_cov.py
├── v03_rechecks/            Session 2 (2026-11-17): rechecks for page v0.3
│   ├── b_matters/           item 1: blind "what matters most" recode
│   ├── c_coverage/          item 4: blind coverage regrade
│   ├── d_checks/            items 2, 3, 5, 6: delay.py and RESULTS.md
│   └── a_instrument/        v0.3 form script (page.js) and jsdom tests (t/)
└── next_version/            aggregate reanalysis, candidate instrument and validation plan
```

Item numbers (1–14) refer to the v0.3 work plan. Items 1–6 were evidence rechecks, items 7–13 were changes
to the questionnaire and item 14 was moving this work into the repo.

## How the work was done

### Session 1 (v0.2)

1. **Vocabulary scan.** Full-text counts of patient terms (crash, PEM, baseline, pacing, spoons) and of
   standard instrument names (`fts_counts.py`). Regex scans for how patients quantify change: percent of
   self, steps, upright time, crash frequency, delays (`patterns.py`).
2. **Corpus-wide extraction** (`scan.py`). It extracts two things from every post and comment by a
   non-deleted author:
   - each strict self-rating ("I'm about 60% of my old self", pattern in `level_rx.py`, with "better",
     "sure", "battery", "oxygen" and similar excluded) → `level.jsonl`;
   - every "I can now …" / "I can't … anymore" phrase → `milestones.jsonl`.

   Authors are stored as SHA-256 hashes.
3. **Post samples** (`sample_change.py`, then an inline snippet). The sampling frame is self-posts of
   400–5,000 characters in r/covidlonghaulers, r/cfs, r/LongCovid, r/LongHaulersRecovery, r/cfsrecovery,
   r/mecfs and r/cfsme.
   - `improve_title`: 300 posts whose title says improved, recover, better, remission, progress or success
     (seed 42).
   - `worsen_title`: 300 posts whose title says worse, relapse, setback, decline or deteriorate.
   - `pct_statement`: 300 texts with a regex self-rating (seed 7).
   - `sample_repro`: 75 + 75 of the change posts, for a two-draw repeatability check.
4. **LLM coding attempt** (`code_llm.py`). The plan was to code the 900-post sample with
   `deepseek/deepseek-v4-flash` via OpenRouter, temperature 0, using the 15-field schema in the script's
   prompt. The OpenRouter key hit its total spending limit after **68 of 900** calls (HTTP 403,
   "Key limit exceeded"). All 300 repeatability calls failed the same way. The 68 coded posts survive in
   `out_all.jsonl` and serve only as a cross-model agreement check.
5. **Agent coding.** Six Claude Sonnet agents each hand-coded 75 posts (450 in all: 150 improve, 150 worsen,
   150 pct) into the same schema plus `questionnaire_gap`. They were told not to call any API or classify with
   scripts. The 450 posts were drawn with seed 11 and include all 68 the LLM coded. They were split into six
   chunks (`chunks/`), and the coded rows are in `coded/chunk_*.jsonl`. `coded_ex2/` is a byte-identical
   copy that `analyze_ex2.py` reads.
6. **Coverage test.** 190 posts were drawn with seed 2026 from self-posts of 300–2,500 characters with no
   question-mark title and some change wording, excluding the samples above. They were stratified 95 severe
   (bedbound, housebound, very severe) and 95 mild/moderate (mild, moderate, back to work, recovered,
   remission). The agent that designed the questionnaire then judged, for each post, whether the weekly
   check would register the change: fully, partly or not, and which questions catch it. Rows were written
   through `coverage/add.py` into `coverage/coded.jsonl`.
7. **Coder agreement.** A second Sonnet pass recoded 40 posts of chunk 0 (`quality/chunk_0_second.jsonl`)
   and 20 of chunk 2 (`quality/chunk_2_recode.jsonl`); `quality/agree.py` compares them field by field.
8. **Self-review.** The session audited its own headline numbers; see
   [Corrections](#corrections-made-along-the-way).

### Session 2 (v0.3)

1. **What matters most** (item 1, `v03_rechecks/b_matters/`). The 242 agent-coded posts that are first-person
   and describe a change were shuffled (seed 42) into three batches of about 81. Each batch went to a fresh
   Sonnet agent that saw only the post text and `CODEBOOK.md`. Twenty posts from batch 0 were also put in
   batch 1, to measure agreement. Each coder picked the one change that mattered most, from 7 categories, and
   gave a verbatim quote. `chk0.py` and `chk1.py` check that every quote really appears in its post.
2. **Blind coverage regrade** (item 4, `v03_rechecks/c_coverage/`). The 157 coverage posts the designer had
   judged usable were split into two batches. Two fresh Sonnet agents, who had not seen the design work,
   judged them with `CODEBOOK.md` (the v0.2 questionnaire is written out in it). They found 114 posts
   describing a change. `analyze.py` compares their judgments with the designer's.
3. **Crash delay** (item 2, `d_checks/delay.py`). This finds sentences where a crash, PEM or flare word
   appears within 80 characters of delay wording, then bins the matches. A hand check read 52 contexts
   drawn from the first 400 retained matches in each bin (`delay_precision_sample.json`).
4. **Instrument names, coder agreement, repeat ratings** (items 3, 5, 6). These re-ran or re-read the
   session 1 scripts; the results are collected in `d_checks/RESULTS.md`.
5. **Questionnaire redesign** (items 7–13, `a_instrument/`). The form was rebuilt with nothing filled in by
   default, the two-day rule on Q2, the new *Within the home* group, tap buttons instead of sliders for Q3
   and Q4, and screen-reader labels. Later, at the study lead's request, Q4 went back to a slider (0–100 in
   steps of 5, unanswered until touched) and every Q2 group gained an "All of these" button, not just the
   first. A review of which questions add value then made Q4 optional (it is the noisiest item and the one
   severe patients use least), shortened the Q2 help to three sentences, told people to tick the shorter
   version of an item when they did the longer one, reworded the "usual responsibilities" item, and renamed
   the trigger "Don't know" to "No clear reason". The current product is tested directly by `t/test.js`.

## Findings and where they come from

Section names in italics are headings on the Methodology and Data page.

| Finding (page section) | Number | Source |
|---|---|---|
| **What matters most** (*What patients say matters most…*) | Specific symptom 43%, trajectory 23%, feeling like yourself 10%, an activity 8%, crashes 8%, unclear 5%, both 2% (n=242) | `v03_rechecks/b_matters/analyze.py` |
| "Feeling like myself" wording anywhere in a post | 30% | same |
| Agreement between the "what matters" coders | 60%, κ 0.46 (20 posts) | same |
| Symptoms held down by doing less (*Why these six questions*) | 17% of change posts | `v02_analysis/analyze_coded.py` |
| Change described with an activity / symptoms / crashes | 58% / 99% / 32% | same |
| Cost of activity / fluctuation mentioned | 33% / 31% | same |
| **Crash delay** (*Crashes are delayed…*) | Candidate matches include next day (3,500 texts), ranges (855), 2 days (691), same day (251) and 4+ days (156). Of 52 audited contexts, 40 described a trigger-to-crash delay (23/28 in the next-day bin). | `v03_rechecks/d_checks/delay.py`, `RESULTS.md` |
| **Instrument names** (*Patients use their own vocabulary…*) | FUNCAP 364, Bell scale 273, Chalder 197, SF-36 89, DePaul 79, PROMIS 27 | `v02_analysis/fts_counts.py` |
| **Coverage** (*Coverage test…*) | Blind raters of v0.2: fully 57%, partly 33%, not 10% (n=114). Designer on the same posts: 69% / 28% / 3%. Agreement 64%, κ 0.29. The paired full-coverage difference was 12.3 points (95% author-cluster interval 2.6–21.9). | `v03_rechecks/c_coverage/analyze.py`, `next_version/audit.py` |
| Share of changes each question helps catch (blind) | Q1 50%, Q2 55%, Q3 88%, Q4 57%, Q5 80% | same |
| Coverage gaps (rough keyword count of the blind rater's notes) | A specific symptom visible only inside Q3's one number (~58% of changes), mental health (~21%), "did it but paid for it" | blind `missing` field; themes in `coverage/themes.py` (local only) |
| **Coder agreement** (*Limitations*) | Sonnet vs DeepSeek, 68 posts: κ 0.61–0.84. Sonnet vs Sonnet, 40 posts: κ 0.54–0.87; current severity weakest at 0.54. Chunk-2 recode, 20 posts: current severity 0.57 | `analyze_coded.py`, `quality/agree.py` |
| **Repeat ratings** (*"Percent of my old self"…*) | 5,919 pattern-derived ratings from 3,099 authors. Pairs 0.5–14 days apart: n=764, r=0.63, 51% identical, SD of change 15.5. Pairs ≥90 days apart: r=0.43. The short pairs were 47% identical with equal author weighting. | `v02_analysis/longit.py`, `next_version/audit.py` |
| Self-rating accuracy of the strict pattern | 62% of matches are true current self-ratings; the value is within 5 points 91% of the time | `analyze_coded.py` (pct sample) |
| Self-rating by severity | Median 10 severe, 84 mild, 95 recovered (small n) | `analyze_coded.py`, `pct_vs_tier.py` |
| **Activity ladder** (*The mild and moderate range…*) | Only about three bands separate: home and self-care, then middle activities, then exercise, full-time work, running | `ladder_ci.py` |

## Corrections made along the way

These are kept here so nobody re-uses a withdrawn number.

| Claimed earlier | Problem | Now |
|---|---|---|
| "% of my old self" appears ~21,000 times from ~8,400 authors | Loose pattern also caught "90% sure", "back to work at 50%" and body-battery readings; only ~40% were real | Strict pattern (`level_rx.py`, ~62% precision): self-ratings in 6.7% of improvement posts vs 0.5% of others |
| Domains "enriched in improvement posts" (`domains.py`) | 44% of improvement posts were questions, and improvement posts are 1.74× longer | Withdrawn. `domains_v2.py` drops question titles; only self-ratings, "baseline" and good/bad days beat the length effect |
| A clean activity ladder | 95% CIs: the bottom eight rungs overlap entirely (tier 2.72–2.94) | Only three bands; Q2 became a checklist, not a ladder |
| Activity and symptoms disagree only 3% of the time | Sample chose posts whose titles announce one direction; the trade-off happens within a person over time | Open question |
| 48% of authors care most about a global state (`review_checks.py`) | A keyword split of a free-text field, not a coding decision | Withdrawn; replaced by the blind recode (10% global) |
| 54% of posts show a "questionnaire gap" | Coders were asked to find a gap, so they found one | Themes kept as a concept list; the percentage dropped |
| Smallest detectable change ~30 points compared with orthopaedic MIDs | The calculation assumes stable patients and repeat measurements of the same item. The regex-derived pairs can include true health changes and matching errors. | Withdrawn as a measurement-error estimate. The observed short-pair SD of change was 15.5 points. |
| Coverage 69% fully captured | Judged by the agent that designed the questions | Blind figure (57%) reported, with both rows |
| 23 quoted milestone phrases | The product mixed coder paraphrases and verbatim patient phrases | v0.3.1 presents thematic summaries |
| Chunk-2 coding | The coder's helper filled skipped fields with "not mentioned"/false | Excluding it moves headlines ≤5 points; 20-post recode in `quality/` |

## Limitations

- **Coders are AI agents.** Every coded field comes from Claude Sonnet agents. Agreement between them is
  moderate (κ 0.29 for coverage, 0.46 for what matters most), so the shares are rough. Human coding is part
  of the validation plan.
- **Reddit is not a trial population.** Authors self-select, skew toward people well enough to post, and
  post when something changes. Severe patients are under-represented.
- **Samples are selected by title wording.** The improve/worsen samples favour stories moving in one clear
  direction.
- **Posts are not weekly reports.** The coverage test asks whether a check *would* register a change
  described in free text, which is a proxy for real responses. It used v0.2, and the blind screen received
  only the 157 posts the designer had already screened in.
- **The data exists only on one machine.** See [Data that is not in Git](#data-that-is-not-in-git).

## Reproducing the results

Requirements:
- The project environment (`uv sync` at the repo root), Python 3.10 or later. The system `python3` on macOS
  is too old for `longit.py` (`statistics.correlation`).
- Node 18 or later for the form tests.
- For the corpus scans, `reddit_2026-06-13.db` at the repo root; for the ladder and severity scripts,
  `data/full_corpus_2026-07-31/records.csv`. Check both hashes in [Inputs](#inputs) first.
- For anything that reads coded data, the local data files described in
  [Data that is not in Git](#data-that-is-not-in-git).
- Form tests read the current product in `docs/baseline_check/` directly.

All commands start from the repo root. None of them call a paid service.

### Next-version audit

```sh
python3 studies/baseline_check/next_version/audit.py reddit_2026-06-13.db
```

Expect `114/157` eligible posts, `Q3 tagged without Q1/Q2: 19.3 [12.4, 26.5]` and `764 pairs, 318 authors`.
See [audit methods and inputs](next_version/README.md#reproduce-the-audit).

### Set up paths for the historical analyses

```sh
REPO=$(git rev-parse --show-toplevel)
DB=$REPO/reddit_2026-06-13.db
CSV=$REPO/data/full_corpus_2026-07-31/records.csv
S=$REPO/studies/baseline_check
```

### v0.3 numbers (seconds each)

```sh
cd $S/v03_rechecks/b_matters && uv run python analyze.py
```
Expect `n=242`, then `symptom 104 43%`, `trajectory 56 23%`, `global 23 10%`, `activity 20 8%`,
`crashes 20 8%`, `global wording anywhere in post: 72 (30%)` and `overlap n=20 agreement 60% kappa 0.46`.

```sh
cd $S/v03_rechecks/c_coverage && uv run python analyze.py ../../v02_analysis/coverage/coded.jsonl
```
Expect `blind judged 157`, `blind: describes change 114`, `BLIND  : fully 57% (65), partly 33% (38), not 10% (11)`,
`FORK same posts: fully 69% (79), …` and `agreement 64%, kappa 0.29`.

```sh
cd $S/v03_rechecks/b_matters && uv run python chk0.py && uv run python chk1.py
```
No `BAD` lines means every quote is verbatim.

```sh
cd "$S/v03_rechecks/a_instrument/t" && npm ci && node test.js
```
Expect 17 `PASS` lines and `17 checks passed`.

### v0.2 numbers (seconds each)

```sh
cd $S/v02_analysis && uv run python longit.py
```
Expect `ratings (author x text): 5919  authors: 3099`, `pairs 0.5-14 days apart: n=764  r=0.63  SD of change=15.5`,
and `pairs >=90 days apart: n=860  r=0.43`. The archived script also prints the withdrawn 30-point estimate.

```sh
cd $S/v02_analysis && uv run python analyze_coded.py
```
Expect `coded: 450 of 450`, `ALL change narratives: n=242`, `restriction explains symptoms 17%`,
`PCT SAMPLE n=150: … 93 (62%)` and the Sonnet-vs-DeepSeek κ table on 68 posts.

```sh
cd $S/v02_analysis/quality && uv run python agree.py ../coded/chunk_0.jsonl chunk_0_second.jsonl
cd $S/v02_analysis/quality && uv run python agree.py ../coded/chunk_2.jsonl chunk_2_recode.jsonl
```
Expect `n=40` with `current_severity 82% kappa=0.54`, then `n=20` with `current_severity 90% kappa=0.57`.

```sh
cd $S/v02_analysis/coverage && uv run python analyze_cov.py
```
Expect `coded 190 usable 157` and `ALL: fully 60% (94), partly 36% (56), not 4% (7)`. These are the
designer's ratings on all 157; the 69% above covers only the 114 the blind rater kept.

### Corpus scans (minutes each; read the 2.5 GB database read-only)

```sh
cd $S/v03_rechecks/d_checks && uv run python delay.py $DB        # item 2; rewrites delay_precision_sample.json (seed 7)
cd $S/v02_analysis && uv run python fts_counts.py $DB             # item 3: FUNCAP 364, Bell 273, Chalder 197, SF-36 89 (posts + comments)
cd $S/v02_analysis && uv run python patterns.py $DB               # writes patterns.json
cd $S/v02_analysis && uv run python domains_v2.py $DB
cd $S/v02_analysis && uv run python tradeoff.py $DB
cd $S/v02_analysis && uv run python pct_vs_tier.py $DB $CSV
```

`fts_counts.py` prints posts and comments separately; the page's figures are their sums.

### Rebuilding the extraction files (slow; overwrites)

```sh
cd $S/v02_analysis && uv run python scan.py $DB      # rewrites level.jsonl and milestones.jsonl
cd $S/v02_analysis && uv run python milestones.py $CSV
cd $S/v02_analysis && uv run python ladder_ci.py $CSV
```

### Do not re-run

These append rows. Re-running them duplicates data:
- the coding-row scripts (`b*.py`, `coded/b*.py`, `quality/c*.py`, `coverage/add.py`);
- `code_llm.py`, which is also a paid call. It skips ids already coded, so a re-run would code the 832
  failed posts and the repeatability draws. Estimate the cost first: the 68 successful calls used about
  77k input and 151k output tokens, so the remaining ~1,130 calls would be roughly 17 times that.

## Script reference

### `v02_analysis/`

| Script | Reads | Writes / prints |
|---|---|---|
| `fts_counts.py DB` | corpus FTS | post and comment counts per concept and instrument name |
| `patterns.py DB` | corpus | `patterns.json`: matches, authors, top captures and 40 sampled contexts per pattern |
| `level_rx.py` | — | defines `LEVEL` (strict self-rating) and `EXCL` (context exclusions); `exec`'d by others |
| `scan.py DB` | corpus | `level.jsonl` (`id`, author hash `a`, `ts`, value `v`, severity words `tiers`, `snip`); `milestones.jsonl` (`a`, `ts`, sign `s` +1 can / −1 can't, phrase `ph`) |
| `domains.py DB` | corpus | domain mention rates, improvement vs other posts (**superseded**) |
| `domains_v2.py DB` | corpus | same, question titles dropped, strict self-rating |
| `pct_vs_tier.py DB CSV` | corpus, records | median self-rating by severity tier and by trajectory |
| `milestones.py CSV` | `milestones.jsonl`, records | top "can now" / "can't" phrases and their share by severity group |
| `ladder.py CSV` | `milestones.jsonl`, records | mean severity tier of authors who can't do each of 20 activities |
| `ladder_ci.py CSV` | same | same with 95% CIs (**use this one**) |
| `tradeoff.py DB` | corpus | counts of "fine as long as I rest", "better because I do less" and similar |
| `longit.py` | `level.jsonl` | rating distribution, severity groups, adjacent same-author pairs and the withdrawn measurement-error estimate |
| `sample_change.py DB` | corpus | `sample_change.json` (300 improve + 300 worsen) |
| `code_llm.py SRC DST [--draws N]` | sample JSON, project LLM config | appends to `DST`; **paid** |
| `analyze_llm.py` | `out_all.jsonl`, `sample_pct.json` | LLM coding summary (68 posts) |
| `analyze_coded.py` | `chunks/`, `coded/`, `sample_pct.json`, `out_all.jsonl` | main v0.2 summary and Sonnet-vs-DeepSeek agreement |
| `analyze_ex2.py` | `coded_ex2/` | same as above |
| `review_checks.py` | `chunks/`, `coded/` | keyword split of `what_matters_most` (**withdrawn 48%**) |
| `fmt.py`, `coded/hdr.py`, `quality/rec.py` | — | defaults and writers the coding agents imported |
| `quality/agree.py A B` | two coded JSONL files | per-field raw agreement and Cohen's κ |
| `coverage/add.py` | stdin, `sample.json` | appends designer ratings to `coded.jsonl` |
| `coverage/analyze_cov.py` | `coverage/coded.jsonl` | designer coverage figures and gap phrases |
| `page.js` | — | v0.2 form behaviour |

### `v03_rechecks/`

| Script | Reads | Writes / prints |
|---|---|---|
| `b_matters/analyze.py` | `meta.json`, `coded_0..2.jsonl` | category shares, global wording, overlap κ |
| `b_matters/chk0.py`, `chk1.py` | `batch_N.txt`, `coded_N.jsonl` | flags quotes not found verbatim or over 25 words |
| `c_coverage/analyze.py OLD` | `blind_0..1.jsonl`, designer `coded.jsonl` | blind vs designer coverage, κ, per-question share, gaps |
| `d_checks/delay.py DB` | corpus FTS | delay bins; `delay_precision_sample.json` for hand checking |
| `a_instrument/t/test.js [DIR]` | Product pages in `docs/baseline_check/` by default | 18 jsdom checks covering form behaviour, scoring and local links |

### Codebooks

- `v03_rechecks/b_matters/CODEBOOK.md`: the 7 "what matters most" categories, `global_wording`, and the
  verbatim-quote rule.
- `v03_rechecks/c_coverage/CODEBOOK.md`: the v0.2 questionnaire written out in full, and the
  fully / partly / not rubric.
- The 15-field post schema is the prompt in `v02_analysis/code_llm.py`; the agents also added
  `questionnaire_gap`.

## Data that is not in Git

Everything below contains or quotes post text, so `.gitignore` excludes it. It exists **only** in the local
copy of this folder (about 24 MB) and has **no backup** yet. Back it up to private S3, for example under
`s3://patientpunk/scientific_validation/baseline_check/`, before deleting anything here.

| Path | Contents |
|---|---|
| `v02_analysis/sample_*.json`, `tiny.json` | sampled post text |
| `v02_analysis/level.jsonl`, `milestones.jsonl`, `patterns.json` | extracted snippets (rebuildable with `scan.py`, `patterns.py`) |
| `v02_analysis/out_all.jsonl`, `out_repro.jsonl`, `tiny_out.jsonl` | LLM coding output (68 good rows) |
| `v02_analysis/chunks/` | the 450 posts given to the coding agents, with sample labels |
| `v02_analysis/coded/`, `coded_ex2/` | agent-coded rows, including quotes |
| `v02_analysis/b*.py`, `coded/b*.py`, `quality/c*.py` | coded rows written as Python, with quotes |
| `v02_analysis/quality/*.jsonl` | second-coder rows |
| `v02_analysis/coverage/sample.json`, `batch_*.txt`, `coded.jsonl`, `themes.py` | coverage posts, designer ratings, gap themes with quotes |
| `v03_rechecks/b_matters/batch_*.txt`, `coded_*.jsonl`, `meta.json`, `results.txt` | what-matters posts, coded rows, batch ids |
| `v03_rechecks/c_coverage/batch_*.txt`, `blind_*.jsonl`, `results.txt` | coverage posts and blind ratings |
| `v03_rechecks/d_checks/delay_precision_sample.json` | delay match contexts |
| `v03_rechecks/index_v02_backup.html`, `index_v03_single_page.html`, `a_instrument/*.html` | earlier page versions (v0.2; v0.3 before the three-page split) and drafts |

The scripts that build the samples and batches ran as inline snippets. Their logic and seeds are recorded in
[How the work was done](#how-the-work-was-done).

## Cost

- OpenRouter (`deepseek/deepseek-v4-flash`): 68 successful calls, about 77k input and 151k output tokens,
  a matter of cents. The remaining calls failed at the key's spending limit.
- Coding agents and the two web-research agents ran inside Claude Code sessions, with no separate API
  billing.
- The scripts in this folder are free to run, except `code_llm.py`.

## Next version

The blind raters expected Q3 to register a change in 22 of 114 v0.2 stories where they tagged neither Q1
nor Q2. The [design plan](next_version/README.md) keeps overall symptom severity in the core and tests a separate
patient-priority symptom item. It also tests dated seven-day activity windows and distinguishes activity cost,
health limitations and opportunity. The pilot compares the outcomes separately and tests whether patients
endorse the trade-offs made by the crash-first endpoint before proposing it as a trial primary.
