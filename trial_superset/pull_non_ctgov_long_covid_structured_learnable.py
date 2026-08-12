"""Screen non-CT.gov registry candidates with the Long COVID NATURAL-premise logic.

Input comes from `mine_registries.py`. This script re-fetches structured ISRCTN
XML, applies a CT.gov-like local Long COVID and NATURAL-premise screen, and emits
both a full audit CSV and a clean subset CSV. EudraCT rows remain audit-only
until a registry fetch adapter is added.
"""

from __future__ import annotations

import csv
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

import requests
import typer
from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table

from pull_ctgov_long_covid_structured_learnable import (
    BEHAVIORAL_DEVICE_TERMS,
    BROAD_INDIVIDUALIZED_TERMS,
    CLINICAL_ADMIN_TERMS,
    LOCAL_LONG_COVID_TERMS,
    SELF_OBTAINABLE_TERMS,
    EndpointSignal,
    contains_any,
    lower_blob,
    normalize_text,
    outcome_signal_for_text,
)

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = PACKAGE_ROOT / "data" / "mined_registries.csv"
DEFAULT_OUTPUT_DIR = PACKAGE_ROOT / "data" / "non_ctgov_structured_learnable"
ISRCTN_API = "https://www.isrctn.com/api/query/format/default"
HEADERS = {
    "accept": "application/xml",
    "user-agent": "PatientPunk trial_superset non-CT.gov Long COVID benchmark pull",
}
DRUG_LIKE_TYPES = {"drug", "supplement"}
COMBINATION_TERMS = (
    " platform ",
    " adaptive ",
    " multi-arm ",
    " multi arm ",
    " factorial ",
    " combination ",
)
COMBINATION_SEPARATORS = (" + ", ",", ";")

app = typer.Typer(add_completion=False)
console = Console()


class MinedRegistryRow(BaseModel):
    """Boundary model for rows emitted by mine_registries.py."""

    trial_id: str
    registry: str
    fetch_ok: str = ""
    usable: str = ""
    looks_long_covid: str = ""
    interventional: str = ""
    randomized: str = ""
    participant_type: str = ""
    intervention_type: str = ""
    condition: str = ""
    title: str = ""
    source_papers: str = ""
    note: str = ""


class IsrctnRecord(BaseModel):
    """Selected structured fields from an ISRCTN XML record."""

    trial_id: str
    title: str = ""
    scientific_title: str = ""
    primary_study_design: str = ""
    secondary_study_design: str = ""
    study_design: str = ""
    trial_type: str = ""
    participant_type: str = ""
    intervention_type: str = ""
    condition: str = ""
    intervention: str = ""
    primary_outcome: str = ""
    recruitment_status: str = ""
    overall_end_date: str = ""
    total_final_enrolment: str = ""
    results: str = ""
    plain_english_report: str = ""
    drug_names: str = ""
    eudract_number: str = ""
    ctgov_number: str = ""


class RegistryAuditRecord(BaseModel):
    """Persisted audit row for a non-CT.gov registry candidate."""

    trial_id: str
    registry: str
    source_url: str
    fetch_ok: bool
    title: str = ""
    condition: str = ""
    intervention_type: str = ""
    intervention: str = ""
    drug_names: str = ""
    primary_outcome: str = ""
    overall_end_date: str = ""
    total_final_enrolment: str = ""
    source_papers: str = ""
    matched_long_covid_terms: str = ""
    completed: bool = False
    results_reference_found: bool = False
    interventional: bool = False
    randomized: bool = False
    patient_population: bool = False
    blinded: bool = False
    single_agent: bool = False
    intervention_accessibility: str = ""
    endpoint_signal: EndpointSignal = "no"
    passes_structural_screen: bool = False
    passes_natural_premise_screen: bool = False
    corpus_learnable_tier: str = "off_premise"
    screen_reason: str = ""
    note: str = ""


class OutputPaths(BaseModel):
    """Output locations for the registry screen."""

    output_dir: Path
    audit_csv: Path
    clean_csv: Path
    ids_txt: Path
    isrctn_reports_dir: Path


def make_output_paths(output_dir: Path) -> OutputPaths:
    return OutputPaths(
        output_dir=output_dir,
        audit_csv=output_dir / "long_covid_non_ctgov_structured_audit.csv",
        clean_csv=output_dir / "long_covid_non_ctgov_structured_learnable.csv",
        ids_txt=output_dir / "long_covid_non_ctgov_structured_learnable_ids.txt",
        isrctn_reports_dir=output_dir / "isrctn_reports",
    )


def read_registry_rows(path: Path) -> list[MinedRegistryRow]:
    if not path.exists():
        raise typer.BadParameter(f"Input CSV does not exist: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [MinedRegistryRow.model_validate(row) for row in csv.DictReader(handle)]


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def collapse_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def first_element_text(root: ET.Element, tag_name: str) -> str:
    for element in root.iter():
        if local_name(element.tag) == tag_name:
            return collapse_text(" ".join(element.itertext()))
    return ""


def parse_isrctn_xml(trial_id: str, xml_text: str) -> IsrctnRecord:
    root = ET.fromstring(xml_text)
    return IsrctnRecord(
        trial_id=trial_id,
        title=first_element_text(root, "title"),
        scientific_title=first_element_text(root, "scientificTitle"),
        primary_study_design=first_element_text(root, "primaryStudyDesign"),
        secondary_study_design=first_element_text(root, "secondaryStudyDesign"),
        study_design=first_element_text(root, "studyDesign"),
        trial_type=first_element_text(root, "trialType"),
        participant_type=first_element_text(root, "participantType"),
        intervention_type=first_element_text(root, "interventionType"),
        condition=first_element_text(root, "condition"),
        intervention=first_element_text(root, "intervention"),
        primary_outcome=first_element_text(root, "primaryOutcome"),
        recruitment_status=first_element_text(root, "recruitmentStatusOverride"),
        overall_end_date=first_element_text(root, "overallEndDate"),
        total_final_enrolment=first_element_text(root, "totalFinalEnrolment"),
        results=first_element_text(root, "results"),
        plain_english_report=first_element_text(root, "plainEnglishReport"),
        drug_names=first_element_text(root, "drugNames"),
        eudract_number=first_element_text(root, "eudraCTNumber"),
        ctgov_number=first_element_text(root, "clinicalTrialsGovNumber"),
    )


def fetch_isrctn_xml(session: requests.Session, trial_id: str) -> str:
    for attempt in range(3):
        try:
            response = session.get(ISRCTN_API, params={"q": trial_id}, timeout=60)
            response.raise_for_status()
            if "<fullTrial" in response.text:
                return response.text
        except requests.RequestException:
            time.sleep(1.5 * (attempt + 1))
    return ""


def parse_isrctn_date(value: str) -> date | None:
    text = normalize_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(text[: len(datetime.now().strftime(fmt))], fmt).date()
        except ValueError:
            continue
    return None


def matched_long_covid_terms(record: IsrctnRecord) -> list[str]:
    haystack = lower_blob(
        record.title,
        record.scientific_title,
        record.condition,
    )
    return sorted({term for term in LOCAL_LONG_COVID_TERMS if term in haystack})


def is_completed(record: IsrctnRecord, today: date) -> bool:
    status_text = lower_blob(record.recruitment_status)
    if contains_any(status_text, ("complete", "closed")):
        return True
    end_date = parse_isrctn_date(record.overall_end_date)
    return bool(end_date and end_date <= today)


def has_results_reference(record: IsrctnRecord) -> bool:
    text = lower_blob(record.results, record.plain_english_report)
    return contains_any(
        text,
        (
            "results article",
            "plain english report",
            "pubmed",
            "doi.org",
            "published results",
        ),
    )


def is_interventional(record: IsrctnRecord) -> bool:
    return "interventional" in lower_blob(record.primary_study_design)


def is_randomized(record: IsrctnRecord) -> bool:
    return "randomi" in lower_blob(record.secondary_study_design, record.study_design)


def is_patient_population(record: IsrctnRecord) -> bool:
    text = lower_blob(record.participant_type)
    return "patient" in text and "healthy" not in text


def is_blinded(record: IsrctnRecord) -> bool:
    text = lower_blob(record.study_design, record.intervention)
    if contains_any(text, ("open-label", "open label", "non-blind", "non blind", "non-blinded")):
        return False
    return contains_any(text, ("double-blind", "single-blind", "blind", "masked", "placebo-controlled"))


def has_single_active_agent(record: IsrctnRecord) -> bool:
    text = lower_blob(record.intervention, record.drug_names, record.study_design, record.scientific_title)
    drug_names = normalize_text(record.drug_names)
    if contains_any(text, COMBINATION_TERMS):
        return False
    if any(separator in drug_names for separator in COMBINATION_SEPARATORS):
        return False
    if " plus " in text and "placebo" not in text:
        return False
    return True


def classify_intervention_accessibility(record: IsrctnRecord) -> tuple[str, str]:
    text = lower_blob(
        record.title,
        record.scientific_title,
        record.intervention_type,
        record.intervention,
        record.drug_names,
    )
    intervention_type = lower_blob(record.intervention_type)
    if "homeopathic medication" in text and contains_any(text, BROAD_INDIVIDUALIZED_TERMS):
        return (
            "broad_individualized",
            "intervention is individualized homeopathic medicines rather than one named treatment",
        )
    if contains_any(text, CLINICAL_ADMIN_TERMS):
        return (
            "clinical_administered",
            "intervention appears infusion, injection, biologic, or procedure based on registry text",
        )
    if "device" in intervention_type or "behavioural" in intervention_type or contains_any(
        text, BEHAVIORAL_DEVICE_TERMS
    ):
        return (
            "behavioral_or_device",
            "intervention appears behavioral, device-based, diet, rehabilitation, or stimulation",
        )
    if not any(token in intervention_type for token in DRUG_LIKE_TYPES):
        return ("off_premise", f"intervention type is not drug-like: {record.intervention_type}")
    if "supplement" in intervention_type or contains_any(text, SELF_OBTAINABLE_TERMS):
        return ("self_obtainable", "active intervention appears self-obtainable from registry text")
    return ("prescription_oral", "active intervention appears to be a self-administered or oral drug")


def screen_isrctn_record(
    row: MinedRegistryRow,
    record: IsrctnRecord,
    today: date,
) -> RegistryAuditRecord:
    terms = matched_long_covid_terms(record)
    completed = is_completed(record, today)
    interventional = is_interventional(record)
    randomized = is_randomized(record)
    patient_population = is_patient_population(record)
    blinded = is_blinded(record)
    single_agent = has_single_active_agent(record)
    accessibility, accessibility_reason = classify_intervention_accessibility(record)
    signal = outcome_signal_for_text(lower_blob(record.primary_outcome))
    results_reference_found = has_results_reference(record)

    structural_reasons: list[str] = []
    if not terms:
        structural_reasons.append("no local Long COVID term in ISRCTN fields")
    if not completed:
        structural_reasons.append("trial does not appear completed from ISRCTN end/status fields")
    if not interventional:
        structural_reasons.append("primaryStudyDesign is not interventional")
    if not randomized:
        structural_reasons.append("studyDesign is not randomized")
    if not patient_population:
        structural_reasons.append("participantType is not patient")
    passes_structural = not structural_reasons

    premise_reasons: list[str] = []
    if not passes_structural:
        premise_reasons.extend(structural_reasons)
    if not single_agent:
        premise_reasons.append("intervention text suggests platform, combination, or multi-agent design")
    if not blinded:
        premise_reasons.append("trial is open-label or masking is missing")
    if accessibility not in {"self_obtainable", "prescription_oral"}:
        premise_reasons.append(accessibility_reason)
    if signal not in {"yes", "partial"}:
        premise_reasons.append("primary endpoint is not patient-signal-relevant")

    strict = (
        passes_structural
        and single_agent
        and blinded
        and accessibility == "self_obtainable"
        and signal == "yes"
    )
    relaxed = (
        passes_structural
        and single_agent
        and blinded
        and accessibility in {"self_obtainable", "prescription_oral"}
        and signal in {"yes", "partial"}
    )
    tier = "strict" if strict else "relaxed" if relaxed else "off_premise"
    reason = (
        f"{accessibility_reason}; endpoint screen: {signal}; "
        f"results_reference_found={results_reference_found}"
        if tier != "off_premise"
        else " | ".join(premise_reasons)
    )

    return RegistryAuditRecord(
        trial_id=row.trial_id,
        registry=row.registry,
        source_url=f"https://www.isrctn.com/{row.trial_id}",
        fetch_ok=True,
        title=record.title,
        condition=record.condition,
        intervention_type=record.intervention_type,
        intervention=record.intervention,
        drug_names=record.drug_names,
        primary_outcome=record.primary_outcome,
        overall_end_date=record.overall_end_date,
        total_final_enrolment=record.total_final_enrolment,
        source_papers=row.source_papers,
        matched_long_covid_terms=" | ".join(terms),
        completed=completed,
        results_reference_found=results_reference_found,
        interventional=interventional,
        randomized=randomized,
        patient_population=patient_population,
        blinded=blinded,
        single_agent=single_agent,
        intervention_accessibility=accessibility,
        endpoint_signal=signal,
        passes_structural_screen=passes_structural,
        passes_natural_premise_screen=tier != "off_premise",
        corpus_learnable_tier=tier,
        screen_reason=reason,
    )


def unsupported_row(row: MinedRegistryRow) -> RegistryAuditRecord:
    note = (
        "EudraCT rows are recorded by mine_registries.py, but this project has no structured "
        "fetch adapter for them yet."
        if row.registry.lower() == "eudract"
        else row.note or "registry fetch failed"
    )
    return RegistryAuditRecord(
        trial_id=row.trial_id,
        registry=row.registry,
        source_url="",
        fetch_ok=False,
        title=row.title,
        condition=row.condition,
        intervention_type=row.intervention_type,
        source_papers=row.source_papers,
        screen_reason=note,
        note=note,
    )


def write_outputs(records: list[RegistryAuditRecord], paths: OutputPaths) -> None:
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    clean_records = [record for record in records if record.passes_natural_premise_screen]
    fieldnames = list(RegistryAuditRecord.model_fields)
    for output_path, rows in ((paths.audit_csv, records), (paths.clean_csv, clean_records)):
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(record.model_dump() for record in rows)
    paths.ids_txt.write_text(
        "\n".join(record.trial_id for record in clean_records) + ("\n" if clean_records else ""),
        encoding="utf-8",
    )


def render_summary(records: list[RegistryAuditRecord], paths: OutputPaths) -> None:
    clean = [record for record in records if record.passes_natural_premise_screen]
    result_ready = [record for record in clean if record.results_reference_found]
    table = Table(title="Non-CT.gov Long COVID registry screen")
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    table.add_row("audit rows", str(len(records)))
    table.add_row("fetch ok", str(sum(record.fetch_ok for record in records)))
    table.add_row("structural screen", str(sum(record.passes_structural_screen for record in records)))
    table.add_row("NATURAL-premise screen", str(len(clean)))
    table.add_row("NATURAL-premise plus results reference", str(len(result_ready)))
    console.print(table)
    console.print(f"Wrote {paths.clean_csv}")
    console.print(f"Wrote {paths.audit_csv}")


def pull_and_screen(
    input_csv: Path,
    output_dir: Path,
    limit: int | None = None,
) -> list[RegistryAuditRecord]:
    rows = read_registry_rows(input_csv)
    if limit is not None:
        rows = rows[:limit]
    paths = make_output_paths(output_dir)
    paths.isrctn_reports_dir.mkdir(parents=True, exist_ok=True)
    today = date.today()
    records: list[RegistryAuditRecord] = []
    with requests.Session() as session:
        session.headers.update(HEADERS)
        for row in rows:
            if row.registry.lower() != "isrctn":
                records.append(unsupported_row(row))
                continue
            xml_text = fetch_isrctn_xml(session, row.trial_id)
            if not xml_text:
                records.append(unsupported_row(row))
                continue
            (paths.isrctn_reports_dir / f"{row.trial_id}.xml").write_text(
                xml_text,
                encoding="utf-8",
            )
            try:
                record = parse_isrctn_xml(row.trial_id, xml_text)
            except ET.ParseError as exc:
                failed = unsupported_row(row)
                failed.screen_reason = f"ISRCTN XML parse failed: {exc}"
                records.append(failed)
                continue
            records.append(screen_isrctn_record(row, record, today))
    write_outputs(records, paths)
    return records


@app.command()
def main(
    input_csv: Path = typer.Option(
        DEFAULT_INPUT,
        "--input",
        "-i",
        help="CSV emitted by mine_registries.py.",
    ),
    output_dir: Path = typer.Option(
        DEFAULT_OUTPUT_DIR,
        "--output-dir",
        "-o",
        help="Directory for audit CSV, clean CSV, id list, and raw ISRCTN XML.",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        help="Optional row limit for smoke tests.",
    ),
) -> None:
    """Screen non-CT.gov registry candidates for Long COVID NATURAL fit."""

    try:
        records = pull_and_screen(input_csv, output_dir, limit)
    except typer.BadParameter:
        raise
    except Exception as exc:
        console.print(f"[red]Failed to screen non-CT.gov registries:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    render_summary(records, make_output_paths(output_dir))


if __name__ == "__main__":
    sys.exit(app())
