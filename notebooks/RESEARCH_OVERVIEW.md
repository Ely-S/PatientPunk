# PatientPunk — Research Questions Overview

## What We Asked

Seven research questions across three patient communities, each demonstrating a different capability of the PatientPunk analysis pipeline.

**Note on sample size:** These analyses use 1-month snapshots of communities with years of available data. The results are preliminary — designed to demonstrate the pipeline's capabilities, not to serve as definitive research. Running the pipeline on 6-month or multi-year datasets would dramatically increase statistical power and confidence. The findings below are signals worth investigating, not conclusions.

**Long COVID** (r/covidlonghaulers — 2,827 users, 6,815 treatment reports, 1-month sample)

1. **Which treatments have the best outcomes?** — Broad survey ranking all treatments by community sentiment. Finds LDN, magnesium, and electrolytes at the top; SSRIs at the bottom.

2. **How do POTS patients compare to the broader population?** — Preliminary subgroup study. POTS patients try 2x as many treatments but report worse outcomes. Beta blockers (first-line clinically) underperform. Surfaces hypotheses for follow-up.

3. **What is the optimal treatment strategy for POTS?** — Follow-up to #2. Finds 4-6 concurrent treatments is the sweet spot. Identifies a core stack: electrolytes + magnesium + LDN + antihistamines.

4. **What helps Long COVID fatigue specifically?** — Symptom-specific analysis. LDN, magnesium, and CoQ10 lead. SSRIs are the only major treatment class with net negative outcomes for fatigue.

**PSSD** (r/PSSD — 500 users, 902 treatment reports)

5. **Which SSRIs cause the worst PSSD?** — Harm/causation analysis. Sertraline and paroxetine are the worst. Microdosing psilocybin helps; full-dose hurts — same compound, opposite outcomes by dose.

6. **What helps PSSD recovery?** — Recovery analysis with causative drugs filtered. Antihistamines are the strongest signal, pointing toward a neuroinflammatory mechanism. Bupropion is the most-discussed but underperforms its reputation.

**Abortion** (r/abortion — ~2,500 users, ~1,400 posts)

7. **What predicts a positive vs negative experience?** — Experience analysis using post text, not just treatment reports. Support system predicts outcomes better than medical method. Relief and guilt coexist as the dominant emotional pattern.

---

## For the Slide

**Title:** PatientPunk Research Demonstrations

**Subtitle:** 7 questions · 3 communities · 10,000+ treatment reports

1. **Long COVID:** Which treatments work best? We rank them.
2. **Long COVID (POTS):** How do POTS patients differ? Preliminary subgroup study.
3. **Long COVID (POTS):** What treatment combinations work? Follow-up to #2.
4. **Long COVID (Fatigue):** What helps the #1 symptom specifically?
5. **PSSD:** Which SSRIs cause the worst harm? Does dose matter?
6. **PSSD:** What helps recovery when medicine has no answers?
7. **Abortion Recovery:** Method, support, or environment — what matters most?

Each question → reproducible notebook with statistics, charts, quotes, and recommendations.
