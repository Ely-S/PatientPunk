# PatientPunk

## The Problem

Reddit, patient forums, and social media are overflowing with firsthand patient reports: symptoms, treatments tried, outcomes, comorbidities, demographics. This data is qualitative, unstructured, and largely invisible to researchers. Patients who have tried dozens of treatments and documented their journeys in detail have no way to contribute that knowledge to science at scale.

Traditional clinical research has a structural blind spot: it relies on data it chooses to collect, from populations it chooses to study, on timelines measured in years and decades. Meanwhile, millions of patients are running informal experiments every day — trying treatments, tracking responses, reporting outcomes in plain language — and that signal disappears into forum threads.

## Patient Reports Are Data

The medical establishment has long treated patient self-reports as soft evidence — anecdote, noise, the kind of thing that gets filtered out before analysis begins. This is a mistake.

Patient reports are the only source of ground truth for the lived experience of disease. No biomarker tells you whether someone can get out of bed. No lab value captures treatment-induced cognitive impairment. No clinical trial follows patients long enough to capture the years-long arc of a complex chronic illness. For conditions like ME/CFS, long COVID, POTS, and other poorly understood diseases, patient testimony is not a weak signal — it is often the *only* signal.

The problem is not the quality of patient data. The problem is that we have never had the infrastructure to aggregate it, normalize it, and make it queryable at scale. PatientPunk is that infrastructure.

## Why Qualitative Markers Matter

Clinical research segments patients by diagnosis codes and lab values. But patients know things about themselves that never make it into their charts: how their symptoms cluster, how severity fluctuates, which comorbidities they believe are connected, what functional limitations look like day-to-day. These self-reported qualitative markers — "I crash after any exertion," "my symptoms are worse in the morning," "I went from bedbound to functional on this protocol" — contain signal that structured clinical data cannot capture.

Segmenting by these markers is not a compromise. It is a research strategy.

A patient who reports post-exertional malaise alongside brain fog and fatigue is a different cohort than one who reports the same diagnosis without PEM. A patient who self-identifies as a "slow responder" to LDN may have biology distinct from someone who saw results in the first week. These distinctions are invisible to standard ICD-10-based analysis. They are only visible if you take patient language seriously and build systems that can query it.

PatientPunk treats self-reported qualitative markers as first-class fields — not as noise to be discarded, but as dimensions to slice and filter on. This is what makes patient-driven science possible.

## What PatientPunk Does

PatientPunk ingests patient-generated content from social media, normalizes it into structured records, and exposes it as queryable datasets for researchers and patient-driven scientists.

A patient or researcher can ask:

> *"Do other patients with ME/CFS, severe neuroinflammation, and brain fog report positive outcomes with LDN treatment?"*

And get back:

> **64% positive outcome · 20% negative outcome · 16% no effect**
> *(based on 312 patient reports)*

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                       INGESTION                         │
│  (modular — Reddit, Twitter/X, patient forums, etc.)    │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                    NORMALIZATION                         │
│  Posts stored in a normalized schema:                   │
│  User entity · Post entity · source metadata            │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                 AI TRANSFORMATION                        │
│  LLM-powered entity extraction · Symptom ontology       │
│  mapping (MeSH / SNOMED) · Outcome scoring              │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                     DATABASE                            │
│  User records · Post records ·                          │
│  LLM outputs stored as structured JSON                  │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                      OUTPUTS                            │
│  CSV exports · SQL queries · REST API · Research kits   │
└─────────────────────────────────────────────────────────┘
```

---

## Key Features

- **Modular ingestion** — swap in new data sources (Reddit, forums, health apps) without changing downstream logic
- **Symptom normalization** — maps patient language ("brain fog", "crushing fatigue") to standard medical ontologies
- **Treatment outcome tracking** — classifies reported outcomes as positive, negative, neutral, or mixed
- **Cohort queries** — filter by condition profile, demographics, comorbidities, and treatment history
- **Privacy-first** — no PII stored; usernames hashed; posts anonymized before storage
- **Researcher-ready exports** — CSV, SQL dumps, and structured JSON for direct analysis

---

## Example Query

```sql
SELECT
  treatment,
  COUNT(*) AS reports,
  ROUND(AVG(outcome_score), 2) AS avg_outcome,
  SUM(CASE WHEN outcome = 'positive' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS pct_positive
FROM patient_reports
WHERE 'ME/CFS' = ANY(conditions)
  AND 'neuroinflammation' = ANY(symptoms)
  AND 'brain_fog' = ANY(symptoms)
GROUP BY treatment
ORDER BY reports DESC;
```

---

## Data Model (simplified)

### User

| Field | Type | Description |
|---|---|---|
| `user_id` | hash | Anonymized identifier (hashed username) |
| `platform` | string | Originating platform (reddit, twitter, etc.) |
| `first_seen` | date | Date of first observed post |
| `post_count` | int | Number of posts attributed to this user |

### Post

| Field | Type | Description |
|---|---|---|
| `post_id` | string | Platform-native post ID |
| `user_id` | hash | FK → User |
| `platform` | string | Originating platform |
| `raw_text` | text | Original post content |
| `posted_at` | date | Date of original post |
| `url` | string | Source URL |
| `llm_output` | jsonb | Structured JSON from AI Transformation (see below) |

### llm_output schema (inside Post)

```json
{
  "conditions": ["ME/CFS", "POTS"],
  "symptoms": ["brain_fog", "neuroinflammation", "fatigue"],
  "treatments": [{ "name": "LDN", "dose": "4.5mg" }],
  "outcome": "positive",
  "outcome_score": 0.8,
  "demographics": { "age_range": "30-40", "sex": "female" },
  "confidence": 0.91
}
```

---

## Ethical Commitments

- Data is used strictly for scientific and patient-benefit purposes
- No re-identification of individuals
- Opt-out mechanisms respected (deleted posts are purged)
- Transparent about data provenance in all exports

---

## Built at

Biotech Hackathon · San Francisco · April 4, 2026 · Frontier Tower

```
██████╗ ██╗ ██████╗     ██████╗ ██╗   ██╗███╗   ██╗██╗  ██╗
██╔══██╗██║██╔═══██╗    ██╔══██╗██║   ██║████╗  ██║██║ ██╔╝
██████╔╝██║██║   ██║    ██████╔╝██║   ██║██╔██╗ ██║█████╔╝
██╔══██╗██║██║   ██║    ██╔═══╝ ██║   ██║██║╚██╗██║██╔═██╗
██████╔╝██║╚██████╔╝    ██║     ╚██████╔╝██║ ╚████║██║  ██╗
╚═════╝ ╚═╝ ╚═════╝     ╚═╝      ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═╝
```
