"""Treatment aliases for Long COVID benchmark corpus-signal checks."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TreatmentSignalSpec(BaseModel):
    """Regex aliases for one benchmark treatment."""

    model_config = ConfigDict(frozen=True)

    treatment: str
    nct_id: str
    clean_treatment_specific_signal: bool
    aliases: tuple[str, ...]
    sensitivity_aliases: tuple[str, ...] = Field(default_factory=tuple)


TREATMENT_SIGNAL_SPECS: tuple[TreatmentSignalSpec, ...] = (
    TreatmentSignalSpec(
        treatment="Niagen",
        nct_id="NCT04809974",
        clean_treatment_specific_signal=True,
        aliases=(
            r"\btru\s*niagen\b",
            r"\bniagen\b",
            r"\bnicotinamide\s+riboside\b",
        ),
        sensitivity_aliases=(
            r"\bvit(?:amin)?\s*b\s*3\b",
            r"\bnad\+?\s+(?:booster|supplement|precursor)\b",
        ),
    ),
    TreatmentSignalSpec(
        treatment="Vortioxetine",
        nct_id="NCT05047952",
        clean_treatment_specific_signal=True,
        aliases=(
            r"\bvortioxetine\b",
            r"\btrintellix\b",
            r"\bbrintellix\b",
            r"\blu\s*aa\s*21004\b",
            r"\bluaa21004\b",
        ),
    ),
    TreatmentSignalSpec(
        treatment="Prospekta",
        nct_id="NCT05074888",
        clean_treatment_specific_signal=True,
        aliases=(r"\bprospekta\b",),
    ),
    TreatmentSignalSpec(
        treatment="Homeopathic Medication",
        nct_id="NCT05104749",
        clean_treatment_specific_signal=False,
        aliases=(
            r"\bhomeopathic\b",
            r"\bhomeopathy\b",
            r"\bhomeopath\w*\b",
        ),
        sensitivity_aliases=(r"\bhpus\b",),
    ),
    TreatmentSignalSpec(
        treatment="TNX-102 SL / cyclobenzaprine",
        nct_id="NCT05472090",
        clean_treatment_specific_signal=True,
        aliases=(
            r"\btnx[-\s]?102(?:\s*sl)?\b",
            r"\bcyclobenzaprine\b",
            r"\bflexeril\b",
            r"\btonmya\b",
            r"\bamrix\b",
            r"\bfexmid\b",
        ),
    ),
    TreatmentSignalSpec(
        treatment="Lithium",
        nct_id="NCT05618587",
        clean_treatment_specific_signal=True,
        aliases=(
            r"\blithium\b",
            r"\beskalith\b",
            r"\blithobid\b",
        ),
    ),
    TreatmentSignalSpec(
        treatment="Fluvoxamine",
        nct_id="NCT05874037",
        clean_treatment_specific_signal=True,
        aliases=(
            r"\bfluvoxamine\b",
            r"\bluvox\b",
            r"\bfaverin\b",
            r"\bfevarin\b",
        ),
    ),
    TreatmentSignalSpec(
        treatment="LAU-7b / fenretinide",
        nct_id="NCT05999435",
        clean_treatment_specific_signal=True,
        aliases=(
            r"\blau[-\s]?7b\b",
            r"\bfenretinide\b",
            r"\b4[-\s]?hpr\b",
            r"\b(?:n[-\s]*)?\(?4[-\s]*hydroxyphenyl\)?\s*retinamide\b",
        ),
    ),
)
