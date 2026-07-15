"""Controlled-vocabulary normalization for the clustering backbone fields.

Extraction emits free text, so the same concept appears in many surface forms
("bedbound"/"bedridden", "me/cfs"/"mecfs"/"cfs", "helped"/"60% better"). That
high cardinality is the single biggest drag on clustering quality (proven at the
day level: value-level silhouette 0.07 -> 0.31 after collapsing). This module
maps the dense backbone fields onto a small curated vocabulary so cluster-prep's
encoding works on real signal instead of surface noise.

Design:
 * Per-field maps live in FIELD_VOCAB as {canonical: [synonyms...]} -- editable.
 * normalize_value() cleans + exact-matches, then applies a few regex rules
   (e.g. "60% better" / "9% reduction" -> a sentiment bucket), else passes the
   cleaned value through (so unmapped values are not lost, just tidied).
 * DROP_FIELDS lists fields too fragmented to be useful (e.g.
   targeted_symptom_domain) -- normalize_records blanks them when asked.

These maps are a FIRST PASS seeded from a small sample + domain knowledge; rerun
the value-frequency scan on the full output and extend the synonym lists. They
are intentionally plain data so that is a one-line edit.
"""

from __future__ import annotations

import re

# --- cleaning ---------------------------------------------------------------

_PUNCT = re.compile(r"[^\w%/+\- ]+")
_WS = re.compile(r"\s+")


def _clean(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("’", "'").replace("‘", "'")  # smart quotes
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    return s


# --- curated vocabulary -----------------------------------------------------
# {field: {canonical: [surface forms / synonyms]}}.  Matching is on cleaned text.
FIELD_VOCAB: dict[str, dict[str, list[str]]] = {
    "conditions": {
        "long_covid": ["long covid", "long-covid", "lc", "long hauler", "longhauler",
                       "post covid", "post-covid syndrome", "pasc"],
        "me_cfs": ["me/cfs", "mecfs", "me cfs", "cfs", "chronic fatigue syndrome",
                   "chronic fatigue", "myalgic encephalomyelitis"],
        "pem": ["pem", "post-exertional malaise", "post exertional malaise",
                "post exertional", "pese"],
        "pots": ["pots", "postural orthostatic tachycardia syndrome",
                 "postural tachycardia", "postural orthostatic tachycardia"],
        "dysautonomia": ["dysautonomia", "autonomic dysfunction", "autonomic neuropathy"],
        "mcas": ["mcas", "mast cell activation syndrome", "mast cell activation",
                 "mast cell", "histamine intolerance"],
        "small_fiber_neuropathy": ["small fiber neuropathy", "sfn", "small fibre neuropathy"],
        "eds": ["ehlers-danlos syndrome", "ehlers danlos", "eds", "hypermobility",
                "heds", "hypermobile"],
        "post_viral": ["post-viral", "post viral", "postviral"],
        "fibromyalgia": ["fibromyalgia", "fibro"],
        "hashimotos": ["hashimoto's", "hashimotos", "hashimoto", "hashimotos thyroiditis"],
        "mctd_autoimmune": ["lupus", "sjogren's", "sjogrens", "rheumatoid arthritis",
                            "psoriatic arthritis", "ankylosing spondylitis"],
    },
    "treatment_outcome": {
        "helped": ["helped", "better", "improved", "improvement", "helps", "helpful",
                   "partial improvement", "some improvement", "worked"],
        "no_effect": ["no effect", "no_effect", "no difference", "no change",
                      "didn't work", "didnt work", "didn't help", "didnt help",
                      "no benefit", "nothing", "neutral"],
        "worsened": ["worsened", "worse", "made it worse", "made worse", "negative",
                     "crashed", "bad reaction", "adverse"],
        "mixed": ["mixed", "mixed results", "varied"],
        "unknown": ["unknown", "unclear", "not sure"],
    },
    "symptom_trajectory": {
        "improving": ["improving", "improved", "getting better", "recovering"],
        "recovered": ["recovered", "recovery", "remission", "fully recovered"],
        "declining": ["worsening", "worse", "severe decline", "declining", "progressive",
                      "deteriorating", "getting worse"],
        "relapsing": ["relapsing", "relapsing-remitting", "fluctuating", "up and down",
                      "remitting", "waxing and waning"],
        "stable": ["stable", "plateau", "plateaued", "same", "unchanged"],
    },
    "functional_status_tier": {
        # ordinal severity (see FUNCTIONAL_RANK below)
        "bedbound": ["bedbound", "bedridden", "bed bound", "mostly in bed"],
        "housebound": ["housebound", "homebound", "house bound", "can't leave home"],
        "mobility_limited": ["wheelchair", "rollator", "mobility aid", "walker",
                             "mobility scooter", "cane"],
        "ambulatory_limited": ["working part time", "part time", "reduced hours",
                               "limited activity", "mild"],
        "severe_unspecified": ["severe", "very severe", "profound"],
    },
}

# Ordinal rank for the severity field (higher = more severe). Useful if you want
# functional_status as a single ordinal feature instead of one-hot.
FUNCTIONAL_RANK = {
    "bedbound": 4, "housebound": 3, "mobility_limited": 2,
    "severe_unspecified": 3, "ambulatory_limited": 1,
}

# Fields too fragmented to normalize usefully -> blank them in normalized output
# (e.g. targeted_symptom_domain extracts prepositional fragments like "with pots").
DROP_FIELDS = {"targeted_symptom_domain"}

# Regex rules applied per field before passthrough (rule order matters).
_PCT = re.compile(r"\b(\d{1,3})\s?%")


def _regex_rules(field: str, cleaned: str) -> str | None:
    if field in ("treatment_outcome", "symptom_trajectory"):
        m = _PCT.search(cleaned)
        if m:
            pct = int(m.group(1))
            # "60% better" / "9% reduction" -> a sentiment bucket
            improved = any(w in cleaned for w in
                           ("better", "reduction", "improve", "recovered", "less"))
            if improved:
                return "recovered" if (field == "symptom_trajectory" and pct >= 80) \
                    else ("helped" if field == "treatment_outcome" else "improving")
    return None


def _invert(vocab: dict[str, list[str]]) -> dict[str, str]:
    inv: dict[str, str] = {}
    for canon, syns in vocab.items():
        inv[_clean(canon)] = canon
        for s in syns:
            inv[_clean(s)] = canon
    return inv


_LOOKUP = {f: _invert(v) for f, v in FIELD_VOCAB.items()}


def normalize_value(field: str, raw: str) -> str | None:
    """Map one raw value to its canonical form (or cleaned passthrough)."""
    cleaned = _clean(raw)
    if not cleaned:
        return None
    lut = _LOOKUP.get(field)
    if lut and cleaned in lut:
        return lut[cleaned]
    rule = _regex_rules(field, cleaned)
    if rule:
        return rule
    # substring fallback for known canonicals embedded in noisy text
    if lut:
        for surface, canon in lut.items():
            if len(surface) >= 4 and re.search(rf"\b{re.escape(surface)}\b", cleaned):
                return canon
    return cleaned  # passthrough: tidied but unmapped (never silently dropped)


def normalize_cell(field: str, cell: str, sep: str = " | ") -> str:
    """Normalize a multi-value cell: split, map each, dedupe (order-stable)."""
    out: list[str] = []
    seen: set[str] = set()
    for part in (cell or "").split(sep):
        v = normalize_value(field, part)
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return sep.join(out)


# ---------------------------------------------------------------------------
# treatment_outcome decomposition
#
# treatment_outcome holds structured "drug: outcome[: symptom]" entries. A flat
# collapse (the generic FIELD_VOCAB pass) would destroy the drug + symptom and
# leave only the bucket -- fine for clustering, useless for analysis. So instead
# we KEEP the raw triple in `treatment_outcome` and emit three derived columns,
# letting the bucket (clustering) and the full pair (analysis) travel together:
#   treatment_outcome_label   -> outcome bucket(s), deduped  (cluster-prep encodes this)
#   treatment_outcome_drug    -> treatment name per entry    (analysis)
#   treatment_outcome_symptom -> affected symptom per entry  (analysis)
# ---------------------------------------------------------------------------
TREATMENT_OUTCOME_RAW = "treatment_outcome"
TREATMENT_OUTCOME_LABEL = "treatment_outcome_label"
TREATMENT_OUTCOME_DRUG = "treatment_outcome_drug"
TREATMENT_OUTCOME_SYMPTOM = "treatment_outcome_symptom"
TREATMENT_OUTCOME_DERIVED = [
    TREATMENT_OUTCOME_LABEL, TREATMENT_OUTCOME_DRUG, TREATMENT_OUTCOME_SYMPTOM,
]
_OUTCOME_LABELS = {"helped", "no_effect", "worsened", "mixed", "unknown"}


def decompose_treatment_outcome(cell: str, sep: str = " | ") -> dict[str, str]:
    """Split a 'drug: outcome[: symptom]' multi-value cell into parallel
    label / drug / symptom columns (see module note above).

    drug and symptom stay aligned per entry (use the raw ``treatment_outcome``
    column for the full drug-outcome-symptom triple); label is the deduped
    outcome-bucket set that cluster-prep encodes. Outcome tokens are mapped to
    the controlled vocabulary; anything unrecognised becomes 'unknown' so the
    label column stays low-cardinality.
    """
    drugs, symptoms, labels, seen = [], [], [], set()
    for entry in (cell or "").split(sep):
        entry = entry.strip()
        if not entry:
            continue
        parts = [p.strip() for p in entry.split(":")]
        if len(parts) >= 2:
            drug, raw_outcome = parts[0], parts[1]
            # Rejoin parts[2:] so a symptom that itself contains ':' isn't truncated.
            symptom = ":".join(parts[2:]) if len(parts) > 2 else ""
        else:
            # Legacy / bare format: a bare outcome word with no drug
            # (e.g. "helped", "80% better"). Keep the outcome; no drug/symptom.
            drug, raw_outcome, symptom = "", parts[0], ""
        drugs.append(drug)
        symptoms.append(symptom)
        if not raw_outcome:
            continue
        # NB: TREATMENT_OUTCOME_RAW ("treatment_outcome") is the correct FIELD_VOCAB
        # key for outcome synonyms (worked->helped, etc.); there is no
        # "treatment_outcome_label" vocab. Do not "fix" this to TREATMENT_OUTCOME_LABEL.
        lbl = normalize_value(TREATMENT_OUTCOME_RAW, raw_outcome)
        if lbl not in _OUTCOME_LABELS:
            lbl = "unknown"
        if lbl not in seen:
            seen.add(lbl)
            labels.append(lbl)
    return {
        TREATMENT_OUTCOME_LABEL: sep.join(labels),
        TREATMENT_OUTCOME_DRUG: sep.join(drugs),
        TREATMENT_OUTCOME_SYMPTOM: sep.join(symptoms),
    }


def normalize_records(rows: list[dict], *, sep: str = " | ",
                      drop_fields: set[str] | None = None) -> list[dict]:
    """Return rows with FIELD_VOCAB fields normalized and DROP_FIELDS blanked.

    ``treatment_outcome`` is special-cased: its raw "drug: outcome: symptom"
    triples are preserved and decomposed into ``treatment_outcome_label`` /
    ``_drug`` / ``_symptom`` (bucket for clustering travels alongside the full
    pair for analysis) instead of being collapsed in place.
    """
    drop = DROP_FIELDS if drop_fields is None else drop_fields
    out = []
    for r in rows:
        nr = dict(r)
        if TREATMENT_OUTCOME_RAW in nr:
            nr.update(decompose_treatment_outcome(nr.get(TREATMENT_OUTCOME_RAW, ""), sep))
        for f in FIELD_VOCAB:
            if f == TREATMENT_OUTCOME_RAW:
                continue  # keep raw triples; bucket lives in treatment_outcome_label
            if f in nr:
                nr[f] = normalize_cell(f, nr.get(f, ""), sep)
        for f in drop:
            if f in nr:
                nr[f] = ""
        out.append(nr)
    return out


def cardinality_report(before: list[dict], after: list[dict], *,
                       sep: str = " | ") -> dict[str, tuple[int, int]]:
    """{field: (distinct_before, distinct_after)} for the normalized fields."""
    def distinct(rows, f):
        s = set()
        for r in rows:
            for v in (r.get(f) or "").split(sep):
                v = v.strip().lower()
                if v:
                    s.add(v)
        return len(s)
    rep = {}
    for f in list(FIELD_VOCAB) + sorted(DROP_FIELDS):
        if before and f in before[0]:
            rep[f] = (distinct(before, f), distinct(after, f))
    return rep
