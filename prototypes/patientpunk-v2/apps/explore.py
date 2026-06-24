"""
apps/explore.py
~~~~~~~~~~~~~~~
Marimo app -- CSV table viewer.

Run with:
    marimo run apps/explore.py
    marimo edit apps/explore.py

Load any CSV output from the pipeline (demographics, records, codebook, etc.)
and explore it as a filterable, sortable table. Export filtered results back
to CSV.
"""

import marimo

__generated_with = "0.9.0"
app = marimo.App(width="wide", app_title="PatientPunk -- Data Explorer")


@app.cell
def _imports():
    import csv
    import io
    from pathlib import Path
    import marimo as mo
    return csv, io, Path, mo


@app.cell
def _file_picker(mo):
    """Pick a CSV file to explore."""
    file_input = mo.ui.file(
        filetypes=[".csv"],
        label="Upload CSV",
    )
    mo.vstack([
        mo.md("## PatientPunk -- Data Explorer"),
        mo.md("Upload a pipeline CSV output (demographics, records, etc.) to explore it as a table."),
        file_input,
    ])
    return (file_input,)


@app.cell
def _load_csv(file_input, csv, io, mo):
    """Parse the uploaded CSV into a list of dicts."""
    if not file_input.value:
        mo.stop(True, mo.md("_Upload a CSV file to begin._"))

    content = file_input.value[0].contents.decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    all_rows = list(reader)
    columns = list(reader.fieldnames or [])

    mo.callout(
        mo.md(f"Loaded **{len(all_rows):,} rows** × **{len(columns)} columns**: "
              + ", ".join(f"`{c}`" for c in columns)),
        kind="success",
    )
    return all_rows, columns


@app.cell
def _filter_controls(columns, mo):
    """Column filter: pick a column and a substring to search."""
    col_dd = mo.ui.dropdown(
        options=["(all columns)"] + columns,
        value="(all columns)",
        label="Filter column",
    )
    search_box = mo.ui.text(
        value="",
        placeholder="search text…",
        label="Contains",
    )
    mo.hstack([col_dd, search_box], gap=2)
    return col_dd, search_box


@app.cell
def _filtered_table(all_rows, columns, col_dd, search_box, mo):
    """Apply filter and render table."""
    needle = search_box.value.strip().lower()
    col = col_dd.value

    if not needle:
        filtered = all_rows
    elif col == "(all columns)":
        filtered = [
            r for r in all_rows
            if any(needle in str(v).lower() for v in r.values())
        ]
    else:
        filtered = [
            r for r in all_rows
            if needle in str(r.get(col, "")).lower()
        ]

    match_label = (
        f"**{len(filtered):,}** of **{len(all_rows):,}** rows"
        if needle else f"**{len(all_rows):,}** rows"
    )
    mo.vstack([
        mo.md(f"Showing {match_label}"),
        mo.ui.table(filtered, selection=None) if filtered else
        mo.callout(mo.md("No rows match the filter."), kind="warn"),
    ])
    return (filtered,)


@app.cell
def _export(filtered, mo, csv, io):
    """Export filtered results to CSV."""
    export_btn = mo.ui.button(label="Download filtered CSV")

    def _on_click(_):
        if not filtered:
            return
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(filtered[0].keys()))
        writer.writeheader()
        writer.writerows(filtered)
        return buf.getvalue()

    mo.hstack([
        export_btn,
        mo.md(f"_{len(filtered):,} rows will be exported_"),
    ], gap=1)
    return (export_btn,)
