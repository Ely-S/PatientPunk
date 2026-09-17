# 7,8-DHF comparator study: findings and remaining questions

This report connects the study's completed analyses. Results are dated because
the sentiment, episode, and severity passes use different source populations and
eligibility rules. See the [study README](../README.md) for the full compound and
community lists and the [runbook](../RUNBOOK.md) for reproduction.

## Which compounds deserve closer investigation?

The original motivation was to place 7,8-DHF in context and identify compounds
worth investigating alongside it. In the September 2 globally deduplicated
sentiment analysis, 7,8-DHF had 482 positive authors among 673 (71.6%).
Cerebrolysin had a 72.5% positive share among 927 authors, and 4'-DMA-7,8-DHF had
71.8% among 255. These are similar descriptive rates, not evidence that one
compound is more effective. The full comparison includes all ten configured
compounds in the [predictor report](78dhf_predictor_analysis.md).

Cerebrolysin therefore remains a candidate for focused follow-up, alongside the
parent compound and its close derivative. A shortlist should also account for
the condition being studied, product and route differences, and the ability to
collect interpretable exposure and harm data. Membership in our comparator set
does not establish treatment suitability. In particular, BPC-157's larger usable
sample makes it useful for evaluating the analysis method, and lion's mane's
inclusion preserves the configured comparator set rather than recommending it because
of its sentiment rank.

## What does normalized sentiment tell us?

The September 2 analysis used an unweighted mean of eligible comparator-compound
positive rates, leaving 7,8-DHF out. Its combined baseline was 66.9%, so 71.6%
for 7,8-DHF was about 4.7 percentage points above that mean. This describes
relative reporting in the chosen compounds and communities. It does not correct
for differences in indication, symptom severity, formulation, or selection.

Reason-for-use categories were extracted only when stated explicitly. The
[predictor report](78dhf_predictor_analysis.md) contains reason-specific results
and describes the separate sentiment z-score sensitivity. A reported benefit,
a side effect, and the reason a person started treatment are different fields.

## Side effects need more than a yes/no label

The September 3 pass retained each distinct effect with an optional explicit
grade. The later analysis distinguishes any reported effect, the number of
different effects, the severity of each effect, and author-level mean and maximum
severity. Ungraded effects remain visible as side-effect reports but are excluded
from analyses requiring a grade.

At this checkpoint, 7,8-DHF had 684 classified authors, 275 with any mapped side
effect, and 22 with an explicit grade. Cerebrolysin had 940, 299, and 29,
respectively. These are updated severity-pass denominators and should not be
paired with the earlier sentiment percentages as if they came from the same run.

Moderate-or-worse means moderate, severe, or life-threatening. The corresponding
counts were 11/684 for 7,8-DHF and 18/940 for Cerebrolysin. Among authors who
explicitly graded an effect, those same numerators become 11/22 and 18/29.
The first denominator describes documented reporting among classified authors;
the second conditions on severity documentation. Neither estimates clinical
incidence, and neither means ungraded effects were mild. No conditional
moderate-or-worse comparator difference against 7,8-DHF survived the recorded
multiple-comparison correction.

## Can dose and route predict severity?

The saved joint models had only two eligible 7,8-DHF authors with explicit
severity, numeric dose, and route. There were also only two with dose when route
was omitted. A treatment-specific severity prediction is unsupported by that
sample. Cerebrolysin had no eligible numeric-dose/severity pairs under these
rules, which should not be mistaken for an absence of volume-based dosing reports.

BPC-157 supported more models. Its joint maximum-severity model retained 33
authors; the pooled model retained 40 and included compound fixed effects. Their
95% dose and route intervals included no association. The recorded moderate-or-
worse models were similarly imprecise. This does not establish that dose has no
effect. Missing exposure data, missing grades, differences between authors, and
the inability to align every exposure to the same episode limit interpretation.

The new reconstruction matches the overall author and graded-effect totals but
not every historical exposure-eligibility decision. It retains one graded
7,8-DHF author with dose instead of two, and some pooled coefficient directions
change. The reconstructed pooled mean-severity dose coefficient is +0.07 points
per doubling (95% CI -0.27 to 0.42), also including zero. These differences are
documented, not presented as an exact replication of the saved models.

Dose bands in the later severity analyses are compound-specific. Dose-only,
route-only, and joint dose/route tables describe different eligible samples.
Pooled dose coefficients are changes per doubling within compounds, not an
assumption that one milligram has the same meaning for every treatment.

## A concrete correction from the dose audit

The earlier >=100 mg 7,8-DHF row contained 11 candidate episodes with 10 labeled
positive. Manual source review found four doses belonging to another compound
and one range straddling the threshold. The retained descriptive row is six
episodes from four authors, with 5/6 positive (83.3%; Wilson 95% interval
43.6%-97.0%) and 1/6 reporting a mapped side effect (16.7%; 3.0%-56.4%). None
had an explicit severity grade.

These are episode-level Wilson intervals, not author-clustered intervals; the
six episodes are not six independent patients. Changing the row does not
retroactively refit the older 122-episode model. The
[episode report](78dhf_episode_analysis.md) marks those models as pre-audit.

## What the evidence supports next

The practical next step is better exposure information for the compounds and
conditions of interest. An opt-in survey is one proposed way to collect dose per
administration, frequency, duration, product/formulation, route, reason for use,
benefit, and each effect's severity together. It has not been launched as part of
this work.

The [saved severity outputs](severity_checkpoint.md) and the
[offline reconstruction](severity_reconstruction.md) are published with
separate provenance. The [model appendix](severity_checkpoint_models.md) and
[exposure tables](severity_checkpoint_exposures.md) retain the detailed results.
Statistical associations should be treated as hypotheses
for follow-up; they are not validated individual predictions or causal safety
rankings.
