"""Loader and aggregation helpers for the garlic beliefs-and-use study.

Reads `data/probes/garlic_pharmacology.db` READ-ONLY and turns the claims of one
pinned run into tidy frames. See `studies/garlic/DESIGN.md` for the study
specification and `studies/garlic/HANDOFF.md` for run provenance.

Privacy contract, enforced here rather than left to the caller:

* `unit.author_hash` is re-identifiable. It is used only to group claims and is
  replaced by a dense integer `reporter` id before it leaves `load_frames()`.
* `source_window.text` is never loaded into a frame. It is read only by
  `quote_character()`, which returns counts, never text.
* The `*_quote` evidence fields are loaded only by `sample_quotes()`, which the
  notebook calls explicitly. DESIGN §7.5 specifies these as short paraphrases;
  `quote_character()` measures how far that actually held.

Headline units are reporter-level (DESIGN §8). A reporter is a Reddit account,
not a verified person.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.stats.proportion import proportion_confint

DB_RELPATH = Path("data/probes/garlic_pharmacology.db")
REPEAT_RELPATH = Path("data/probes/garlic_pharmacology_repeat.db")
ENV_VAR = "PP_GARLIC_DB"

#: The live run. HANDOFF.md lists `0ec115ec…`, `7c68eba2…` and `3a368b7d…` as
#: stale specs living in the same file; claims must never be merged across them.
RUN_ID = "c05891b6ecad47900230eb606afbb230a9867fc9f41d1d2b88ec0292a05b03df"

SPEECH_ACTS = (
    "actual_use", "food_list", "culinary", "recommendation", "mechanism_belief",
    "question", "other", "avoidance", "planned_or_considered", "warning",
)
POLARITIES = ("pro_use", "anti_use", "mixed", "unclear")
MECHANISMS = (
    "antimicrobial", "gut_or_biofilm", "immune", "cardiovascular_or_bleeding",
    "herx_or_dieoff", "histamine_or_mcas_trigger", "allium_intolerance", "other",
)
PREPARATIONS = (
    "raw_clove", "crushed_wait_allicin", "allicin_supplement", "aged_extract_kyolic",
    "oil", "tea", "black_garlic", "topical_or_otic", "cooked_culinary", "other",
    "unspecified_form",
)
DIRECTIONS = ("helped", "no_effect", "worsened", "mixed")
AE_STATUSES = ("reported", "explicit_none", "not_stated")
AE_CATEGORIES = (
    "gi", "odor", "histamine_flare", "allergy", "bleeding_or_anticoagulant",
    "herx", "other",
)

#: Reporter n below which a bin is coded but never headlined (DESIGN §4.6, §8).
MIN_REPORTERS = 30

COLORS = {
    "pro_use": "#2b6cb0", "anti_use": "#c53030", "mixed": "#dd6b20",
    "unclear": "#a0aec0", "helped": "#2b6cb0", "worsened": "#c53030",
    "no_effect": "#a0aec0", "accent": "#2b6cb0", "muted": "#a0aec0",
    "prior": "#cbd5e0",
}

#: Regex lower bounds over the same 1,928 FTS authors, from DESIGN §4. They are
#: keyword floors, not labels, and the probe is expected to exceed them.
PRIORS = {
    "authors": 1928,
    "speech_act": {
        "actual_use": 156, "food_list": 536, "avoidance": 37, "culinary": 201,
    },
    "mechanism": {
        "gut_or_biofilm": 259, "antimicrobial": 227, "immune": 110,
        "cardiovascular_or_bleeding": 70, "herx_or_dieoff": 39,
        "histamine_or_mcas_trigger": 198,
    },
    "preparation": {
        "raw_clove": 334, "allicin_supplement": 215, "crushed_wait_allicin": 114,
        "topical_or_otic": 69, "aged_extract_kyolic": 37, "oil": 20,
        "black_garlic": 11, "tea": 8,
    },
}

# ── Loading ────────────────────────────────────────────────────────────────


def db_path(relpath: Path = DB_RELPATH) -> Path:
    """Absolute path to a probe database. `PP_GARLIC_DB` overrides discovery."""
    env = os.environ.get(ENV_VAR)
    if env and relpath == DB_RELPATH:
        p = Path(env).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(f"{ENV_VAR}={env!r} is not a file ({p})")
        return p
    here = Path.cwd().resolve()
    for d in [here, *here.parents]:
        if (d / relpath).is_file():
            return d / relpath
    raise FileNotFoundError(
        f"Could not find {relpath} walking up from {here}. "
        f"Run from inside the PatientPunk repo, or set {ENV_VAR}."
    )


def open_db(path: Path | None = None) -> sqlite3.Connection:
    """Read-only connection. The database holds raw text and must never be written."""
    return sqlite3.connect(f"file:{path or db_path()}?mode=ro", uri=True)


@dataclass(frozen=True)
class Frames:
    """Every table the notebook reads. No quotes, no raw window text, no hashes."""

    run: dict
    members: pd.DataFrame    # one row per cohort author
    units: pd.DataFrame      # one row per planned LLM unit
    attempts: pd.DataFrame   # one row per provider attempt
    claims: pd.DataFrame     # one row per extracted garlic event
    mechanisms: pd.DataFrame # long: one row per (claim, mechanism)
    effects: pd.DataFrame
    adverse: pd.DataFrame
    doses: pd.DataFrame


def load_frames(path: Path | None = None, run_id: str = RUN_ID) -> Frames:
    """Load one pinned run into tidy frames, stripping every unsafe field."""
    con = open_db(path)
    try:
        row = con.execute(
            "SELECT run_id, config_json, created_at FROM probe_run WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            held = [r[0][:12] for r in con.execute("SELECT run_id FROM probe_run")]
            raise ValueError(f"run_id {run_id[:12]}… not in this database; it holds {held}")
        run = {"run_id": row[0], "config": json.loads(row[1]), "created_at": row[2]}

        members = pd.DataFrame(
            con.execute(
                "SELECT author_hash, target FROM cohort_member WHERE run_id = ?",
                (run_id,),
            ).fetchall(),
            columns=["author_hash", "target"],
        )
        units = pd.DataFrame(
            con.execute(
                "SELECT unit_key, author_hash, character_count, status "
                "FROM unit WHERE run_id = ?",
                (run_id,),
            ).fetchall(),
            columns=["unit_key", "author_hash", "characters", "status"],
        )
        windows = dict(
            con.execute(
                "SELECT unit_key, COUNT(*) FROM source_window WHERE run_id = ? GROUP BY 1",
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

    # One dense id per author_hash, first-seen order. The hash is dropped here
    # and exists nowhere downstream.
    ids: dict[str, int] = {}

    def rid(h: str) -> int:
        return ids.setdefault(h, len(ids))

    members["reporter"] = [rid(h) for h in members["author_hash"]]
    units["reporter"] = [rid(h) for h in units["author_hash"]]
    members = members.drop(columns=["author_hash"])
    units = units.drop(columns=["author_hash"])
    unit_reporter = dict(zip(units["unit_key"], units["reporter"]))

    attempts["usage"] = [json.loads(u) if isinstance(u, str) else {}
                         for u in attempts["usage_json"]]
    for field in ("input_tokens", "output_tokens", "reasoning_tokens", "provider_cost"):
        attempts[field] = [u.get(field) for u in attempts["usage"]]
    attempts["failure"] = [failure_category(s, e)
                           for s, e in zip(attempts["status"], attempts["error"])]
    attempts = attempts.drop(columns=["usage_json", "usage", "error"])

    claims, mechs, effects, adverse, doses = [], [], [], [], []
    for claim_id, unit_key, included, values_json in claim_rows:
        v = json.loads(values_json)
        base = {"claim_id": claim_id, "reporter": unit_reporter[unit_key]}
        use_allowed = v["speech_act"] == "actual_use" and v["subject"] == "self"
        claims.append(
            base | {
                "unit_key": unit_key,
                "included": bool(included),
                "speech_act": v["speech_act"],
                "subject": v["subject"],
                "exposure_status": v["exposure_status"],
                "use_payload_allowed": use_allowed,
                "preparation": v.get("preparation"),
                "polarity": v.get("polarity"),
                "cited_authority": v.get("cited_authority"),
                "adverse_event_status": v["adverse_event_status"],
                "n_mechanisms": len(v["mechanisms"]),
                "n_effects": len(v["effects"]),
                "n_adverse": len(v["adverse_events"]),
                "n_doses": len(v["doses"]),
            }
        )
        for m in v["mechanisms"]:
            mechs.append(base | {"mechanism": m, "polarity": v.get("polarity"),
                                 "speech_act": v["speech_act"]})
        for e in v["effects"]:
            labels = symptom_labels(e.get("target"))
            effects.append(
                base | {
                    "direction": e["direction"],
                    "confidence": e["confidence"],
                    "magnitude": e.get("magnitude_0_10"),
                    "magnitude_basis": e.get("magnitude_basis"),
                    "preparation": v.get("preparation"),
                    "target": e.get("target"),
                    "symptom_class": primary_symptom(e.get("target")),
                    "duration_bin": (e.get("duration") or {}).get("normalized"),
                }
                | {f"sx_{name}": name in labels for name in SYMPTOM_CLASSES}
            )
        for a in v["adverse_events"]:
            adverse.append(
                base | {
                    "category": a["category"],
                    "confidence": a["confidence"],
                    "preparation": v.get("preparation"),
                    "raw_event": a.get("raw_event"),
                    "duration_bin": (a.get("duration") or {}).get("normalized"),
                }
            )
        for d in v["doses"]:
            doses.append(
                base | {
                    "raw_text": d.get("raw_text"),
                    "unit_raw": d.get("unit"),
                    "unit_family": dose_family(d.get("unit"), d.get("raw_text")),
                    "amount_lower": d.get("amount_lower"),
                    "amount_upper": d.get("amount_upper"),
                    "preparation": v.get("preparation"),
                }
            )

    return Frames(
        run=run, members=members, units=units, attempts=attempts,
        claims=pd.DataFrame(claims), mechanisms=pd.DataFrame(mechs),
        effects=pd.DataFrame(effects), adverse=pd.DataFrame(adverse),
        doses=pd.DataFrame(doses),
    )


# ── Free-text canonicalization ─────────────────────────────────────────────
# `target`, `unit` and `raw_text` are model-written free text. Each is mapped
# into a closed vocabulary so the analysis never turns on an ungoverned string.

#: Multilabel: one target may name several symptoms, and all of them count.
#: Order is also the priority for `primary_symptom`.
SYMPTOM_PATTERNS: tuple[tuple[str, str], ...] = (
    ("infection_antimicrobial",
     r"infect|fung|candida|bacteri|pseudomonas|escherichia|prevotella|desulfovibrio|"
     r"methanobrev|methanogen|overgrowth|yeast|biofilm|mold|virus|covid|hauler|"
     r"illness|tonsil stone|food poison"),
    ("gut_gi",
     r"\bgut\b|\bgi\b|stomach|bowel|sibo|\bibs\b|\bimo\b|digest|bloat|reflux|stool|"
     r"colon|microbiome|constipat|oesophagus|esophagus|methane|cramp|tummy"),
    ("cardiovascular",
     r"blood pressure|\bbp\b|circulat|clot|heart|palpitat|vascular|vasodil|"
     r"vasoconstric|\bhr\b|cholesterol|blood flow|blood thin|platelet|vessel|"
     r"cold hands|cold feet|orthostat|thumping|\bed\b"),
    ("fatigue_pem",
     r"fatigue|\bpem\b|energy|crash|exhaust|malaise|exercise tolerance|discomfort and"),
    ("cognitive_mood",
     r"brain fog|memory|cognit|mood|depress|calm|emotion|mental clarity|affect|"
     r"squishy brain|brain inflam"),
    ("histamine_mcas", r"histamine|\bmcas\b|allerg"),
    ("respiratory_ent",
     r"sinus|nasal|throat|lung|breath|\bsob\b|\bear\b|ear |cough|asthma|congestion|"
     r"smell|taste|parosmia|mucus|mucous|nose"),
    ("pain",
     r"pain|headache|migraine|ache|sore|burning|neuropath|tremor|spasm|nerve|"
     r"head pressure|dizz|vertigo|tinnitus|ringing"),
    ("general_unspecified",
     r"overall|general|well-?being|health|unspecified|everything|maintenance|"
     r"functioning|symptoms|prevent|relapse|recovery|sleep"),
)
SYMPTOM_CLASSES = tuple(name for name, _ in SYMPTOM_PATTERNS) + ("unclassified",)
_SYMPTOM_RE = {name: re.compile(pat) for name, pat in SYMPTOM_PATTERNS}


def symptom_labels(target: str | None) -> tuple[str, ...]:
    """Every symptom class a free-text effect target names. Multilabel."""
    if not target:
        return ()
    text = target.lower()
    hits = tuple(name for name in _SYMPTOM_RE if _SYMPTOM_RE[name].search(text))
    return hits or ("unclassified",)


def primary_symptom(target: str | None) -> str:
    """The highest-priority class of a target, for a partitioned view."""
    if not target:
        return "not_stated"
    labels = symptom_labels(target)
    return next((n for n in SYMPTOM_CLASSES if n in labels), "unclassified")


_DOSE_FAMILIES: tuple[tuple[str, str], ...] = (
    ("whole_garlic", r"clove|head|bulb"),
    ("weight", r"^m?gs?$|^gram|^g$|mcg"),
    ("count_units", r"pill|capsule|tablet|dose|drop"),
    ("volume", r"cup|spoon|tsp|tbsp|teaspoon|tablespoon|ml|oz"),
)


def dose_family(unit: str | None, raw_text: str | None) -> str:
    """Coarse family of a stated amount. Never converts between families.

    DESIGN §7.3 forbids inventing or converting units. `mg of an allicin
    supplement` and `cloves of raw garlic` are different quantities on different
    substances, so they are binned separately and never pooled.
    """
    for source in (unit, raw_text):
        if not source:
            continue
        text = source.lower().strip()
        for name, pattern in _DOSE_FAMILIES:
            if re.search(pattern, text):
                return name
    return "unparsed"


# ── Extraction reliability ─────────────────────────────────────────────────

_FAILURE_RULES = (
    ("connection_error", r"APIConnectionError|Connection"),
    ("timeout", r"APITimeoutError|timed out|timeout"),
    ("null_content", r"null content"),
    ("truncated_max_tokens", r"max_tokens|truncat"),
    ("unparseable_json", r"did not contain valid JSON"),
    ("quote_not_grounded", r"not grounded"),
    ("empty_quote", r"quote must be non-empty"),
    ("wrong_source_reference",
     r"source does not belong to unit|source ID/type does not match|"
     r"source_type must be post or comment"),
    ("use_payload_on_ineligible_event", r"require speech_act=actual_use|use_payload"),
    ("schema_extra_inputs", r"Extra inputs are not permitted"),
    ("adverse_status_inconsistent", r"adverse[_ ]event"),
    ("duplicate_event", r"duplicate event"),
    ("placeholder_value", r"placeholder value is forbidden"),
)


def failure_category(status: str, error: str | None) -> str | None:
    """Bucket an attempt error. The error text is never surfaced: it can echo
    model output, which can echo the source."""
    if status == "accepted":
        return None
    text = error or ""
    for label, pattern in _FAILURE_RULES:
        if re.search(pattern, text):
            return label
    return "other_schema_error"


def attempt_summary(f: Frames) -> pd.DataFrame:
    a = f.attempts
    cost = a["provider_cost"].dropna()
    return pd.DataFrame([
        {"metric": "attempts", "value": f"{len(a):,}"},
        {"metric": "accepted", "value": f"{int((a.status == 'accepted').sum()):,}"},
        {"metric": "validation_failed",
         "value": f"{int((a.status == 'validation_failed').sum()):,}"},
        {"metric": "transport_failed",
         "value": f"{int((a.status == 'transport_failed').sum()):,}"},
        {"metric": "cache hits", "value": f"{int(a.cache_hit.sum()):,}"},
        {"metric": "billing_uncertain (excluded from cost)",
         "value": f"{int(a.billing_uncertain.sum()):,}"},
        {"metric": "input tokens", "value": f"{int(a.input_tokens.fillna(0).sum()):,}"},
        {"metric": "output tokens", "value": f"{int(a.output_tokens.fillna(0).sum()):,}"},
        {"metric": "of which reasoning",
         "value": f"{int(a.reasoning_tokens.fillna(0).sum()):,}"},
        {"metric": "realized cost (attempts carrying usage)",
         "value": f"${cost.sum():.4f} over {len(cost):,} attempts"},
    ]).set_index("metric")


def cost_by_status(f: Frames) -> pd.DataFrame:
    a = f.attempts[f.attempts.provider_cost.notna()]
    out = (a.groupby("status")["provider_cost"]
           .agg(attempts="size", cost="sum").reset_index())
    out["share of spend"] = out["cost"] / out["cost"].sum()
    return out.sort_values("cost", ascending=False).reset_index(drop=True)


def failure_table(f: Frames) -> pd.DataFrame:
    bad = f.attempts[f.attempts.failure.notna()]
    return (bad.groupby(["status", "failure"])
            .agg(attempts=("attempt_no", "size"), units=("unit_key", "nunique"))
            .reset_index().sort_values(["status", "attempts"], ascending=[True, False])
            .reset_index(drop=True))


def quote_character(path: Path | None = None, run_id: str = RUN_ID) -> pd.DataFrame:
    """How verbatim the evidence quotes actually are, per field.

    DESIGN §7.5 asks for short paraphrases and the validator enforces only a 0.5
    bag-of-words floor, which a verbatim span also passes. This reads the window
    text to count, and returns counts only -- no text leaves this function.
    """
    con = open_db(path)
    try:
        windows = dict(con.execute(
            "SELECT source_window_id, text FROM source_window WHERE run_id = ?",
            (run_id,)).fetchall())
        rows = con.execute(
            "SELECT source_window_id, evidence_json FROM claim WHERE run_id = ?",
            (run_id,)).fetchall()
    finally:
        con.close()

    token = re.compile(r"[a-z0-9]+")
    norm = lambda s: " ".join(token.findall(s.lower()))
    out: list[dict] = []
    for window_id, evidence_json in rows:
        window = windows.get(window_id)
        if window is None:
            continue
        normalized = norm(window)
        vocabulary = set(normalized.split())
        for anchor in json.loads(evidence_json):
            quote = norm(anchor["quote"])
            if not quote:
                continue
            tokens = quote.split()
            out.append({
                "field_path": anchor["field_path"].split("[")[0].split(".")[-1]
                              if "." in anchor["field_path"]
                              else anchor["field_path"].split("[")[0],
                "words": len(tokens),
                "contiguous": quote in normalized,
                "overlap": sum(t in vocabulary for t in tokens) / len(tokens),
            })
    q = pd.DataFrame(out)
    return (q.groupby("field_path")
            .agg(quotes=("words", "size"), median_words=("words", "median"),
                 contiguous_verbatim=("contiguous", "mean"),
                 mean_overlap=("overlap", "mean"),
                 full_overlap=("overlap", lambda s: (s >= 0.999).mean()))
            .sort_values("quotes", ascending=False))


def sample_quotes(field: str, n: int = 8, seed: int = 0,
                  path: Path | None = None, run_id: str = RUN_ID) -> list[str]:
    """A deterministic sample of evidence quotes for one field path.

    Quotes are short (median 7 words) and carry no reporter id. They are NOT
    reliably paraphrases -- see `quote_character()` -- so treat anything printed
    from here as potentially verbatim source text.
    """
    con = open_db(path)
    try:
        rows = con.execute(
            "SELECT evidence_json FROM claim WHERE run_id = ?", (run_id,)).fetchall()
    finally:
        con.close()
    found = sorted({a["quote"].strip()
                    for (ej,) in rows for a in json.loads(ej)
                    if a["field_path"].startswith(field)})
    rng = np.random.default_rng(seed)
    picks = rng.choice(len(found), size=min(n, len(found)), replace=False)
    return [found[i] for i in sorted(picks)]


# ── Reporter-level aggregation ─────────────────────────────────────────────


def reporter_matrix(f: Frames, column: str, values: tuple[str, ...]) -> pd.DataFrame:
    """Boolean reporter x value membership. Rows overlap by construction.

    A reporter who posts a food list and also reports taking a supplement is
    True in both columns. DESIGN §8: that is a finding, not a coding error.
    """
    sub = f.claims[f.claims[column].notna()]
    m = pd.crosstab(sub["reporter"], sub[column]).reindex(columns=values, fill_value=0)
    return m.astype(bool)


def rate_table(matrix: pd.DataFrame, denominator: int | None = None,
               priors: dict | None = None) -> pd.DataFrame:
    """Reporter share of each column, with a Wilson interval and a denominator.

    Reporters are the independent unit here (one row each), so a binomial
    interval is appropriate; claim-level rates are not, and are never used as a
    headline.
    """
    n = denominator if denominator is not None else len(matrix)
    rows = []
    for col in matrix.columns:
        k = int(matrix[col].sum())
        est, lo, hi = wilson(k, n)
        row = {"value": col, "reporters": k, "denominator": n,
               "rate": est, "ci_lo": lo, "ci_hi": hi,
               "headline": k >= MIN_REPORTERS}
        if priors is not None:
            prior = priors.get(col)
            row["regex prior"] = prior
            row["vs prior"] = (np.nan if prior is None else k - prior)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("reporters", ascending=False).reset_index(drop=True)


def wilson(count: int, nobs: int) -> tuple[float, float, float]:
    if nobs == 0:
        return (np.nan, np.nan, np.nan)
    lo, hi = proportion_confint(count, nobs, alpha=0.05, method="wilson")
    return (count / nobs, lo, hi)


def cohens_h(p1: float, p2: float) -> float:
    if pd.isna(p1) or pd.isna(p2):
        return np.nan
    return (2 * np.arcsin(np.sqrt(np.clip(p1, 0, 1)))
            - 2 * np.arcsin(np.sqrt(np.clip(p2, 0, 1))))


BASE_SEED = 20260813
N_BOOT = 2000


def seed_for(*parts) -> int:
    """Deterministic bootstrap seed, stable across processes (hash() is salted)."""
    return (BASE_SEED + zlib.crc32("|".join(map(str, parts)).encode())) % 2**32


def clustered_rate(frame: pd.DataFrame, indicator: str, seed: int = BASE_SEED,
                   n_boot: int = N_BOOT) -> tuple[float, float, float]:
    """Rate over rows with a 95% interval from resampling whole reporters.

    Used only where the row, not the reporter, is the natural unit (effect
    records, dose records). Claims cluster hard inside accounts -- one account
    contributes up to 32 -- so an unclustered interval would be too narrow.
    """
    sub = frame[["reporter", indicator]].dropna()
    if sub.empty:
        return (np.nan, np.nan, np.nan)
    reporters = np.array(sorted(sub["reporter"].unique()))
    grouped = sub.groupby("reporter")[indicator].agg(["sum", "count"]).reindex(reporters)
    sums = grouped["sum"].to_numpy(float)
    counts = grouped["count"].to_numpy(float)
    point = sums.sum() / counts.sum()
    if len(reporters) < 2:
        return (point, np.nan, np.nan)
    idx = np.random.default_rng(seed).integers(0, len(reporters), (n_boot, len(reporters)))
    boot = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    return (point, float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975)))


# ── Stage 5b repeat-pass agreement ─────────────────────────────────────────


def repeat_agreement(main: Path | None = None, repeat: Path | None = None,
                     run_id: str = RUN_ID) -> tuple[pd.DataFrame, dict]:
    """Field-level agreement between the full run and the Stage 5b repeat.

    Both stores hold the same `run_id`; the repeat is a separate `--output-db`,
    so the response cache is cold and the calls are genuinely new. Temperature is
    0, so this measures residual provider nondeterminism -- a floor on
    instability, not a full re-elicitation (DESIGN §9).

    Claims are paired greedily within a unit on `source_window_id` + `speech_act`,
    then on window alone, matching the procedure recorded in HANDOFF.md.
    """
    def read(path):
        con = open_db(path)
        try:
            units = {k: s for k, s in con.execute(
                "SELECT unit_key, status FROM unit WHERE run_id = ?", (run_id,))}
            claims: dict[str, list] = {}
            for unit_key, window_id, values_json in con.execute(
                "SELECT unit_key, source_window_id, values_json FROM claim "
                "WHERE run_id = ?", (run_id,)):
                claims.setdefault(unit_key, []).append(
                    (window_id, json.loads(values_json)))
        finally:
            con.close()
        return units, claims

    a_units, a_claims = read(main or db_path())
    b_units, b_claims = read(repeat or db_path(REPEAT_RELPATH))
    shared = sorted({u for u, s in a_units.items() if s == "complete"}
                    & {u for u, s in b_units.items() if s == "complete"})

    pairs = []
    for unit_key in shared:
        pool = list(b_claims.get(unit_key, []))
        for window_id, av in a_claims.get(unit_key, []):
            match = next((i for i, (w, bv) in enumerate(pool)
                          if w == window_id and bv["speech_act"] == av["speech_act"]),
                         None)
            if match is None:
                match = next((i for i, (w, _) in enumerate(pool) if w == window_id),
                             None)
            if match is not None:
                pairs.append((av, pool.pop(match)[1]))

    rows, field_set_same, value_hits, value_total = [], 0, 0, 0
    for sa, sb in pairs:
        # Top-level keys, lists included: `doses`, `effects`, `adverse_events`
        # and `mechanisms` compare by full equality, so a payload that gained or
        # lost one record counts as a disagreement.
        field_set_same += set(sa) == set(sb)
        shared_keys = set(sa) & set(sb)
        equal = sum(sa[k] == sb[k] for k in shared_keys)
        value_hits += equal
        value_total += len(shared_keys)
        rows.append({"all shared fields equal": equal == len(shared_keys),
                     **{k: sa.get(k) == sb.get(k)
                        for k in ("speech_act", "subject", "exposure_status",
                                  "adverse_event_status", "polarity", "preparation")}})
    r = pd.DataFrame(rows)
    table = pd.DataFrame([
        {"metric": "top-level field set identical",
         "n": field_set_same, "of": len(pairs), "rate": field_set_same / len(pairs)},
        {"metric": "shared top-level values equal",
         "n": value_hits, "of": value_total, "rate": value_hits / value_total},
        *[{"metric": f"{c} identical", "n": int(r[c].sum()), "of": len(r),
           "rate": r[c].mean()}
          for c in ("all shared fields equal", "speech_act", "subject",
                    "exposure_status", "polarity", "preparation")],
    ])
    context = {
        "units complete in both": len(shared),
        "units attempted on repeat": sum(1 for s in b_units.values() if s != "planned"),
        "units failed or unfinished on repeat":
            sum(1 for s in b_units.values() if s in ("failed", "running")),
        "claim pairs": len(pairs),
        "unmatched claims (full run)":
            sum(len(a_claims.get(u, [])) for u in shared) - len(pairs),
        "unmatched claims (repeat)":
            sum(len(b_claims.get(u, [])) for u in shared) - len(pairs),
    }
    return table, context


# ── Provenance and plotting ────────────────────────────────────────────────

SOURCE_SNAPSHOT = "reddit_2026-06-13.db"
#: Not in RunConfig and not part of run_id, so it is recorded rather than read
#: back (DESIGN §9). Value confirmed at GATE 3 on 2026-08-12.
HTTP_TIMEOUT = "connect=10, read=90, write=90, pool=60"


def provenance_table(f: Frames, path: Path | None = None) -> pd.DataFrame:
    path = Path(path or db_path())
    cfg = f.run["config"]
    return pd.DataFrame([
        {"item": "database", "value": path.name},
        {"item": "database SHA-256",
         "value": hashlib.sha256(path.read_bytes()).hexdigest()},
        {"item": "run ID (pinned)", "value": f.run["run_id"]},
        {"item": "run created", "value": f.run["created_at"]},
        {"item": "model", "value": cfg.get("model")},
        {"item": "provider / base URL",
         "value": f"{cfg.get('provider')} / {cfg.get('base_url')}"},
        {"item": "sampling",
         "value": f"temperature {cfg.get('temperature')}, "
                  f"max_tokens {cfg.get('max_tokens'):,}, "
                  f"reasoning_effort {cfg.get('reasoning_effort')}"},
        {"item": "HTTP timeout (not in run_id)", "value": HTTP_TIMEOUT},
        {"item": "prompt version", "value": "2026-08-12-v3 (short-paraphrase contract)"},
        {"item": "quote grounding floor", "value": "0.5 bag-of-words, no verbatim companion"},
        {"item": "source snapshot", "value": SOURCE_SNAPSHOT},
        {"item": "content date range",
         "value": "unavailable — timestamps are not loaded and chronology is never inferred"},
        {"item": "cohort", "value": "FTS `garlic OR allicin OR kyolic`, non-bot authors"},
        {"item": "execution date (UTC)",
         "value": datetime.now(timezone.utc).date().isoformat()},
        {"item": "loader", "value": "studies/garlic/garlic.py"},
        {"item": "inference",
         "value": "no p-values; Wilson intervals on reporter shares, "
                  "reporter-clustered bootstrap on row-level rates"},
        {"item": "headline bin floor", "value": f"reporter n ≥ {MIN_REPORTERS}"},
    ])


def apply_style(plt) -> None:
    plt.rcParams.update({
        "figure.dpi": 120, "font.size": 9, "axes.grid": True, "grid.alpha": 0.25,
        "axes.spines.top": False, "axes.spines.right": False,
    })


def ci_bars(ax, labels, rates, los, his, ns, color="#2b6cb0", title=""):
    """Horizontal rate bars with Wilson error bars and denominators in the tick."""
    y = np.arange(len(labels))[::-1]
    rates, los, his = np.array(rates), np.array(los), np.array(his)
    ax.barh(y, rates, xerr=np.array([rates - los, his - rates]), height=0.62,
            color=color, error_kw={"lw": 0.9, "ecolor": "#2d3748"})
    ax.set_yticks(y, [f"{l}  (n={n:,})" for l, n in zip(labels, ns)])
    if title:
        ax.set_title(title, fontsize=9)
    return ax


def counts_bars(ax, labels, values, color="#2b6cb0"):
    y = np.arange(len(labels))[::-1]
    ax.barh(y, values, height=0.62, color=color)
    ax.set_yticks(y, labels)
    for yi, v in zip(y, values):
        ax.annotate(f"{v:,}", (v, yi), xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=7.5)
    return ax
