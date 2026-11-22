# Baseline Check next-version design and validation

Baseline Check is being developed as a short weekly measure for Long COVID and ME/CFS studies. The next version
will test time spent in a crash or flare, everyday activity and its consequences, and symptom severity as
distinct outcomes. The first use is exploratory follow-up across illness severities. Selection
of a primary trial endpoint and a responder threshold depends on patient and trial data.
[FDA guidance on fit-for-purpose clinical outcome assessments](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/patient-focused-drug-development-selecting-developing-or-modifying-fit-purpose-clinical-outcome)

## What the existing data can tell us

`audit.py` reanalyses the archived v0.2-form ratings and the regex-extracted percent-self statements. Of 190
sampled coverage posts, the designer screened in 157. The blind raters screened in 114 of those. The 33
designer exclusions received no blind review. The paired estimates below use the 114 eligible stories from
110 authors and condition on both screening decisions. The severity rows use the sample's keyword strata.

| Keyword stratum | Eligible / regraded | Blind full | Blind partial | Blind none | Q1 or Q2 tagged | Q3 tagged without Q1 or Q2 |
|---|---:|---:|---:|---:|---:|---:|
| All | 114/157 | 65 | 38 | 11 | 81 | 22 |
| Severe | 54/79 | 32 | 20 | 2 | 47 | 5 |
| Mild/moderate | 60/78 | 33 | 18 | 9 | 34 | 17 |

- On the same posts, the designer judged 79/114 fully captured (69.3%) and the blind raters 65/114 (57.0%).
  The paired difference was 12.3 percentage points (95% author-cluster bootstrap interval 2.6–21.9). The
  blind estimate's interval was 47.8–66.4%. The bootstrap resamples authors and keeps their post ratings
  paired. These intervals quantify variation across stories under the existing screening and coding, with
  the coder assignments held fixed. Generalization to trial participants requires prospective data.
- The blind raters tagged Q1 or Q2 on 81/114 stories (71.1%, interval 62.6–79.1%). They tagged Q3 on another
  22/114 (19.3%, interval 12.4–26.5%), including 17/60 in the mild/moderate keyword stratum. In this rubric,
  a tag means a rater expected an item to register some change. The full/partial judgments apply to the
  whole questionnaire. Keep Q3 in the core, and compare symptom and activity scores directly in the pilot.
- Q4 or Q5 appeared alongside Q1–Q3 wherever the blind raters tagged them. In the informal percent-self
  data, 51.3% of 764 adjacent same-author pairs 0.5–14 days apart were identical and 14.0% differed by at
  least 20 points. Giving the 318 authors equal weight changes those figures to 46.5% and 16.0%. These
  regex-extracted pairs combine possible true health changes, errors in matching text, and self-rating
  variability. Keep Q4 optional and estimate measurement error prospectively in independently stable patients.
- The 190 coverage stories and the 600 title-screened discovery stories have disjoint post IDs and share
  14 authors. For the next coverage study, hold out authors. Use the existing material to develop the
  rubric and sample new stories without requiring a change title, including mixed and stable narratives.
  Two independent human coders should screen the entire evaluation sample and rate both versions in
  counterbalanced order, blinded to historical ratings and the design hypotheses. Report agreement on
  eligibility and the full/partial/none rubric before adjudication. Compare the paired full-coverage rates
  overall and by pre-specified severity group, with author-cluster intervals. Include narratives below the
  current activity floor. This is a content check on wording to complement patient interviews.

## Candidate wording and scoring

| Measure | Candidate for cognitive testing | What to compare |
|---|---|---|
| Q1 crash or flare days | Keep all-cause days, 0–7, in a dated seven-day window. Count a day once even when triggers overlap. In the diary, ask separately whether each flare followed exertion, had a different suspected trigger, or had no known trigger. | Agreement on total days, distinct from agreement on exertional days. Probe chronic severe symptoms, flares continuing from the previous week, and low-exposure weeks. |
| Q2 performed activity | Ask what the person actually did in a dated window. For each item tested, distinguish did it without a later cost, did it with a later cost, and had both types of experience. For activities they did not do, distinguish health or pacing from lack of opportunity or other reasons. Allow uncertain consequences and a skipped answer. | Compare a short fixed set spanning severity, cognition and physical function with the current 23-item checklist. Retain at least some very low-demand items and examine whether nested activities count the same change twice. |
| Q3 symptom severity | Keep the overall 0–10 item. Try a second 0–10 item for one symptom the patient names as important at baseline. Use the same severity instructions and time window for that symptom each week. | Test whether the named symptom detects patient-confirmed changes missed by Q3, and at what cost in time and completion. Record a change in the selected symptom and start a new series for it. |
| Q4 and Q5 | Keep percent-self optional. Keep the change question for feedback and record the date of the previous check, including missed weeks. In self-report collect symptoms in the patient's own voice, including answers recorded with help. | Evaluate optional Q4 for added information and completion. Capture respondent mode per visit. Evaluate observer reports of observable activity and flare signs as a separate measure, with unknown where observation is insufficient. |

For the Q2 candidate, count activities with only cost-free attempts, only attempts followed by a cost,
and both types of attempts separately. The first and third counts together give the closest analogue to
the current count of activities done at least once without a cost. Report health-limited, other-reason, uncertain
and missing items separately across the same fixed item set. A missed opportunity can lower an observed-activity
count while capacity is unchanged. Retain the raw responses, including whether assistance or a modification
was used in the diary subset. Probe what patients count as a cost, including symptom worsening and extra
recovery time. In interviews, check that a short walk followed by a flare, a cancelled outing, and an
unobserved consequence each produce distinct records. The FUNCAP27 is a comparator for functional capacity
and effects of exertion. Its development identified choice, preferences and support as influences on
activity frequency. [FUNCAP development and validation study](https://www.mdpi.com/2077-0383/13/12/3486)

### Handling the delay after activity

At a fixed weekly check time, the current five-day window can repeatedly omit the same two weekdays. In a
calendar-based candidate, use seven consecutive full local calendar days with a fixed offset from each
scheduled check. Test offsets giving at least 48 or 72 hours between the end of the activity window and
the scheduled check. Show the dates, keep scheduled windows fixed for late submissions, and record the
actual completion time. Code an observation without enough follow-up as pending or unknown. An activity
on an omitted weekday should appear in a dated seven-day window. An end-of-window activity whose consequence
is still unknown should remain unknown. For any combined analysis, join scores by the dates they describe.
Use the same target weeks for all scores in each four-week period, even if Q2 is collected later. Check that
no reference window crosses treatment start or the scheduled follow-up boundary.

Use a voluntary daily diary of usual activities, symptom worsening, perceived links to exertion and timing,
with follow-up beyond the activity window. Compare diary-derived counts for the current five-day window and
seven-day candidates at 48 and 72 hours against the panel's observed consequences, with an explicit
unknown category when diary follow-up is missing. Tabulate losses by weekday and by severity, plus delayed
worsening detected after each cutoff. Compare agreement of the weekly answers with diary-derived answers
for the same dates and estimate the added recall error and burden. CDC describes typical onset at 12–48
hours in ME/CFS and Long COVID. The retrospective regex matches here are imprecise and selectively reported,
so the two offsets are candidates to test. [CDC ME/CFS guidance](https://www.cdc.gov/me-cfs/hcp/clinical-care/treating-the-most-disruptive-symptoms-first-and-preventing-worsening-of-symptoms.html), [CDC Long COVID guidance](https://www.cdc.gov/long-covid/hcp/clinical-guidance/index.html)

The [runnable diary bridge](DIARY_BRIDGE.md) defines the export and compares the first five versus all seven
days at the same follow-up horizon, then compares 48 versus 72 hours on the same seven days. It reports
weekday coverage, delayed costs, and how incomplete diaries affect the score comparisons.

## How to choose the next version

1. **Cognitive interviews.** Recruit across conditions, baseline severity (including bedbound patients),
   activity opportunity and respondent modes. In iterative rounds, ask patients to describe their priorities
   before showing the form, then paraphrase each candidate and score their own week and shared vignettes.
   Use short sessions and accessible formats to include people who can only answer a few questions at a time.
   Log recurring misinterpretations, burden and missing concepts by severity. Revise wording before locking
   the candidate for quantitative comparison.
2. **Prospective comparison.** In the 12-week cohort, compare the current and revised questions in a paired,
   counterbalanced subset over the same scheduled weeks where feasible. Archive the exact wording and
   scoring rules of both versions before enrollment. Use the diary subset to isolate
   effects of the time window from wording changes. Collect external anchors for crash burden, daily
   function and symptom severity, aligned to the change windows. For four-week score comparisons, ask about
   change between the dated baseline and follow-up periods. Use FUNCAP27 for function and a PEM measure
   for exertional worsening. Use any step counts as context for ambulation. Size the pilot by precision of
   paired differences and counts of stable, minimally improved and minimally worsened participants, including
   the severe group. Multiple weeks from one person contribute repeated measures.
3. **Measurement performance.** In a short retest of the same dated period, use an independent stability
   question and estimate absolute agreement (ICC for numeric scores, with within-person differences and
   their limits). Report completion, time to complete, missingness reasons, floor and ceiling, and change
   by severity, condition and respondent mode. Compare change against the matched anchors, including
   deterioration and disagreements between activity, symptoms and crash days. Use participant-level
   resampling for uncertainty. Estimate meaningful within-patient change from the independent anchors
   with intervals, checking whether changes can be distinguished from measurement error. Pre-specify how
   many completed weeks each four-week score needs. Compare complete windows with a relaxed rule and
   sensitivity analyses for missed weeks due to worsening. [FDA draft guidance on clinical outcome assessment endpoints](https://www.fda.gov/media/166830/download)
4. **Decision and trial use.** Lock the comparison criteria with patients before reviewing a held-out
   participant set. Prefer a candidate item when it improves recognition of changes patients judge important
   or reduces misclassification, with acceptable completion and burden in the severe group. Publish the
   counts and uncertainty behind the choice. Carry crash burden, observed activity and symptom severity
   into the exploratory trial as separate outcomes. Assess the proposed crash-first hierarchy against them,
   tabulating which tier decides each pair, ties and unevaluable comparisons. Use vignettes to elicit
   trade-off preferences. Under the proposed hierarchy, a patient with two fewer crash days and four fewer
   activities wins against someone with unchanged crash days and two more activities. Ask patients whether
   that ranking reflects improvement. Examine how results change across plausible margins, priorities and
   missing-data assumptions, with uncertainty estimated at the participant level. A
   within-patient meaningful-change estimate informs interpretation. The margin that decides a comparison
   between two patients with different changes needs its own rationale. Confirm any primary endpoint and
   responder definition in an independent sample before relying on them for trial conclusions.

## Reproduce the audit

Run this command from the repository root. It uses the archived local analysis inputs and the corpus listed
in the [study README](../README.md#inputs).

```sh
python3 studies/baseline_check/next_version/audit.py reddit_2026-06-13.db
```

The script reads `v02_analysis/coverage/coded.jsonl`, `v02_analysis/sample_change.json`, the two blind
coverage JSONL files and `v02_analysis/level.jsonl`. It queries the corpus read-only for author linkage and
prints aggregate results. The output should include `114/157` paired eligibility, `0 posts, 14 authors`
shared with the title-screened frame, `Designer minus blind fully (pp): 12.3 [2.6, 21.9]`, and
`764 pairs, 318 authors` for the percent-self analysis.
