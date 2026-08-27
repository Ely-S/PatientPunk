# 7,8-DHF (tropoflavin) — r/Nootropics analysis notes

Working notes. Numbers here are reproducible from the scripts in this directory.

**Why r/Nootropics and not the patient subreddits:** across all nine patient communities
(1.35M ME/CFS + 2.49M Long COVID items) this compound has **33 mentions from 13 authors**, of whom
4 describe taking it — unstudiable. r/Nootropics has **1,792 mentions from ~750 authors**. See
`studies/tropoflavin/` for the patient-side case series and why it was abandoned.

**Population caveat, applies to everything below:** r/Nootropics is a *healthy-user* population
experimenting with cognitive enhancement. It can answer dose, route, tolerability, subjective
effect and the 7,8-DHF vs 4'-DMA distinction. It cannot answer patient outcomes.

---

## 1. Data

| | |
|---|---|
| Comments | `PatientPunk_data/r_nootropics_comments.jsonl` — 1,827,221 lines, 2009-09-25 → 2026-08-18 |
| Posts | `OneDrive/Documents/r_nootropics_posts.jsonl` — 184,321 lines, → 2026-08-17 |
| S3 | `s3://patientpunk/raw_data/arctic_shift_ndjson/r_nootropics_{comments,posts}.jsonl` |

An earlier comments download was **truncated at 2019-05-02** — it looked healthy (no month gaps,
last line parsed) but was missing 7¼ years. Always check the max timestamp, not the file size.

### Rebuild the corpus

```bash
python studies/tropoflavin_nootropics/build_corpus.py     # → source/subreddit_posts.json
python studies/tropoflavin_nootropics/build_corpus_B.py   # → source_B/users/*.json
```

`build_corpus.py` selects every thread containing a mention (posts **and** comments), then pulls
those threads whole so reply context survives. Result: 1,047 posts + 44,620 comments = **45,667
items**, 99.9% parent-chain survival, 13,568 distinct authors.

---

## 2. How to sample

### The match pattern

```python
PAT = re.compile(r"(?i)(tropoflavin|hydroxyflavone|\b7[ .,'-]{0,2}8[ .,'-]{0,2}dhf\b|\bdhf\b)")
PRE = (b"dhf", b"flavon", b"tropoflav")   # cheap bytes prefilter before json.loads
```

Two-stage: bytes prefilter on the raw line, then regex on the parsed body. The prefilter is what
makes a 2.2 GB scan take seconds instead of minutes.

**Three traps, all of which have bitten this project:**

- **Match body text only.** Reddit base36 ids contain strings like `i78dhf6`; scanning the raw
  JSON line counts them as mentions.
- **`\bdhf\b` misses `7,8DHF`** (preceded by a digit, so no word boundary). Hence the numeric
  alternation. Variants seen in the wild: `7,8-DHF`, `7.8DHF`, `7 8 dhf`, `78dhf`, `4DMA-7,8DHF`.
- **FTS5 undercounts.** An OR-query on `dhf OR tropoflavin OR dihydroxyflavone` misses `7.8DHF`
  because the tokenizer never produces a bare `dhf` token. Use FTS to narrow, regex to confirm.

### Sampling for reading

```bash
python studies/tropoflavin_nootropics/sample_quotes.py     # first-person intent statements
```

Filters to items containing a mention **and** a first-person intent phrase (`i take`, `i tried`,
`helps my`, …), 80–400 chars, deduped on the first 60 chars, `random.seed(7)` for reproducibility.
Change the seed to draw a different sample.

---

## 3. What people use it for

`python studies/tropoflavin_nootropics/analyze_purpose.py`

Keyword context across all **1,792** mentioning items. An item can match several rows.

| Stated context | items | share |
|---|---|---|
| neurogenesis / BDNF / "rewiring" | 449 | **25.1%** |
| depression / mood | 297 | 16.6% |
| focus / cognition / brain fog | 279 | 15.6% |
| sleep | 170 | 9.5% |
| memory / learning | 163 | 9.1% |
| anxiety | 123 | 6.9% |
| ADHD | 116 | 6.5% |
| neuroprotection / repair | 91 | 5.1% |
| stimulant recovery / tolerance | 76 | 4.2% |
| Alzheimer's / dementia | 62 | 3.5% |
| exercise mimetic / fat loss | 56 | 3.1% |
| drug damage (PSSD / PFS / HPPD) | 43 | 2.4% |
| libido / sexual | 15 | 0.8% |
| neuropathy / nerve / tinnitus | 11 | 0.6% |
| autism / Rett | 11 | 0.6% |
| TBI / concussion | 9 | 0.5% |

**The dominant frame is mechanism, not symptom.** A quarter of mentions invoke BDNF/TrkB/
neurogenesis directly — more than any actual complaint. People reach for it *because it raises
BDNF*, then decide what that should be good for. Opposite of the patient subreddits, where the
symptom comes first and the mechanism vocabulary is rare.

### Co-mentioned substances

| | items | share |
|---|---|---|
| **4'-DMA-7,8-DHF (eutropoflavin)** | 594 | **33.1%** |
| noopept | 155 | 8.6% |
| semax | 149 | 8.3% |
| racetams | 129 | 7.2% |
| NSI-189 | 117 | 6.5% |
| lion's mane | 111 | 6.2% |
| dihexa / bromantane | 81 each | 4.5% |

**One third of mentions co-occur with the 4'-DMA derivative** — by far the top co-mention. The
community treats them as a pair and consistently reports the derivative as stronger. This is the
single biggest analysis hazard here (§5).

### Practical convention

Bioavailability is the recurring theme: sublingual dosing, insufflation, and a "refined"
Nootropics Depot version all appear as workarounds for poor oral absorption. Independently
matches the r/cfs account (~1 mg sublingual, capsules "much weaker").

---

## 4. Sentiment

### Pipeline A — drug sentiment ✅ done

```bash
export LLM_MAX_TOKENS=16000
uv run python src/run_sentiment_pipeline.py \
  --db studies/tropoflavin_nootropics/noots.db \
  --output-dir studies/tropoflavin_nootropics/outputs_A \
  --drug-file studies/tropoflavin_nootropics/aliases_78dhf.txt \
  --subreddit Nootropics --workers 12
```

4,603 pairs (1,653 direct + 2,950 context-inherited) → prefilter kept 988 → **661 records from
301 distinct users**.

One vote per user (most recent, ties broken by signal strength — the rule in
`studies/rct_validation/scripts/dump_per_drug_csvs.py`):

| | n | share |
|---|---|---|
| positive | 214 | **71.1%** (95% Wilson 65.7–75.9) |
| negative | 77 | 25.6% |
| mixed | 5 | 1.7% |
| neutral | 5 | 1.7% |

Read the level with the documented ~10–20% positive over-call in mind; the negative rate is the
more trustworthy number. `LLM_MAX_TOKENS=16000` is required — deepseek-v4-flash bills thinking
tokens against `max_tokens` and truncates without it.

### Pipeline B — variable extraction ✅ done

**`--drug` does not exist in pipeline B.** Its unit is the patient, not the drug, so targeting
means feeding it a pre-filtered corpus — `build_corpus_B.py` writes one `users/<hash>.json` per
author who named the compound (**752 authors**, 8,822 texts).

```bash
cd variable_extraction
uv run python main.py run --schema schemas/nootropics_schema.json \
  --input-dir ../studies/tropoflavin_nootropics/source_B --workers 12
```

`schemas/nootropics_schema.json` was created for this — the CLH schema is Long-COVID-specific
(`_target_subreddit: r/covidlonghaulers`, extensions for infection count and long-covid duration).
It keeps all 25 base clinical fields and drops those extensions.

**Do not point B at `subreddit_posts.json`.** `Corpus._texts_from_post` reads title+body only and
deliberately excludes comments ("other users' text"). It would run cleanly, produce 1,047
post-author records, and silently drop 81% of the signal — only 345 of the 1,792 mentions are in
posts. Commenters reach the extractor only via `users/`.

The historical output was `source_B/records.csv`, one row per author. On the
#142/#141 stack, dosage and administration route use explicit treatment-value
pairs and export both raw and decomposed columns. Relevant columns include
`medications`, `dosage`, `dosage_treatment`, `dosage_value`,
`administration_route`, `administration_route_treatment`,
`administration_route_value`, `treatment_outcome`, and `conditions`.

Example of the linked contract:

```
medications:        7,8 dhf | polygala tenuifolia
dosage:             7,8 dhf: 5 grams | polygala tenuifolia: 2 grams
dosage_treatment:   7,8 dhf | polygala tenuifolia
dosage_value:       5 grams | 2 grams
administration_route:             7,8 dhf: sublingual
administration_route_treatment:   7,8 dhf
administration_route_value:       sublingual
treatment_outcome:  polygala tenuifolia: helped: alcohol craving | 7,8 dhf: no_effect
```

The extractor omits an unlinked value rather than assigning it by list position or
proximity. It also does not infer a route from a treatment's usual form.

**B splits `4dma` from `7,8 dhf` into separate outcome entries. A structurally cannot** — its
alias regex matches `7,8-DHF` inside `4'-DMA-7,8-DHF` with word boundaries intact on both sides.

**Current linked-field run:** 752 records, 2,090 field fills (2.78/record),
44 minutes including a two-record high-budget repair. Group attribution was
enabled, reasoning was off, and a fresh cache was used. Fill rates:

| field | filled | field | filled |
|---|---|---|---|
| medications | 58.6% | cognitive_neurological | 18.4% |
| treatment_outcome | 41.2% | administration_route | 15.8% |
| dosage | 27.0% | other_symptoms | 12.6% |
| mental_health | 23.5% | sleep | 10.5% |
| conditions | 17.2% | alternative_treatments | 7.8% |

`python studies/tropoflavin_nootropics/analyze_B.py`

### The two compounds, separated

| outcome | 7,8-DHF | 4'-DMA-7,8-DHF |
|---|---|---|
| helped | **60.2%** | **64.2%** |
| worsened | 20.5% | 24.2% |
| no_effect | **14.3%** | **5.0%** |
| mixed / unknown | 5.0% | 6.7% |
| *entries / authors* | *161 / 94* | *120 / 75* |

Reported targets for both: mood, focus, anxiety, depression, sleep, energy, memory.

The derivative is reported as helping somewhat more often and as inert less
often. That comparison is descriptive, not causal: authors self-select compounds,
20 authors appear in both groups, and the matched subset does not reproduce the
no-effect difference.

### A vs B — the contamination is measurable

Pipeline A returned **71.1% positive** over both compounds blended. The current
group-guarded B split puts plain 7,8-DHF at 60.2% helped and 4'-DMA at 64.2%.
The regimes are not directly comparable, but B remains the only valid source for
per-compound claims because A's alias matches inside `4'-DMA-7,8-DHF`.

---

## 5. Follow-up results

`python studies/tropoflavin_nootropics/analyze_followups.py`

### no_effect gap - selection-sensitive

Author-level (one vote per author per compound; multi-entry authors collapse to their most
informative outcome, ranked worsened > no_effect > mixed > helped).

| | 7,8-DHF | 4'-DMA |
|---|---|---|
| **no_effect** | 21/94 = 22.3% | 5/75 = 6.7% |
| helped | 46/94 = 48.9% | 40/75 = 53.3% |
| worsened | 20/94 = 21.3% | 23/75 = 30.7% |

A full-sample Fisher test is invalid because 20 authors appear in both groups.
Among those matched authors, no-effect totals are 5/20 versus 4/20; the discordant
reports are 4 parent-only versus 3 derivative-only (exact McNemar p=1.0). Among
mutually exclusive authors, the
rates are 16/74 versus 1/55 (OR 14.9, Fisher p=0.001). The gap is therefore
strong between self-selected populations but absent within the small matched
subset. It should not be interpreted as evidence that the derivative works better.

### sentiment by use-case — artifact, do not report as a finding

| use-case | users | pos % | BH q |
|---|---|---|---|
| depression / mood | 96 | 88.5% | <0.001 |
| focus / cognition | 95 | 87.4% | <0.001 |
| memory / learning | 43 | 83.7% | 0.148 |
| anxiety | 53 | 79.2% | 0.234 |
| neurogenesis / BDNF | 74 | 78.4% | 0.209 |
| sleep | 69 | 71.0% | 1.000 |
| baseline (all) | 301 | 71.1% | — |

Two categories clear FDR at ~17 points above baseline, and it is almost certainly spurious:
**every category sits at or above baseline, none below.** Neutral slices would straddle it. The
categories are keyword-derived from the same text the classifier read, and positive reports name
what improved ("helped my depression" fires both) while nulls say "did nothing" and name no
domain — so the categorisation excludes nulls by construction and every domain inherits an upward
bias.

**The uncontaminated comparison is category vs category, not vs baseline.** depression/mood 88.5%
vs sleep 71.0% is the one to run; sleep is a partial control because insomnia is also the top side
effect, so it is not purely outcome-naming.

### side effects

137/661 records (20.7%) carry them — 216 mentions, 135 distinct terms.

| term | n | related |
|---|---|---|
| insomnia | 14 | sleep issues 3, sleep disruption 3 |
| headache(s) | 10 | |
| **hair loss** | 7 | hair thinning 3 → **10** |
| irritability | 7 | restlessness 3, overstimulated 3 |
| anxiety | 7 | |
| appetite suppression | 6 | lowered appetite 2 → 8 |

**Overstimulation cluster** (insomnia, irritability, restlessness, anxiety, appetite suppression)
is coherent and matches both the "similar to modafinil" framing here and the r/cfs report of
stimulation persisting into the evening.

**Hair loss is the unexpected signal** — third most common, not an obvious consequence of TrkB
agonism, and specific enough that people would not report it casually. Whether it attributes to
7,8-DHF or to a co-stacked substance is exactly what group attribution makes hard. Checkable.

**135 terms for 216 mentions = heavy fragmentation.** Every count above understates: run the
side-effect vocabulary through canonicalisation before quoting any of it.

## 6. Open work

**Sentiment by use-case — the next analysis.** §3 gives the purpose split, §4 gives per-user
sentiment; joining them answers the question worth asking: *does it fare better for mood than for
cognition?* Join on `post_id` → `treatment_reports.post_id`, tag each record with its purpose
categories from `analyze_purpose.py`, then compare positive rates. Expect small cells for the
tail categories — pool or drop anything under ~30 users rather than reporting it.

**Re-run sentiment-by-use-case as category vs category.** The baseline comparison in §5 is
confounded; see the note there for why and which pairing to use.

**Canonicalise the side-effect vocabulary** before quoting counts, and test whether hair loss
attributes to 7,8-DHF or to co-stacked substances.

**Treatment-linked dose and route extraction is now complete.** For plain
7,8-DHF, 61 quantitative mass-dose entries from 46 authors have an author-level
median of 27.5 mg (IQR 25-50); the most common amounts are 25 mg (20 entries) and
50 mg (12). For 4'-DMA, 27 entries from 23 authors have a median of 10 mg (IQR
8-10); 10 mg (10 entries) and 8 mg (6) dominate. Seven non-mass or invalid values
are retained in the audit count but excluded from dose summaries.

Explicit administration routes are mostly sublingual: 32/46 route entries for
7,8-DHF and 16/21 for 4'-DMA. Plain 7,8-DHF also has intranasal (7), oral (5), and
topical (2) reports; the derivative has five oral reports. These are descriptive
self-reports, not dosing recommendations.

**Null reports are real and countable now.** *"I tried both tropoflavin and eutropoflavin. Both
sublingually. Both inert no matter the dose."* B puts numbers on this: 14.3% of the parent
compound's entry-level outcomes and 22.3% of its author-level outcomes are `no_effect`. The
patient corpus was too small to show nulls; this one isn't.

**Cross-reference to the patient corpora.** The compound entered ME/CFS discourse in 2021 with
zero prior mentions, while r/Nootropics peaked in 2014. The dose and route conventions patients
quote were established here years earlier — worth tracing which specific claims propagated.

## Caveats

- Mention counts are not outcomes; §3 is keyword co-occurrence within an item, not attribution.
- Group attribution: many mentions sit inside long stacks (one item is a 12-supplement "COVID
  stack"). Run the monotherapy sensitivity check before quoting any rate.
- Healthy-user population — see the header.
- Positive sentiment is over-called ~10–20% on this pipeline; negatives are reliable.
