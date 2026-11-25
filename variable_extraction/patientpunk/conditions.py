"""One name for each condition, shared by the extractor that stores conditions and the filter that queries them."""

import re

# One name for the conditions most often written several ways, so conditions_latest keeps one row for
# each. Other names are kept as the model wrote them, in lower case. The author's words stay in evidence.
_CONDITION_ALIASES = {
    "long covid": ("long-covid", "longcovid", "lc", "long covid (lc)", "long hauler", "long haul covid",
                   "long-haul covid", "long haul", "pasc", "post covid", "post-covid", "post covid syndrome",
                   "post-covid syndrome", "post-covid condition", "post covid condition"),
    "me/cfs": ("me", "cfs", "mecfs", "me cfs", "me / cfs", "chronic fatigue syndrome", "myalgic encephalomyelitis"),
    "pots": ("pots syndrome", "postural orthostatic tachycardia syndrome", "postural tachycardia syndrome"),
    "mcas": ("mast cell activation syndrome",),
    "pem": ("post-exertional malaise", "post exertional malaise", "crash", "pem crash", "post-exertional crash"),
    "small fiber neuropathy": ("sfn", "small fibre neuropathy"),
    "eds": ("ehlers-danlos syndrome", "ehlers danlos syndrome", "ehlers-danlos"),
    "insomnia": ("trouble sleeping", "difficulty sleeping", "sleep disturbance", "sleep difficulty", "sleep issue",
                 "sleep problem", "can't sleep", "cannot sleep", "sleeplessness"),
    "muscle cramp": ("cramp", "cramping", "muscle cramping"),
    "headache": ("head pain",),
    "palpitation": ("heart palpitation",),
    "difficulty concentrating": ("trouble concentrating", "poor concentration", "lack of concentration",
                                 "concentration problem"),
    "craniocervical instability": ("cranio-cervical instability", "cci"),
    "post-concussion syndrome": ("post concussion syndrome", "postconcussion syndrome"),
    "dark circles": ("dark circles under eyes", "dark circles under the eyes"),
    "burning eyes": ("eye burning",),
}
# A plural is one condition with its singular ("headaches" is headache). Listed, not a rule, because
# many names end in s without being plurals: pots, ms, lupus, diabetes, herpes, shingles, mitosis.
_SINGULAR = {f"{w}{'es' if w.endswith(('sh', 'ch')) else 's'}": w for w in (
    "headache", "migraine", "crash", "cramp", "muscle cramp", "palpitation", "heart palpitation", "seizure",
    "nightmare", "rash", "tremor", "spasm", "muscle spasm", "night sweat", "hot flash", "flare", "brain zap",
    "adrenaline dump", "sleep issue", "sleep problem", "concentration problem", "infection", "nosebleed",
    "ulcer", "panic attack", "pem crash")}
_CONDITIONS = {alias: name for name, aliases in _CONDITION_ALIASES.items() for alias in (name, *aliases)}


def canonical_condition(name: str) -> str:
    """One name for a condition written several ways ("LC", "Long-COVID" -> "long covid"); others in lower case."""
    plain = re.sub(r"\s+", " ", name.strip().casefold().replace("’", "'")).removesuffix(".")
    plain = _SINGULAR.get(plain, plain)
    return _CONDITIONS.get(plain, plain)
