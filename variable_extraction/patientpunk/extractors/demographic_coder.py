"""
patientpunk.extractors.demographic_coder
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Inductive + deductive demographic coder.

Wraps ``scripts/code_demographics_llm.py``.  Supports three coding modes:

* **deductive** -- extract predefined fields (age, sex_gender, location_country,
  location_state) from author self-reports.
* **inductive** -- discover new demographic categories (occupation, ethnicity,
  disability status, etc.) that emerge from the data.
* **both** (default) -- do deductive + inductive in a single LLM pass.

Output files
------------
* ``{output_dir}/demographics_deductive.csv``  -- predefined fields (deductive)
* ``{output_dir}/demographics_inductive.json`` -- per-record discoveries (inductive)
* ``{output_dir}/demographics_codebook.json``  -- aggregated category frequencies

Requires an Anthropic API key in the project-root ``.env``.

Example
-------
>>> coder = DemographicCoder(
...     input_dir=Path("../reddit_sample_data"),
...     mode="both",
...     workers=10,
... )
>>> result = coder.run()
>>> print(f"Coding done in {result.elapsed:.1f}s")
"""

from __future__ import annotations

from pathlib import Path

from .base import BaseExtractor


class DemographicCoder(BaseExtractor):
    """
    Inductive + deductive demographic coder.

    Parameters
    ----------
    input_dir:
        Directory containing ``subreddit_posts.json`` and/or ``users/``.
    output_dir:
        Output directory for CSV and JSON files.  Defaults to *input_dir*.
    mode:
        Coding mode -- ``"deductive"`` | ``"inductive"`` | ``"both"`` (default).
    workers:
        Concurrent Haiku API requests (default: 10).
    include_posts:
        Process ``subreddit_posts.json`` (default: *True*).
    include_users:
        Process ``users/*.json`` histories (default: *True*).
    max_chars:
        Maximum characters of text sent per record to the LLM (default: 8000).
    """

    _SCRIPT = "code_demographics_llm.py"

    def __init__(
        self,
        input_dir: Path,
        output_dir: Path | None = None,
        *,
        mode: str = "both",
        workers: int = 10,
        include_posts: bool = True,
        include_users: bool = True,
        max_chars: int = 8000,
    ) -> None:
        super().__init__(input_dir=input_dir, schema_path=None, temp_dir=input_dir)
        self.output_dir = Path(output_dir) if output_dir else None
        self.mode = mode
        self.workers = workers
        if not include_posts and not include_users:
            raise ValueError(
                "At least one source must be enabled: "
                "include_posts and include_users cannot both be False."
            )
        self.include_posts = include_posts
        self.include_users = include_users
        self.max_chars = max_chars

    def _build_args(self) -> list[str]:
        args = [
            "--input-dir", str(self.input_dir),
            "--mode",      self.mode,
            "--workers",   str(self.workers),
            "--max-chars", str(self.max_chars),
        ]
        if self.output_dir:
            args += ["--output-dir", str(self.output_dir)]
        if not self.include_posts and self.include_users:
            args += ["--users-only"]
        elif self.include_posts and not self.include_users:
            args += ["--posts-only"]
        return args
