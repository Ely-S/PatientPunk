"""
Notebook builder and executor for PatientPunk research notebooks.

Usage:
    from build_notebook import build_notebook, execute_and_export

    nb = build_notebook(
        cells=[
            ("md", "# My Analysis\\n\\nAbstract here..."),
            ("code", "df = pd.read_sql('SELECT * FROM treatment', conn)\\ndisplay(df.head(10))"),
            ("md", "**What this means:** ..."),
        ],
        db_path="historical_validation_2020-07_to_2022-12.db",
        title="My Analysis",
    )

    execute_and_export(nb, "notebooks/v2/1_my_analysis")
"""

import nbformat
from nbformat.v4 import new_notebook, new_code_cell, new_markdown_cell
from pathlib import Path


# ── Default DB-resolution block ─────────────────────────────────────────────
# Callers can override this by passing `db_path_block=` to build_notebook().
# The default is the simple "literal path" form preserved for backward
# compatibility with other notebooks in the repo.
DEFAULT_DB_PATH_BLOCK = '''DB_PATH = "{db_path}"
conn = sqlite3.connect(DB_PATH)'''


# ── Standard setup code injected into every notebook ────────────────────────
SETUP_CODE = '''import warnings
warnings.filterwarnings("ignore")

import sqlite3
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats as sp_stats
from scipy.stats import binomtest, mannwhitneyu, fisher_exact, kruskal
from statsmodels.stats.proportion import proportion_confint
from IPython.display import display, HTML, Markdown

# ── Database connection ──
{db_path_block}

# ── Sentiment mapping ──
SENTIMENT_SCORE = {{"positive": 1.0, "mixed": 0.5, "neutral": 0.0, "negative": -1.0}}

def to_numeric(s):
    """Convert sentiment string to numeric score."""
    return SENTIMENT_SCORE.get(s, 0.0)

def classify_outcome(avg_score):
    """Classify user-level average into outcome category."""
    if avg_score > 0.7:
        return "positive"
    elif avg_score < -0.3:
        return "negative"
    return "mixed/neutral"

def wilson_ci(k, n, alpha=0.05):
    """Wilson score confidence interval for a binomial proportion.
    Thin wrapper around statsmodels.stats.proportion.proportion_confint
    so notebook code has the convenience name.
    """
    if n == 0:
        return 0.0, 0.0
    return proportion_confint(k, n, alpha=alpha, method="wilson")

def nnt(treatment_rate, baseline_rate):
    """Number needed to treat. Returns None if rates are equal or inverted."""
    diff = treatment_rate - baseline_rate
    if diff <= 0:
        return None
    return round(1 / diff, 1)

# ── Chart defaults ──
sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (12, 6)
plt.rcParams["font.size"] = 11

# ── Filtering sets ──
GENERIC_TERMS = {{
    "supplements", "medication", "treatment", "therapy", "drug", "drugs",
    "vitamin", "prescription", "pill", "pills", "dosage", "dose",
}}

# Colors
COLORS = {{"positive": "#2ecc71", "mixed/neutral": "#95a5a6", "negative": "#e74c3c"}}
'''


def build_notebook(cells, db_path="patientpunk.db", db_path_block=None, title=None):
    """Build a valid Jupyter notebook from a list of (type, source) tuples.

    Args:
        cells: list of ("md", source_string) or ("code", source_string) tuples
        db_path: path to SQLite database (injected into setup cell as a string
                 literal). Ignored if db_path_block is provided.
        db_path_block: raw Python source that defines `DB_PATH` and `conn`.
                       Use this when callers need richer resolution than a
                       hard-coded literal — e.g., the RCT validation package
                       embeds its anchor-based resolver here so the notebook
                       finds its DB regardless of cwd.
        title: optional — not used in the notebook, just for reference

    Returns:
        nbformat.NotebookNode ready for execution
    """
    nb = new_notebook()
    nb.metadata.kernelspec = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }

    if db_path_block is None:
        # Keep path as posix (forward slashes) so the notebook is portable
        db_path_resolved = Path(db_path).as_posix()
        db_path_block = DEFAULT_DB_PATH_BLOCK.format(db_path=db_path_resolved)
    # Inject setup cell (produces zero output)
    setup = SETUP_CODE.format(db_path_block=db_path_block)
    nb.cells.append(new_code_cell(source=setup))

    # Add user cells
    for cell_type, source in cells:
        if cell_type == "md":
            nb.cells.append(new_markdown_cell(source=source))
        elif cell_type == "code":
            nb.cells.append(new_code_cell(source=source))
        else:
            raise ValueError(f"Unknown cell type: {cell_type!r}. Use 'md' or 'code'.")

    return nb


def execute_and_export(nb, output_stem, timeout=600):
    """Execute a notebook and export to HTML.

    Args:
        nb: nbformat.NotebookNode (from build_notebook)
        output_stem: path without extension, e.g., "notebooks/v2/1_overview"
                     Produces: {stem}.ipynb, {stem}_executed.ipynb, {stem}.html
        timeout: max seconds per cell

    Returns:
        Path to HTML file
    """
    from nbconvert.preprocessors import ExecutePreprocessor
    from nbconvert import HTMLExporter

    stem = Path(output_stem)
    stem.parent.mkdir(parents=True, exist_ok=True)

    # Save source notebook
    source_path = stem.with_suffix(".ipynb")
    nbformat.write(nb, str(source_path))

    # Execute
    ep = ExecutePreprocessor(timeout=timeout, kernel_name="python3")
    ep.preprocess(nb, {"metadata": {"path": str(stem.parent)}})

    # Save executed notebook
    executed_path = stem.parent / f"{stem.stem}_executed.ipynb"
    nbformat.write(nb, str(executed_path))

    # Export to HTML (no code cells)
    exporter = HTMLExporter()
    exporter.exclude_input = True
    body, _ = exporter.from_notebook_node(nb)
    html_path = stem.with_suffix(".html")
    html_path.write_text(body, encoding="utf-8")

    return html_path
