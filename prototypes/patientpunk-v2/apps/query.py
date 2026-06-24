"""
apps/query.py
~~~~~~~~~~~~~
Marimo app -- Treatment outcome query.

Run with:
    marimo run apps/query.py
    marimo edit apps/query.py   # (editable notebook mode)

Lets researchers filter by drug, condition, sex, age group and see
sentiment aggregates from the combined Shaun + Polina pipeline outputs.
"""

import marimo

__generated_with = "0.9.0"
app = marimo.App(width="wide", app_title="PatientPunk -- Treatment Outcomes")


@app.cell
def _imports():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

    import sqlite3
    import marimo as mo
    from patientpunk.db import (
        init_db,
        query_treatment_outcomes,
        list_drugs,
        list_conditions,
    )
    return mo, init_db, query_treatment_outcomes, list_drugs, list_conditions, Path, sqlite3


@app.cell
def _db_path(mo, Path):
    """Pick the database file."""
    default_db = str(Path(__file__).parent.parent / "patientpunk.db")
    db_path_input = mo.ui.text(
        value=default_db,
        label="Database path",
        full_width=True,
    )
    db_path_input
    return (db_path_input,)


@app.cell
def _connect(db_path_input, init_db, Path, mo):
    """Open (or create) the database."""
    db_path = Path(db_path_input.value.strip())
    schema_sql = Path(__file__).parent.parent / "schema.sql"
    try:
        conn = init_db(db_path, schema_sql=schema_sql)
        db_status = mo.callout(mo.md(f"Connected: `{db_path}`"), kind="success")
    except Exception as e:
        conn = None
        db_status = mo.callout(mo.md(f"**Error:** {e}"), kind="danger")
    db_status
    return conn, db_path


@app.cell
def _filter_options(conn, list_drugs, list_conditions, mo):
    """Build dropdown options from what's actually in the database."""
    if conn is None:
        drug_options = []
        condition_options = []
    else:
        drug_options = ["(all)"] + list_drugs(conn)
        condition_options = ["(all)"] + list_conditions(conn)

    drug_dd = mo.ui.dropdown(
        options=drug_options,
        value="(all)",
        label="Drug / intervention",
    )
    condition_dd = mo.ui.dropdown(
        options=condition_options,
        value="(all)",
        label="Condition",
    )
    sex_dd = mo.ui.dropdown(
        options=["(all)", "female", "male", "non-binary", "other"],
        value="(all)",
        label="Sex / gender",
    )
    age_dd = mo.ui.dropdown(
        options=["(all)", "10s", "20s", "30s", "40s", "50s", "60s", "70s", "80s"],
        value="(all)",
        label="Age group",
    )

    mo.hstack([drug_dd, condition_dd, sex_dd, age_dd], gap=2)
    return drug_dd, condition_dd, sex_dd, age_dd


@app.cell
def _results(conn, drug_dd, condition_dd, sex_dd, age_dd,
              query_treatment_outcomes, mo):
    """Run query and display results table."""
    if conn is None:
        mo.stop(True, mo.callout(mo.md("No database connection."), kind="warn"))

    drug    = None if drug_dd.value == "(all)" else drug_dd.value
    cond    = None if condition_dd.value == "(all)" else condition_dd.value
    sex     = None if sex_dd.value == "(all)" else sex_dd.value
    age     = None if age_dd.value == "(all)" else age_dd.value

    rows = query_treatment_outcomes(conn, drug=drug, condition=cond, sex=sex, age_bucket=age)

    if not rows:
        mo.callout(mo.md("No results match the selected filters."), kind="warn")
    else:
        # Format percentages and round floats for display
        display_rows = []
        for r in rows:
            display_rows.append({
                "Drug":        r["drug"],
                "Reports":     r["n_reports"],
                "% Positive":  f'{r["pct_positive"]:.1f}%',
                "% Mixed":     f'{r["pct_mixed"]:.1f}%',
                "% Neutral":   f'{r["pct_neutral"]:.1f}%',
                "% Negative":  f'{r["pct_negative"]:.1f}%',
                "Avg Sentiment": f'{r["avg_sentiment"]:+.3f}',
                "Avg Signal":  f'{r["avg_signal"]:.3f}',
            })
        mo.ui.table(display_rows, selection=None)
