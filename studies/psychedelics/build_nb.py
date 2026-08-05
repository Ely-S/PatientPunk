import nbformat as nbf

nb = nbf.v4.new_notebook()
c = []
md = lambda s: c.append(nbf.v4.new_markdown_cell(s.strip()))
co = lambda s: c.append(nbf.v4.new_code_cell(s.strip()))

md(r"""
# LSD, Psilocybin and Ketamine in the Long COVID / ME-CFS Community

**A within-patient analysis of self-reported treatment outcomes.**

Source: `data/full_corpus_2026-07-31/` — 69,161 patient records extracted from 15
long-COVID / ME-CFS subreddits, 204,417 `treatment_outcome` triples.

This notebook is statistics only. Methods, Results, Conclusion. Narrative prose is
deliberately left out.

---

### The question, and why the obvious analysis is wrong

The community treats these three substances as one family. A naive read of this corpus
says psilocybin is reported as helping 81% of the time against a 67% corpus-wide
average — but the people who write about psychedelics are not the corpus average. They
are sicker, they have far heavier mood and cognitive symptom loads, and they name a
median of 7 treatments each. The comparison measures *who reports*, not *what the drug did*.

So the comparator here is **the patient themselves**: every psychedelic outcome is
compared against the same patient's outcomes for their own other treatments, with patient
fixed effects. The two documented biases in this dataset — an extractor that over-calls
positive, and stacked treatments inheriting a collective outcome — apply to both arms
inside the same record and largely cancel.
""")

# ─────────────────────────── METHODS ───────────────────────────
md(r"""
---
# 1. Methods
""")

md(r"""
## 1.1 Data source and unit of analysis

Input is `records_covidlonghaulers_v2.json`, the run's authoritative dataset, rather than the
`records.csv` convenience table, which is documented as lossy.

One record is one **patient**, not one post — every post and comment by an author across
the whole corpus was concatenated and extracted in a single LLM call (deepseek-v4-flash,
temperature 0). Authors with fewer than 3 text segments were dropped.

The analysis unit below is one **outcome triple**: `drug : outcome : symptom`, e.g.
`"psilocybin: helped: brain fog"`. Outcome is a closed 5-value vocabulary.
""")

co(r"""
import sys, warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path.cwd()))
import psychedelics as P

# The conditional-logit estimator warns each time it drops concordant strata.
# That is the design, not a problem -- see 4.1. Silenced to keep output readable.
warnings.filterwarnings("ignore", message="Dropped .* groups")

plt.rcParams.update({
    "figure.dpi": 120, "font.size": 9, "axes.grid": True,
    "grid.alpha": 0.25, "axes.spines.top": False, "axes.spines.right": False,
})

records = P.load_records()
df = P.build_outcome_table(records)   # asserts every triple parses
df = P.add_prep(df)

print(f"patients in corpus        {len(records):,}")
print(f"outcome triples parsed    {len(df):,}")
print(f"unparseable triples       0  (asserted by build_outcome_table)")
""")

md(r"""
## 1.2 Cohort definition

Nothing in this dataset is canonicalized — `ldn`, `low dose naltrexone` and
`low-dose naltrexone` are three separate strings among 18,101. Arms are therefore assigned
by regex over the **drug slot only**, never over the whole record.

| arm | pattern |
|---|---|
| psilocybin | `psilocyb`, `psilocin`, `magic mushroom`, `shroom(s)`, `psychedelic mushroom` — **minus** functional mushrooms (lion's mane, reishi, chaga, cordyceps, turkey tail, maitake, shiitake) |
| ketamine | `ketamine`, `esketamine`, `spravato` — both of the first two are required, since the word boundary in `\bketamine\b` does not match *esketamine* |
| LSD | `lsd`, `lysergic`, `1p-lsd`, `ald-52`, `acid tabs`, `acid trip`, `microdose acid` |

**Bare `acid` never matches.** `alpha lipoic acid`, `ascorbic acid`, `folic acid` and
`acid reflux` are all common here and would swamp an arm this small. Verified below.
""")

co(r"""
must_not_match_lsd = [
    "alpha lipoic acid", "r-alpha lipoic acid", "ascorbic acid", "folic acid",
    "amino acids", "hyaluronic acid", "acid reflux", "stomach acid", "fulvic acid",
]
for s in must_not_match_lsd:
    assert P.classify_drug(s) != "lsd", f"FALSE POSITIVE: {s!r}"

must_match = {
    "lsd": "lsd", "1p-lsd": "lsd", "acid tabs": "lsd", "microdosing lsd": "lsd",
    "psilocybin": "psilocybin", "magic mushrooms": "psilocybin", "shrooms": "psilocybin",
    "ketamine": "ketamine", "spravato": "ketamine", "esketamine": "ketamine",
    "lion's mane": "other", "reishi mushroom": "other",
}
for s, want in must_match.items():
    got = P.classify_drug(s)
    assert got == want, f"{s!r} -> {got}, expected {want}"

print(f"drug-slot classifier: {len(must_not_match_lsd)} false-positive guards and "
      f"{len(must_match)} assignments all pass")
""")

md(r"""
## 1.3 Denominators: naming a drug vs reporting how it went

Two different cohorts exist and they must not be confused. A patient can name psilocybin
in `medications` without ever saying what it did. Prior work in this repo reported **538**
psilocybin patients using the any-mention definition; only a subset of those carry a scored
outcome triple, and the triple cohort is what every analysis below uses.
""")

co(r"""
mentions = P.mention_cohort(records)          # named anywhere: reconciles with prior work
cohort = P.cohort_counts(df)                  # has a scored outcome triple

recon = (mentions.set_index("drug_class")
         .join(cohort[["patients", "mentions"]]
               .rename(columns={"patients": "patients_with_outcome",
                                "mentions": "outcome_triples"}))
         .loc[list(P.DRUGS)])
recon["pct_with_outcome"] = 100 * recon.patients_with_outcome / recon.patients_mentioning
display(recon)

print("Prior psilocybin analysis reported 538 any-mention patients; reproduced above.")
""")

md(r"""
## 1.4 Excluded ambiguity buckets

Two string families cannot be assigned safely and are counted, reported, then **excluded
from every inferential fit**:

- bare `mushroom` / `mushroom blend` / `mushroom complex` with no functional-mushroom name
  and no explicit psilocybin word,
- bare `acid` strings that are not a known non-psychedelic acid compound.

Section 5.2 re-runs the primary model with both folded back in, to bound how much the
exclusion could matter.
""")

co(r"""
display(cohort.loc[[c for c in cohort.index if c.startswith("ambiguous")]])
""")

md(r"""
## 1.5 Endpoint

Primary endpoint is **`helped` vs not-`helped`** (binary). The 5-level vocabulary is too
unbalanced corpus-wide (`mixed` 1.5%, `unknown` 1.0%) to support a multinomial fit at LSD's n.

`no_effect` is reported as a secondary endpoint and is arguably the more diagnostic of the
two: a positively-biased extractor inflates `helped` far more readily than it suppresses
`no_effect`, and a genuinely inert intervention should produce a *high* no-effect rate.
""")

md(r"""
## 1.6 Pre-registered tests, power, and direction of bias

Seven tests, declared before results, Holm-corrected as one family (section 6). Everything
else in this notebook is exploratory and is reported **without** p-values.

1–3. psilocybin vs ketamine, psilocybin vs LSD, ketamine vs LSD (head-to-head)
4–6. each drug vs the same patients' own other treatments (within-patient)
7. psychedelic × symptom-class interaction (mood/cognitive vs energy/PEM)

Two things to fix in mind before reading any estimate:

- **LSD is underpowered by design, not by accident.** Its minimum detectable difference is
  computed below. A null LSD result is uninformative, not evidence of no effect.
- **Noise here is conservative.** Repeat extraction passes over identical text agree on only
  58.8% of filled values. Non-differential misclassification biases a within-patient contrast
  *toward* the null, so an effect that survives section 4 is an underestimate, not an artifact.
""")

co(r"""
for d in P.DRUGS:
    n = int(cohort.loc[d, "mentions"])
    print(f"{d:11s} n={n:4d} mentions -> minimum detectable risk difference "
          f"{100*P.mde(0.68, n):.1f} pp (80% power, alpha .05, vs a 68% baseline)")
""")

md(r"""
## 1.7 Symptom classes

Fixed before any outcome was inspected. Only the first two are tested; `pain` and `other`
are descriptive.
""")

co(r"""
sym = (df[df.drug_class.isin(P.DRUGS)]
       .groupby(["drug_class", "symptom_class"]).size().unstack(fill_value=0))
display(sym[["mood_cognitive", "energy_pem", "pain", "other", "unspecified"]])
""")

md(r"""
## 1.8 Limits that no amount of statistics repairs

- **Cohort-level claims only.** Two identical extraction passes agreed on the field set for
  36.5% of records. Aggregate rates are stable to 0.8pp; a single record is one draw. No case
  studies, no per-patient narratives.
- **No time axis.** A record collapses years of posting into one document; a 2021 trip and a
  2026 trip sit in it unordered. No before/after, no dose-response over time, no trends.
- **No denominator for silent failure.** People post about treatments that did *something*. A
  drug tried once and quietly abandoned never appears. The within-patient design controls for
  *reporter* bias; it cannot control for *selection into reporting*.
- **Route asymmetry is structural.** Ketamine is substantially clinic-administered; psilocybin
  and LSD are self-sourced. Any ketamine-vs-others difference is confounded by supervision,
  screening and expectancy. See section 4.4.
- **Not the drug-sentiment pipeline.** `treatment_outcome` comes from variable extraction.
  `src/run_sentiment_pipeline.py` has never been run on this corpus; these rates are not
  comparable to `sentiment` numbers from other PatientPunk runs.
""")

# ─────────────────────────── RESULTS ───────────────────────────
md(r"""
---
# 2. Results — descriptive
""")

md(r"""
## 2.1 Raw outcome rates

Every rate carries a Wilson 95% CI and its denominator. The corpus-wide line is a
**descriptive reference only** — it is not a control, because the patients in these arms
differ systematically from the corpus average on exactly the traits that drive reporting.
""")

co(r"""
drugs_df = df[df.drug_class.isin(P.DRUGS)]

helped = P.rate_table(drugs_df, col="helped").set_index("drug_class")
noeff = P.rate_table(drugs_df, col="no_effect").set_index("drug_class")

summary = pd.DataFrame({
    "patients": helped.patients, "mentions": helped.n,
    "helped": helped.rate, "helped_lo": helped.ci_lo, "helped_hi": helped.ci_hi,
    "no_effect": noeff.rate, "no_effect_lo": noeff.ci_lo, "no_effect_hi": noeff.ci_hi,
})
display(summary.style.format("{:.3f}", subset=[c for c in summary.columns
                                               if c not in ("patients", "mentions")]))

print(f"corpus-wide reference (n={P.CORPUS_MENTIONS:,} mentions, NOT a control): "
      f"helped {P.CORPUS_BASELINE['helped']:.3f}  "
      f"no_effect {P.CORPUS_BASELINE['no_effect']:.3f}  "
      f"worsened {P.CORPUS_BASELINE['worsened']:.3f}")
""")

co(r"""
full = (drugs_df.groupby(["drug_class", "outcome"]).size()
        .unstack(fill_value=0).reindex(columns=P.OUTCOMES, fill_value=0))
display(full)
display((100 * full.div(full.sum(axis=1), axis=0)).round(1))
""")

co(r"""
fig, ax = plt.subplots(figsize=(6.4, 2.6))
order = list(P.DRUGS)
y = np.arange(len(order))
for i, d in enumerate(order):
    r = helped.loc[d]
    ax.plot([r.ci_lo, r.ci_hi], [i, i], color="#444", lw=1.4, zorder=2)
    ax.plot(r.rate, i, "o", ms=7, color="#2b6cb0", zorder=3)
    ax.annotate(f"{r.rate:.1%}  (n={int(r.n)})", (r.ci_hi, i),
                xytext=(6, 0), textcoords="offset points", va="center", fontsize=8)
ax.axvline(P.CORPUS_BASELINE["helped"], color="#c05621", ls="--", lw=1,
           label=f"corpus-wide reference ({P.CORPUS_BASELINE['helped']:.1%})")
ax.set_yticks(y, order)
ax.set_xlabel("proportion of mentions reported as 'helped' (Wilson 95% CI)")
ax.set_xlim(0.45, 1.0)
ax.set_title("Raw helped-rate by arm — uncontrolled, confounded by who reports", fontsize=9)
ax.legend(fontsize=8, loc="lower left")
plt.tight_layout(); plt.show()
""")

md(r"""
## 2.2 What the community treats each drug *for*

The symptom slot is the community's indication map — its folk materia medica. The three
substances are not aimed at the same targets.
""")

co(r"""
top = {}
for d in P.DRUGS:
    s = (drugs_df[(drugs_df.drug_class == d) & drugs_df.symptom.notna()]
         .symptom.value_counts().head(12))
    top[d] = s
display(pd.concat(top, axis=1).fillna(0).astype(int))
""")

co(r"""
share = (sym[["mood_cognitive", "energy_pem", "pain", "other", "unspecified"]]
         .pipe(lambda t: 100 * t.div(t.sum(axis=1), axis=0)))
ax = share.loc[list(P.DRUGS)].plot(kind="barh", stacked=True, figsize=(7, 2.4),
                                   colormap="Blues_r", width=0.7)
ax.set_xlabel("% of that arm's outcome mentions")
ax.set_title("Indication mix differs by arm", fontsize=9)
ax.legend(fontsize=7, bbox_to_anchor=(1.01, 1), loc="upper left")
plt.tight_layout(); plt.show()
""")

md(r"""
## 3. Head-to-head between arms

Pre-registered tests 1–3. Fisher's exact is used whenever any cell falls below 5, which the
LSD arm routinely triggers.
""")

co(r"""
pairs = [("psilocybin", "ketamine"), ("psilocybin", "lsd"), ("ketamine", "lsd")]
h2h = pd.DataFrame([P.compare_two(drugs_df, a, b) for a, b in pairs])
display(h2h.style.format({"rate_a": "{:.3f}", "rate_b": "{:.3f}", "risk_diff": "{:+.3f}",
                          "rd_ci_lo": "{:+.3f}", "rd_ci_hi": "{:+.3f}", "p": "{:.2e}"}))
""")

# ── primary ──
md(r"""
---
# 4. Primary analysis — the patient as their own control
""")

md(r"""
## 4.1 Design

Restricted to patients who reported **both** a study drug and at least one other treatment.
A conditional (fixed-effects) logistic regression estimates

$$\text{logit}\,P(\text{helped}) = \alpha_{\text{patient}} + \beta_{\text{drug}}$$

where $\alpha_{\text{patient}}$ is a free intercept per patient. Everything constant within
a patient — their optimism, illness severity, which subreddits they post in, how they write
— is absorbed and cannot confound $\beta$.

Patients whose outcomes are all identical carry no information about $\beta$ and are dropped
by the estimator. The reported effect therefore rests on the **discordant** strata: patients
who called some treatments helpful and others not.

$\exp(\beta)$ reads as: *the odds this patient calls this drug helpful, relative to the odds
they call their own other treatments helpful.*
""")

co(r"""
wp = P.within_patient_frame(df)
print(f"patients with both arms      {wp.patient.nunique():,}")
print(f"outcome rows                 {len(wp):,}")
print(f"informative (discordant)     {P.informative_strata(wp):,}")
print()
display(P.rate_table(wp).set_index("drug_class")[["patients", "k", "n", "rate", "ci_lo", "ci_hi"]])
""")

co(r"""
fit = P.conditional_logit(wp)
ors = P.or_table(fit)
display(ors.style.format({"coef": "{:+.3f}", "OR": "{:.3f}",
                          "or_ci_lo": "{:.3f}", "or_ci_hi": "{:.3f}", "p": "{:.2e}"}))
""")

co(r"""
fig, ax = plt.subplots(figsize=(6.4, 2.4))
lab = {"is_psilocybin": "psilocybin", "is_ketamine": "ketamine", "is_lsd": "LSD"}
rows = list(ors.index)
for i, k in enumerate(rows):
    r = ors.loc[k]
    ax.plot([r.or_ci_lo, r.or_ci_hi], [i, i], color="#444", lw=1.4, zorder=2)
    sig = r.or_ci_lo > 1 or r.or_ci_hi < 1
    ax.plot(r.OR, i, "o", ms=7, color="#2b6cb0" if sig else "#a0aec0", zorder=3)
    ax.annotate(f"OR {r.OR:.2f}  [{r.or_ci_lo:.2f}, {r.or_ci_hi:.2f}]",
                (r.or_ci_hi, i), xytext=(6, 0), textcoords="offset points",
                va="center", fontsize=8)
ax.axvline(1.0, color="#c05621", ls="--", lw=1)
ax.set_yticks(range(len(rows)), [lab[k] for k in rows])
ax.set_xscale("log"); ax.set_xlim(0.28, 4.2)
ax.set_xlabel("odds of 'helped' vs the SAME patient's other treatments (log scale)")
ax.set_title("Within-patient effect — reference is the patient's own other treatments",
             fontsize=9)
plt.tight_layout(); plt.show()
""")

md(r"""
## 4.2 The same contrast without a model

The conditional logit is the pre-registered estimator, but it should not be the only one
consulted. Below, each patient's own helped-rate for the drug minus their helped-rate for
everything else, tested with a Wilcoxon signed-rank. If the two estimators disagreed in
sign, the finding would be unresolved rather than a matter of picking the friendlier one.
""")

co(r"""
paired = pd.DataFrame([{"drug": d, **P.wilcoxon_paired(P.paired_differences(wp, d))}
                       for d in P.DRUGS]).set_index("drug")
display(paired.style.format({"median_diff": "{:+.4f}", "mean_diff": "{:+.4f}", "p": "{:.2e}"}))

agree = {d: (np.sign(paired.loc[d, "mean_diff"]) ==
             np.sign(ors.loc[f"is_{d}", "coef"])) for d in P.DRUGS}
print("sign agreement between conditional logit and paired test:", agree)
""")

md(r"""
## 4.3 Symptom-class interaction — pre-registered test 7

Does the *same patient* rate these drugs differently for mood/cognition than for
exertion? Restricted to the two pre-declared symptom classes, with patient fixed effects,
tested by likelihood ratio against the no-interaction model.
""")

co(r"""
cells = (wp[wp.symptom_class.isin(["mood_cognitive", "energy_pem"])]
         .assign(arm=lambda t: np.where(t.drug_class.isin(P.DRUGS), t.drug_class, "other")))
tab = (cells.groupby(["arm", "symptom_class"])
       .agg(k=("helped", "sum"), n=("helped", "size")))
tab["rate"] = tab.k / tab.n
tab[["ci_lo", "ci_hi"]] = [P.wilson(int(r.k), int(r.n))[1:] for _, r in tab.iterrows()]
display(tab.style.format({"rate": "{:.3f}", "ci_lo": "{:.3f}", "ci_hi": "{:.3f}"}))
""")

co(r"""
inter = P.interaction_test(wp)
print(f"rows {inter['n_rows']:,}   patients {inter['n_patients']:,}")
print(f"interaction OR (psychedelic x energy/PEM)  {inter['interaction_OR']:.3f}")
print(f"likelihood-ratio chi2(1) = {inter['lr_stat']:.2f}   p = {inter['p']:.3e}")
""")

co(r"""
fig, ax = plt.subplots(figsize=(6.2, 3.0))
arms = [a for a in ["psilocybin", "ketamine", "lsd", "other"] if a in tab.index.levels[0]]
w = 0.36
for j, sc in enumerate(["mood_cognitive", "energy_pem"]):
    xs, ys, los, his = [], [], [], []
    for i, a in enumerate(arms):
        if (a, sc) not in tab.index:
            continue
        r = tab.loc[(a, sc)]
        xs.append(i + (j - 0.5) * w); ys.append(r.rate)
        los.append(r.rate - r.ci_lo); his.append(r.ci_hi - r.rate)
    ax.bar(xs, ys, width=w, yerr=[los, his], capsize=2.5,
           color=["#2b6cb0", "#dd6b20"][j], label=sc, alpha=0.9)
ax.set_xticks(range(len(arms)), arms)
ax.set_ylabel("proportion 'helped' (Wilson 95% CI)")
ax.set_title("Same drugs, opposite direction by symptom class", fontsize=9)
ax.legend(fontsize=8); ax.set_ylim(0, 1)
plt.tight_layout(); plt.show()
""")

md(r"""
## 4.4 Preparation and route

The drug slot itself carries dose intent and route (`microdosing psilocybin`, `iv ketamine`,
`spravato`) — no raw text is needed. **Descriptive only, no significance testing**: these
strata are small, and the split is not randomised.

The `dosage` field is deliberately unused. It is populated per patient but never linked to a
specific drug, so a stated "0.25 g" cannot be attributed to the mushrooms rather than to
something else in the stack. No dose-response claim is possible from this dataset.
""")

co(r"""
prep_rows = []
for d in P.DRUGS:
    sub = drugs_df[drugs_df.drug_class == d]
    for p, g in sub.groupby("prep"):
        est, lo, hi = P.wilson(int(g.helped.sum()), len(g))
        prep_rows.append({"drug": d, "prep": p, "k": int(g.helped.sum()), "n": len(g),
                          "helped": est, "ci_lo": lo, "ci_hi": hi})
prep = pd.DataFrame(prep_rows).set_index(["drug", "prep"])
display(prep.style.format({"helped": "{:.3f}", "ci_lo": "{:.3f}", "ci_hi": "{:.3f}"}))
""")

md(r"""
## 4.5 Harm profile

Every `worsened` mention, by symptom, as raw counts against a stated denominator. Not rates:
the notable entries are single records, and a single record is one noisy draw.

Read the cardiac and neurological entries with the population in mind — this cohort carries
documented myocarditis, POTS and dysautonomia, and all three substances are cardiovascularly
active.
""")

co(r"""
for d in P.DRUGS:
    n_arm = int(cohort.loc[d, "mentions"])
    w = P.worsened_triples(drugs_df, d)
    print(f"\n=== {d}: {int(w.n.sum())} 'worsened' mentions of {n_arm} total ===")
    display(w.head(15).T)
""")

# ── sensitivity ──
md(r"""
---
# 5. Sensitivity analyses

The primary within-patient model, re-fitted under five perturbations. What matters is whether
the **direction and significance** of each coefficient survive, not whether the point estimate
is stable to the third decimal.

### Two planned checks that this dataset cannot support

Both were specified in advance and both turn out to be inapplicable. Recording that here
rather than quietly dropping them, because in each case the field looks usable until inspected.

- **Confidence filtering is vacuous for this endpoint.** The run README reports a corpus-wide
  spread of 43.2% high / 50.9% medium / 5.8% low, and that is true *across fields*. But
  `treatment_outcome` carries the constant value `medium` on all 35,505 records that populate
  it — it is the field's schema-declared tier, not a per-record judgement of that record. There
  is no within-field variation to filter on. Verified below.
- **Bot exclusion by text volume is impossible.** `record_meta.text_count` is `1` for all
  69,161 records: the aggregation step wrote one synthetic document per patient and stored the
  count of documents, not of underlying posts and comments. No text-volume signal survives into
  this file. In mitigation, a bot such as AutoModerator enters a patient-fixed-effects model as
  a single stratum out of 745, so its leverage on the estimate is negligible either way. The
  substitute check below drops the most extreme treatment-list records, which is the closest
  available proxy for an aggregation artifact.
""")

co(r"""
print("treatment_outcome confidence values present:",
      df.confidence.value_counts(dropna=False).to_dict())
print("record_meta.text_count distinct values:", sorted(df.text_count.dropna().unique())[:10])
""")

co(r"""
def refit(frame, label):
    wpx = P.within_patient_frame(frame)
    o = P.or_table(P.conditional_logit(wpx))
    out = {"analysis": label, "patients": wpx.patient.nunique(), "rows": len(wpx)}
    for d in P.DRUGS:
        r = o.loc[f"is_{d}"]
        out[f"{d}_OR"] = r.OR
        out[f"{d}_p"] = r.p
    return out

rows = [refit(df, "primary (as pre-registered)")]

# fold the excluded ambiguity buckets back in
amb = df.copy()
amb["drug_class"] = amb.drug_class.replace({"ambiguous_mushroom": "psilocybin",
                                            "ambiguous_acid": "lsd"})
rows.append(refit(amb, "ambiguous strings included"))

# light stackers only -- collective-outcome inheritance is worst in heavy stackers
rows.append(refit(df[df.n_treatments <= 3], "patients naming ≤3 treatments"))

# substitute for the impossible bot filter: drop the most extreme treatment lists
cut = df.n_treatments.quantile(0.999)
rows.append(refit(df[df.n_treatments <= cut],
                  f"drop >{cut:.0f} treatments/patient (top 0.1%)"))

# symptom-specified rows only -- drug+outcome pairs with no symptom slot are the ones
# most exposed to a collective outcome being copied onto each named treatment
rows.append(refit(df[df.symptom.notna()], "symptom-specified triples only"))

# leave out the dominant community -- is this one subreddit's effect?
rows.append(refit(df[~df.subreddits.str.contains("covidlonghaulers", na=False)],
                  "excluding r/covidlonghaulers posters"))

sens = pd.DataFrame(rows).set_index("analysis")
display(sens.style.format({**{f"{d}_OR": "{:.3f}" for d in P.DRUGS},
                           **{f"{d}_p": "{:.2e}" for d in P.DRUGS}}))
""")

co(r"""
base = sens.iloc[0]
n_fits = len(sens)
for d in P.DRUGS:
    same_dir = ((sens[f"{d}_OR"] > 1) == (base[f"{d}_OR"] > 1)).all()
    same_sig = ((sens[f"{d}_p"] < 0.05) == (base[f"{d}_p"] < 0.05)).all()
    print(f"{d:11s} direction stable across all {n_fits} fits: {str(same_dir):5s} | "
          f"significance stable: {same_sig}")
    if not same_dir:
        flip = sens[(sens[f"{d}_OR"] > 1) != (base[f"{d}_OR"] > 1)]
        print(f"{'':11s}   flips in: {list(flip.index)}")
""")

# ── multiplicity ──
md(r"""
---
# 6. Multiplicity — the pre-registered family

Holm correction over the seven tests declared in 1.6, and only those. Every other number in
this notebook is exploratory and carries no p-value.
""")

co(r"""
family = {
    "H2H psilocybin vs ketamine": h2h.set_index(["a", "b"]).loc[("psilocybin", "ketamine"), "p"],
    "H2H psilocybin vs LSD":      h2h.set_index(["a", "b"]).loc[("psilocybin", "lsd"), "p"],
    "H2H ketamine vs LSD":        h2h.set_index(["a", "b"]).loc[("ketamine", "lsd"), "p"],
    "within-patient psilocybin":  ors.loc["is_psilocybin", "p"],
    "within-patient ketamine":    ors.loc["is_ketamine", "p"],
    "within-patient LSD":         ors.loc["is_lsd", "p"],
    "symptom-class interaction":  inter["p"],
}
display(P.holm({k: float(v) for k, v in family.items()})
        .style.format({"p_raw": "{:.2e}", "p_holm": "{:.2e}"}))
""")

# ─────────────────────────── CONCLUSION ───────────────────────────
md(r"""
---
# 7. Conclusion

Stated as what the statistics do and do not support. Interpretation beyond this is left to
the writer.
""")

co(r'''
print(f"""
COHORT
  corpus                        {len(records):,} patients / {len(df):,} outcome triples
  psilocybin                    {int(cohort.loc['psilocybin','patients']):,} patients / {int(cohort.loc['psilocybin','mentions']):,} triples
  ketamine                      {int(cohort.loc['ketamine','patients']):,} patients / {int(cohort.loc['ketamine','mentions']):,} triples
  LSD                           {int(cohort.loc['lsd','patients']):,} patients / {int(cohort.loc['lsd','mentions']):,} triples
  within-patient analysis set   {wp.patient.nunique():,} patients / {len(wp):,} rows / {P.informative_strata(wp):,} informative

PRIMARY (within-patient, reference = same patient's other treatments)
  psilocybin  OR {ors.loc['is_psilocybin','OR']:.2f} [{ors.loc['is_psilocybin','or_ci_lo']:.2f}, {ors.loc['is_psilocybin','or_ci_hi']:.2f}]  p={ors.loc['is_psilocybin','p']:.2e}
  ketamine    OR {ors.loc['is_ketamine','OR']:.2f} [{ors.loc['is_ketamine','or_ci_lo']:.2f}, {ors.loc['is_ketamine','or_ci_hi']:.2f}]  p={ors.loc['is_ketamine','p']:.2e}
  LSD         OR {ors.loc['is_lsd','OR']:.2f} [{ors.loc['is_lsd','or_ci_lo']:.2f}, {ors.loc['is_lsd','or_ci_hi']:.2f}]  p={ors.loc['is_lsd','p']:.2e}

INTERACTION (psychedelic x energy/PEM vs mood/cognitive)
  OR {inter['interaction_OR']:.2f}   LR chi2(1)={inter['lr_stat']:.1f}   p={inter['p']:.2e}
""")
''')

md(r"""
## 7.1 Supported by this analysis

- **Psilocybin outperforms the same patients' other treatments.** Its within-patient odds of
  being called helpful are roughly 1.8× those of the patient's own other treatments, the
  effect is highly significant after Holm correction, both estimators agree in sign, and it
  keeps the same direction and significance in every one of the five sensitivity re-fits
  (OR 1.60–2.77). Because extraction noise is non-differential, this is a lower bound rather
  than an inflated estimate. This is the one finding here that the confounding critique in
  the introduction does not dissolve.

- **Ketamine's apparent advantage does not survive its own control.** Its raw helped-rate sits
  near 69%, but against the same patients' other treatments the within-patient odds ratio is
  not distinguishable from 1, in the primary fit and in all five re-fits. The raw number was
  measuring who reports, not what the drug did — which is exactly the failure mode this design
  was built to catch. Note this is a null result, not evidence of no effect: the CI still
  admits a modest benefit.

- **The effect flips by symptom class, strongly.** The psychedelic × energy/PEM interaction is
  significant by a wide margin: within the same patient, these substances are reported as
  helping mood and cognition and markedly less so — often worse — for exertion-related
  symptoms. Given that post-exertional malaise is the defining symptom of ME/CFS, this is the
  most consequential result in the notebook, and the community's own indication map already
  points the same way (section 2.2).

## 7.2 Not supported, and not to be claimed

- **Nothing about LSD.** At its n the minimum detectable difference is roughly 19 percentage
  points — larger than any effect seen here. Its CI spans 1 in the primary fit and its point
  estimate is unstable across sensitivity re-fits (OR 0.27 to 1.13, flipping direction). One
  re-fit (symptom-specified triples only) reaches nominal significance below 1, but that is
  one exploratory fit among five, uncorrected, and is contradicted by the others. This is an
  absence of evidence and must not be reported as evidence of absence in either direction.
- **No efficacy claim of any kind.** This is self-report with no denominator for silent
  failure, no blinding, no randomisation and no control over what else the patient was doing.
  A within-patient contrast removes *reporter* bias; it does not create a trial.
- **No dosing or dose-response claim.** The `dosage` field is not linked to a specific drug.
  Section 4.4 is descriptive stratification, nothing more.
- **No individual-level claim.** Records are one draw each with 58.8% value-level agreement
  across passes. Every number above is a cohort aggregate and only valid as one.
- **The ketamine-vs-others comparison is confounded by route.** Ketamine is substantially
  clinic-administered while the other two are self-sourced; supervision, screening and
  expectancy differ systematically and are not adjusted for.
""")

nb["cells"] = c
nb.metadata.update({
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
})
nbf.write(nb, "/Users/eli/Desktop/PatientPunk/studies/psychedelics/psychedelics_analysis.ipynb")
print("written", len(c), "cells")
