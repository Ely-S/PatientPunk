"""Cohort construction and statistics for the LSD / psilocybin / ketamine study.

Reads `data/full_corpus_2026-07-31/records_covidlonghaulers_v2.json` (the JSON, not
records.csv -- the CSV drops the per-cell confidence ratings the sensitivity analysis
needs) and turns the `treatment_outcome` triples into one tidy row per
(patient, drug string, outcome, symptom).

Import-only: nothing here reads the disk or plots until a function is called.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
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

# The raw scrape the extraction ran on. Only the testimonial layer (section 8) reads
# it; every section before that uses the extracted records alone.
REDDIT_DB_RELPATH = Path("reddit_2026-06-13.db")
DB_ENV_VAR = "PP_REDDIT_DB"

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


def mention_pairs(records: list[dict], *, require_author_hash: bool = False) -> pd.DataFrame:
    """Distinct ``(author_hash, drug_class)`` pairs naming a study drug.

    ``require_author_hash`` is used by raw-text joins, where a synthetic fallback ID
    cannot be linked to a Reddit author.  The historical summary keeps its fallback
    behavior so existing notebook counts remain unchanged.
    """
    pairs: set[tuple[str, str]] = set()
    missing: list[int] = []
    for i, rec in enumerate(records):
        fields = rec.get("fields", {})
        pid = rec.get("record_meta", {}).get("author_hash")
        blob = [s for f in MENTION_FIELDS for s in _values(fields, f)]
        classes = {classify_drug(s) for s in blob}
        study_classes = classes.intersection(DRUGS)
        if not study_classes:
            continue
        if not pid:
            if require_author_hash:
                missing.append(i)
                continue
            pid = f"_norow_{i}"
        pairs.update((pid, drug_class) for drug_class in study_classes)
    if missing:
        raise ValueError(
            f"{len(missing)} psychedelic-mentioning records lack author_hash; "
            f"first record indexes: {missing[:5]}"
        )
    return pd.DataFrame(
        sorted(pairs), columns=["author_hash", "drug_class"]
    )


def mention_cohort(records: list[dict]) -> pd.DataFrame:
    """Patients naming each drug ANYWHERE, not just in a scored outcome triple.

    Reconciles this study's denominators with the prior psilocybin run, which
    counted any mention across treatment_outcome / medications /
    alternative_treatments and reported 538 psilocybin patients. Naming a drug is
    not the same as reporting how it went, so every analysis below uses the
    smaller triple-level cohort; this function exists to show the gap explicitly.
    """
    pairs = mention_pairs(records)
    return pd.DataFrame(
        [
            {
                "drug_class": drug_class,
                "patients_mentioning": int(
                    pairs.loc[pairs["drug_class"] == drug_class, "author_hash"].nunique()
                ),
            }
            for drug_class in DRUGS
        ]
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


# ── Ketamine route ─────────────────────────────────────────────────────────
# Finer than prep_label's single `clinical_route` bucket, which lumps IV infusion
# in with intranasal esketamine and at-home sublingual troches. Those differ in
# supervision, screening, cost and bioavailability, so the lump is not one exposure.
# The ketamine arm has only 17 distinct drug strings, so these patterns were written
# against the complete observed set rather than guessed -- see route_coverage().

IV_RE = re.compile(r"\biv\b|\bi\.v\.|\binfusion|intravenous", re.I)
INTRANASAL_RE = re.compile(r"spravato|esketamine|nasal|spray", re.I)
SUBLINGUAL_RE = re.compile(r"troche|lozenge|sublingual", re.I)
TOPICAL_RE = re.compile(r"topical|lotion|cream", re.I)


def ketamine_route(drug_string: str) -> str:
    """Route of administration as stated in the drug slot, else `unspecified`.

    IV first: `iv ketamine` and `ketamine infusion therapy` are the same exposure.
    Intranasal before sublingual so `spravato` is never read as an at-home form.
    """
    s = drug_string
    if IV_RE.search(s):
        return "iv_infusion"
    if INTRANASAL_RE.search(s):
        return "intranasal"
    if SUBLINGUAL_RE.search(s):
        return "sublingual"
    if TOPICAL_RE.search(s):
        return "topical"
    return "unspecified"


def add_ketamine_route(df: pd.DataFrame) -> pd.DataFrame:
    """Add a `route` column: the ketamine taxonomy, `n/a` for every other arm."""
    out = df.copy()
    out["route"] = [
        ketamine_route(s) if c == "ketamine" else "n/a"
        for s, c in zip(out["drug_string"], out["drug_class"])
    ]
    return out


def route_coverage(df: pd.DataFrame) -> pd.DataFrame:
    """Every distinct ketamine string and the route it was assigned.

    The audit fixture for the taxonomy. The arm is small enough to read in full,
    so route assignment is verifiable by eye rather than taken on trust.
    """
    k = df[df["drug_class"] == "ketamine"]
    out = (
        k.groupby("drug_string")
        .agg(mentions=("helped", "size"), patients=("patient", "nunique"))
        .reset_index()
    )
    out.insert(0, "route", out["drug_string"].map(ketamine_route))
    return out.sort_values(["route", "mentions"], ascending=[True, False]).reset_index(
        drop=True
    )


def route_within_patient(
    df_wp: pd.DataFrame, route: str = "iv_infusion", outcome_col: str = "helped"
):
    """Within-patient fit for ONE ketamine route against the patient's own others.

    Splits the ketamine arm so the target route is its own regressor and all other
    ketamine is a separate nuisance term -- otherwise the reference class would
    silently absorb the rest of the ketamine arm and the contrast would no longer
    be route-vs-other-treatments.

    Returns (result, diagnostics). ALWAYS read the diagnostics: at this arm's size
    the estimate can be extremely underpowered, and a wide CI here is the finding.
    """
    d = add_ketamine_route(df_wp)
    target = (d["drug_class"] == "ketamine") & (d["route"] == route)
    other_k = (d["drug_class"] == "ketamine") & (d["route"] != route)

    exog = pd.DataFrame(
        {
            f"is_{route}": target.astype(float),
            "is_ketamine_other": other_k.astype(float),
            "is_psilocybin": (d["drug_class"] == "psilocybin").astype(float),
            "is_lsd": (d["drug_class"] == "lsd").astype(float),
        },
        index=d.index,
    )
    res = ConditionalLogit(
        d[outcome_col].astype(float), exog, groups=d["patient"]
    ).fit(disp=False)

    pts = set(d.loc[target, "patient"])
    contrib = d[d["patient"].isin(pts)]
    diag = {
        "route": route,
        "rows": int(target.sum()),
        "patients": len(pts),
        "informative_strata": informative_strata(contrib, outcome_col),
        "helped": int(d.loc[target, outcome_col].sum()),
    }
    return res, diag


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


# ── Descriptive helpers ────────────────────────────────────────────────────
# Support for the narrative sections. All of these are counts and shares; none of
# them feeds an inferential fit.

def naming_vocabulary(df: pd.DataFrame, drug: str, n: int = 12) -> pd.DataFrame:
    """The exact strings patients used for one arm, by number of patients using them.

    Nothing is canonicalized upstream, so this is the community's own nomenclature
    rather than a drug dictionary's.
    """
    sub = df[df["drug_class"] == drug]
    out = (
        sub.groupby("drug_string")
        .agg(patients=("patient", "nunique"), mentions=("helped", "size"))
        .sort_values("patients", ascending=False)
        .head(n)
    )
    out["pct_of_arm_patients"] = 100 * out["patients"] / sub["patient"].nunique()
    return out


def stack_sizes(df: pd.DataFrame) -> pd.DataFrame:
    """Treatments named per patient, split by whether they named a study drug.

    One row per patient. `n_treatments` counts distinct drug strings in their record,
    so it measures how much of their treatment history they wrote down.
    """
    flag = df.groupby("patient")["drug_class"].apply(
        lambda s: "names a psychedelic" if s.isin(DRUGS).any() else "everyone else"
    )
    size = df.groupby("patient")["drug_string"].nunique()
    return pd.DataFrame({"n_treatments": size, "group": flag}).reset_index()


def co_treatments(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """What else is in the stack of patients who name a psychedelic.

    Restricted to their non-psychedelic treatments, so it describes the company these
    substances keep rather than the substances themselves.
    """
    pts = df.loc[df["drug_class"].isin(DRUGS), "patient"].unique()
    sub = df[df["patient"].isin(pts) & (df["drug_class"] == REFERENCE_CLASS)]
    out = (
        sub.groupby("drug_string")
        .agg(patients=("patient", "nunique"), helped=("helped", "mean"))
        .sort_values("patients", ascending=False)
        .head(n)
    )
    out["pct_of_psychedelic_patients"] = 100 * out["patients"] / len(pts)
    return out


def arm_overlap(df: pd.DataFrame) -> pd.DataFrame:
    """How many of the three substances a single patient reports on."""
    per = df[df["drug_class"].isin(DRUGS)].groupby("patient")["drug_class"].apply(
        lambda s: tuple(sorted(set(s)))
    )
    out = per.value_counts().rename("patients").to_frame()
    out.index = ["+".join(k) for k in out.index]
    out["n_substances"] = [k.count("+") + 1 for k in out.index]
    return out.sort_values(["n_substances", "patients"], ascending=[True, False])


def symptom_matrix(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    """Top named symptoms by arm, as each arm's share of its own symptom-named rows.

    Column-normalized so the arms are comparable despite very different sizes -- this
    is the community's indication map, not a volume chart.
    """
    sub = df[df["drug_class"].isin(DRUGS) & df["symptom"].notna()]
    top = sub["symptom"].value_counts().head(n).index
    tab = (
        sub[sub["symptom"].isin(top)]
        .groupby(["symptom", "drug_class"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=top, columns=list(DRUGS), fill_value=0)
    )
    return 100 * tab / tab.sum(axis=0)


def own_stack_rank(df: pd.DataFrame, drug: str) -> pd.DataFrame:
    """Per patient: their helped-rate for `drug` against their own stack's rate.

    The legible form of the within-patient contrast -- one point per patient, with the
    stack size attached so heavy and light experimenters can be told apart.
    """
    piv = paired_differences(df, drug)
    stack = df.groupby("patient")["drug_string"].nunique().rename("n_treatments")
    return piv.join(stack, how="left")


# Ordered so a bar chart reads worst-to-best rather than alphabetically.
FUNCTIONAL_TIERS = ("mostly_functional", "mild", "moderate", "severe",
                    "housebound", "bedbound")
TRAJECTORIES = ("recovered", "improving", "stable", "relapsing", "worsening")


def field_profile(
    records: list[dict],
    df: pd.DataFrame,
    field: str,
    values: tuple[str, ...] | None = None,
    conditional: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Who names a psychedelic, on one extracted field, against everyone else.

    The universe is the outcome-triple cohort only, so both groups are patients who
    reported at least one treatment outcome and differ in nothing else structural.

    `conditional=True` restricts the denominator to patients whose record populates
    the field at all -- right for a single-valued closed vocabulary like
    `functional_status_tier`, where a missing value means "never stated". For an
    open multi-valued field like `mental_health`, pass False and read the result as
    "share whose record names this", never as prevalence: silence is not absence.
    """
    psy = set(df.loc[df["drug_class"].isin(DRUGS), "patient"])
    universe = set(df["patient"])
    groups = {"names a psychedelic": [], "everyone else": []}
    for rec in records:
        pid = rec.get("record_meta", {}).get("author_hash")
        if pid not in universe:
            continue
        vals = {v.strip().lower() for v in _values(rec.get("fields", {}), field)}
        if conditional and not vals:
            continue
        groups["names a psychedelic" if pid in psy else "everyone else"].append(vals)

    keys = values or tuple(
        pd.Series([v for g in groups.values() for vals in g for v in vals])
        .value_counts().head(12).index
    )
    out = pd.DataFrame(
        {g: [100 * sum(k in vals for vals in rows) / len(rows) for k in keys]
         for g, rows in groups.items()},
        index=list(keys),
    )
    return out, {g: len(rows) for g, rows in groups.items()}


# ── The testimonial layer: raw post and comment text ───────────────────────
# Sections 1-7 never leave the extracted records, where an outcome is one of five
# words and carries no magnitude. Section 8 reads the underlying scrape, because a
# claim's STRENGTH exists only in the text the patient actually wrote.
#
# Everything here is regex over sentences. No LLM is involved, so it is deterministic
# and re-runnable at zero cost -- and correspondingly blunt. `detector_audit()` exists
# so the bluntness is measurable rather than assumed.

def reddit_db_path(start: Path | None = None) -> Path:
    """Absolute path to the raw scrape. `PP_REDDIT_DB` overrides discovery."""
    env = os.environ.get(DB_ENV_VAR)
    if env:
        p = Path(env).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(f"{DB_ENV_VAR}={env!r} does not point to a file ({p})")
        return p

    here = Path(start).resolve() if start else Path.cwd().resolve()
    for d in [here, *here.parents]:
        candidate = d / REDDIT_DB_RELPATH
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"Could not find {REDDIT_DB_RELPATH} walking up from {here}.\n"
        f"Set {DB_ENV_VAR} to an absolute path, or skip section 8."
    )


def open_reddit(path: Path | None = None) -> sqlite3.Connection:
    """Read-only connection to the scrape. FTS5 indexes are already built."""
    p = path or reddit_db_path()
    return sqlite3.connect(f"file:{p}?mode=ro", uri=True)


def author_hash(name: str) -> str:
    """The record_meta.author_hash for a Reddit username.

    Verified against the extracted records: the aggregation step hashed the username
    verbatim, so raw text joins back to a patient record on this key.
    """
    return hashlib.sha256(name.encode()).hexdigest()


# Sentence-level gates. A claim counts only if the patient is describing themselves.
FIRST_PERSON_RE = re.compile(r"\b(i|i'?ve|i'?m|i'?d|i'?ll|my|me|myself)\b", re.I)

# Someone else's outcome is not this patient's testimony. Second person is here too:
# "you'd be amazed" and "if you've read that it cured people" are both advice, not report.
THIRD_PARTY_RE = re.compile(
    r"\b(my (friend|wife|husband|partner|mum|mom|dad|father|mother|sister|brother|son|"
    r"daughter|doctor|therapist|neighbou?r|coworker|colleague)|"
    r"a friend|someone|somebody|some (guy|people|person|folks)|"
    r"other people|a lot of people|many people|lots of people|"
    r"i('ve| have)? (heard|read|seen)|you('ve| have|d| would|r)?\s|your |"
    r"people (say|report|claim|cured|recover\w*|heal\w*)|"
    r"this (guy|woman|man|person)|he |she |they (cured|report|say|claim)|"
    r"the creator|on tiktok|on youtube|a study|studies|research (shows|suggests)|trial)\b",
    re.I,
)

# Negation and irrealis. "it was not a miracle" and "I hope it is life-changing" both
# contain a strong marker and neither is a strong claim.
NEGATION_RE = re.compile(
    r"\b(not|n'?t|no|never|hardly|barely|nothing|didn'?t|doesn'?t|wasn'?t|isn'?t|"
    r"haven'?t|hasn'?t|won'?t|wouldn'?t|hope|hoping|wish|if|would|could|might|maybe|"
    r"planning|considering|thinking about|want to|going to|curious|plan to)\b",
    re.I,
)

STRONG_POS_RE = re.compile(
    r"life[- ]?chang\w+|chang\w+ my life|gave me my life back|sav\w+ my life|"
    r"complete(ly)? (gone|resolved|cured|better|lifted)|cured|remission|"
    r"night and day|miracle|miraculous|game[- ]?chang\w+|transform\w+|profound\w*|"
    # "of my symptoms", never bare "of" -- that matched "insurance covers 95% of it".
    r"\b(7[5-9]|8[0-9]|9[0-9]|100)\s?%\s?(better|improvement|improved|recovered|gone|of my)|"
    r"the only thing that (has )?(ever )?(help|work)\w*|"
    # "back to baseline" is deliberately NOT here. In this community baseline is the
    # illness, so the phrase reports an effect wearing off -- MODERATE_RE catches it.
    r"back to (normal|myself|my old self)|"
    r"dramatic\w* (improv|better|help)\w*|massive\w* (improv|help)\w*|"
    r"huge (difference|improvement|change)|"
    r"out of bed for the first time|best thing i'?ve ever (done|tried)|"
    r"single (biggest|best) thing",
    re.I,
)

# Deliberately built to roughly the same breadth as STRONG_POS_RE. An asymmetric pair
# of pattern lists would manufacture the finding that strong claims are mostly
# positive; detector_audit() reports the imbalance that remains.
STRONG_NEG_RE = re.compile(
    r"worst (thing|mistake|decision|experience)|set me back (months|years|weeks|\d)|"
    r"never again|permanent(ly)? (worse|damage|disab\w+)|ruined me|ruined my life|"
    r"crash\w* for (weeks|months)|made (me|it|everything|things) (so much |way |much )?worse|"
    r"land\w+ me in (the )?(hospital|er)|regret \w*ing (it|that)|biggest regret|"
    r"sent me into a (crash|flare|relapse|spiral)|wrecked me|destroyed me|"
    r"trauma(tis|tiz)\w+ me|triggered (a|my) (crash|flare|relapse|pem)|"
    r"worse than ever|severe(ly)? (crash|worse|setback)|"
    r"took me (months|weeks) to recover|bedbound (for|since|after)",
    re.I,
)

# The middle of the scale: a real but bounded or temporary effect. Its size is the
# check on whether the detector is simply finding enthusiasm everywhere.
MODERATE_RE = re.compile(
    r"\b(slightly|a little|a bit|somewhat|marginal\w*|mild(ly)?|temporar\w+|"
    r"short[- ]?lived|wore off|back to baseline|not a (miracle|cure)|"
    r"some (improvement|benefit|help)|helped a bit|"
    r"for a (few|couple of|couple) (days|hours|weeks))\b",
    re.I,
)

# Link roundups and table posts by aggregator bots are not testimony.
BOTLIKE_RE = re.compile(r"\\?#\d+:\s*\[|^\s*\|.*\|.*\|", re.I | re.M)
BOT_AUTHORS = frozenset({
    "AutoModerator", "[deleted]", "sneakpeekbot", "RemindMeBot", "B0tRank",
    "WikiTextBot", "SubredditLinkBot", "totesmessenger", "None",
})

SENTENCE_RE = re.compile(r"(?<=[.!?\n])\s+")

CLAIM_KINDS = ("strong_pos", "strong_neg", "moderate")

# label -> (FTS5 query, regex over the sentence, category)
# The FTS query is a recall net; the regex is what actually decides a match, so the
# query can be loose. Comparators were picked as the treatments this community talks
# about most, across both pharmaceuticals and supplements, not for their results.
TESTIMONY_TARGETS: dict[str, tuple[str, re.Pattern, str]] = {
    "psilocybin": ("psilocybin OR psilocin OR shrooms OR shroom OR mushrooms OR truffles",
                   re.compile(r"psilocyb|psilocin|magic mushroom|\bshrooms?\b"
                              r"|psychedelic mushroom|magic truffle", re.I), "psychedelic"),
    "ketamine": ("ketamine OR esketamine OR spravato",
                 re.compile(r"\bketamine\b|\besketamine\b|\bspravato\b", re.I), "psychedelic"),
    "LSD": ("lsd OR lysergic",
            re.compile(r"\blsd\b|lysergic|\b1c?p-?lsd\b|\bald-?52\b|\bacid tabs?\b"
                       r"|\bacid trips?\b", re.I), "psychedelic"),
    "LDN": ('ldn OR naltrexone', re.compile(r"\bldn\b|naltrexone", re.I), "prescription"),
    "mestinon": ("mestinon OR pyridostigmine",
                 re.compile(r"mestinon|pyridostigmine", re.I), "prescription"),
    "beta blocker": ("propranolol OR metoprolol OR bisoprolol OR ivabradine",
                     re.compile(r"propranolol|metoprolol|bisoprolol|ivabradine", re.I),
                     "prescription"),
    "SSRI / SNRI": ("sertraline OR fluoxetine OR escitalopram OR duloxetine OR lexapro "
                    "OR zoloft OR prozac OR cymbalta",
                    re.compile(r"sertraline|fluoxetine|escitalopram|duloxetine|lexapro"
                               r"|zoloft|prozac|cymbalta", re.I), "prescription"),
    "antihistamine": ("famotidine OR cetirizine OR loratadine OR fexofenadine OR zyrtec "
                      "OR pepcid OR claritin",
                      re.compile(r"famotidine|cetirizine|loratadine|fexofenadine|zyrtec"
                                 r"|pepcid|claritin", re.I), "prescription"),
    "valacyclovir": ("valtrex OR valacyclovir",
                     re.compile(r"valtrex|valacyclovir", re.I), "prescription"),
    "Paxlovid": ("paxlovid OR nirmatrelvir",
                 re.compile(r"paxlovid|nirmatrelvir", re.I), "prescription"),
    "metformin": ("metformin", re.compile(r"\bmetformin\b", re.I), "prescription"),
    "rapamycin": ("rapamycin OR sirolimus",
                  re.compile(r"rapamycin|sirolimus", re.I), "prescription"),
    "modafinil": ("modafinil OR armodafinil OR provigil",
                  re.compile(r"modafinil|provigil", re.I), "prescription"),
    "nicotine patch": ('nicotine', re.compile(r"nicotine (patch|patches)", re.I), "other"),
    "HBOT": ("hbot OR hyperbaric",
             re.compile(r"\bhbot\b|hyperbaric", re.I), "other"),
    "stellate ganglion block": ("sgb OR stellate",
                                re.compile(r"\bsgb\b|stellate ganglion", re.I), "other"),
    "nattokinase": ("nattokinase OR natto",
                    re.compile(r"nattokinase", re.I), "supplement"),
    "vitamin D": ('"vitamin d"', re.compile(r"vitamin ?d\b", re.I), "supplement"),
    "B12": ('b12 OR methylcobalamin OR "vitamin b12"',
            re.compile(r"\bb-?12\b|methylcobalamin", re.I), "supplement"),
    "magnesium": ("magnesium", re.compile(r"magnesium", re.I), "supplement"),
    "NAC": ('nac OR acetylcysteine',
            re.compile(r"\bnac\b|acetylcysteine", re.I), "supplement"),
    "CoQ10": ('coq10 OR ubiquinol OR "coenzyme q10"',
              re.compile(r"\bcoq-?10\b|ubiquinol|coenzyme q10", re.I), "supplement"),
}

PSYCHEDELIC_LABELS = ("psilocybin", "ketamine", "LSD")


def _iter_segments(con: sqlite3.Connection, fts_query: str):
    """(text, author, subreddit, created_utc) for every post and comment matching."""
    for body, author, sub, ts in con.execute(
        "SELECT c.body, c.author, c.subreddit, c.created_utc FROM comments_fts f "
        "JOIN comments c ON c.rowid = f.rowid WHERE f.comments_fts MATCH ?", (fts_query,)
    ):
        yield body or "", author, sub, ts
    for title, self_, author, sub, ts in con.execute(
        "SELECT p.title, p.selftext, p.author, p.subreddit, p.created_utc FROM posts_fts f "
        "JOIN posts p ON p.rowid = f.rowid WHERE f.posts_fts MATCH ?", (fts_query,)
    ):
        yield f"{title or ''}\n{self_ or ''}", author, sub, ts


def classify_claim(sentence: str) -> str | None:
    """Claim strength for one sentence, or None if it makes no graded claim.

    Positive is tested first: a sentence carrying both a strong-positive and a
    moderate marker ("a huge difference, though it wore off") is a strong claim with a
    caveat, not a moderate one.
    """
    for kind, pat in (("strong_pos", STRONG_POS_RE), ("strong_neg", STRONG_NEG_RE),
                      ("moderate", MODERATE_RE)):
        m = pat.search(sentence)
        # Negation or irrealis in the 60 characters before the marker cancels it.
        if m and not NEGATION_RE.search(sentence[max(0, m.start() - 60):m.start()]):
            return kind
    return None


# Anaphora, for carrying a claim across a sentence break: "I took psilocybin. It
# changed everything." Without this the second sentence is invisible; with it
# unrestricted, an unrelated neighbouring sentence gets attributed to the drug.
ANAPHOR_RE = re.compile(r"^\W*(it|this|that|they|the (trip|dose|effect|experience))\b", re.I)


def _other_targets(term: re.Pattern) -> list[re.Pattern]:
    return [t for _f, t, _c in TESTIMONY_TARGETS.values() if t is not term]


def iter_claims(text: str, term: re.Pattern):
    """Yield (kind, sentence) for first-person claims about `term` in one segment.

    A sentence qualifies if it names the treatment, or if it opens with an anaphor
    pointing back at a sentence that does. Either way it is discarded when it names a
    DIFFERENT tracked treatment, because this community stacks heavily and
    "LDN and ketamine ... it wrecked me" attributes to whichever one you ask for.

    That guard cannot catch a stack of untracked treatments, which is the detector's
    main residual error and is reported as such in 8.2.
    """
    if BOTLIKE_RE.search(text):
        return
    others = _other_targets(term)
    sents = SENTENCE_RE.split(text)
    for i, s in enumerate(sents):
        named = term.search(s)
        if not named and not (i and ANAPHOR_RE.match(s) and term.search(sents[i - 1])):
            continue
        if not FIRST_PERSON_RE.search(s) or THIRD_PARTY_RE.search(s):
            continue
        if any(o.search(s) for o in others):
            continue
        kind = classify_claim(s)
        if kind:
            yield kind, s.strip()


def scan_target(con: sqlite3.Connection, label: str) -> dict:
    """Count DISTINCT AUTHORS at each claim strength for one treatment.

    Authors, not sentences: one person who posted the same recovery story thirty times
    would otherwise carry a whole arm. That is not hypothetical here -- see 8.4.
    """
    fts, term, category = TESTIMONY_TARGETS[label]
    speakers: set[str] = set()
    by_kind: dict[str, set[str]] = {k: set() for k in CLAIM_KINDS}
    sentences = 0
    for text, author, _sub, _ts in _iter_segments(con, fts):
        if not author or author in BOT_AUTHORS:
            continue
        hit = False
        for kind, _s in iter_claims(text, term):
            by_kind[kind].add(author)
            sentences += 1
            hit = True
        if hit or _first_person_mention(text, term):
            speakers.add(author)
    out = {"treatment": label, "category": category,
           "speakers": len(speakers), "claim_sentences": sentences}
    for k in CLAIM_KINDS:
        out[k] = len(by_kind[k])
    out["strong_pos_rate"] = out["strong_pos"] / len(speakers) if speakers else np.nan
    return out


def _first_person_mention(text: str, term: re.Pattern) -> bool:
    """Did the writer mention this treatment in the first person, at any strength?

    The denominator for a strong-claim rate. Without it the rate would be strong
    claims over *everyone who typed the word*, including people asking whether to try it.
    """
    if BOTLIKE_RE.search(text):
        return False
    for s in SENTENCE_RE.split(text):
        if term.search(s) and FIRST_PERSON_RE.search(s) and not THIRD_PARTY_RE.search(s):
            return True
    return False


def testimony_table(con: sqlite3.Connection, labels=None) -> pd.DataFrame:
    """scan_target over every treatment, with a Wilson CI on each strong-claim rate."""
    rows = [scan_target(con, l) for l in (labels or TESTIMONY_TARGETS)]
    out = pd.DataFrame(rows)
    ci = [wilson(int(r.strong_pos), int(r.speakers))[1:] for _, r in out.iterrows()]
    out[["rate_lo", "rate_hi"]] = ci
    return out.sort_values("strong_pos_rate", ascending=False).reset_index(drop=True)


def testimony_examples(
    con: sqlite3.Connection, label: str, kind: str = "strong_pos", n: int = 8
) -> pd.DataFrame:
    """Up to `n` example sentences, at most ONE per author.

    Verbatim text with no username attached. These illustrate what the detector is
    matching on; they are not evidence, and no individual's story is built from them.
    """
    _fts, term, _cat = TESTIMONY_TARGETS[label]
    seen: set[str] = set()
    rows = []
    for text, author, sub, _ts in _iter_segments(con, TESTIMONY_TARGETS[label][0]):
        if not author or author in BOT_AUTHORS or author in seen:
            continue
        for k, s in iter_claims(text, term):
            if k == kind:
                seen.add(author)
                rows.append({"subreddit": sub, "sentence": " ".join(s.split())[:300]})
                break
        if len(rows) >= n:
            break
    return pd.DataFrame(rows)


def claim_authors(con: sqlite3.Connection, label: str, kind: str = "strong_pos") -> set[str]:
    """author_hash for every patient making a claim of this strength about `label`.

    The join key back to the extracted records, which is what makes the placebo checks
    in 8.5 possible: the same people can be looked up in the outcome table.
    """
    _fts, term, _cat = TESTIMONY_TARGETS[label]
    out = set()
    for text, author, _sub, _ts in _iter_segments(con, TESTIMONY_TARGETS[label][0]):
        if not author or author in BOT_AUTHORS:
            continue
        if any(k == kind for k, _ in iter_claims(text, term)):
            out.add(author_hash(author))
    return out


def top_speakers(con: sqlite3.Connection, label: str, kind: str = "strong_pos",
                 n: int = 5) -> pd.DataFrame:
    """Claim sentences per author, most prolific first -- the concentration check.

    If a handful of authors produce most of an arm's strong claims, the arm is a few
    people repeating themselves and must be described that way.
    """
    _fts, term, _cat = TESTIMONY_TARGETS[label]
    tally: dict[str, int] = {}
    for text, author, _sub, _ts in _iter_segments(con, TESTIMONY_TARGETS[label][0]):
        if not author or author in BOT_AUTHORS:
            continue
        c = sum(1 for k, _ in iter_claims(text, term) if k == kind)
        if c:
            tally[author] = tally.get(author, 0) + c
    s = pd.Series(tally, name="claim_sentences").sort_values(ascending=False)
    total = int(s.sum())
    out = s.head(n).to_frame()
    out["pct_of_arm"] = 100 * out["claim_sentences"] / total if total else np.nan
    out.index = [f"author #{i + 1}" for i in range(len(out))]
    return out


def detector_audit() -> pd.DataFrame:
    """Alternation count per pattern -- how much surface area each detector covers.

    A strong-positive list twice the length of the strong-negative list would produce
    "strong claims here are overwhelmingly positive" as a pure artifact. This makes the
    remaining imbalance visible instead of leaving it implicit.
    """
    pats = {"strong_pos": STRONG_POS_RE, "strong_neg": STRONG_NEG_RE,
            "moderate": MODERATE_RE}
    return pd.DataFrame(
        [{"detector": k, "alternations": v.pattern.count("|") + 1,
          "pattern_chars": len(v.pattern)} for k, v in pats.items()]
    ).set_index("detector")


def mention_volume_by_year(con: sqlite3.Connection, labels=None) -> pd.DataFrame:
    """Segments naming each treatment per year, and the whole corpus per year.

    This is a chart of the CONVERSATION, not of outcomes. The extracted records have no
    time axis; the raw scrape does, and how often a community talks about something is
    a legitimate thing to measure over time even when its outcomes are not.
    """
    totals = dict(con.execute(
        "SELECT strftime('%Y', created_utc, 'unixepoch'), COUNT(*) FROM comments GROUP BY 1"
    ))
    for y, n in con.execute(
        "SELECT strftime('%Y', created_utc, 'unixepoch'), COUNT(*) FROM posts GROUP BY 1"
    ):
        totals[y] = totals.get(y, 0) + n

    rows = []
    for label in (labels or PSYCHEDELIC_LABELS):
        fts, term, _cat = TESTIMONY_TARGETS[label]
        per_year: dict[str, int] = {}
        for text, _a, _s, ts in _iter_segments(con, fts):
            if term.search(text):
                y = pd.to_datetime(ts, unit="s").strftime("%Y")
                per_year[y] = per_year.get(y, 0) + 1
        for y, n in per_year.items():
            rows.append({"year": y, "treatment": label, "segments": n,
                         "corpus_segments": totals.get(y, 0)})
    out = pd.DataFrame(rows)
    out["per_10k"] = 1e4 * out["segments"] / out["corpus_segments"]
    return out.sort_values(["treatment", "year"]).reset_index(drop=True)
