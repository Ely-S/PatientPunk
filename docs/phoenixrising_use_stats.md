# Phoenix Rising — real-world USE data for the FDA comment (Section 6 & 7)

**Source:** Phoenix Rising ME/CFS Forums (forums.phoenixrising.me), 276 drug-focused
threads discovered via the public sitemap, scraped 2026-06-09.
**Corpus:** 5,081 posts/comments from 703 unique participants, spanning **2009–2026**.
**Method:** robots.txt-compliant scrape (on-site `/search/` not used); usernames
SHA-256 hashed before storage. Counts below are **substring/alias matches** (word-boundary,
case-insensitive) over post text — they characterize **off-label USE and UNMET NEED, not efficacy.**

> Framing note (per the comment's own Section 6 guidance): these figures answer FDA's
> Question 4 on *how to collect/characterize data about unapproved community use*. They
> are **not** a substitute for controlled effectiveness data. The "% positive/negative"
> patient-experience numbers come from the separate LLM classification step (pending).

---

## Headline numbers

| | Low-dose naltrexone (LDN) | Pyridostigmine / Mestinon |
|---|---|---|
| Posts directly mentioning the drug | **2,447** | **333** |
| Unique participants discussing it | **514** | **106** |
| Discussion span | 2009 → 2025 | 2011 → 2026 |
| Posts citing an explicit mg dose | 804 (1,649 dose figures) | 101 (197 dose figures) |
| Most-cited doses | 4.5mg, 1.5mg, 1mg, 3mg, 0.5mg (73% of dose figures ≤4.5mg) | 30mg, 60mg, 120mg, 180mg |

**Dosing corroborates the off-label pattern.** For naltrexone, **73% of all dose figures
are ≤4.5 mg** — the characteristic low-dose range — with a modal 4.5 mg and a clear
titration ladder (0.5 → 1 → 1.5 → 3 → 4.5 mg). The standard 50 mg dose appears mainly as
the *reference* point ("LDN is ~1/10th of the 50 mg dose"). This confirms the community use
in question is specifically **low-dose**, distinct from the approved 50 mg indication.
Mestinon clusters at the expected 30–60 mg (up to 180 mg/day), matching the LIFT-trial
titration described in the comment.

## Barriers (among posts that directly mention each drug)

| Barrier theme | LDN posts | Mestinon posts |
|---|---|---|
| Sourcing / compounding (where to get it, compounded liquid, no-prescription routes) | 166 | 8 |
| Cost / insurance (affordability, price, coverage) | 175 | 14 |
| Prescriber reluctance / access (off-label, "won't prescribe", "convince my doctor") | 28 | 5 |

These directly support **Section 7** (the absence of an approved low-dose formulation forces
reliance on compounded LDN; off-label status drives access friction) — quantified from
patient voices rather than asserted.

---

## Draft text for Section 6 (USE / dosing / barriers — paste-ready)

> To characterize real-world community use, we analyzed patient discussion on the Phoenix
> Rising ME/CFS forum, a long-running patient community. Across 276 treatment-focused
> threads spanning 2009–2026 (5,081 posts from 703 participants), low-dose naltrexone was
> discussed in **2,447 posts by 514 distinct participants**, and pyridostigmine (Mestinon)
> in **333 posts by 106 participants** — a sustained, high-volume off-label conversation
> maintained over more than a decade in the absence of any approved therapy.
>
> Self-reported dosing matched the off-label regimens precisely: naltrexone use clustered in
> the low-dose range (73% of cited doses ≤4.5 mg, with a characteristic 0.5→4.5 mg titration
> ladder), and pyridostigmine at 30–180 mg/day — the same ranges under study in the LIFT
> trial. Patients also described concrete access barriers: sourcing and compounding of LDN
> (166 posts), cost and insurance coverage (175 posts), and prescriber reluctance tied to
> off-label status (28 posts) — corroborating the formulation and incentive gaps discussed
> in Section 7.
>
> Patient-reported outcomes were summarized by classifying **every** LDN and pyridostigmine
> post for sentiment (a full census of 2,447 and 333 posts, not a sample). Among the 46% of
> LDN posts and 38% of pyridostigmine posts that described a personal experience, **38% of LDN
> reports (95% CI 35–41%) and 42% of pyridostigmine reports (95% CI 34–50%) were positive, and
> 63% and 61% respectively were positive-or-mixed** — i.e., a clear majority reported at least
> some benefit, even on a forum that skews toward the most severe and treatment-refractory
> patients. Both drugs also drew substantial negative / dose-sensitivity reports (~37–39%
> negative), and patients catalogued consistent side-effect profiles (LDN: insomnia by far,
> then fatigue, anxiety, sleep disturbance, vivid dreams; pyridostigmine: GI/cramping,
> breathlessness, nausea, chills). This real-world signal is **more mixed than uncritical
> enthusiasm would suggest** — a substantial responder subset alongside a meaningful
> non-responder/non-tolerator group — which is itself the argument for the controlled LIFT
> trial to identify *who* benefits. (The automated classification was validated against a
> 400-post hand-labeled subset: 90% agreement on positive-vs-not, 93% on any-benefit-vs-not.)

## Methods & limitations note (paste-ready)

> **Method.** Threads were identified from the forum's public sitemap by drug name and
> scraped in compliance with the site's robots.txt; usernames were cryptographically hashed.
> Drug mentions were identified by validated alias matching; the dosing and barrier figures
> are automated text counts.
>
> **Limitations.** This is a single, self-selected patient community; diagnoses are
> self-reported and unverified; people with strong experiences (good or bad) are likelier to
> post; and discussion volume reflects interest and access, not effectiveness. We present
> these data as a measure of the scale and texture of real-world off-label use and unmet
> need — explicitly **not** as evidence of efficacy, which only the controlled trials
> (Section 3–5) can establish.

---

## Sentiment classification — RESULTS (full census, in-session, no API)

**Method.** Threads were discovered two ways: (1) the forum sitemap, by drug name in the
thread *title* (276 threads), and (2) external site-scoped web search, which surfaces threads
that mention the drugs in the *body* but not the title (+17 threads). **Every** direct-mention
post across all 293 threads was then classified (full census, not a sample) against the rubric
in `docs/ldn_notes.md` (positive / negative / mixed / neutral + signal + side effects), via
fan-out annotator agents. Per-post labels: `outputs/manual/full/labels_*.json`;
summary: `outputs/manual/census_summary.json`.
**Validation:** on the 400 posts also hand-labeled by the lead annotator, agreement was
**84% exact (4-class), 90% positive-vs-not, 93% any-benefit-vs-not.**

| | Low-dose naltrexone (LDN) | Pyridostigmine / Mestinon |
|---|---|---|
| Posts classified (full census) | 2,493 | 386 |
| Expressed a personal experience | 1,140 (46%) | 148 (38%) |
| **Positive** (of experiential) | **38%**  (95% CI 35–41%) | **43%**  (95% CI 35–51%) |
| Mixed | 25% | 18% |
| Negative | 37% | 40% |
| **Positive-or-mixed (some benefit)** | **63%** | **60%** |
| Top side effects | insomnia (119), fatigue (45), anxiety (36), nausea (32), headache (32), vivid dreams (25), depression (25) | muscle twitching (8), chills (6), shortness of breath (6), respiratory depression (6), nausea (6) |
| Posts flagging 50 mg / full-dose (kept, not excluded) | 146 | 5 |

**Caveats specific to this classification (state these in the comment):**
- Full census (not a sample) — 95% CIs are tight (±3 pts for LDN; ±8 for the smaller Mestinon
  set). Single automated pass, validated against 400 hand-labels (above); not multi-rater/adjudicated.
- The naltrexone alias set includes the rare full-dose (50 mg) mention; the corpus is
  overwhelmingly low-dose (73% of cited doses ≤4.5 mg).
- A cluster of LDN negatives traces to **one** severe-reaction case (several posts by one
  caregiver), so entry-level counts slightly overweight it; a user-level tally would temper it.
- A few reports are secondhand (a member describing a relative).
- Sentiment ≠ efficacy: people with strong experiences (good or bad) are likelier to post.

**To re-run the classification** (all 2,493 / 386 posts) later via LLM, set `ANTHROPIC_API_KEY`
(needs billing credit) or a local/free model, then:
```
.venv/bin/python src/run_sentiment_pipeline.py --db data/phoenixrising.db \
    --output-dir outputs/naltrexone --drug-file drugs/naltrexone.txt --workers 4
.venv/bin/python src/run_sentiment_pipeline.py --db data/phoenixrising.db \
    --output-dir outputs/pyridostigmine --drug-file drugs/pyridostigmine.txt --workers 4
```

---

## Broader-recall expansion (beyond thread titles)

Title-based discovery (276 threads) was supplemented with **external site-scoped web search**
to catch threads that discuss the drugs in the *body* but not the title — e.g. "recovery
story" / "what treatments helped" / "treatments to explore" / dysautonomia threads, plus one
**misspelled-title** thread ("Mestonin") the alias filter could never have matched. This added
**17 threads / 770 posts**, yielding **+46 LDN and +53 Mestinon** new direct mentions.

**Combined corpus: 293 threads** — LDN **2,493 posts / 529 participants**; pyridostigmine
**386 posts / 119 participants** (2009–2026).

**Robustness:** folding in these non-titled mentions left the sentiment split essentially
unchanged (LDN 38% positive; pyridostigmine 42→43%; both ~60–63% positive-or-mixed) — i.e. the
title-based core was **not** a biased sample. Caveat: external search is not exhaustive (it
surfaces well-indexed body mentions, not every scattered one); a complete forum-wide census
would require crawling all ~55k threads, so treat these as a floor.
