"""
patientpunk.extractors.demographics
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
LLM-only demographic extractor (age, sex/gender, location).

Wraps ``scripts/extract_demographics_llm.py``.  Unlike the main pipeline's
Phase 1 + 2 combination (regex → LLM backfill), this extractor skips regex
entirely and sends every record straight to Claude Haiku with a strict
self-reference constraint: the model is instructed to extract **only**
demographics the author explicitly states about themselves.

Extracts four fields per record
--------------------------------
* ``age``              -- integer, or null
* ``sex_gender``       -- ``"male"`` | ``"female"`` | ``"non-binary"`` | other | null
* ``location_country`` -- country name, or null
* ``location_state``   -- US state name / abbreviation, or null

Works across both corpus sources
----------------------------------
* Subreddit posts  (``subreddit_posts.json``)
* Full user histories (``users/*.json``) -- typically yields 4-5× more
  demographic coverage than single posts because people repeat demographics
  across many posts and comments.

Output file
-----------
* ``{output_path}``  (defaults to ``output/demographics.csv``)

Requires an Anthropic API key in ``variable_extraction/.env``.

Example
-------
>>> extractor = DemographicsExtractor(
...     input_dir=Path("../../reddit_sample_data"),
...     output_path=Path("output/demographics.csv"),
...     workers=10,
... )
>>> result = extractor.run()
>>> print(f"LLM-only demographics done in {result.elapsed:.1f}s")
"""

from __future__ import annotations

from pathlib import Path

from .base import BaseExtractor

# Default max-chars value mirrors the constant in extract_demographics_llm.py
_DEFAULT_MAX_CHARS = 6000


class DemographicsExtractor(BaseExtractor):
    """
    LLM-only demographic extraction (age, sex/gender, location).

    Parameters
    ----------
    input_dir:
        Directory containing ``subreddit_posts.json`` and/or ``users/``.
    output_path:
        Output CSV path.  Defaults to ``{input_dir}/demographics.csv``.
    workers:
        Concurrent Haiku API requests (default: 10).
    include_posts:
        Process ``subreddit_posts.json`` (default: *True*).
    include_users:
        Process ``users/*.json`` histories (default: *True*).
    max_chars:
        Maximum characters of text sent per record to the LLM.
        Larger values are more thorough but cost more.  Default: 6 000.
    """

    _SCRIPT = "extract_demographics_llm.py"

    def __init__(
        self,
        input_dir: Path,
        output_path: Path | None = None,
        *,
        workers: int = 10,
        include_posts: bool = True,
        include_users: bool = True,
        max_chars: int = _DEFAULT_MAX_CHARS,
    ) -> None:
        # This extractor has no schema and writes directly to a CSV, so
        # temp_dir is unused -- we pass input_dir as both values.
        super().__init__(input_dir=input_dir, schema_path=None, temp_dir=input_dir)
        self.output_path = Path(output_path) if output_path else None
        self.workers = workers
        self.include_posts = include_posts
        self.include_users = include_users
        self.max_chars = max_chars

    def _build_args(self) -> list[str]:
        args = [
            "--input-dir", str(self.input_dir),
            "--workers",   str(self.workers),
            "--max-chars", str(self.max_chars),
        ]
        if self.output_path:
            args += ["--output", str(self.output_path)]
        if not self.include_posts and self.include_users:
            args += ["--users-only"]
        elif self.include_posts and not self.include_users:
            args += ["--posts-only"]
        return args
