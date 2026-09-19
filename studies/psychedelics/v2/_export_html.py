"""Re-export the executed v2 notebooks as reader-facing HTML.

The notebooks stay the reproducible artifact; the HTML is the report, so code
inputs are excluded. Nothing is re-executed -- the outputs already in the
notebook are what gets published.

Every export is scanned before it is written. The probe database holds verbatim
patient text and re-identifiable author hashes, and the loader is what keeps
those out of the frames; this is the second gate, on the file that actually
leaves the repo.

    python studies/psychedelics/v2/_export_html.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import nbformat
from nbconvert import HTMLExporter

HERE = Path(__file__).parent
NOTEBOOKS = (
    "psychedelics_v2_01_methods",
    "psychedelics_v2_02_overview",
    "psychedelics_v2_03_deep_dive",
)

# Checked against rendered outputs only. The notebooks' prose names these fields
# to explain the privacy boundary, and a scan over the whole page would fire on
# that narrative rather than on anything exposed.
UNSAFE_IN_OUTPUT = (
    ("author hash", re.compile(r"author_hash", re.I)),
    ("raw source text", re.compile(r"\braw_text\b|\braw_event\b|evidence_json", re.I)),
    ("source window text", re.compile(r"source_window\.text", re.I)),
    ("evidence quote", re.compile(r"\bquote\b", re.I)),
)
# Checked against the whole page, prose included.
UNSAFE_ANYWHERE = (
    ("local filesystem path", re.compile(r"(?:/Users/|/home/|C:\\Users\\)\S+")),
)


def rendered_outputs(nb) -> str:
    """Everything a reader sees that came from executing a cell."""
    parts = []
    for cell in nb.cells:
        for out in cell.get("outputs", []):
            parts.append(out.get("text", ""))
            for mime, payload in out.get("data", {}).items():
                if mime.startswith("text/"):
                    parts.append(payload)
    return "".join(
        p if isinstance(p, str) else "".join(p) for p in parts
    )


def scan(body: str, outputs: str) -> list[str]:
    hits = [
        (label, pattern.search(outputs))
        for label, pattern in UNSAFE_IN_OUTPUT
    ] + [
        (label, pattern.search(body))
        for label, pattern in UNSAFE_ANYWHERE
    ]
    return [f"{label}: {m.group(0)[:80]!r}" for label, m in hits if m]


def main() -> int:
    exporter = HTMLExporter()
    exporter.exclude_input = True
    exporter.exclude_input_prompt = True
    exporter.exclude_output_prompt = True

    failed = False
    for stem in NOTEBOOKS:
        nb = nbformat.read(HERE / f"{stem}.ipynb", as_version=4)
        body, _ = exporter.from_notebook_node(nb)
        problems = scan(body, rendered_outputs(nb))
        if problems:
            failed = True
            print(f"REFUSED {stem}.html")
            for p in problems:
                print(f"  {p}")
            continue
        out = HERE / f"{stem}.html"
        out.write_text(body, encoding="utf-8")
        print(f"wrote {out.name}  ({out.stat().st_size / 1e6:.1f} MB)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
