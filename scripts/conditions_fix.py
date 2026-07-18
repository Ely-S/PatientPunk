"""
conditions_fix.py — the Tier-2 fix for the `conditions` field: surface canonicalization + a
symptoms-vs-conditions schema-boundary rule.

The boundary rule is the load-bearing part: two producers co-fail on `conditions` because they both
treat symptoms (PEM, fatigue, brain fog) as diagnosed conditions. This strips symptom-type terms and
keeps diagnosis/syndrome-type terms.

**Production note:** the boundary test here is a transparent long-COVID *domain lexicon*. In production
this is a UMLS semantic-type lookup — keep `T047 Disease or Syndrome` / `T019 Congenital Abnormality` /
`T191 Neoplastic Process`, drop `T184 Sign or Symptom`. The lexicon approximates that offline so the
prototype needs no UMLS license.
"""
from __future__ import annotations
import re

# If any of these appear, the term is a diagnosis/syndrome -> KEEP (takes precedence over symptom match,
# so "chronic fatigue syndrome" is kept even though it contains "fatigue").
CONDITION_KEYS = {
    "covid", "pasc", "pots", "cfs", "myalgic", "mcas", "mast cell", "dysautonomia", "fibromyalgia",
    "ehlers", "eds", "hypermobility", "diabetes", "thyroid", "hashimoto", "graves", "apnea", "osa",
    "kidney", "ckd", "renal", "asthma", "copd", "hypertension", "sibo", "ibs", "crohn", "colitis",
    "lyme", "epstein", "ebv", "adrenal", "insufficiency", "syndrome", "disease", "disorder", "cancer",
    "arthritis", "lupus", "celiac", "endometriosis", "pcos", "migraine", "narcolepsy", "dysfunction",
    "failure", "deficiency", "anemia", "anaemia", "neuropathy", "gastroparesis", "reflux", "gerd",
    "prolapse", "hernia", "cardiomyopathy", "myocarditis", "pericarditis", "embolism", "clot",
}
# If present and NO condition key matched, the term is a symptom -> STRIP.
SYMPTOM_KEYS = {
    "fatigue", "tiredness", "exhaustion", "pem", "post-exertional", "post exertional", "brain fog",
    "brainfog", "fog", "pain", "ache", "headache", "insomnia", "sleepless", "palpitation", "dizziness",
    "vertigo", "lighthead", "nausea", "shortness of breath", "breathless", "dyspnea", "air hunger",
    "numbness", "tingling", "paresthesia", "tinnitus", "fever", "chills", "weakness", "malaise",
    "burning", "cough", "congestion", "sore throat", "rash", "bloating", "cramp", "tremor", "twitch",
    "sweating", "flushing", "tachycardia", "crash", "flare",
}

def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9/ +-]", " ", str(t).lower())).strip()


def classify(term: str) -> str:
    """condition | symptom  (default: condition — conservative, don't over-strip).
    Matches on the WHOLE term (parentheticals kept), so "fever (now resolved)" reads as the symptom
    "fever" and "mcas (mast cell activation syndrome)" reads as a condition — no fragment promotion."""
    n = _norm(term)
    if not n:
        return "symptom"
    if any(c in n for c in CONDITION_KEYS):
        return "condition"
    if any(s in n for s in SYMPTOM_KEYS):
        return "symptom"
    return "condition"


def _split(value) -> list:
    """One term per list item; split string values only on obvious separators. Do NOT split on
    parentheses — parenthetical annotations ("(now resolved)", "(suggested by commenter)") must stay
    attached to their term, or a default-keep rule promotes the annotation to a spurious condition."""
    items = [value] if isinstance(value, str) else list(value or [])
    out = []
    for it in items:
        out.extend(re.split(r"[;,]", str(it)))
    return out


def fix_conditions(value) -> list:
    """The Tier-2 boundary RULE only: drop symptom-type terms, keep condition/diagnosis terms VERBATIM
    (case-deduped). Surface synonymy is deliberately left to the judge/ontology — canonicalizing crude
    real-world strings by hand injects more mismatches than it removes (see the prototype notebook)."""
    out, seen = [], set()
    for it in _split(value):
        it = str(it).strip()
        if not it or classify(it) != "condition":
            continue
        k = it.lower()
        if k not in seen:
            seen.add(k); out.append(it)
    return out


if __name__ == "__main__":  # quick self-check on the diagnostic cases
    cases = [
        (["long covid", "PEM", "fatigue"], "symptom strip -> [long covid]"),
        (["severe dysautonomia", "pots", "long covid"], "severity strip"),
        (["long covid", "kidney failure stage 2a", "chronic kidney disease stage 2"], "kidney canon"),
        (["sleep apnea", "asthma"], "genuine content kept (vs osa case)"),
        (["long covid", "post-exertional malaise", "brain fog", "insomnia"], "symptoms stripped"),
    ]
    for v, note in cases:
        print(f"{v}\n  -> {fix_conditions(v)}   ({note})\n")
