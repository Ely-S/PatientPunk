# 7,8-DHF (tropoflavin) — r/Nootropics analysis notes

Working notes. Numbers here are reproducible from the scripts in this directory.

**Why r/Nootropics and not the patient subreddits:** across all nine patient communities
(1.35M ME/CFS + 2.49M Long COVID items) this compound has **33 mentions from 13 authors**, of whom
4 describe taking it — unstudiable. r/Nootropics has **1,792 mentions from ~750 authors**. See
`studies/tropoflavin/` for the patient-side case series and why it was abandoned.

**Population caveat, applies to everything below:** r/Nootropics is a *healthy-user* population
experimenting with cognitive enhancement. It can answer dose, route, tolerability, subjective
effect and the 7,8-DHF vs 4'-DMA distinction. It cannot answer patient outcomes.

**Comparator extension:** `comparator_cohort.json` defines one target, eight
mechanistically tiered comparators, and one adjacent-market control. Every compound is
run over one shared r/Nootropics source population with identical classifier settings.
The parent matcher excludes spans that belong only to 4'-DMA-7,8-DHF. Comparisons use
one most-recent vote per author and compound, with matched-author results retained as a
sensitivity analysis. These are self-reporting-pattern comparisons, not comparative
efficacy or safety estimates.

**Completed comparator run (2026-08-31):** the private corpus contains 560,443
thread-context items, while the committed `comparator_analysis.md` contains aggregates
only. Every configured cohort had usable reports, from 159 reports and 88 authors for
4'-DMA-7,8-DHF to 10,459 reports and 5,215 authors for lion's mane. The target had
653 reports from 279 authors.

At the one-vote-per-author level, 7,8-DHF was 71.3% positive. The parent did not differ
after FDR correction from 4'-DMA-7,8-DHF (73.9%), Semax (66.8%), Cerebrolysin (68.0%),
Selank (67.6%), Dihexa (62.5%), 9-MBC (71.8%), or the BPC-157 control (68.2%). It was
more positive than NSI-189 (59.7%, BH q=0.0022) and lion's mane (59.6%, BH q=0.0008).
Matched-author overlap was sparse and did not provide robust multiplicity-adjusted
corroboration, so the independent results remain reporting-pattern differences rather
than comparative treatment effects.

The leading parent-specific safety signals were insomnia or sleep disruption (31
authors), cognitive or perceptual disturbance (20), activation or irritability (17),
anxiety or panic (17), and headache or migraine (15). For 4'-DMA-7,8-DHF they were
insomnia or sleep disruption (7), anxiety or panic (5), cognitive or perceptual
disturbance (5), activation or irritability (4), and headache or migraine (3). These
are author-deduplicated reporting counts, not adverse-event incidence. The linked
outcome data contained general-fatigue targets but no explicit PEM-targeted rows.

The author-level cross-report join adds side-effect reporting percentages to each dose
and route bucket. For plain 7,8-DHF, any-side-effect reporting was 33.3% (3/9) at
10 to <25 mg, 38.5% (10/26) at 25 to <50 mg, 53.8% (7/13) at 50 to <100 mg, and
50.0% (3/6) at >=100 mg. Oral-mucosal reports were 40.6% (13/32), nasal-mucosal
28.6% (2/7), swallowed-oral 20.0% (1/5), and dermal 50.0% (1/2). The derivative
was 28.6% (2/7) at 5 to <10 mg and 14.3% (2/14) at 10 to <25 mg; its route strata
were 31.2% (5/16) oral mucosal and 40.0% (2/5) swallowed oral. Very small cells,
incomplete classifier coverage, repeated authors across buckets, and the lack of an
administration-event link make these descriptive signal checks only. They do not show
a credible dose-response or route effect.

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

Pipeline A contains 661 reports from 301 users. Side effects were explicit in 137
reports from 93 users (30.9% of Pipeline A users), producing 216 mentions. That is
a reporting proportion, not adverse-event incidence.

Canonical safety domains, deduplicated by user:

| domain | users | mentions |
|---|---:|---:|
| activation or anxiety | 30 | 48 |
| neurologic or cognitive/perceptual | 30 | 52 |
| sleep | 28 | 37 |
| mood | 8 | 13 |
| cardiovascular or autonomic | 6 | 9 |
| fatigue or sedation | 6 | 12 |
| appetite or weight | 5 | 10 |
| hair or skin | 5 | 12 |

The leading canonical terms are insomnia or sleep disruption (28 users),
cognitive or perceptual disturbance (20), activation or irritability (17),
anxiety or panic (14), and headache or migraine (10). Hair loss or thinning is
reported by five users across 12 mentions. Pipeline A can blend the parent and
derivative and includes context-inherited mentions, so these signals are not
compound-specific and cannot be joined causally to a reported dose or route.

### Combined database and proposed-study analysis

`build_combined_db.py` copies the completed Pipeline A database through SQLite's
backup API and imports the complete Pipeline B run. The source database remains
unchanged. The versioned artifact contains 661 Pipeline A reports, 752 Pipeline B
records, 643 linked dosage pairs, 231 linked route pairs, 1,482 treatment-outcome
entries, 202 target author-compound exposures, and 216 canonicalized side-effect
mentions.

The key study-design table is `pipeline_b_compound_exposures`, one row per author
and compound. It keeps dose bands, route families, conservative outcome, and
explicit desired-result buckets together. It does not claim that separately
reported dose and route observations describe the same administration event.
Only 13 parent and seven derivative rows have one dose and one route observation;
11 additional rows have both but ambiguous pairing.

Observed quantitative doses use common cross-compound bands:

| compound | <5 mg | 5 to <10 | 10 to <25 | 25 to <50 | 50 to <100 | >=100 |
|---|---:|---:|---:|---:|---:|---:|
| 7,8-DHF entries | 3 | 1 | 11 | 27 | 13 | 6 |
| 4'-DMA entries | 3 | 7 | 14 | 2 | 1 | 0 |

The parent distribution centers on 25 to <50 mg, while the derivative centers on
10 to <25 mg. This is descriptive only. Sparse outcome-linked cells do not show a
credible monotonic dose-response.

Route families preserve the distinction relevant to exposure. Sublingual is
stored as oral mucosal, not pooled with swallowed oral. Parent reports include 32
oral-mucosal, seven nasal-mucosal, five swallowed-oral, and two dermal entries.
The derivative has 16 oral-mucosal and five swallowed-oral entries. Outcome-linked
route cells are small and selected; they are useful for choosing measurements,
not for asserting route efficacy.

Explicit desired-result domains most often support mood/depression,
focus/attention, energy/motivation, cognition, and sleep measurement. Sleep is
bidirectional: it is an outcome target but also the leading canonical safety
signal, particularly for 4'-DMA reports. The generated
`study_design_analysis.md` contains exact author-level counts and Wilson intervals.

No human interventional study was identified in ClinicalTrials.gov or PubMed in
the 2026-08-27 search. Directly relevant evidence remains preclinical or in vitro,
including poor Caco-2 transport (PMID 31384856), in-vitro CYP inhibition (PMID
31731555), and mouse work on both compounds (PMID 23446639). The community data
can inform endpoint selection and safety surveillance, but not a human starting
dose.

## 6. Open work

**Validate the new analysis buckets against a blinded sample.** The dose boundaries
are deterministic, but the desired-result and side-effect domains are regex-based.
Before protocol use, manually review a stratified sample and report precision by
domain.

**Add an administration-event identifier in a future extraction schema.** The
current author-compound exposure table can say that dose and route were both
reported, but it cannot prove they belong to the same administration event.

**Compound-specific safety signals are now available.** The comparator pipeline binds
each report and side effect to one treatment ID, and enclosing-compound exclusions keep
the parent out of derivative-only spans. The output remains signal generation, not a
comparative adverse-event rate.

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
