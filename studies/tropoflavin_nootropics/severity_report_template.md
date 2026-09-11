# Side-effect severity: the September 3 analysis checkpoint

This report makes the saved September 3, 2026 analysis reviewable. It re-renders validated aggregate outputs; it does not rerun extraction or refit the historical models. Some source files were finalized just after midnight UTC on September 4. The source hashes and recorded settings are in [the provenance manifest](severity_checkpoint_provenance.json). Later reconstructed model runs must be reported separately because they are not the original analysis code.

The [separate reconstruction report](severity_reconstruction.md) records the results of the newly implemented analysis. Its stricter exposure eligibility retains one jointly linked, graded 7,8-DHF author rather than the two recorded here. It uses saved dose values and does not independently re-audit their original text attribution. The historical figures below are preserved so that this implementation difference is visible.

## What the data can support

The study covers $community_count independently processed communities and ten compounds. For 7,8-DHF, $dhf_authors classified authors reduce to $dhf_graded authors with an explicitly graded side effect, $dhf_dose graded authors with a usable dose, and $dhf_joint graded authors with both dose and route before rare-route exclusions. A large overall corpus therefore does not provide a sufficiently large sample for its severity regression. Cerebrolysin has $cerebro_authors classified authors and $cerebro_graded with an explicit grade, but no graded authors with both usable numeric mg dose and route in this checkpoint. A missing mg dose does not mean the original post contained no dosing information; volume-based preparations require separate treatment-specific handling.

The detailed severity outcome retains a distinct author-treatment-canonical side-effect observation and the maximum explicit grade for repeat mentions of that same effect. It keeps different effects from one author separate and clusters model uncertainty by author. Author-level maximum and average severity are secondary summaries. Mild=1, moderate=2, severe=3, and life-threatening=4. These are ordinal categories; the linear summaries assume equal spacing for convenience.

## Denominators and missingness

Every row below deduplicates an author across all communities for that compound. Authors can appear under more than one compound. Any side effect means a mapped report; a missing report is not evidence that a person experienced none. Severity is only extracted when explicitly graded. Unknown severity is never coded as mild or zero.

The abbreviated 4'-DMA label means 4'-DMA-7,8-DHF, which is kept separate from plain 7,8-DHF.

$summary_table

All intervals in these proportion tables are two-sided 95% Wilson intervals. They describe author-level sampling uncertainty under a binomial model. They do not include extraction error, self-selection, or uncertainty about unreported outcomes. The all-author moderate+ rate is the fraction with a documented qualifying report in this corpus, not clinical incidence and not a lower bound on population incidence. The conditional rate describes the selected authors who supplied a severity grade.

![Moderate-or-worse reporting with 95% Wilson intervals](severity_moderate_or_worse.png)

## Why dose and route prediction remain limited

$eligibility_table

Dose, route, and joint counts in this table use the saved linear-model eligibility definition and are before sparse route levels are removed. The separately listed graded-effect counts use the fine-grained definition, which retains distinct effects. Their denominators must not be interchanged. The earlier severity feasibility report used a different, fixed dose-band rule and counted one jointly eligible 7,8-DHF author; the later model eligibility stage counted two. This is a definition change, not two conflicting estimates of the same sample.

![Authors available for explicit severity and linked exposure models](severity_eligibility.png)

These are author-history links: a person's dose, route, and outcome can have appeared in different posts. They are not guaranteed to describe the same exposure episode. The separate [same-post episode analysis](78dhf_episode_analysis.md) addresses episode linkage and has different denominators. Its episodes can repeat within authors, so a simple Wilson interval over episodes is descriptive and does not account for that dependence. Individual dose-route cells here are descriptive and cannot establish a causal dose or route effect.

## Moderate-or-worse side effects worth examining

Moderate+ includes moderate, severe, and life-threatening explicit grades. The following is the saved leading-effect subset, not an exhaustive effect inventory. An author may appear in several rows. A compound absent from this subset has no selected row, which is not evidence of zero moderate+ reports.

$effects_table

## Models: dose alone, route alone, and both together

The historical maximum-severity models use log2 dose, so a dose coefficient is the expected score-point difference per doubling. Route is categorical, with the reference in each term. Fine-grained models additionally distinguish any reported effect, distinct-effect count, and ordinal severity of an effect. Ratios have a null value of 1; linear score differences have a null value of 0. The joint model includes dose and route main effects. An interaction model asks the additional question of whether the dose association differs by route.

The frozen analysis contains no estimable 7,8-DHF severity model, including dose alone. BPC-157 supplied most of the joint severity sample. Its moderate+ models are conditional on having an explicitly graded effect:

$moderate_models_table

![BPC-157 conditional moderate-or-worse associations](severity_moderate_models.png)

The dose-only and joint models use different eligible samples, so their coefficients are not a controlled comparison of adjustment alone. All displayed conditional moderate+ confidence intervals include the null odds ratio of 1. They do not establish absence of an effect. Estimated means or probabilities, even where a model fits, are in-sample associations without demonstrated predictive performance on new participants.

Historical linear joint-model estimates and the secondary average-severity comparison are shown below. The complete dose-only, route-only, joint, interaction, sensitivity coefficients and non-estimable statuses are in the [model appendix](severity_checkpoint_models.md).

$joint_models_table

The source fine-grained report includes nominal pooled associations for occurrence and effect count. They should remain exploratory: several outcomes, treatments, and models were examined, the exposure links are across author history, and extreme-dose sensitivity changed some results. A fitted model or a small nominal p value is not evidence of clinical benefit or safety.

## Compound-specific exposure summaries

Dose cut points were derived separately for each treatment from dose-linked authors after the primary plausibility screen. Tied cut points are kept together and can collapse three intended groups into two. These are sample-derived descriptive bins, not clinical dose recommendations or equivalent potency across treatments. Dose uses a geometric mean only when the author's eligible numeric mg values remain in one band. Primary dose analyses exclude 7,8-DHF values at or above 100 mg; the separately audited historical high-dose episodes are described in the study README and episode report.

$dose_definitions_table

Regression groups oral mucosal and swallowed oral as oral, and nasal mucosal as nasal. The [exposure appendix](severity_checkpoint_exposures.md) preserves all saved dose-only, route-only, and dose-plus-route cells, including average and maximum severity and the recorded 95% bootstrap intervals. These groupings sacrifice formulation detail and do not equate absorption across routes.

Bootstrap intervals based on two or three authors can be unstable. If all observed scores are identical, the saved percentile interval can collapse to one value; this reflects the observed resample support, not certainty about the population. A missing interval is explicitly shown as not estimable. A linear prediction may also fall outside the 1-4 scale and should not be read as an actual severity category.

## Implication for the next study

The strongest contribution is identifying what to measure prospectively: exact compound and formulation, dose and schedule, route, reason for use, concurrent treatments, and each side effect's explicit severity and timing. An opt-in survey could improve completeness, but recall and selection bias would remain. The online reports are hypothesis-generating evidence. Compounds should not be ranked as safer from the conditional severity percentages alone.

The nootropic-adjacent communities and disease-focused communities were processed independently. Their identities and recorded database digests are retained in the provenance manifest. The combined results above do not establish that their respondents represent OMF's disease population.
