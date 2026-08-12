"""Pull CT.gov-structured Long COVID trials that fit NATURAL's premise.

This is a shareable, single-file version of the project logic used to isolate the
CT.gov-structured corpus-learnable Long COVID benchmark subset.

The script has no target NCT list. It:
1. Downloads completed interventional CT.gov studies with posted results using the
   broad Long COVID scope query from `seed_terms.py`.
2. Applies the local Long COVID condition/MeSH filter from `seed_terms.CLASSIFY`.
3. Applies a lightweight structural screen over CT.gov JSON fields that mirrors the
   `noparallel_notbinary_apo` NATURAL preset closely enough for audit.
4. Applies the NATURAL-premise screen used in this project: single-agent, blinded,
   accessible drug/supplement intervention, and patient-signal-relevant primary endpoint.

Run from the repo root:
  python trial_superset/pull_ctgov_long_covid_structured_learnable.py

Outputs:
  trial_superset/data/nikita_ctgov_structured_learnable/long_covid_structured_learnable.csv
  trial_superset/data/nikita_ctgov_structured_learnable/long_covid_structured_audit.csv
  trial_superset/data/nikita_ctgov_structured_learnable/long_covid_structured_learnable_ncts.txt
  trial_superset/data/nikita_ctgov_structured_learnable/nct_reports/<NCT>.json
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Literal

import requests
import typer
from pydantic import BaseModel, Field
from rich import box
from rich.console import Console
from rich.table import Table

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = PACKAGE_ROOT / "data" / "nikita_ctgov_structured_learnable"
CTGOV_API = "https://clinicaltrials.gov/api/v2/studies"
CTGOV_HEADERS = {
    "accept": "application/json",
    "User-Agent": "PatientPunk trial_superset Long COVID benchmark pull",
}

BROAD_LONG_COVID_QUERY = (
    "COVID OR SARS-CoV-2 OR PASC OR Post-Acute Sequelae of SARS-CoV-2 OR "
    "Post-COVID-19 Condition OR Chronic COVID OR Long-haul COVID"
)

LOCAL_LONG_COVID_TERMS = (
    "long covid",
    "long-covid",
    "post-covid",
    "post covid",
    "postcovid",
    "pasc",
    "post-acute covid",
    "post-acute sequelae",
)

AGG_FILTERS = "studyType:int,results:with,status:com"
ACTIVE_ARM_TYPES = {"EXPERIMENTAL", "ACTIVE_COMPARATOR"}
DRUG_TYPES = {"DRUG", "DIETARY_SUPPLEMENT"}

PLACEBO_TERMS = ("placebo", "sham", "matching placebo", "normal saline", "saline")
SELF_OBTAINABLE_TERMS = (
    "niagen",
    "nicotinamide",
    "homeopathic",
    "prospekta",
    "supplement",
    "vitamin",
    "probiotic",
)
CLINICAL_ADMIN_TERMS = (
    "intravenous",
    " iv ",
    "(iv",
    "infusion",
    "infusions",
    "inject",
    "injection",
    "ultrasound guided",
    "ganglion block",
    "stellate",
    "stem cell",
    "hb-admsc",
    "admsc",
    "allogeneic",
    "rintatolimod",
    "ampligen",
    "efgartigimod",
)
BEHAVIORAL_DEVICE_TERMS = (
    "device",
    "tdcs",
    "tens",
    "stimulation",
    "stimulator",
    "vagal nerve",
    "brainhq",
    "rehabilitation",
    "cognitive orientation",
    "co-op",
    "diet",
    "fasting",
    "exercise",
    "yoga",
    "training",
    "occupational",
)
BROAD_INDIVIDUALIZED_TERMS = (
    "individualized",
    "based on the totality",
    "totality of their physical",
    "complete list of homeopathic medicines",
    "for a complete list",
)
ADMIN_ENDPOINT_TERMS = (
    "total number of participants enrolled",
    "appendix-specific outcome",
    "recruitment rate",
    "retention rate",
    "usability",
    "acceptability",
    "appropriateness",
    "feasibility",
    "adverse event",
    "teae",
    "tesae",
    "laboratory values",
    "vital signs",
    "physical examination",
)
YES_ENDPOINT_TERMS = (
    "self-report",
    "self reported",
    "self-rated",
    "patient-reported",
    "patient reported",
    "questionnaire",
    "daily diary",
    "numeric rating scale",
    " nrs",
    "visual analog",
    "promis",
    "fatigue severity scale",
    "fatigue assessment scale",
    "severity scale",
    "symptom score",
    "symptoms",
    "fatigue",
    "pain",
    "brain fog",
)
PARTIAL_ENDPOINT_TERMS = (
    "ecog",
    "digit symbol",
    "dsst",
    "cognitive",
    "cognition",
    "quality of life",
    "sf-36",
    "rand 36",
    "physical component summary",
    "composite",
    "functional status",
    "orthostatic",
    "parosmia",
    "olfactory",
)

EndpointSignal = Literal["yes", "partial", "no"]


class CtgovPage(BaseModel):
    """Boundary model for CT.gov paginated search responses."""

    studies: list[dict[str, Any]] = Field(default_factory=list)
    nextPageToken: str | None = None
    totalCount: int | None = None


class NaturalPremiseScreen(BaseModel):
    """Computed second-screen fields from CT.gov JSON only."""

    passes: bool
    tier: str
    reason: str
    primary_intervention: str
    accessibility: str
    endpoint_signal: EndpointSignal
    single_agent: bool
    blinded: bool
    combination_arm: bool
    active_intervention_types: str


class TrialAuditRecord(BaseModel):
    """One row in the all-candidate audit CSV."""

    nct_id: str
    brief_title: str
    overall_status: str
    phase: str
    enrollment: int | None
    conditions: str
    condition_mesh_terms: str
    matched_long_covid_terms: str
    interventions: str
    intervention_types: str
    primary_outcomes: str
    passes_lightweight_structural_audit: bool
    lightweight_structural_notes: str
    passes_natural_premise_screen: bool
    corpus_learnable_tier: str
    natural_premise_reason: str
    primary_intervention: str
    intervention_accessibility: str
    endpoint_signal: EndpointSignal
    single_agent: bool
    blinded: bool
    combination_arm: bool
    active_intervention_types: str
    ctgov_url: str


CtgovPage.model_rebuild()
NaturalPremiseScreen.model_rebuild()
TrialAuditRecord.model_rebuild()

app = typer.Typer(add_completion=False)
console = Console()
CONSOLE_ENCODING = sys.stdout.encoding or "utf-8"


def display_text(value: object) -> str:
    """Return text that is safe for the active console encoding."""

    return str(value).encode(CONSOLE_ENCODING, errors="replace").decode(CONSOLE_ENCODING)


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def lower_blob(*values: object) -> str:
    return " ".join(normalize_text(value).lower() for value in values if value is not None)


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def get_path(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def nct_id(study: dict[str, Any]) -> str:
    return normalize_text(get_path(study, "protocolSection", "identificationModule", "nctId", default=""))


def fetch_broad_pool(query: str, page_size: int) -> list[dict[str, Any]]:
    studies: list[dict[str, Any]] = []
    page_token: str | None = None

    with requests.Session() as session:
        session.headers.update(CTGOV_HEADERS)
        while True:
            params: dict[str, str | int] = {
                "format": "json",
                "aggFilters": AGG_FILTERS,
                "query.cond": query,
                "countTotal": "true",
                "pageSize": page_size,
            }
            if page_token:
                params["pageToken"] = page_token

            response = session.get(CTGOV_API, params=params, timeout=120)
            response.raise_for_status()
            page = CtgovPage.model_validate(response.json())
            studies.extend(page.studies)

            page_token = page.nextPageToken
            if not page_token:
                break

    return studies


def conditions(study: dict[str, Any]) -> list[str]:
    values = get_path(study, "protocolSection", "conditionsModule", "conditions", default=[])
    return [normalize_text(value) for value in values or []]


def condition_mesh_terms(study: dict[str, Any]) -> list[str]:
    meshes = get_path(study, "derivedSection", "conditionBrowseModule", "meshes", default=[])
    return [
        normalize_text(mesh.get("term", ""))
        for mesh in meshes or []
        if isinstance(mesh, dict) and mesh.get("term")
    ]


def matched_long_covid_terms(study: dict[str, Any]) -> list[str]:
    haystack = [term.lower() for term in conditions(study) + condition_mesh_terms(study)]
    return sorted({token for token in LOCAL_LONG_COVID_TERMS if any(token in term for term in haystack)})


def is_local_long_covid(study: dict[str, Any]) -> bool:
    return bool(matched_long_covid_terms(study))


def interventions(study: dict[str, Any]) -> list[dict[str, Any]]:
    values = get_path(study, "protocolSection", "armsInterventionsModule", "interventions", default=[])
    return [value for value in values or [] if isinstance(value, dict)]


def intervention_names(study: dict[str, Any]) -> list[str]:
    return [normalize_text(item.get("name", "")) for item in interventions(study) if item.get("name")]


def intervention_types(study: dict[str, Any]) -> list[str]:
    return sorted({normalize_text(item.get("type", "")) for item in interventions(study) if item.get("type")})


def intervention_lookup(study: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {normalize_intervention_name(item.get("name", "")): item for item in interventions(study)}


def arm_groups(study: dict[str, Any]) -> list[dict[str, Any]]:
    values = get_path(study, "protocolSection", "armsInterventionsModule", "armGroups", default=[])
    return [value for value in values or [] if isinstance(value, dict)]


def active_arm_groups(study: dict[str, Any]) -> list[dict[str, Any]]:
    return [arm for arm in arm_groups(study) if arm.get("type") in ACTIVE_ARM_TYPES]


def primary_outcomes(study: dict[str, Any]) -> list[dict[str, Any]]:
    values = get_path(study, "protocolSection", "outcomesModule", "primaryOutcomes", default=[])
    return [value for value in values or [] if isinstance(value, dict)]


def primary_outcome_names(study: dict[str, Any]) -> list[str]:
    return [normalize_text(item.get("measure", "")) for item in primary_outcomes(study) if item.get("measure")]


def normalize_intervention_name(value: object) -> str:
    text = normalize_text(value)
    if ":" in text:
        text = text.split(":", 1)[1]
    return " ".join(text.lower().split())


def clean_intervention_display(value: object) -> str:
    text = normalize_text(value)
    if ":" in text:
        text = text.split(":", 1)[1]
    return " ".join(text.split())


def is_placebo_name(value: object) -> bool:
    return contains_any(normalize_intervention_name(value), PLACEBO_TERMS)


def active_intervention_names(study: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for arm in active_arm_groups(study):
        for name in arm.get("interventionNames") or []:
            clean = normalize_intervention_name(name)
            if clean and not is_placebo_name(clean):
                names.append(clean)
    return names


def active_intervention_display_names(study: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for arm in active_arm_groups(study):
        for name in arm.get("interventionNames") or []:
            clean = clean_intervention_display(name)
            if clean and not is_placebo_name(clean):
                names.append(clean)
    return names


def active_intervention_text(study: dict[str, Any]) -> str:
    lookup = intervention_lookup(study)
    pieces: list[str] = []
    for arm in active_arm_groups(study):
        pieces.append(arm.get("label", ""))
        pieces.append(arm.get("description", ""))
        for name in arm.get("interventionNames") or []:
            clean = normalize_intervention_name(name)
            pieces.append(clean)
            item = lookup.get(clean)
            if item:
                pieces.append(item.get("type", ""))
                pieces.append(item.get("name", ""))
                pieces.append(item.get("description", ""))
    return lower_blob(*pieces)


def active_intervention_type_set(study: dict[str, Any]) -> set[str]:
    lookup = intervention_lookup(study)
    types: set[str] = set()
    for name in active_intervention_names(study):
        item = lookup.get(name)
        if item and item.get("type"):
            types.add(normalize_text(item.get("type", "")))
    if not types:
        for arm in active_arm_groups(study):
            for name in arm.get("interventionNames") or []:
                clean = normalize_intervention_name(name)
                if not clean or is_placebo_name(clean):
                    continue
                prefix = normalize_text(name).split(":", 1)[0].upper() if ":" in normalize_text(name) else ""
                if prefix:
                    types.add(prefix)
    return types


def primary_intervention(study: dict[str, Any]) -> str:
    names = active_intervention_display_names(study)
    if not names:
        arms = active_arm_groups(study)
        return normalize_text(arms[0].get("label", "")) if arms else ""
    return names[0]


def has_combination_arm(study: dict[str, Any]) -> bool:
    for arm in active_arm_groups(study):
        non_placebo = [
            normalize_intervention_name(name)
            for name in arm.get("interventionNames") or []
            if normalize_intervention_name(name) and not is_placebo_name(name)
        ]
        if len(non_placebo) > 1:
            return True
    return False


def is_blinded(study: dict[str, Any]) -> bool:
    masking = normalize_text(
        get_path(study, "protocolSection", "designModule", "designInfo", "maskingInfo", "masking", default="")
    ).upper()
    return masking not in {"", "NONE"}


def intervention_accessibility(study: dict[str, Any]) -> tuple[str, str]:
    text = active_intervention_text(study)
    types = active_intervention_type_set(study)
    active_names = active_intervention_names(study)

    if not active_arm_groups(study):
        return ("off_premise", "no experimental or active-comparator arm")
    if not active_names:
        return ("off_premise", "no non-placebo active intervention name")
    if "homeopathic medication" in active_names and contains_any(text, BROAD_INDIVIDUALIZED_TERMS):
        return (
            "broad_individualized",
            "intervention is individualized homeopathic medicines rather than one named treatment",
        )
    if "BIOLOGICAL" in types or contains_any(text, CLINICAL_ADMIN_TERMS):
        return ("clinical_administered", "intervention appears infusion, injection, biologic, or procedure based on JSON text")
    if "DEVICE" in types or "BEHAVIORAL" in types or contains_any(text, BEHAVIORAL_DEVICE_TERMS):
        return ("behavioral_or_device", "intervention appears behavioral, device-based, diet, rehabilitation, or stimulation")
    if not (types & DRUG_TYPES or "OTHER" in types):
        return ("off_premise", f"active intervention type is not drug-like: {' | '.join(sorted(types))}")
    if contains_any(text, SELF_OBTAINABLE_TERMS):
        return ("self_obtainable", "active intervention appears self-obtainable from JSON name/description")
    return ("prescription_oral", "active intervention appears to be a self-administered or oral prescription drug")


def outcome_signal_for_text(text: str) -> EndpointSignal:
    if contains_any(text, ADMIN_ENDPOINT_TERMS):
        return "no"
    if contains_any(text, YES_ENDPOINT_TERMS):
        return "yes"
    if contains_any(text, PARTIAL_ENDPOINT_TERMS):
        return "partial"
    return "no"


def endpoint_signal(study: dict[str, Any]) -> tuple[EndpointSignal, str]:
    signals: list[EndpointSignal] = []
    labels: list[str] = []
    for outcome in primary_outcomes(study):
        measure = normalize_text(outcome.get("measure", ""))
        text = lower_blob(outcome.get("measure", ""), outcome.get("description", ""), outcome.get("timeFrame", ""))
        signal = outcome_signal_for_text(text)
        signals.append(signal)
        labels.append(f"{measure}: {signal}" if measure else signal)

    if "yes" in signals:
        return ("yes", " | ".join(labels))
    if "partial" in signals:
        return ("partial", " | ".join(labels))
    return ("no", " | ".join(labels) if labels else "no primary outcomes found")


def lightweight_structural_audit(study: dict[str, Any]) -> tuple[bool, list[str]]:
    """Mirror the project-level NATURAL preset from CT.gov JSON fields."""

    notes: list[str] = []
    protocol = get_path(study, "protocolSection", default={}) or {}
    status = get_path(protocol, "statusModule", "overallStatus", default="")
    design = get_path(protocol, "designModule", default={}) or {}
    design_info = design.get("designInfo", {}) or {}
    eligibility = get_path(protocol, "eligibilityModule", default={}) or {}

    if status != "COMPLETED":
        notes.append(f"status is {status or 'missing'}, not COMPLETED")
    if design.get("studyType") != "INTERVENTIONAL":
        notes.append(f"studyType is {design.get('studyType') or 'missing'}, not INTERVENTIONAL")
    if design_info.get("allocation") != "RANDOMIZED":
        notes.append(f"allocation is {design_info.get('allocation') or 'missing'}, not RANDOMIZED")

    healthy = eligibility.get("healthyVolunteers")
    if healthy in (True, "true", "TRUE", "Yes", "YES"):
        notes.append("healthyVolunteers is true")

    if not active_arm_groups(study):
        notes.append("no EXPERIMENTAL or ACTIVE_COMPARATOR arm")
    if not get_path(study, "resultsSection", default=None):
        notes.append("missing resultsSection")

    return not notes, notes


def natural_premise_screen(study: dict[str, Any]) -> NaturalPremiseScreen:
    accessibility, accessibility_reason = intervention_accessibility(study)
    signal, signal_reason = endpoint_signal(study)
    combo = has_combination_arm(study)
    single_agent = not combo
    blinded = is_blinded(study)
    types = " | ".join(sorted(active_intervention_type_set(study)))
    reasons: list[str] = []

    if combo:
        reasons.append("active arm has more than one non-placebo intervention")
    if not blinded:
        reasons.append("trial is open-label or masking is missing")
    if accessibility not in {"self_obtainable", "prescription_oral"}:
        reasons.append(accessibility_reason)
    if signal not in {"yes", "partial"}:
        reasons.append(f"primary endpoint is not patient-signal-relevant: {signal_reason}")

    strict = single_agent and blinded and accessibility == "self_obtainable" and signal == "yes"
    relaxed = single_agent and blinded and accessibility in {"self_obtainable", "prescription_oral"} and signal in {
        "yes",
        "partial",
    }
    tier = "strict" if strict else "relaxed" if relaxed else "off_premise"

    if tier != "off_premise":
        reason = f"{accessibility_reason}; endpoint screen: {signal_reason}"
    else:
        reason = " | ".join(reasons) if reasons else "failed NATURAL-premise screen"

    return NaturalPremiseScreen(
        passes=tier != "off_premise",
        tier=tier,
        reason=reason,
        primary_intervention=primary_intervention(study),
        accessibility=accessibility,
        endpoint_signal=signal,
        single_agent=single_agent,
        blinded=blinded,
        combination_arm=combo,
        active_intervention_types=types,
    )


def build_audit_record(study: dict[str, Any]) -> TrialAuditRecord:
    nct = nct_id(study)
    protocol = get_path(study, "protocolSection", default={}) or {}
    identification = protocol.get("identificationModule", {}) or {}
    status = protocol.get("statusModule", {}) or {}
    design = protocol.get("designModule", {}) or {}
    audit_ok, audit_notes = lightweight_structural_audit(study)
    premise = natural_premise_screen(study)

    return TrialAuditRecord(
        nct_id=nct,
        brief_title=normalize_text(identification.get("briefTitle", "")),
        overall_status=normalize_text(status.get("overallStatus", "")),
        phase=" | ".join(normalize_text(value) for value in design.get("phases", []) or []),
        enrollment=(design.get("enrollmentInfo", {}) or {}).get("count"),
        conditions=" | ".join(conditions(study)),
        condition_mesh_terms=" | ".join(condition_mesh_terms(study)),
        matched_long_covid_terms=" | ".join(matched_long_covid_terms(study)),
        interventions=" | ".join(intervention_names(study)),
        intervention_types=" | ".join(intervention_types(study)),
        primary_outcomes=" | ".join(primary_outcome_names(study)),
        passes_lightweight_structural_audit=audit_ok,
        lightweight_structural_notes=" | ".join(audit_notes),
        passes_natural_premise_screen=premise.passes,
        corpus_learnable_tier=premise.tier,
        natural_premise_reason=premise.reason,
        primary_intervention=premise.primary_intervention,
        intervention_accessibility=premise.accessibility,
        endpoint_signal=premise.endpoint_signal,
        single_agent=premise.single_agent,
        blinded=premise.blinded,
        combination_arm=premise.combination_arm,
        active_intervention_types=premise.active_intervention_types,
        ctgov_url=f"https://clinicaltrials.gov/study/{nct}",
    )


def write_outputs(records: list[TrialAuditRecord], audit_records: list[TrialAuditRecord], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = output_dir / "nct_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    for existing in reports_dir.glob("*.json"):
        existing.unlink()

    csv_path = output_dir / "long_covid_structured_learnable.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TrialAuditRecord.model_fields))
        writer.writeheader()
        for record in records:
            writer.writerow(record.model_dump(mode="json"))

    audit_path = output_dir / "long_covid_structured_audit.csv"
    with audit_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TrialAuditRecord.model_fields))
        writer.writeheader()
        for record in audit_records:
            writer.writerow(record.model_dump(mode="json"))

    nct_path = output_dir / "long_covid_structured_learnable_ncts.txt"
    nct_path.write_text("\n".join(record.nct_id for record in records) + "\n", encoding="utf-8")


def write_json_reports(records: list[TrialAuditRecord], studies_by_nct: dict[str, dict[str, Any]], output_dir: Path) -> None:
    reports_dir = output_dir / "nct_reports"
    for record in records:
        json_path = reports_dir / f"{record.nct_id}.json"
        json_path.write_text(
            json.dumps(studies_by_nct[record.nct_id], indent=2, sort_keys=True),
            encoding="utf-8",
        )


def render_summary(
    records: list[TrialAuditRecord],
    broad_count: int,
    local_count: int,
    structural_count: int,
    output_dir: Path,
) -> None:
    table = Table(
        title="CT.gov-structured Long COVID trials passing NATURAL-premise screen",
        box=box.SIMPLE,
        safe_box=True,
    )
    table.add_column("NCT")
    table.add_column("Tier")
    table.add_column("Intervention")
    table.add_column("Reason")
    table.add_column("Title")

    for record in records:
        table.add_row(
            record.nct_id,
            record.corpus_learnable_tier,
            display_text(record.primary_intervention),
            display_text(record.intervention_accessibility),
            display_text(record.brief_title),
        )

    console.print(table)
    console.print(f"Broad CT.gov pool: {broad_count}")
    console.print(f"After local Long COVID condition/MeSH filter: {local_count}")
    console.print(f"After lightweight structural audit: {structural_count}")
    console.print(f"After JSON-field NATURAL-premise screen: {len(records)}")
    console.print(f"Output directory: {output_dir}")


@app.command()
def main(
    output_dir: Path = typer.Option(
        DEFAULT_OUTPUT_DIR,
        "--output-dir",
        "-o",
        help="Directory for the CSV, audit CSV, NCT list, and raw CT.gov JSON files.",
    ),
    page_size: int = typer.Option(1000, help="CT.gov page size."),
) -> None:
    """Download CT.gov studies and select the corpus-learnable structured Long COVID subset."""

    studies = fetch_broad_pool(BROAD_LONG_COVID_QUERY, page_size)
    studies_by_nct = {nct_id(study): study for study in studies if nct_id(study)}

    local_long_covid = {
        nct: study for nct, study in studies_by_nct.items()
        if is_local_long_covid(study)
    }
    structural_long_covid = {
        nct: study for nct, study in local_long_covid.items()
        if lightweight_structural_audit(study)[0]
    }

    audit_records = [
        build_audit_record(study)
        for _, study in sorted(structural_long_covid.items())
    ]
    final_records = [record for record in audit_records if record.passes_natural_premise_screen]

    write_outputs(final_records, audit_records, output_dir)
    write_json_reports(final_records, studies_by_nct, output_dir)
    render_summary(final_records, len(studies), len(local_long_covid), len(structural_long_covid), output_dir)


if __name__ == "__main__":
    app()
