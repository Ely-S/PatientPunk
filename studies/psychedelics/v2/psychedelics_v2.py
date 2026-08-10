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


def load_frames(path: Path | None = None) -> Frames:
    """Load the whole run into tidy frames, stripping every unsafe field."""
    con = open_db(path)
    try:
        run_id, config_json, created_at = con.execute(
            "SELECT run_id, config_json, created_at FROM probe_run"
        ).fetchone()
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
            effects.append(
                base | {
                    "direction": e["direction"],
                    "confidence": e["confidence"],
                    "magnitude": e.get("magnitude_0_10"),
                    "magnitude_basis": e.get("magnitude_basis"),
                    "symptom_class": classify_symptom(e.get("target")),
                    "duration_bin": (e.get("duration") or {}).get("normalized"),
                }
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


# Symptom classes carried over from v1, so the effect targets are reported as
# classes rather than as the free-text labels the model wrote.
MOOD_COGNITIVE = re.compile(
    r"depress|anxiet|anxious|mood|anhedon|brain ?fog|cognit|memory|focus|"
    r"concentrat|motivat|mental health|ptsd|suicid|ocd|panic|clarity|apath|"
    r"depersonal|dereal|trauma|wellbeing|well-being|well being",
    re.I,
)
ENERGY_PEM = re.compile(
    r"\bpem\b|fatigue|energy|crash|exertion|stamina|exhaust|cfs|me/cfs|tired",
    re.I,
)
PAIN = re.compile(r"\bpain\b|\bache|migraine|headache|neuralgia|fibromyalgia", re.I)


def classify_symptom(target: str | None) -> str:
    """Coarse class for an effect's stated target, or `unspecified` when absent."""
    if not target or not target.strip():
        return "unspecified"
    if MOOD_COGNITIVE.search(target):
        return "mood_cognitive"
    if ENERGY_PEM.search(target):
        return "energy_pem"
    if PAIN.search(target):
        return "pain"
    return "other"


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
