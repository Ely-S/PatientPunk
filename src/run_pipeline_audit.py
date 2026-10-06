"""Audit the latest persisted sentiment, dose, and effect decisions."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from pipeline.audit import MODEL_CODEX, ROOT, preflight, run_audit


app = typer.Typer(help=__doc__, no_args_is_help=True)
console = Console()


@app.command()
def main(
    db: Annotated[Path | None, typer.Option(help="Existing pipeline SQLite database, opened read-only.")] = None,
    output_db: Annotated[Path | None, typer.Option(help="Separate audit SQLite database outside the repo.")] = None,
    drug: Annotated[str | None, typer.Option(help="Canonical treatment name; omit for all treatments.")] = None,
    kind: Annotated[list[str] | None, typer.Option(help="Repeat sentiment, dose, or effect. Default: all.")] = None,
    limit: Annotated[int, typer.Option(min=0, help="At most N new decisions; 0 means all.")] = 0,
    max_rounds: Annotated[int, typer.Option(min=1, max=10,
        help="Maximum rounds of judge discussion per decision.")] = 10,
    codex_model: Annotated[str, typer.Option(help="gpt-6-astra or gpt-6.1-sol.")] = MODEL_CODEX,
    preflight_only: Annotated[bool, typer.Option(help="Check subscription logins without processing data.")] = False,
) -> None:
    """Run two independent subscription judges, then reconcile disagreements."""
    try:
        if preflight_only:
            preflight()
            console.print("[green]Subscription login configuration found.[/green] "
                          "A live call may still require reauthentication.")
            return
        if db is None or not db.is_file():
            raise ValueError(f"Source database does not exist: {db}")
        kinds = set(kind or ("sentiment", "dose", "effect"))
        if kinds - {"sentiment", "dose", "effect"}:
            raise ValueError("--kind must be sentiment, dose, or effect")
        data = Path(os.environ.get("PATIENTPUNK_DATA") or ROOT.parent / "PatientPunk_data")
        destination = output_db or data / "audits" / f"{db.stem}-dual-judge.sqlite"
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        counts = run_audit(db, destination, drug=drug, kinds=kinds, limit=limit,
                           max_rounds=max_rounds, codex_model=codex_model)
    except (ValueError, RuntimeError, OSError) as exc:
        console.print(f"[red]Audit failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    table = Table(title="Pipeline decision audit")
    table.add_column("Status")
    table.add_column("Decisions", justify="right")
    for label, count in counts.model_dump().items():
        table.add_row(label, str(count))
    console.print(table)
    console.print(f"Audit database: {destination.resolve()}")


if __name__ == "__main__":
    app()
