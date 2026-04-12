# Research Questions

These questions were used to generate the analysis notebooks in this repository. Each demonstrates a different capability of the PatientPunk research skill.

To reproduce any notebook, open Claude Code in this project directory and ask the question. The research-assistant skill will explore the database, propose an analysis plan, and generate an executed notebook with HTML export.

---

## Notebook 1 — Treatment Overview (Long COVID)

**Database:** `polina_onemonth.db` (r/covidlonghaulers, 2,827 users, 6,815 treatment reports)

**Question:** Which treatments have the best outcomes in Long COVID?

**Demonstrates:** Broad survey analysis. Treatment ranking with Wilson CIs, causal-context filtering (vaccines), sensitivity checks, tiered recommendations.

---

## Notebook 2 — Preliminary POTS Study

**Database:** `polina_onemonth.db` (80 POTS users identified via conditions table)

**Question:** How do POTS patients in the Long COVID community compare to the broader population?

**Demonstrates:** Preliminary survey / subgroup comparison. Establishes baseline differences, identifies surprising findings (beta blocker paradox, famotidine inversion), and surfaces hypotheses for follow-up.

---

## Notebook 3 — POTS Follow-Up: Treatment Strategy

**Database:** `polina_onemonth.db` (same 80 POTS users)

**Question:** Following up on the preliminary POTS analysis: what is the optimal treatment strategy for Long COVID POTS?

**Demonstrates:** Targeted follow-up investigation. Takes findings from NB2 (polypharmacy signal, first-line underperformance) and drills into treatment stacking, combination analysis, and the optimal number of concurrent treatments. Shows the tool can handle a research workflow where one analysis motivates the next.

---

## Notebook 4 — Fatigue Treatments (Long COVID)

**Database:** `polina_onemonth.db` (442 users mentioning fatigue)

**Question:** What is the best way to reduce fatigue in Long COVID?

**Demonstrates:** Symptom-specific analysis. Defines a cohort by text mining (users mentioning "fatigue"), compares fatigue vs non-fatigue subgroups, and produces actionable recommendations for a specific symptom rather than the condition overall.

---

## Notebook 5 — PSSD Harm Profile

**Database:** `pssd.db` (r/PSSD, 500 users, 902 treatment reports, 62% negative sentiment)

**Question:** Which SSRIs cause the worst PSSD, and what predicts a more severe case?

**Demonstrates:** Harm/causation analysis in a community defined by drug injury. Inverted sentiment baseline (62% negative vs typical 60%+ positive). Shows the tool can analyze what caused harm, not just what helps recovery. The micro vs macro psilocybin finding emerges here as a dose-dependent effect.

---

## Notebook 6 — PSSD Recovery

**Database:** `pssd.db` (same community, ~80 users mentioning recovery)

**Question:** What treatments improve PSSD once people have it?

**Demonstrates:** Recovery analysis with causal-context filtering. SSRIs (which caused the condition) are separated from recovery treatments. Treatment categories grouped by mechanism. Recovery cohort compared to non-recovery users. Shows the tool can handle communities where the primary drugs discussed are harmful, not helpful.

---

## Notebook 7 — Abortion Experience

**Database:** `abortion_1month.db` (r/abortion, ~2,500 users, ~1,400 posts)

**Question:** What predicts a positive vs negative abortion experience? Is it the method, the support system, or the clinical environment?

**Demonstrates:** Community experience analysis where the richest signal is in post text, not treatment reports. Text-based theme mining (support, fear, guilt, relief, provider quality) alongside sentiment pipeline output. Shows the tool can pivot from drug analysis to experiential analysis when the data warrants it.

---

## Reproducing These Analyses

```bash
# 1. Ensure the database exists (e.g., polina_onemonth.db)
# 2. Open Claude Code in the project directory
# 3. Ask the question — the research-assistant skill handles the rest

# Example:
# "Using polina_onemonth.db, which treatments have the best outcomes in Long COVID?"

# The skill will:
#   - Read the database profile from notebooks/profiles/
#   - Propose an analysis plan
#   - Build, execute, and export the notebook to HTML
```

## Question Design Principles

When writing new research questions for this tool:

1. **Be specific about the population** — "Long COVID patients with fatigue" not just "patients"
2. **Ask a question with a testable answer** — "does multi-prong beat monotherapy?" not "tell me about POTS"
3. **Follow-up questions should reference prior findings** — "Following up on the POTS analysis, what combinations drive the polypharmacy signal?"
4. **Consider what the data can actually answer** — treatment sentiment from Reddit posts, not clinical efficacy
5. **Choose questions that demonstrate different tool capabilities** — survey, subgroup comparison, follow-up, symptom-specific, harm analysis, recovery analysis, experience analysis
