"""Cohort, extraction and pharmacology tables for the v2 psychedelics study.

Reads the probe database written by `probes run psychedelic_pharmacology`
(`data/probes/psychedelic_pharmacology.db`) READ-ONLY and turns its claims into
tidy, quote-free DataFrames.

Privacy contract, enforced here rather than left to the caller:

* Every quote-bearing or raw-text field is dropped at load time and never
  reaches a DataFrame -- `claim.evidence_json` is not read at all, and the
  free-text `raw_text` / `raw_event` fields inside `values_json` are discarded.
  `source_window.text` is never selected.
* `unit.author_hash` is re-identifiable. It is used only to group claims by
  patient and is replaced by a dense integer `patient` id before it leaves
  `load_frames()`. No frame, plot or export carries the hash.
* Free-text dose fields are reported only through closed canonical vocabularies
  and coverage counts, never as the strings patients typed.

Import-only: nothing here touches the disk until a function is called.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.stats.proportion import proportion_confint

DB_RELPATH = Path("data/probes/psychedelic_pharmacology.db")
ENV_VAR = "PP_PROBE_DB"
RUN_ENV_VAR = "PP_PROBE_RUN_ID"

DRUGS = ("psilocybin", "ketamine", "lsd")
DIRECTIONS = ("helped", "no_effect", "worsened", "mixed")
AE_STATUSES = ("reported", "explicit_none", "not_stated")
SEVERITIES = ("mild", "moderate", "severe")
DURATION_BINS = (
    "acute_session", "under_24_hours", "one_to_six_days", "one_to_four_weeks",
    "one_to_six_months", "over_six_months", "ongoing_at_report",
)

COLORS = {
    "helped": "#2b6cb0", "worsened": "#c53030", "no_effect": "#a0aec0",
    "mixed": "#dd6b20", "accent": "#2b6cb0", "muted": "#a0aec0",
}

# ── Loading ────────────────────────────────────────────────────────────────

def db_path(start: Path | None = None) -> Path:
    """Absolute path to the probe database. `PP_PROBE_DB` overrides discovery."""
    env = os.environ.get(ENV_VAR)
    if env:
        p = Path(env).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(f"{ENV_VAR}={env!r} does not point to a file ({p})")
        return p
    here = Path(start).resolve() if start else Path.cwd().resolve()
    for d in [here, *here.parents]:
        candidate = d / DB_RELPATH
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"Could not find {DB_RELPATH} walking up from {here}.\n"
        f"Run from inside the PatientPunk repo, or set {ENV_VAR} to an absolute path."
    )


def open_db(path: Path | None = None) -> sqlite3.Connection:
    """Read-only connection. The database holds raw text and must never be written."""
    return sqlite3.connect(f"file:{path or db_path()}?mode=ro", uri=True)


@dataclass(frozen=True)
class Frames:
    """Every table the notebook uses. No quotes, no raw text, no author hashes."""

    run: dict
    members: pd.DataFrame   # one row per cohort patient-drug pair
    units: pd.DataFrame     # one row per planned LLM unit
    attempts: pd.DataFrame  # one row per provider attempt
    claims: pd.DataFrame    # one row per extracted exposure event
    effects: pd.DataFrame
    adverse: pd.DataFrame
    doses: pd.DataFrame


def select_run(con: sqlite3.Connection, run_id: str | None = None) -> tuple[str, str, str]:
    """Resolve exactly one probe run, or raise.

    A database can accumulate runs, so the run is never chosen implicitly: pass a
    full `run_id` (or set `PP_PROBE_RUN_ID`) to pin one, otherwise the database
    must hold exactly one run.
    """
    wanted = run_id or os.environ.get(RUN_ENV_VAR) or None
    rows = con.execute(
        "SELECT run_id, config_json, created_at FROM probe_run ORDER BY run_id"
    ).fetchall()
    if wanted:
        matches = [r for r in rows if r[0] == wanted]
        if not matches:
            raise ValueError(
                f"run_id {wanted!r} is not in this database. "
                f"It holds {len(rows)} run(s): {[r[0] for r in rows]}"
            )
        if len(matches) > 1:
            raise ValueError(f"run_id {wanted!r} is not unique in this database")
        return matches[0]
    if not rows:
        raise ValueError("This database contains no probe_run rows.")
    if len(rows) > 1:
        raise ValueError(
            f"This database contains {len(rows)} runs: {[r[0] for r in rows]}. "
            f"Pass run_id= or set {RUN_ENV_VAR} to choose one explicitly."
        )
    return rows[0]


def load_frames(path: Path | None = None, run_id: str | None = None) -> Frames:
    """Load one run into tidy frames, stripping every unsafe field."""
    con = open_db(path)
    try:
        run_id, config_json, created_at = select_run(con, run_id)
        run = {"run_id": run_id, "created_at": created_at,
               "config": json.loads(config_json)}

        members = pd.DataFrame(
            con.execute(
                "SELECT author_hash, target FROM cohort_member WHERE run_id = ?",
                (run_id,),
            ).fetchall(),
            columns=["author_hash", "drug"],
        )
        units = pd.DataFrame(
            con.execute(
                "SELECT unit_key, author_hash, target, character_count, status "
                "FROM unit WHERE run_id = ?",
                (run_id,),
            ).fetchall(),
            columns=["unit_key", "author_hash", "drug", "characters", "status"],
        )
        windows = dict(
            con.execute(
                "SELECT unit_key, COUNT(*) FROM source_window WHERE run_id = ? "
                "GROUP BY 1",
                (run_id,),
            ).fetchall()
        )
        units["windows"] = units["unit_key"].map(windows).fillna(0).astype(int)

        attempts = pd.DataFrame(
            con.execute(
                "SELECT unit_key, attempt_no, status, cache_hit, billing_uncertain, "
                "usage_json, error FROM attempt WHERE run_id = ?",
                (run_id,),
            ).fetchall(),
            columns=["unit_key", "attempt_no", "status", "cache_hit",
                     "billing_uncertain", "usage_json", "error"],
        )
        claim_rows = con.execute(
            "SELECT claim_id, unit_key, included, values_json FROM claim WHERE run_id = ?",
            (run_id,),
        ).fetchall()
    finally:
        con.close()

    # One dense id per author_hash, assigned in first-seen order. The hash itself
    # is dropped here and exists nowhere downstream.
    ids: dict[str, int] = {}
    def pid(h: str) -> int:
        return ids.setdefault(h, len(ids))

    members["patient"] = [pid(h) for h in members["author_hash"]]
    units["patient"] = [pid(h) for h in units["author_hash"]]
    members = members.drop(columns=["author_hash"])
    units = units.drop(columns=["author_hash"])

    unit_drug = dict(zip(units["unit_key"], units["drug"]))
    unit_pt = dict(zip(units["unit_key"], units["patient"]))

    attempts["usage"] = [
        json.loads(u) if isinstance(u, str) else {} for u in attempts["usage_json"]
    ]
    for field in ("input_tokens", "output_tokens", "reasoning_tokens", "provider_cost"):
        attempts[field] = [u.get(field) for u in attempts["usage"]]
    attempts["failure"] = [failure_category(s, e)
                           for s, e in zip(attempts["status"], attempts["error"])]
    attempts = attempts.drop(columns=["usage_json", "usage", "error"])

    claims, effects, adverse, doses = [], [], [], []
    for claim_id, unit_key, included, values_json in claim_rows:
        v = json.loads(values_json)
        drug, patient = unit_drug[unit_key], unit_pt[unit_key]
        base = {"claim_id": claim_id, "patient": patient, "drug": drug}
        claims.append(
            base | {
                "unit_key": unit_key,
                "included": bool(included),
                "subject": v["subject"],
                "exposure_status": v["exposure_status"],
                "adverse_event_status": v["adverse_event_status"],
                "n_effects": len(v["effects"]),
                "n_adverse": len(v["adverse_events"]),
                "n_doses": len(v["doses"]),
            }
        )
        for e in v["effects"]:
            labels = symptom_labels(e.get("target"))
            effects.append(
                base | {
                    "direction": e["direction"],
                    "confidence": e["confidence"],
                    "magnitude": e.get("magnitude_0_10"),
                    "magnitude_basis": e.get("magnitude_basis"),
                    "symptom_class": classify_symptom(e.get("target")),
                    "n_symptom_labels": len(labels),
                    "duration_bin": (e.get("duration") or {}).get("normalized"),
                }
                | {f"sx_{name}": name in labels for name, _ in SYMPTOM_PATTERNS}
            )
        for a in v["adverse_events"]:
            adverse.append(
                base | {
                    "category": a["category"],
                    "severity": a.get("severity"),
                    "confidence": a["confidence"],
                    "duration_bin": (a.get("duration") or {}).get("normalized"),
                }
            )
        for d in v["doses"]:
            doses.append(
                base | {
                    "amount_lower": d.get("amount_lower"),
                    "amount_upper": d.get("amount_upper"),
                    "unit_canon": canon_unit(d.get("unit")),
                    "route_canon": canon_route(d.get("route")),
                    "intent_canon": canon_intent(d.get("author_stated_intent")),
                    "has_formulation": d.get("formulation") is not None,
                    "has_schedule": d.get("frequency_schedule") is not None,
                    "has_context": d.get("treatment_context") is not None,
                }
            )

    return Frames(
        run=run,
        members=members,
        units=units,
        attempts=attempts,
        claims=pd.DataFrame(claims),
        effects=pd.DataFrame(effects),
        adverse=pd.DataFrame(adverse),
        doses=pd.DataFrame(doses),
    )


# ── Canonicalization of the free-text dose fields ──────────────────────────
# `unit`, `route` and `author_stated_intent` are model-copied free text. Each is
# mapped into a closed vocabulary so nothing patient-authored is ever displayed;
# anything unmatched lands in `other`, which is reported rather than hidden.

_UNIT_RULES = (
    ("g", r"^(g|gs|gr|gm|gram|grams|gramme|grammes)$"),
    ("mg", r"^(mg|milligram|milligrams)$"),
    ("mcg", r"^(ug|mcg|microgram|micrograms|mycrograms|µg)$"),
    ("mg/kg", r"^mg\s*/\s*kg$"),
    ("mg/ml", r"^mg\s*/\s*ml$"),
    ("count", r"^(tab|tabs|hit|hits|piece|pieces|dose|doses|capsule|capsules|"
              r"session|sessions|treatment|treatments)$"),
    ("oz", r"^(oz|ounce|ounces)$"),
)
_ROUTE_RULES = (
    ("iv", r"\b(iv|i\.v\.|intravenous|infusion|infusions)\b"),
    ("intranasal", r"\b(nasal|intranasal|spray|snort\w*|insufflat\w*)\b"),
    ("sublingual_buccal", r"\b(sublingual|buccal|troche|troches|lozenge|lozenges)\b"),
    ("intramuscular", r"\b(im|i\.m\.|intramuscular|injection|shot)\b"),
    ("oral", r"\b(oral|orally|ingest\w*|swallow\w*|tea|capsule|eaten|by mouth)\b"),
    ("other", r"\b(topical|rectal|suppository|transdermal|patch)\b"),
)
_INTENT_RULES = (
    ("microdose", r"micro|mini"),
    ("low_dose", r"low[\s-]?dos|small dos"),
    ("high_dose_or_trip", r"heroic|macro|high dos|large dos|full dos|trip|recreational"),
)


def _canon(value: str | None, rules) -> str | None:
    if not value or not value.strip():
        return None
    s = value.strip().lower()
    for label, pattern in rules:
        if re.search(pattern, s):
            return label
    return "other"


def canon_unit(value: str | None) -> str | None:
    return _canon(value, _UNIT_RULES)


def canon_route(value: str | None) -> str | None:
    return _canon(value, _ROUTE_RULES)


def canon_intent(value: str | None) -> str | None:
    return _canon(value, _INTENT_RULES)


# Effect targets are free text, so they are reported as classes rather than as
# the labels the model wrote. Two rules shape the vocabulary:
#
# * Post-exertional malaise is a specific construct. Only language that states
#   post-exertional worsening earns `pem_explicit`; exertion-related complaints,
#   nonspecific fatigue and low energy are separate classes and must not be
#   described as PEM. (The v1 composite `energy_pem` matched all four at once.)
# * A target can name several symptoms, so membership is multilabel. The single
#   display label is the first match in `SYMPTOM_PATTERNS`, which is ordered by
#   how specific the matched construct is -- explicit post-exertional worsening,
#   then exertion, then two named symptom domains, then nonspecific tiredness,
#   then bare low energy. The order is fixed here, independently of any outcome.
#
# `me/cfs` is a diagnosis label rather than a statement of post-exertional
# worsening, so it counts as general fatigue, not as explicit PEM.
SYMPTOM_PATTERNS = (
    ("pem_explicit", re.compile(
        r"\bpem\b|post[-\s]?exertion(?:al)?|\bpayback\b|"
        r"crash\w*\s+(?:after|from|following)", re.I)),
    ("exertion_intolerance", re.compile(
        r"exert\w*|exercis\w*|physical activity|activity tolerance|overdo\w*|"
        r"stamina|endurance|deconditio\w*", re.I)),
    ("pain", re.compile(
        r"\bpain\b|\bache|migraine|headache|neuralgia|fibromyalgia", re.I)),
    ("mood_cognitive", re.compile(
        r"depress|anxiet|anxious|mood|anhedon|brain ?fog|cognit|memory|focus|"
        r"concentrat|motivat|mental health|ptsd|suicid|ocd|panic|clarity|apath|"
        r"depersonal|dereal|trauma|wellbeing|well-being|well being", re.I)),
    ("fatigue_general", re.compile(
        r"fatigue|exhaust\w*|\btired\w*|lethargy|lethargic|malaise|"
        r"\bcfs\b|\bme[/\s-]?cfs\b", re.I)),
    ("low_energy", re.compile(r"\benerg\w*|sluggish|listless", re.I)),
)

#: Display vocabulary: the matchable classes, then the two fallbacks.
SYMPTOM_CLASSES = tuple(name for name, _ in SYMPTOM_PATTERNS) + ("other", "unspecified")

#: The four classes the v1 `energy_pem` composite collapsed into one.
ENERGY_FAMILY = ("pem_explicit", "exertion_intolerance", "fatigue_general", "low_energy")


def symptom_labels(target: str | None) -> tuple[str, ...]:
    """Every symptom class the target matches, in precedence order."""
    if not target or not target.strip():
        return ()
    return tuple(name for name, pattern in SYMPTOM_PATTERNS if pattern.search(target))


def classify_symptom(target: str | None) -> str:
    """Single display class: the most specific match.

    `unspecified` when no target was stated, `other` when one was but it matches
    no class. Multilabel membership is kept alongside this in the effects frame,
    so nothing is lost to the precedence rule.
    """
    if not target or not target.strip():
        return "unspecified"
    labels = symptom_labels(target)
    return labels[0] if labels else "other"


# ── Extraction reliability ─────────────────────────────────────────────────

_FAILURE_RULES = (
    ("connection_error", r"APIConnectionError"),
    ("timeout", r"APITimeoutError|timed out"),
    ("null_content", r"null content"),
    ("unparseable_json", r"did not contain valid JSON"),
    ("quote_not_grounded", r"not grounded in the cited source"),
    ("empty_quote", r"evidence quote must be non-empty"),
    ("wrong_source_reference", r"source does not belong to unit|source ID/type does not match"),
    ("outcomes_on_excluded_event", r"doses/effects/adverse_events require"),
    ("adverse_status_inconsistent", r"adverse[_ ]event"),
    ("duplicate_event", r"duplicate event"),
    ("target_drug_mismatch", r"target_drug mismatch"),
    ("placeholder_value", r"placeholder value is forbidden"),
)


def failure_category(status: str, error: str | None) -> str | None:
    """Bucket an attempt error. The error text itself is never surfaced: it can
    echo model output, which can echo the source."""
    if status == "accepted":
        return None
    text = error or ""
    for label, pattern in _FAILURE_RULES:
        if re.search(pattern, text):
            return label
    return "other_schema_error"


def attempt_summary(f: Frames) -> pd.DataFrame:
    a = f.attempts
    return pd.DataFrame(
        [
            {"metric": "attempts", "value": len(a)},
            {"metric": "accepted", "value": int((a.status == "accepted").sum())},
            {"metric": "validation_failed",
             "value": int((a.status == "validation_failed").sum())},
            {"metric": "transport_failed",
             "value": int((a.status == "transport_failed").sum())},
            {"metric": "cache_hits", "value": int(a.cache_hit.sum())},
            {"metric": "billing_uncertain", "value": int(a.billing_uncertain.sum())},
            {"metric": "attempts with usage recorded", "value": int(a.input_tokens.notna().sum())},
            {"metric": "input tokens", "value": int(a.input_tokens.fillna(0).sum())},
            {"metric": "output tokens", "value": int(a.output_tokens.fillna(0).sum())},
            {"metric": "reasoning tokens", "value": int(a.reasoning_tokens.fillna(0).sum())},
        ]
    ).set_index("metric")


def failure_table(f: Frames) -> pd.DataFrame:
    """Failure categories by attempt status, with the units they touched."""
    bad = f.attempts[f.attempts.failure.notna()]
    out = (
        bad.groupby(["status", "failure"])
        .agg(attempts=("attempt_no", "size"), units=("unit_key", "nunique"))
        .reset_index()
        .sort_values(["status", "attempts"], ascending=[True, False])
        .reset_index(drop=True)
    )
    return out


def attempts_per_unit(f: Frames) -> pd.DataFrame:
    n = f.attempts.groupby("unit_key").size().rename("attempts")
    d = f.units.set_index("unit_key").join(n).fillna({"attempts": 0})
    return (
        d.groupby(["status", "attempts"]).size().rename("units").reset_index()
        .astype({"attempts": int})
    )


# ── Statistics ─────────────────────────────────────────────────────────────

def wilson(count: int, nobs: int) -> tuple[float, float, float]:
    """Point estimate and Wilson 95% CI, as in v1. Every rate reports one."""
    if nobs == 0:
        return (np.nan, np.nan, np.nan)
    lo, hi = proportion_confint(count, nobs, alpha=0.05, method="wilson")
    return (count / nobs, lo, hi)


def patient_drug_effects(f: Frames) -> pd.DataFrame:
    """One row per (patient, drug) pair that has at least one extractable effect.

    This is the analysis unit for every headline rate. Claims are clustered
    within patients -- 2,921 included claims come from ~1,041 people -- so a rate
    over claims would be pseudo-replication. Aggregating to the pair first makes
    the observations exchangeable enough for a binomial interval.
    """
    e = f.effects
    g = e.groupby(["patient", "drug"])["direction"]
    out = pd.DataFrame({
        "any_helped": g.apply(lambda s: (s == "helped").any()),
        "any_worsened": g.apply(lambda s: (s == "worsened").any()),
        "any_no_effect": g.apply(lambda s: (s == "no_effect").any()),
        "any_mixed": g.apply(lambda s: (s == "mixed").any()),
        "n_effects": g.size(),
    }).reset_index()
    out["profile"] = [
        "helped only" if h and not (w or n or m)
        else "worsened only" if w and not (h or n or m)
        else "no effect only" if n and not (h or w or m)
        else "mixed / conflicting"
        for h, w, n, m in zip(out.any_helped, out.any_worsened,
                              out.any_no_effect, out.any_mixed)
    ]
    return out


def dose_outcome_rows(f: Frames, bins: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Link each binned dose to the effects extracted from the *same claim*.

    A claim is one extracted exposure event, and it is the finest shared key the
    probe stores, so it is the only level at which a dose and an outcome are known
    to describe the same episode. Joining on (patient, drug) instead would copy a
    pair's whole outcome summary onto every dose bin that pair ever mentioned,
    counting one reported benefit as evidence for incompatible dose levels.

    Two documented exclusions, applied before any outcome is read:

    * a claim whose dose records straddle more than one bin is ambiguous -- there
      is no rule that assigns its outcome to one bin -- and is dropped whole;
    * a claim carrying no effect record has no outcome to link and is dropped.

    `bins` maps (drug, unit_canon) -> (group_label, [(upper_inclusive, bin_name), ...]).
    Returns the analyzable rows and an audit frame of retained/excluded counts.
    """
    d = f.doses[f.doses.amount_lower.notna() & f.doses.unit_canon.notna()].copy()
    d["amount"] = d.amount_lower.astype(float)

    def assign(drug, unit, amount):
        spec = bins.get((drug, unit))
        if spec is None:
            return None, None
        group, edges = spec
        return group, next(name for upper, name in edges if amount <= upper)

    d["dose group"], d["dose bin"] = zip(*[
        assign(r.drug, r.unit_canon, r.amount) for r in d.itertuples()
    ]) if len(d) else ((), ())
    binnable = d[d["dose group"].notna()]

    spans = binnable.groupby("claim_id")["dose bin"].nunique()
    ambiguous = set(spans[spans > 1].index)
    unambiguous = binnable[~binnable.claim_id.isin(ambiguous)]

    claim_outcome = f.effects.groupby("claim_id")["direction"].agg(
        helped=lambda s: (s == "helped").any(),
        worsened=lambda s: (s == "worsened").any(),
    )
    keys = unambiguous[
        ["claim_id", "patient", "drug", "dose group", "dose bin"]
    ].drop_duplicates()
    rows = keys.merge(claim_outcome, left_on="claim_id", right_index=True, how="inner")

    audit = pd.DataFrame([
        {"step": "dose records with amount + canonical unit", "records": len(d),
         "claims": d.claim_id.nunique()},
        {"step": "in a binned drug/unit subset", "records": len(binnable),
         "claims": binnable.claim_id.nunique()},
        {"step": "excluded: claim straddles >1 dose bin",
         "records": len(binnable) - len(unambiguous), "claims": len(ambiguous)},
        {"step": "excluded: claim carries no effect record",
         "records": len(unambiguous) - len(rows),
         "claims": unambiguous.claim_id.nunique() - rows.claim_id.nunique()},
        {"step": "retained for dose/outcome analysis", "records": len(rows),
         "claims": rows.claim_id.nunique()},
    ])
    return rows.reset_index(drop=True), audit


def rate_table(df: pd.DataFrame, col: str, by: str = "drug",
               order: tuple[str, ...] = DRUGS) -> pd.DataFrame:
    """Per-group share of `col` with a Wilson CI and its denominator attached."""
    rows = []
    for key in order:
        sub = df[df[by] == key]
        k, n = int(sub[col].sum()), len(sub)
        est, lo, hi = wilson(k, n)
        rows.append({by: key, "k": k, "n": n, "rate": est,
                     "ci_lo": lo, "ci_hi": hi})
    return pd.DataFrame(rows)


def direction_mix(f: Frames, level: str = "patient") -> pd.DataFrame:
    """Effect-direction mix by drug.

    `level='patient'`: share of (patient, drug) pairs reporting each direction at
    least once -- the categories overlap, because one person can report both.
    `level='event'`: share of individual effect records. Clustered; descriptive only.
    """
    if level == "patient":
        pd_eff = patient_drug_effects(f)
        rows = []
        for d in DRUGS:
            sub = pd_eff[pd_eff.drug == d]
            for direction in DIRECTIONS:
                k, n = int(sub[f"any_{direction}"].sum()), len(sub)
                est, lo, hi = wilson(k, n)
                rows.append({"drug": d, "direction": direction, "k": k, "n": n,
                             "rate": est, "ci_lo": lo, "ci_hi": hi})
        return pd.DataFrame(rows)
    tab = (
        f.effects.groupby(["drug", "direction"]).size().unstack(fill_value=0)
        .reindex(index=list(DRUGS), columns=list(DIRECTIONS), fill_value=0)
    )
    return tab


def adverse_denominators(f: Frames) -> pd.DataFrame:
    """The reported / explicit_none / not_stated split, per drug.

    Restricted to included claims, which are the only ones allowed to carry a
    status other than `not_stated`. `not_stated` is silence, not a denial.
    """
    inc = f.claims[f.claims.included]
    tab = (
        inc.groupby(["drug", "adverse_event_status"]).size().unstack(fill_value=0)
        .reindex(index=list(DRUGS), columns=list(AE_STATUSES), fill_value=0)
    )
    tab["included_claims"] = tab.sum(axis=1)
    return tab


def symptom_composition(e: pd.DataFrame) -> pd.DataFrame:
    """What each symptom class actually contains, per class.

    Multilabel columns count a record under every class it matches, so they sum
    to more than the record total; exclusive columns use the display label only.
    The gap between the two is what the precedence rule reassigns.
    """
    rows = []
    for name in SYMPTOM_CLASSES:
        multi = e[e[f"sx_{name}"]] if f"sx_{name}" in e else e[e.symptom_class == name]
        excl = e[e.symptom_class == name]
        rows.append({
            "symptom class": name,
            "records (multilabel)": len(multi),
            "reporters (multilabel)": multi.patient.nunique(),
            "records (exclusive)": len(excl),
            "reporters (exclusive)": excl.patient.nunique(),
        })
    return pd.DataFrame(rows).set_index("symptom class")


def symptom_overlap(e: pd.DataFrame) -> pd.DataFrame:
    """How many effect records match 0, 1, 2, ... symptom classes at once.

    Every record above one class is a record whose analytical category the old
    single-label rule decided by pattern order rather than by the text.
    """
    counts = e.n_symptom_labels.value_counts().sort_index()
    out = counts.rename("records").rename_axis("classes matched").reset_index()
    out["share"] = out["records"] / len(e)
    return out


def dose_coverage(f: Frames) -> pd.DataFrame:
    """How much of each dose record is actually populated, per drug."""
    d = f.doses
    rows = []
    for drug in DRUGS:
        sub = d[d.drug == drug]
        rows.append({
            "drug": drug,
            "dose_records": len(sub),
            "patients": sub.patient.nunique(),
            "with_amount": int(sub.amount_lower.notna().sum()),
            "with_unit": int(sub.unit_canon.notna().sum()),
            "with_amount_and_unit": int((sub.amount_lower.notna() & sub.unit_canon.notna()).sum()),
            "with_route": int(sub.route_canon.notna().sum()),
            "with_intent": int(sub.intent_canon.notna().sum()),
            "with_schedule": int(sub.has_schedule.sum()),
            "with_formulation": int(sub.has_formulation.sum()),
            "with_context": int(sub.has_context.sum()),
        })
    return pd.DataFrame(rows).set_index("drug")


# ── Plot helpers ───────────────────────────────────────────────────────────

def apply_style(plt) -> None:
    plt.rcParams.update({
        "figure.dpi": 120, "font.size": 9, "axes.grid": True,
        "grid.alpha": 0.25, "axes.spines.top": False, "axes.spines.right": False,
    })


def ci_bars(ax, labels, rates, los, his, ns, color="#2b6cb0", title=""):
    """Horizontal rate bars with Wilson error bars and denominators in the tick."""
    y = np.arange(len(labels))[::-1]
    err = np.array([np.array(rates) - np.array(los), np.array(his) - np.array(rates)])
    ax.barh(y, rates, xerr=err, height=0.62, color=color,
            error_kw={"lw": 0.9, "ecolor": "#2d3748"})
    ax.set_yticks(y, [f"{l}  (n={n})" for l, n in zip(labels, ns)])
    ax.set_xlim(0, 1)
    if title:
        ax.set_title(title, fontsize=9)
    return ax


def counts_bars(ax, labels, values, color="#2b6cb0", annotate=True):
    y = np.arange(len(labels))[::-1]
    ax.barh(y, values, height=0.62, color=color)
    ax.set_yticks(y, labels)
    if annotate:
        for yi, v in zip(y, values):
            ax.annotate(f"{v:,}", (v, yi), xytext=(4, 0),
                        textcoords="offset points", va="center", fontsize=7.5)
    return ax
