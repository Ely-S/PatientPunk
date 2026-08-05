"""Cohort construction and statistics for the LSD / psilocybin / ketamine study.

Reads `data/full_corpus_2026-07-31/records_covidlonghaulers_v2.json` (the JSON, not
records.csv -- the CSV drops the per-cell confidence ratings the sensitivity analysis
needs) and turns the `treatment_outcome` triples into one tidy row per
(patient, drug string, outcome, symptom).

Import-only: nothing here reads the disk or plots until a function is called.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.discrete.conditional_models import ConditionalLogit
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import (
    confint_proportions_2indep,
    proportion_confint,
    test_proportions_2indep,
)

RECORDS_RELPATH = Path("data/full_corpus_2026-07-31/records_covidlonghaulers_v2.json")
ENV_VAR = "PP_RECORDS"

# Corpus-wide reference line (all 204,417 treatment_outcome mentions), from the run
# README. Descriptive only -- it is not a control for anything.
CORPUS_BASELINE = {
    "helped": 0.671,
    "worsened": 0.161,
    "no_effect": 0.143,
    "mixed": 0.015,
    "unknown": 0.010,
}
CORPUS_MENTIONS = 204_417
CORPUS_PATIENTS = 69_161

OUTCOMES = ("helped", "worsened", "no_effect", "mixed", "unknown")

# ── Drug slot patterns ─────────────────────────────────────────────────────
# Matched against the DRUG slot of a `drug: outcome: symptom` triple only, never
# against the whole record: 18,101 distinct treatment strings, none canonicalized.

# Verbatim from data/full_corpus_2026-07-31/analysis/psilocybin_analysis.py so the
# psilocybin arm reproduces the prior run's 538 patients exactly.
PSILOCYBIN_RE = re.compile(
    r"psilocyb|psilocin|magic mushroom|\bshrooms?\b|psychedelic mushroom", re.I
)
FUNCTIONAL_RE = re.compile(
    r"lion'?s mane|reishi|chaga|cordyceps?|cordycep|turkey tail|maitake|shiitake|wood ear",
    re.I,
)

KETAMINE_RE = re.compile(r"\bketamine\b|\besketamine\b|\bspravato\b", re.I)

# Bare "acid" MUST NOT match: alpha lipoic acid, ascorbic acid, folic acid, amino
# acid, and acid reflux are all common in this corpus and would swamp an arm this
# small (90 mentions). Every alternative below is either the drug name itself or
# "acid" bound to an unambiguous psychedelic context.
LSD_RE = re.compile(
    r"\blsd\b|lysergic|\b1c?p-?lsd\b|\bald-?52\b|\bacid tabs?\b"
    r"|\b(?:micro)?dos\w*\s+acid\b|\bacid trips?\b",
    re.I,
)

# Ambiguity buckets: reported in Methods, then excluded from every inferential fit.
AMBIG_MUSHROOM_RE = re.compile(r"\bmushroom", re.I)
AMBIG_ACID_RE = re.compile(r"\bacid\b", re.I)
# ...but these acid compounds are known non-psychedelics, not ambiguity.
KNOWN_ACID_RE = re.compile(
    r"lipoic|ascorbic|folic|amino|hyaluronic|fatty|fulvic|humic|salicylic|boric"
    r"|butyric|caprylic|citric|glutamic|malic|nicotinic|pantothenic|reflux|stomach"
    r"|uric|valproic|tranexamic|acetic|alginic|azelaic|bile|caffeic|chlorogenic"
    r"|ellagic|ferulic|gallic|glycolic|kojic|lactic|linoleic|oleic|oxalic|phosphoric"
    r"|retinoic|rosmarinic|succinic|tannic|tartaric|ursolic|arachidonic|aspartic",
    re.I,
)

DRUGS = ("psilocybin", "ketamine", "lsd")
REFERENCE_CLASS = "other"

# ── Symptom classes ────────────────────────────────────────────────────────
# Declared before any outcome was inspected. The mood/cognitive vs energy/PEM
# contrast is the pre-registered interaction; `pain` and `other` are descriptive.

MOOD_COGNITIVE = {
    "depression", "anxiety", "brain fog", "brainfog", "mood", "anhedonia",
    "mental health", "ptsd", "suicidal ideation", "cognition", "cognitive function",
    "memory", "focus", "concentration", "motivation", "depersonalization",
    "derealization", "ocd", "panic attacks", "mental clarity", "apathy",
}
ENERGY_PEM = {
    "pem", "fatigue", "energy", "crash", "crashes", "exercise intolerance",
    "post-exertional malaise", "post exertional malaise", "stamina", "exhaustion",
    "energy levels", "fatigue and pem", "pem/crashes", "tiredness",
}
PAIN_RE = re.compile(r"\bpain\b|\bache|migraine|headache|neuralgia|fibromyalgia", re.I)


# ── Loading ────────────────────────────────────────────────────────────────

def records_path(start: Path | None = None) -> Path:
    """Absolute path to the records JSON. `PP_RECORDS` overrides discovery."""
    env = os.environ.get(ENV_VAR)
    if env:
        p = Path(env).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(f"{ENV_VAR}={env!r} does not point to a file ({p})")
        return p

    here = Path(start).resolve() if start else Path.cwd().resolve()
    for d in [here, *here.parents]:
        candidate = d / RECORDS_RELPATH
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"Could not find {RECORDS_RELPATH} walking up from {here}.\n"
        f"Run from inside the PatientPunk repo, or set {ENV_VAR} to an absolute path."
    )


def load_records(path: Path | None = None) -> list[dict]:
    """Load the 69,161 patient records (~275 MB JSON, a few seconds)."""
    return json.load(open(path or records_path()))


def _values(fields: dict, name: str) -> list[str]:
    v = (fields.get(name) or {}).get("values")
    if not v:
        return []
    return [v] if isinstance(v, str) else list(v)


# ── Cohort assignment ──────────────────────────────────────────────────────

def classify_drug(drug_string: str) -> str:
    """Map a drug slot to one of the three arms, an ambiguity bucket, or `other`.

    Order matters. Functional mushrooms (lion's mane, reishi, ...) are ruled out
    before any mushroom test, so they never reach the psilocybin arm.
    """
    s = drug_string
    if KETAMINE_RE.search(s):
        return "ketamine"
    if LSD_RE.search(s):
        return "lsd"
    if FUNCTIONAL_RE.search(s) and not PSILOCYBIN_RE.search(s):
        return REFERENCE_CLASS
    if PSILOCYBIN_RE.search(s):
        return "psilocybin"
    if AMBIG_MUSHROOM_RE.search(s):
        return "ambiguous_mushroom"
    if AMBIG_ACID_RE.search(s) and not KNOWN_ACID_RE.search(s):
        return "ambiguous_acid"
    return REFERENCE_CLASS


def classify_symptom(symptom: str | None) -> str:
    if not symptom:
        return "unspecified"
    s = symptom.strip().lower()
    if s in MOOD_COGNITIVE:
        return "mood_cognitive"
    if s in ENERGY_PEM:
        return "energy_pem"
    if PAIN_RE.search(s):
        return "pain"
    return "other"


def build_outcome_table(records: list[dict]) -> pd.DataFrame:
    """One row per (patient, drug string, outcome, symptom) triple.

    Asserts the run README's claim that every `treatment_outcome` value parses --
    a silent parse failure would quietly shrink an arm, so it fails loudly instead.
    """
    rows, unparseable = [], []
    for i, rec in enumerate(records):
        fields = rec.get("fields", {})
        vals = _values(fields, "treatment_outcome")
        if not vals:
            continue
        meta = rec.get("record_meta", {})
        pid = meta.get("author_hash") or f"_norow_{i}"
        conf = (fields.get("treatment_outcome") or {}).get("confidence")
        subs = " ".join(
            p.split(":")[0] for p in (meta.get("subreddits") or "").split()
        )
        for raw in vals:
            parts = [p.strip().lower() for p in raw.split(":")]
            if len(parts) < 2 or not parts[0] or parts[1] not in OUTCOMES:
                unparseable.append(raw)
                continue
            drug, outcome = parts[0], parts[1]
            symptom = parts[2] if len(parts) >= 3 and parts[2] else None
            rows.append(
                {
                    "patient": pid,
                    "drug_string": drug,
                    "drug_class": classify_drug(drug),
                    "outcome": outcome,
                    "helped": int(outcome == "helped"),
                    "no_effect": int(outcome == "no_effect"),
                    "symptom": symptom,
                    "symptom_class": classify_symptom(symptom),
                    "confidence": conf,
                    "subreddits": subs,
                    "text_count": meta.get("text_count"),
                }
            )

    if unparseable:
        raise AssertionError(
            f"{len(unparseable)} treatment_outcome values did not parse as "
            f"'drug: outcome[: symptom]' with a known outcome. First 5: {unparseable[:5]}"
        )

    df = pd.DataFrame(rows)
    df["n_treatments"] = df.groupby("patient")["drug_string"].transform("nunique")
    return df


MENTION_FIELDS = ("treatment_outcome", "medications", "alternative_treatments")


def mention_cohort(records: list[dict]) -> pd.DataFrame:
    """Patients naming each drug ANYWHERE, not just in a scored outcome triple.

    Reconciles this study's denominators with the prior psilocybin run, which
    counted any mention across treatment_outcome / medications /
    alternative_treatments and reported 538 psilocybin patients. Naming a drug is
    not the same as reporting how it went, so every analysis below uses the
    smaller triple-level cohort; this function exists to show the gap explicitly.
    """
    counts = {k: set() for k in DRUGS}
    for i, rec in enumerate(records):
        fields = rec.get("fields", {})
        pid = rec.get("record_meta", {}).get("author_hash") or f"_norow_{i}"
        blob = [s for f in MENTION_FIELDS for s in _values(fields, f)]
        for s in blob:
            c = classify_drug(s)
            if c in counts:
                counts[c].add(pid)
    return pd.DataFrame(
        [{"drug_class": k, "patients_mentioning": len(v)} for k, v in counts.items()]
    ).sort_values("patients_mentioning", ascending=False).reset_index(drop=True)


def cohort_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Patients and mentions per arm, including the excluded ambiguity buckets."""
    g = df.groupby("drug_class")
    out = pd.DataFrame(
        {"patients": g["patient"].nunique(), "mentions": g.size()}
    ).sort_values("mentions", ascending=False)
    out["pct_of_corpus_patients"] = 100 * out["patients"] / CORPUS_PATIENTS
    return out


def within_patient_frame(
    df: pd.DataFrame, drugs: tuple[str, ...] = DRUGS
) -> pd.DataFrame:
    """Rows for patients who reported BOTH a study drug and some other treatment.

    This is the analysis set for the primary comparison: the comparator is the
    patient's own other treatments, so patient-level optimism, severity and
    reporting style are held fixed.
    """
    keep = df[df["drug_class"].isin([*drugs, REFERENCE_CLASS])].copy()
    has_drug = keep.groupby("patient")["drug_class"].transform(
        lambda s: s.isin(drugs).any()
    )
    has_other = keep.groupby("patient")["drug_class"].transform(
        lambda s: (s == REFERENCE_CLASS).any()
    )
    return keep[has_drug & has_other].copy()


# ── Preparation and route, read off the drug slot ──────────────────────────
# The community encodes dose intent and route in the drug name itself
# ("microdosing psilocybin", "iv ketamine", "spravato"). No raw text needed.
# The `dosage` field is NOT usable here: it is populated per patient and never
# linked to a specific drug, so a stated "0.25 g" cannot be attributed to the
# mushrooms rather than to something else in the stack.

MICRODOSE_RE = re.compile(r"microdos|micro-dos|\bmicro dose", re.I)
CLINICAL_RE = re.compile(
    r"\bspravato\b|\besketamine\b|\biv\b|\bi\.v\.|infusion|clinic|intramuscular|\bim\b"
    r"|nasal|troche|lozenge|sublingual|prescri",
    re.I,
)


def prep_label(drug_string: str, drug_class: str) -> str:
    """Dose intent / route as stated in the drug slot, else `unspecified`."""
    if MICRODOSE_RE.search(drug_string):
        return "microdose"
    if drug_class == "ketamine" and CLINICAL_RE.search(drug_string):
        return "clinical_route"
    return "unspecified"


def add_prep(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["prep"] = [
        prep_label(s, c) for s, c in zip(out["drug_string"], out["drug_class"])
    ]
    return out


def worsened_triples(df: pd.DataFrame, drug: str) -> pd.DataFrame:
    """Every `worsened` mention for one drug, by symptom.

    Reported as raw counts against a stated denominator, never as a rate: the
    notable entries (seizure, cardiac stress) are single records, and per-record
    extraction is one noisy draw.
    """
    sub = df[(df["drug_class"] == drug) & (df["outcome"] == "worsened")]
    return (
        sub.groupby(sub["symptom"].fillna("(unspecified)"))
        .size()
        .sort_values(ascending=False)
        .rename("n")
        .to_frame()
    )


# ── Statistics ─────────────────────────────────────────────────────────────

def wilson(count: int, nobs: int) -> tuple[float, float, float]:
    """Point estimate and Wilson 95% CI. Every rate in this study reports one."""
    if nobs == 0:
        return (np.nan, np.nan, np.nan)
    lo, hi = proportion_confint(count, nobs, alpha=0.05, method="wilson")
    return (count / nobs, lo, hi)


def rate_table(df: pd.DataFrame, by: str = "drug_class", col: str = "helped") -> pd.DataFrame:
    """Per-group rate of `col` with Wilson CIs and denominators attached."""
    rows = []
    for key, sub in df.groupby(by):
        est, lo, hi = wilson(int(sub[col].sum()), len(sub))
        rows.append(
            {
                by: key,
                "k": int(sub[col].sum()),
                "n": len(sub),
                "rate": est,
                "ci_lo": lo,
                "ci_hi": hi,
                "patients": sub["patient"].nunique(),
            }
        )
    return pd.DataFrame(rows).sort_values("n", ascending=False).reset_index(drop=True)


def compare_two(df: pd.DataFrame, a: str, b: str, col: str = "helped") -> dict:
    """Head-to-head on `col`: risk difference with a Newcombe CI, plus a p-value.

    Uses Fisher's exact when any cell is small, chi-square otherwise -- the LSD arm
    (90 mentions) routinely trips the small-cell condition.
    """
    from scipy import stats

    sa, sb = df[df["drug_class"] == a], df[df["drug_class"] == b]
    ka, na = int(sa[col].sum()), len(sa)
    kb, nb = int(sb[col].sum()), len(sb)
    table = [[ka, na - ka], [kb, nb - kb]]
    small = min(min(r) for r in table) < 5
    if small:
        _, p = stats.fisher_exact(table)
        test = "fisher"
    else:
        p = float(test_proportions_2indep(ka, na, kb, nb, compare="diff").pvalue)
        test = "z-test (diff)"
    lo, hi = confint_proportions_2indep(ka, na, kb, nb, compare="diff", method="newcomb")
    return {
        "a": a, "b": b, "k_a": ka, "n_a": na, "k_b": kb, "n_b": nb,
        "rate_a": ka / na if na else np.nan,
        "rate_b": kb / nb if nb else np.nan,
        "risk_diff": (ka / na - kb / nb) if na and nb else np.nan,
        "rd_ci_lo": lo, "rd_ci_hi": hi, "test": test, "p": p,
    }


def conditional_logit(
    df: pd.DataFrame, drugs: tuple[str, ...] = DRUGS, outcome_col: str = "helped"
):
    """Patient-fixed-effects logit: `outcome ~ drug dummies`, reference = other.

    Patients whose outcomes are all identical contribute nothing to the likelihood
    (they are the concordant strata) and are dropped by the estimator. The result is
    a within-patient odds ratio: how much more often a patient calls THIS drug
    helpful than they call their OWN other treatments helpful.
    """
    d = df[df["drug_class"].isin([*drugs, REFERENCE_CLASS])].copy()
    exog = pd.DataFrame(
        {f"is_{k}": (d["drug_class"] == k).astype(float) for k in drugs},
        index=d.index,
    )
    return ConditionalLogit(d[outcome_col].astype(float), exog, groups=d["patient"]).fit(
        disp=False
    )


def or_table(result) -> pd.DataFrame:
    """Odds ratios with 95% CIs from a fitted conditional logit."""
    ci = result.conf_int()
    return pd.DataFrame(
        {
            "coef": result.params,
            "OR": np.exp(result.params),
            "or_ci_lo": np.exp(ci[0]),
            "or_ci_hi": np.exp(ci[1]),
            "p": result.pvalues,
        }
    )


def informative_strata(df: pd.DataFrame, outcome_col: str = "helped") -> int:
    """Patients with a mix of outcomes -- the only ones the fixed-effects fit uses."""
    g = df.groupby("patient")[outcome_col].nunique()
    return int((g > 1).sum())


def paired_differences(
    df: pd.DataFrame, drug: str, outcome_col: str = "helped"
) -> pd.DataFrame:
    """Per patient: their rate for `drug` minus their rate for everything else.

    The legible companion to the conditional logit. If the two disagree in sign the
    finding is unresolved, not a matter of picking the friendlier estimator.
    """
    d = df[df["drug_class"].isin([drug, REFERENCE_CLASS])]
    piv = (
        d.groupby(["patient", "drug_class"])[outcome_col]
        .mean()
        .unstack("drug_class")
        .dropna(subset=[drug, REFERENCE_CLASS])
    )
    piv["diff"] = piv[drug] - piv[REFERENCE_CLASS]
    return piv


def wilcoxon_paired(piv: pd.DataFrame) -> dict:
    from scipy import stats

    d = piv["diff"].to_numpy()
    nonzero = d[d != 0]
    if len(nonzero) < 5:
        return {"n_pairs": len(d), "n_nonzero": len(nonzero), "median_diff": float(np.median(d)), "p": np.nan}
    res = stats.wilcoxon(nonzero)
    return {
        "n_pairs": len(d),
        "n_nonzero": len(nonzero),
        "median_diff": float(np.median(d)),
        "mean_diff": float(np.mean(d)),
        "p": float(res.pvalue),
    }


def interaction_test(df: pd.DataFrame, drugs: tuple[str, ...] = DRUGS) -> dict:
    """Pre-registered 1-df test: does the psychedelic effect flip by symptom class?

    Restricted to the two pre-declared classes (mood_cognitive vs energy_pem) and
    fitted with patient fixed effects, so it asks whether the SAME patient rates
    these drugs differently for mood than for exertion.
    """
    d = df[df["symptom_class"].isin(["mood_cognitive", "energy_pem"])].copy()
    d = d[d["drug_class"].isin([*drugs, REFERENCE_CLASS])]
    d["psychedelic"] = d["drug_class"].isin(drugs).astype(float)
    d["energy"] = (d["symptom_class"] == "energy_pem").astype(float)
    d["psy_x_energy"] = d["psychedelic"] * d["energy"]

    full = ConditionalLogit(
        d["helped"].astype(float),
        d[["psychedelic", "energy", "psy_x_energy"]],
        groups=d["patient"],
    ).fit(disp=False)
    reduced = ConditionalLogit(
        d["helped"].astype(float),
        d[["psychedelic", "energy"]],
        groups=d["patient"],
    ).fit(disp=False)

    from scipy import stats

    lr = 2 * (full.llf - reduced.llf)
    return {
        "n_rows": len(d),
        "n_patients": d["patient"].nunique(),
        "interaction_coef": float(full.params["psy_x_energy"]),
        "interaction_OR": float(np.exp(full.params["psy_x_energy"])),
        "lr_stat": float(lr),
        "p": float(stats.chi2.sf(lr, 1)),
        "full": full,
    }


def holm(pvalues: dict[str, float]) -> pd.DataFrame:
    """Holm correction over the pre-registered family of 7 tests."""
    keys = list(pvalues)
    raw = [pvalues[k] for k in keys]
    reject, adj, _, _ = multipletests(raw, alpha=0.05, method="holm")
    return pd.DataFrame(
        {"test": keys, "p_raw": raw, "p_holm": adj, "significant": reject}
    ).sort_values("p_raw").reset_index(drop=True)


def mde(baseline: float, n_per_arm: int, power: float = 0.80) -> float:
    """Minimum detectable risk difference, for pre-declaring that LSD is underpowered."""
    from scipy import stats

    za = stats.norm.ppf(0.975)
    zb = stats.norm.ppf(power)
    return float((za + zb) * np.sqrt(2 * baseline * (1 - baseline) / n_per_arm))
