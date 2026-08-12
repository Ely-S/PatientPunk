# Long COVID structured 21-trial set

This document isolates the 21 CT.gov-structured completed/result Long COVID trials from the current improved Long COVID study.

## Source files

- Study YAML: `C:\Users\scgee\OneDrive\Documents\Projects\PatientPunk\trial_superset\data\improved_outputs\long_covid\studies\long_covid_noparallel_notbinary_apo_study.yaml`
- Row-level export: `C:\Users\scgee\OneDrive\Documents\Projects\PatientPunk\trial_superset\data\long_covid_structured_21_rows.csv`
- Trial-level export: `C:\Users\scgee\OneDrive\Documents\Projects\PatientPunk\trial_superset\data\long_covid_structured_21_trials.csv`
- Master source CSV: `C:\Users\scgee\OneDrive\Documents\Projects\PatientPunk\trial_superset\data\master_pulled_data.csv`

## Filters

Broad CT.gov retrieval query:

```text
COVID OR SARS-CoV-2 OR PASC OR Post-Acute Sequelae of SARS-CoV-2 OR Post-COVID-19 Condition OR Chronic COVID OR Long-haul COVID
```

Final local Long COVID condition/MeSH filter terms:

```text
long covid
long-covid
post-covid
post covid
postcovid
pasc
post-acute covid
post-acute sequelae
```

The local filter checks CT.gov condition terms plus CT.gov condition MeSH terms. It does not use title, summary, interventions, outcomes, paper abstracts, or full text.

## Counts

- Trials: 21
- Master CSV rows preserved in row-level export: 106
- Earlier clean structured set: 17 trials
- Added by broadened retrieval: 4 trials
- Removed from earlier clean set: 0 trials

The four broadened-retrieval additions are:

- `NCT04876417` - Transcranial Direct Current Stimulation (tDCS) for Post COVID-19 Fatigue
- `NCT05074888` - Сlinical Trial of Efficacy and Safety of Prospekta in the Treatment of Post-COVID-19 Asthenia.
- `NCT05126563` - Randomized Double-Blind Phase 2 Study of Allogeneic HB-adMSCs for the Treatment of Chronic Post-COVID-19 Syndrome
- `NCT06136871` - Cognitive Rehabilitation in Post-COVID-19 Syndrome

## Trial table

| NCT | Split | Added by broadened retrieval | In Nikita seed | Matched local terms | Title |
|---|---|---:|---:|---|---|
| `NCT05104749` | train | False | False | post-acute covid | Homeopathic Treatment of Post-acute COVID-19 Syndrome |
| `NCT04876417` | train | True | False | post covid | Transcranial Direct Current Stimulation (tDCS) for Post COVID-19 Fatigue |
| `NCT05200858` | train | False | False | post-acute covid | Transcutaneous Electrical Nerve Stimulation (TENS) in Patients With Postacute Sequelae of Sars-CoV-2 |
| `NCT05074888` | train | True | False | post-acute covid | Сlinical Trial of Efficacy and Safety of Prospekta in the Treatment of Post-COVID-19 Asthenia. |
| `NCT05576662` | train | False | True | long covid , post-acute covid , post-acute sequelae | Paxlovid for Treatment of Long Covid |
| `NCT05126563` | train | True | False | post covid , post-acute covid | Randomized Double-Blind Phase 2 Study of Allogeneic HB-adMSCs for the Treatment of Chronic Post-COVID-19 Syndrome |
| `NCT05472090` | train | False | True | long covid , pasc , post-acute covid , post-acute sequelae | A Phase 2 Study to Evaluate the Efficacy and Safety of TNX-102 SL in Patients With Multi-Site Pain Associated With Post-Acute Sequelae of SARS-CoV-2 Infection |
| `NCT05047952` | train | False | False | post-covid , post-acute covid | Vortioxetine for Post-COVID-19 Condition |
| `NCT05592418` | train | False | True | long covid , post covid , post-acute covid | Study to Evaluate the Efficacy and Safety of Ampligen in Patients With Post-COVID Conditions |
| `NCT05618587` | train | False | True | long covid , post-acute covid | Effect of Lithium Therapy on Long COVID Symptoms |
| `NCT05445427` | train | False | False | post covid | Vagal Nerve Stimulation for Post COVID Fatigue |
| `NCT05633407` | train | False | False | post-acute covid | Efficacy and Safety Study of Efgartigimod in Adults With Post-COVID-19 POTS |
| `NCT04809974` | val | False | False | post-acute covid | Clinical Trial of Niagen to Examine Recovery in People With Persistent Cognitive and Physical Symptoms After COVID-19 |
| `NCT05965752` | val | False | True | long covid , post-acute covid | RECOVER-NEURO: Platform Protocol to Measure the Effects of Cognitive Dysfunction Interventions on Long COVID Symptoms |
| `NCT06253806` | val | False | False | post-acute covid | Stellate Ganglion Block for COVID-induced Parosmia |
| `NCT05595369` | val | False | True | long covid , post-acute covid | RECOVER-VITAL: Platform Protocol to Measure the Effects of Antiviral Therapies on Long COVID Symptoms |
| `NCT05999435` | val | False | True | long covid , post-acute covid | Study of LAU-7b for the Treatment of Long COVID in Adults |
| `NCT06136871` | val | True | False | post-covid , post-acute covid | Cognitive Rehabilitation in Post-COVID-19 Syndrome |
| `NCT05965726` | val | False | True | long covid , post-acute covid | RECOVER-VITAL: Platform Protocol, Appendix to Measure the Effects of Paxlovid on Long COVID Symptoms |
| `NCT06214455` | val | False | True | long covid , post-acute covid | Intermittent Fasting and a No-Sugar Diet for Long COVID Symptoms |
| `NCT05874037` | val | False | True | long covid , post-acute covid | Fluvoxamine for Long COVID-19 |

## NATURAL assumption flags

These 21 trials all pass Natural's `check_trial` under the `noparallel_notbinary_apo` preset. The CSVs now include explicit Natural assumption columns:

- `passes_natural_check_trial`: final Natural structural-filter pass/fail. This is `True` for all 21 trials.
- `natural_requires_randomized` and `natural_randomized_actual`: Natural requires randomized allocation here.
- `natural_requires_parallel` and `natural_parallel_actual`: parallel design is not required in this preset, but the actual design flag is still recorded.
- `natural_min_active_or_experimental_arms`, `natural_active_or_experimental_arm_count`, and `natural_has_required_active_or_experimental_arm`: APO mode requires at least one active or experimental arm.
- `natural_requires_nonhealthy` and `natural_nonhealthy_actual`: healthy-volunteer studies are excluded.
- `natural_requires_binary_endpoint` and `natural_binary_endpoint_actual`: binary endpoints are not required in the `notbinary` preset, but the actual primary-endpoint flag is still recorded.

Important interpretation: `noparallel` means Natural does not require a parallel design. It does not mean parallel trials are excluded. `notbinary` means Natural does not require a binary endpoint. It does not mean binary endpoints are excluded.

Corpus-learnable interpretation: only 8 of these 21 CT.gov-structured trials appear to satisfy NATURAL's actual patient-community-signal premise. The other 13 are mostly behavioral, device-based, clinic-administered, or otherwise off-premise for NATURAL estimation. The full 50-trial Long COVID benchmark has 9 corpus-learnable trials because it also includes one paper-rescued corpus-learnable trial, `NCT04795557`.

## Notes from the single CT.gov query test

A stricter single CT.gov condition query recovered all 21 trials, but it did not define exactly the same cohort by itself.

Single CT.gov query tested:

```text
"Long COVID" OR "Long-COVID" OR "Post-COVID" OR "Post COVID" OR "Post-COVID-19" OR "Post COVID-19" OR PostCOVID OR PASC OR "Post-Acute COVID" OR "Post-Acute COVID-19" OR "Post-Acute Sequelae" OR "Postacute Sequelae"
```

That query returned all 21 after applying the local condition/MeSH filter, but CT.gov also returned additional structurally valid records where Long COVID language appeared in title or keywords while condition/MeSH remained generic COVID-19. Those are intentionally not included in this 21-trial document.

## Column preservation

`long_covid_structured_21_rows.csv` preserves every original column from `master_pulled_data.csv` for the 106 rows associated with these 21 trials. It appends only audit metadata columns for membership in the 21-trial set, membership in the earlier 17-trial set, broadened-retrieval additions, and the CT.gov condition/MeSH/keyword strings used for filter review.

`long_covid_structured_21_trials.csv` is a one-row-per-trial rollup. Multi-row fields such as outcomes, arms, endpoint types, flags, and condition tags are joined with ` | ` so the trial-level file stays traceable to the row-level export.
