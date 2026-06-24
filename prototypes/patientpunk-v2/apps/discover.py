"""
apps/discover.py
~~~~~~~~~~~~~~~~
Marimo app -- Variable picker.

Run with:
    marimo run apps/discover.py
    marimo edit apps/discover.py

Workflow:
  1. Upload the validated candidates JSON (Phase 2 output from discover_fields.py)
  2. Optionally upload the field report JSON (for corpus coverage stats)
  3. Review the candidate table -- check which fields to keep
  4. Click a row to see the detail panel (description, examples, regex patterns)
  5. Upload the target schema JSON and click Merge to write selected fields in

The app never auto-merges everything. Only fields you explicitly check get written.
"""

import marimo

__generated_with = "0.9.0"
app = marimo.App(width="wide", app_title="PatientPunk -- Variable Picker")


@app.cell
def _imports():
    import json
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

    import marimo as mo
    from patientpunk.models import ValidatedField, DiscoveryReport
    from patientpunk.db import merge_selected
    return json, Path, mo, ValidatedField, DiscoveryReport, merge_selected


@app.cell
def _header(mo):
    mo.vstack([
        mo.md("## PatientPunk -- Variable Picker"),
        mo.md(
            "Upload the **validated candidates JSON** produced by the discovery pipeline. "
            "Review each candidate, check the ones worth keeping, then merge into your schema."
        ),
    ])
    return ()


# ── File uploads ───────────────────────────────────────────────────────────────

@app.cell
def _uploads(mo):
    candidates_file = mo.ui.file(
        filetypes=[".json"],
        label="Validated candidates JSON (required)",
    )
    report_file = mo.ui.file(
        filetypes=[".json"],
        label="Field report JSON (optional -- adds coverage %)",
    )
    mo.hstack([candidates_file, report_file], gap=4)
    return candidates_file, report_file


@app.cell
def _load_candidates(candidates_file, report_file, json, mo,
                     ValidatedField, DiscoveryReport):
    """Parse uploaded files into typed objects."""
    if not candidates_file.value:
        mo.stop(True, mo.md("_Upload a validated candidates JSON file to begin._"))

    raw_candidates = json.loads(candidates_file.value[0].contents.decode("utf-8"))

    # The pipeline writes a list of dicts at the top level
    if isinstance(raw_candidates, dict) and "discovered_fields" in raw_candidates:
        raw_candidates = raw_candidates["discovered_fields"]

    candidates = [ValidatedField.model_validate(c) for c in raw_candidates]

    # Enrich with coverage from the report if provided
    report: DiscoveryReport | None = None
    if report_file.value:
        raw_report = json.loads(report_file.value[0].contents.decode("utf-8"))
        report = DiscoveryReport.model_validate(raw_report)
        for c in candidates:
            stat = report.field_stats.get(c.field_name)
            if stat:
                c.coverage = stat.coverage

    mo.callout(
        mo.md(
            f"Loaded **{len(candidates)}** candidate fields"
            + (f" with corpus coverage data from report" if report else "")
        ),
        kind="success",
    )
    return candidates, report


# ── Candidate table with checkboxes ───────────────────────────────────────────

@app.cell
def _candidate_table(candidates, mo):
    """Render the candidate selection table."""

    def _pct(v: float | None) -> str:
        return f"{v*100:.1f}%" if v is not None else "--"

    def _conf_badge(c: str) -> str:
        icons = {"high": "🟢", "medium": "🟡", "low": "🔴"}
        return f"{icons.get(c, '⚪')} {c}"

    table_rows = {
        c.field_name: {
            "Field":         c.field_name,
            "Description":   c.description[:80] + ("…" if len(c.description) > 80 else ""),
            "Coverage":      _pct(c.coverage),
            "Hit rate":      _pct(c.hit_rate) if c.hit_rate else "--",
            "Confidence":    _conf_badge(c.confidence),
            "Frequency":     c.frequency_hint,
            "LLM-only":      "yes" if c.llm_only else "no",
        }
        for c in candidates
    }

    checkbox_table = mo.ui.table(
        list(table_rows.values()),
        label="Select fields to keep",
        selection="multi",
    )
    checkbox_table
    return checkbox_table, table_rows


# ── Detail panel ───────────────────────────────────────────────────────────────

@app.cell
def _detail_panel(checkbox_table, candidates, mo):
    """Show details for the selected row(s)."""
    selected_indices = checkbox_table.value  # list of selected row dicts

    if not selected_indices:
        mo.stop(False)  # show nothing, don't halt execution

    # Match selected row back to candidate by field name
    selected_names_in_table = {r["Field"] for r in selected_indices}
    to_show = [c for c in candidates if c.field_name in selected_names_in_table]

    panels = []
    for c in to_show:
        patterns_md = "\n".join(f"- `{p}`" for p in c.patterns) or "_none_"
        vocab_md = ", ".join(f"`{v}`" for v in c.trigger_vocabulary) or "_none_"
        allowed_md = (
            ", ".join(f"`{v}`" for v in c.allowed_values)
            if c.allowed_values else "_free text_"
        )
        panels.append(mo.callout(
            mo.md(f"""
### {c.field_name}

**Description:** {c.description}

**Research value:** {c.research_value or "_not specified_"}

**Regex patterns ({len(c.patterns)}):**
{patterns_md}

**Trigger vocabulary:** {vocab_md}

**Allowed values:** {allowed_md}

**Extractability note:** {c.extractability_note or "_none_"}
"""),
            kind="info",
        ))

    mo.vstack(panels)
    return ()


# ── Schema merge ───────────────────────────────────────────────────────────────

@app.cell
def _merge_controls(mo):
    schema_file = mo.ui.file(
        filetypes=[".json"],
        label="Target schema JSON",
    )
    merge_btn = mo.ui.button(label="Merge selected into schema", kind="success")
    mo.hstack([schema_file, merge_btn], gap=4)
    return schema_file, merge_btn


@app.cell
def _merge_action(merge_btn, schema_file, checkbox_table, candidates,
                  merge_selected, json, Path, mo):
    """Write selected fields into the uploaded schema and offer download."""
    if not merge_btn.value:
        mo.stop(False)

    if not schema_file.value:
        mo.callout(mo.md("**Upload a target schema JSON first.**"), kind="danger")
        mo.stop(False)

    selected_rows = checkbox_table.value
    if not selected_rows:
        mo.callout(mo.md("**No fields selected.**"), kind="warn")
        mo.stop(False)

    selected_names = {r["Field"] for r in selected_rows}
    validated_dicts = [c.model_dump() for c in candidates]

    # Parse the uploaded schema, apply merge in memory, return updated JSON
    schema_content = schema_file.value[0].contents.decode("utf-8")
    schema = json.loads(schema_content)
    extension_fields = schema.setdefault("extension_fields", {})

    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    added = []
    for field in validated_dicts:
        name = field.get("field_name", "")
        if name not in selected_names:
            continue
        extension_fields[name] = {
            "description":            field.get("description", ""),
            "confidence":             field.get("confidence", "medium"),
            "source":                 field.get("source", "llm_discovered"),
            "_discovered_at":         now,
            "hit_rate_at_discovery":  field.get("hit_rate", 0.0),
            "coverage":               field.get("coverage"),
            "frequency_hint":         field.get("frequency_hint", "occasional"),
            "research_value":         field.get("research_value", ""),
            "patterns":               field.get("patterns", []),
            "llm_only":               field.get("llm_only", False),
            "extractability_note":    field.get("extractability_note", ""),
            "allowed_values":         field.get("allowed_values"),
            "trigger_vocabulary":     field.get("trigger_vocabulary", []),
        }
        added.append(name)

    updated_json = json.dumps(schema, indent=2)

    mo.vstack([
        mo.callout(
            mo.md(f"Merged **{len(added)}** field(s) into schema: "
                  + ", ".join(f"`{n}`" for n in added)),
            kind="success",
        ),
        mo.download(
            data=updated_json.encode("utf-8"),
            filename="schema_updated.json",
            mimetype="application/json",
            label="Download updated schema",
        ),
    ])
    return ()
