"""Privacy checks for aggregate study artifacts proposed for Git."""

from __future__ import annotations

import re
from pathlib import Path

import typer
from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console

from studies.tropoflavin_nootropics.study_support import (
    CANONICAL_SIDE_EFFECT_BUCKETS,
    CANONICAL_SIDE_EFFECT_LABELS,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()
_FORBIDDEN = {
    "Windows user path": re.compile(r"(?i)\b[A-Z]:[\\/]Users[\\/]"),
    "POSIX user path": re.compile(r"(?i)(?:/Users/|/home/)[^\s`]+"),
    "author-sized hexadecimal identifier": re.compile(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])"),
    "record-level author field": re.compile(r"(?i)[\"']author_hash[\"']\s*:"),
    "record-level body field": re.compile(r"(?i)[\"']body_text[\"']\s*:"),
}


class PrivacyFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: Path
    rule: str
    line: int = Field(ge=1)


def scan_aggregate_artifact(path: Path) -> tuple[PrivacyFinding, ...]:
    """Return privacy findings without echoing sensitive matching text."""
    findings: list[PrivacyFinding] = []
    text = path.read_text(encoding="utf-8")
    for line_number, line in enumerate(text.splitlines(), start=1):
        for rule, pattern in _FORBIDDEN.items():
            if pattern.search(line):
                findings.append(
                    PrivacyFinding(path=path, rule=rule, line=line_number)
                )
        cells = tuple(cell.strip() for cell in line.strip().strip("|").split("|"))
        if (
            len(cells) >= 3
            and cells[2] in CANONICAL_SIDE_EFFECT_BUCKETS
            and cells[1] not in CANONICAL_SIDE_EFFECT_LABELS
        ):
            findings.append(
                PrivacyFinding(
                    path=path,
                    rule="noncanonical side-effect wording",
                    line=line_number,
                )
            )
    return tuple(findings)


def require_private_aggregate_artifacts(paths: tuple[Path, ...]) -> None:
    """Raise when any proposed aggregate artifact contains sensitive patterns."""
    findings = tuple(
        finding for path in paths for finding in scan_aggregate_artifact(path)
    )
    if findings:
        summary = ", ".join(
            f"{finding.path.name}:{finding.line} ({finding.rule})"
            for finding in findings
        )
        raise ValueError(f"Aggregate artifact privacy scan failed: {summary}")


@app.command()
def main(paths: list[Path] = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    """Scan proposed aggregate artifacts before they are added to Git."""
    try:
        require_private_aggregate_artifacts(tuple(paths))
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]Privacy scan passed[/green] for {len(paths)} artifact(s)")


if __name__ == "__main__":
    app()
