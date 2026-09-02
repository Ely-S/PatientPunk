"""Shared paths, record boundaries, and attribution helpers for this study."""

from __future__ import annotations

import csv
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

STUDY_ROOT = Path(__file__).resolve().parent


class StudyPaths(BaseModel):
    """Validated input and output paths, optionally overridden for versioned runs."""

    model_config = ConfigDict(frozen=True)

    database: Path = STUDY_ROOT / "noots.db"
    records: Path = STUDY_ROOT / "source_B" / "records.csv"
    corpus: Path = STUDY_ROOT / "source" / "subreddit_posts.json"
    workbook: Path = STUDY_ROOT / "results_workbook.xlsx"

    @classmethod
    def from_environment(cls) -> StudyPaths:
        values = {
            field: os.environ[name]
            for field, name in {
                "database": "TROPOFLAVIN_DB",
                "records": "TROPOFLAVIN_RECORDS",
                "corpus": "TROPOFLAVIN_CORPUS",
                "workbook": "TROPOFLAVIN_WORKBOOK",
            }.items()
            if os.environ.get(name)
        }
        return cls.model_validate(values)


class PipelineBRecord(BaseModel):
    """CSV boundary for the linked dosage and administration-route contract."""

    model_config = ConfigDict(extra="allow")

    author_hash: str = Field(min_length=1)
    treatment_outcome: str = ""
    dosage_treatment: str
    dosage_value: str
    administration_route_treatment: str
    administration_route_value: str

    @field_validator("author_hash", mode="before")
    @classmethod
    def strip_author_hash(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class LinkedValue(BaseModel):
    """One explicitly attributed treatment-value pair."""

    model_config = ConfigDict(frozen=True)

    treatment: str = Field(min_length=1)
    value: str = Field(min_length=1)

    @field_validator("treatment", "value", mode="before")
    @classmethod
    def strip_value(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


def load_pipeline_b_records(path: Path) -> list[PipelineBRecord]:
    """Load records.csv and require the post-#142 linked-field contract."""
    required = {
        "author_hash",
        "dosage_treatment",
        "dosage_value",
        "administration_route_treatment",
        "administration_route_value",
    }
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(required - set(reader.fieldnames or ()))
        if missing:
            names = ", ".join(missing)
            raise ValueError(
                f"{path} predates the linked dose/route schema; missing columns: {names}. "
                "Rerun pipeline B on the #140 stack."
            )
        try:
            return [PipelineBRecord.model_validate(row) for row in reader]
        except ValidationError as exc:
            raise ValueError(f"Invalid pipeline B record in {path}: {exc}") from exc


def _split_cell(value: str) -> list[str]:
    return [part.strip() for part in value.split(" | ") if part.strip()]


def linked_values(
    record: PipelineBRecord, field: Literal["dosage", "administration_route"]
) -> list[LinkedValue]:
    """Return aligned treatment-value pairs, rejecting partial or shifted rows."""
    treatments = _split_cell(getattr(record, f"{field}_treatment"))
    values = _split_cell(getattr(record, f"{field}_value"))
    if len(treatments) != len(values):
        raise ValueError(
            f"{field} columns are misaligned for author {record.author_hash}: "
            f"{len(treatments)} treatments and {len(values)} values"
        )
    return [
        LinkedValue(treatment=treatment, value=value)
        for treatment, value in zip(treatments, values, strict=True)
    ]


DMA = re.compile(r"(?i)\b4[ '’]?-?\s?dma|eutropoflav")
PLAIN = re.compile(
    r"(?i)tropoflavin|dihydroxyflavone|\b7[ .,'-]{0,2}8[ .,'-]{0,2}dhf\b|\bdhf\b"
)
COMPOUNDS = ("7,8-DHF", "4'-DMA")


def compound_for_treatment(treatment: str) -> str | None:
    """Map a treatment label to the parent or derivative, testing derivative first."""
    if DMA.search(treatment):
        return "4'-DMA"
    if PLAIN.search(treatment):
        return "7,8-DHF"
    return None


@dataclass(frozen=True)
class TargetValueSummary:
    counts: dict[str, Counter[str]]
    authors: dict[str, set[str]]


def summarize_target_values(
    records: list[PipelineBRecord],
    field: Literal["dosage", "administration_route"],
) -> TargetValueSummary:
    counts = {compound: Counter() for compound in COMPOUNDS}
    authors = {compound: set() for compound in COMPOUNDS}
    for record in records:
        for pair in linked_values(record, field):
            compound = compound_for_treatment(pair.treatment)
            if compound is None:
                continue
            counts[compound][pair.value.lower()] += 1
            authors[compound].add(record.author_hash)
    return TargetValueSummary(counts=counts, authors=authors)


_NUMBER = r"\d+(?:\.\d+)?"
_MASS_UNIT = r"mg|mcg|ug|µg|μg|g|gram|grams"
_REPEATED_UNIT_RANGE = re.compile(
    rf"(?i)(~?{_NUMBER})\s*({_MASS_UNIT})\s*(?:-|–|to)\s*({_NUMBER})\s*({_MASS_UNIT})\b"
)
_SHARED_UNIT_RANGE = re.compile(
    rf"(?i)(~?{_NUMBER})\s*(?:-|–|to)\s*({_NUMBER})\s*({_MASS_UNIT})\b"
)
_SINGLE_MASS = re.compile(rf"(?i)(~?{_NUMBER})\s*({_MASS_UNIT})\b")
_MASS_TO_MG = {
    "mg": 1.0,
    "mcg": 0.001,
    "ug": 0.001,
    "µg": 0.001,
    "μg": 0.001,
    "g": 1000.0,
    "gram": 1000.0,
    "grams": 1000.0,
}


@dataclass(frozen=True)
class MassDosage:
    low_mg: float
    high_mg: float

    @property
    def midpoint_mg(self) -> float:
        return (self.low_mg + self.high_mg) / 2

    @property
    def label(self) -> str:
        low = f"{self.low_mg:g}"
        high = f"{self.high_mg:g}"
        return f"{low} mg" if self.low_mg == self.high_mg else f"{low}-{high} mg"


@dataclass(frozen=True)
class DoseBand:
    order: int
    label: str


_DOSE_BANDS = (
    (5.0, DoseBand(order=1, label="<5 mg")),
    (10.0, DoseBand(order=2, label="5 to <10 mg")),
    (25.0, DoseBand(order=3, label="10 to <25 mg")),
    (50.0, DoseBand(order=4, label="25 to <50 mg")),
    (100.0, DoseBand(order=5, label="50 to <100 mg")),
    (float("inf"), DoseBand(order=6, label=">=100 mg")),
)


def dose_band(midpoint_mg: float) -> DoseBand:
    """Map a mass-dose midpoint to stable, cross-compound milligram bands."""
    if midpoint_mg < 0:
        raise ValueError("Dose midpoint cannot be negative")
    return next(band for upper_bound, band in _DOSE_BANDS if midpoint_mg < upper_bound)


_ROUTE_BUCKETS = {
    "oral": "swallowed oral",
    "sublingual": "oral mucosal",
    "buccal": "oral mucosal",
    "intranasal": "nasal mucosal",
    "topical": "dermal",
    "transdermal": "dermal",
    "inhaled": "pulmonary",
    "intravenous": "parenteral",
    "intramuscular": "parenteral",
    "subcutaneous": "parenteral",
    "injection": "parenteral",
    "rectal": "rectal or vaginal",
    "vaginal": "rectal or vaginal",
    "suppository": "rectal or vaginal",
    "other": "other explicit route",
}


def route_bucket(route: str) -> str:
    """Group the controlled route vocabulary by pharmacologically useful family."""
    return _ROUTE_BUCKETS.get(route.strip().lower(), "other explicit route")


_DESIRED_RESULT_PATTERNS = (
    (
        "post-exertional malaise",
        re.compile(
            r"\bpem\b|post.?exertional|fatigue after exertion|"
            r"(?:exert|activity).{0,30}(?:crash|worsen|malaise)|"
            r"(?:crash|worsen|malaise).{0,30}(?:exert|activity)",
            re.I,
        ),
    ),
    (
        "general fatigue",
        re.compile(r"fatigue|tired|letharg|exhaust|sleepy|somnol", re.I),
    ),
    (
        "mood or depression",
        re.compile(
            r"mood|depress|anhedon|emotion|happ|well.?being|dysphor|confidence", re.I
        ),
    ),
    (
        "anxiety or stress",
        re.compile(
            r"anxi|stress|panic|calm|fight or flight|obsess|restless|overthink", re.I
        ),
    ),
    (
        "focus or attention",
        re.compile(r"focus|attention|concentrat|executive|adhd|productiv", re.I),
    ),
    ("memory or learning", re.compile(r"memory|learning|recall", re.I)),
    (
        "energy or motivation",
        re.compile(
            r"energy|motivat|drive|stamina|endurance", re.I
        ),
    ),
    ("sleep or wakefulness", re.compile(r"sleep|insomnia|wakeful|vivid dream", re.I)),
    (
        "cognition or brain fog",
        re.compile(
            r"cognit|brain fog|clear.?head|clearer thinking|mental (clarity|sharp|effort)|"
            r"decision|creative thinking|speech|articulation|insight|behavior change",
            re.I,
        ),
    ),
    (
        "neuroprotection or recovery",
        re.compile(r"neurogen|bdnf|brain repair|neuroprotect|recover|heal", re.I),
    ),
    (
        "pain or neurologic symptoms",
        re.compile(
            r"pain|neuropath|neuralgia|headache|migraine|brain zap|numb|paresthesia|"
            r"balance|tactile|vision alteration|dereal|dissociat",
            re.I,
        ),
    ),
    (
        "stimulant recovery or reduction",
        re.compile(r"stimulant|dopamine depletion|dosage reduction", re.I),
    ),
    (
        "cardiovascular or autonomic",
        re.compile(r"chest tight|palpitation|heart racing|blood pressure", re.I),
    ),
    ("hair or skin", re.compile(r"hair|skin|hives", re.I)),
    ("gastrointestinal", re.compile(r"reflux|nausea|stomach|digest|diarrh|gut", re.I)),
    ("social functioning", re.compile(r"social", re.I)),
    ("sexual function", re.compile(r"libido|sexual|erect", re.I)),
)


def desired_result_bucket(symptom: str) -> str:
    """Bucket an explicitly extracted treatment target without adding context."""
    value = symptom.strip()
    if not value:
        return "unspecified"
    for label, pattern in _DESIRED_RESULT_PATTERNS:
        if pattern.search(value):
            return label
    return "other specified result"


_SIDE_EFFECT_PATTERNS = (
    (
        "post-exertional malaise or exertional crash",
        "fatigue or exertional intolerance",
        re.compile(
            r"\bpem\b|post.?exertional|fatigue after exertion|"
            r"(?:exert|activity).{0,30}(?:crash|worsen|malaise)",
            re.I,
        ),
    ),
    (
        "insomnia or sleep disruption",
        "sleep",
        re.compile(
            r"insomnia|sleep|fall asleep|keeps me (up|awake)|awake all day|nightmare|"
            r"vivid dream|reduced nrem|wake up",
            re.I,
        ),
    ),
    (
        "hair loss or thinning",
        "hair or skin",
        re.compile(r"hair loss|hair thinning|hair shed|weak hair|bald", re.I),
    ),
    ("headache or migraine", "neurologic", re.compile(r"headache|migraine", re.I)),
    (
        "activation or irritability",
        "activation or anxiety",
        re.compile(
            r"irritab|restless|agitat|over.?stimulat|jitter|gitter|wired|edg|impulsiv|"
            r"too much mental energy|too intense|too strong|teeth grinding|mind all over",
            re.I,
        ),
    ),
    ("anxiety or panic", "activation or anxiety", re.compile(r"anxi|panic", re.I)),
    (
        "appetite change",
        "appetite or weight",
        re.compile(r"appetite|hunger|weight loss", re.I),
    ),
    (
        "gastrointestinal",
        "gastrointestinal",
        re.compile(r"nausea|stomach|\bgi\b|diarrh|gut|digest|vomit|reflux", re.I),
    ),
    (
        "fatigue or sedation",
        "fatigue or sedation",
        re.compile(r"fatigue|tired|letharg|sedat|drows|sleepy|somnol|yawn", re.I),
    ),
    (
        "dizziness or vertigo",
        "neurologic",
        re.compile(r"dizz|vertigo|light.?headed", re.I),
    ),
    (
        "depressed or flattened mood",
        "mood",
        re.compile(
            r"depress|low mood|anhedon|emotionally flat|flatten|apathy|dysphor|"
            r"down in the dumps|labile|moody|pissed off",
            re.I,
        ),
    ),
    ("crash or rebound", "activation or anxiety", re.compile(r"crash|rebound", re.I)),
    (
        "cardiovascular or autonomic",
        "cardiovascular or autonomic",
        re.compile(
            r"palpitation|tachy|heart rate|heart racing|blood pressure|hypertension|"
            r"hypotension|chest tight|flush|overheat|dry mouth",
            re.I,
        ),
    ),
    ("sexual", "sexual", re.compile(r"libido|sexual|erect", re.I)),
    (
        "cognitive or perceptual disturbance",
        "neurologic",
        re.compile(
            r"brain fog|foggy|cognit|memory problem|articulation|typo|spac|loopy|"
            r"delirium|depersonali|dereal|dpdr|hallucin|hearing things|visual|"
            r"pupil|dilated eyes|light sensitivity|thought doubling|conspiratorial|"
            r"social skills|fried my brain|analysis paralysis|feeling in head|seizure|"
            r"inner-ear|numb|tingly",
            re.I,
        ),
    ),
    (
        "local irritation or odor",
        "local irritation",
        re.compile(r"nasal irritation|sinus|strong smell|weird odor", re.I),
    ),
    ("muscle cramps", "musculoskeletal", re.compile(r"cramp", re.I)),
    (
        "tolerance or short duration",
        "tolerance or duration",
        re.compile(r"tolerance|downregulation|short duration", re.I),
    ),
)


def canonical_side_effect(value: str) -> tuple[str, str]:
    """Return a reproducible canonical term and safety-domain bucket."""
    cleaned = " ".join(value.strip().lower().split())
    for canonical, bucket, pattern in _SIDE_EFFECT_PATTERNS:
        if pattern.search(cleaned):
            return canonical, bucket
    return cleaned or "unspecified", "other"


def parse_mass_dosage(value: str) -> MassDosage | None:
    """Parse the first explicit mass amount or range and normalize it to mg."""
    repeated = _REPEATED_UNIT_RANGE.search(value)
    if repeated:
        low = (
            float(repeated.group(1).lstrip("~"))
            * _MASS_TO_MG[repeated.group(2).lower()]
        )
        high = float(repeated.group(3)) * _MASS_TO_MG[repeated.group(4).lower()]
        return MassDosage(low_mg=min(low, high), high_mg=max(low, high))

    shared = _SHARED_UNIT_RANGE.search(value)
    if shared:
        low = float(shared.group(1).lstrip("~"))
        high = float(shared.group(2))
        factor = _MASS_TO_MG[shared.group(3).lower()]
        return MassDosage(
            low_mg=min(low, high) * factor,
            high_mg=max(low, high) * factor,
        )

    single = _SINGLE_MASS.search(value)
    if single:
        amount = (
            float(single.group(1).lstrip("~")) * _MASS_TO_MG[single.group(2).lower()]
        )
        return MassDosage(low_mg=amount, high_mg=amount)
    return None


@dataclass(frozen=True)
class TargetDosageSummary:
    counts: dict[str, Counter[str]]
    authors: dict[str, set[str]]
    excluded: dict[str, Counter[str]]
    midpoints_mg: dict[str, list[float]]
    author_midpoints_mg: dict[str, dict[str, list[float]]]


def summarize_target_dosages(records: list[PipelineBRecord]) -> TargetDosageSummary:
    """Summarize comparable mass doses and retain excluded values for audit."""
    counts = {compound: Counter() for compound in COMPOUNDS}
    authors = {compound: set() for compound in COMPOUNDS}
    excluded = {compound: Counter() for compound in COMPOUNDS}
    midpoints = {compound: [] for compound in COMPOUNDS}
    author_midpoints = {compound: {} for compound in COMPOUNDS}
    for record in records:
        for pair in linked_values(record, "dosage"):
            compound = compound_for_treatment(pair.treatment)
            if compound is None:
                continue
            parsed = parse_mass_dosage(pair.value)
            if parsed is None:
                excluded[compound][pair.value.lower()] += 1
                continue
            counts[compound][parsed.label] += 1
            authors[compound].add(record.author_hash)
            midpoints[compound].append(parsed.midpoint_mg)
            author_midpoints[compound].setdefault(record.author_hash, []).append(
                parsed.midpoint_mg
            )
    return TargetDosageSummary(
        counts=counts,
        authors=authors,
        excluded=excluded,
        midpoints_mg=midpoints,
        author_midpoints_mg=author_midpoints,
    )


def readonly_sqlite_uri(path: Path) -> str:
    """Build an absolute, read-only SQLite URI."""
    return f"{path.resolve().as_uri()}?mode=ro"


PROXIMITY_WINDOW = 150
PROXIMITY_ALIAS = re.compile(
    r"(?i)(tropoflavin|7[ .,'-]{0,2}8[ .,'-]{0,2}dhf|"
    r"7[ ,'-]{0,2}8[ ,'-]{0,2}dihydroxyflavone|dihydroxyflavone)"
)
DOSE = re.compile(
    r"(?i)(\d+(?:\.\d+)?)\s*(?:(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*)?"
    r"(mg|mcg|ug|µg|μg|g|gram|grams)\b"
)
UNIT = {
    "mg": 1.0,
    "mcg": 0.001,
    "ug": 0.001,
    "µg": 0.001,
    "μg": 0.001,
    "g": 1000.0,
    "gram": 1000.0,
    "grams": 1000.0,
}


def doses_near(text: str) -> list[float]:
    """Return doses whose match begins near a 7,8-DHF alias."""
    spans = [match.start() for match in PROXIMITY_ALIAS.finditer(text)]
    if not spans:
        return []
    output = []
    for match in DOSE.finditer(text):
        if min(abs(match.start() - start) for start in spans) > PROXIMITY_WINDOW:
            continue
        low, high, unit = match.group(1), match.group(2), match.group(3).lower()
        value = (float(low) + float(high)) / 2 if high else float(low)
        output.append(value * UNIT[unit])
    return output


def proximity_dose_bin(mg: float) -> str | None:
    if mg < 1 or mg > 1000:
        return None
    if mg < 10:
        return "1-9 mg"
    if mg < 20:
        return "10-19 mg"
    if mg < 30:
        return "20-29 mg"
    if mg < 50:
        return "30-49 mg"
    if mg < 100:
        return "50-99 mg"
    return "100-1000 mg"


STRICT_ALIAS = re.compile(
    r"(?i)(tropoflavin|eutropoflavin\w*|(?:4.?dma.?)?7[ .,'-]{0,2}8[ .,'-]{0,2}dhf|"
    r"7[ .,'-]{0,2}8[ .,'-]{0,2}dihydroxyflavone|dihydroxyflavone)"
)
STRICT_FILLER = {
    "a",
    "about",
    "am",
    "an",
    "and",
    "approx",
    "approximately",
    "around",
    "at",
    "av",
    "average",
    "been",
    "caps",
    "capsule",
    "capsules",
    "currently",
    "daily",
    "day",
    "days",
    "dose",
    "dosed",
    "doses",
    "dosing",
    "each",
    "evening",
    "every",
    "for",
    "from",
    "g",
    "have",
    "i",
    "in",
    "is",
    "it",
    "its",
    "just",
    "maybe",
    "mg",
    "morning",
    "my",
    "night",
    "now",
    "of",
    "on",
    "once",
    "one",
    "only",
    "or",
    "per",
    "pill",
    "pills",
    "pm",
    "powder",
    "roughly",
    "start",
    "started",
    "sublingual",
    "sublingually",
    "take",
    "taken",
    "taking",
    "tablet",
    "the",
    "this",
    "to",
    "total",
    "twice",
    "typically",
    "up",
    "use",
    "used",
    "using",
    "usually",
    "was",
    "were",
    "with",
    "x",
}
WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")


def bind_strict_doses(text: str) -> list[float]:
    """Return doses separated from an alias only by connective filler."""
    output = []
    spans = [(match.start(), match.end()) for match in STRICT_ALIAS.finditer(text)]
    for match in DOSE.finditer(text):
        for start, end in spans:
            gap = (
                text[end : match.start()]
                if match.start() >= end
                else text[match.end() : start]
            )
            if len(gap) > 60:
                continue
            if any(word.lower() not in STRICT_FILLER for word in WORD.findall(gap)):
                continue
            low, high, unit = match.group(1), match.group(2), match.group(3).lower()
            value = (float(low) + float(high)) / 2 if high else float(low)
            output.append(value * UNIT[unit])
            break
    return output


def strict_dose_bin(mg: float) -> str | None:
    if not 0.5 <= mg <= 1000:
        return None
    if mg < 10:
        return "<10 mg"
    if mg < 25:
        return "10-24 mg"
    if mg < 50:
        return "25-49 mg"
    return "50+ mg"
