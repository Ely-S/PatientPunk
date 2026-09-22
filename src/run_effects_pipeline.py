#!/usr/bin/env python3
"""
run_effects_pipeline.py — Extract every effect the author says the drug had, one row per effect per report.

Run after run_sentiment_pipeline.py and run_dose_pipeline.py with the same --db and --drug.
Reads the latest treatment report per post for that drug, sends each report (with its parent
post and its dose rows as context) to the model, and writes report_effects rows under a new
extraction_runs row; a rerun replaces a report's rows.
Without --exclude-compound / --exclude-file the exclusions recorded by the sentiment run are used.

Usage:
    python src/run_sentiment_pipeline.py --db data/posts.db --output-dir outputs --drug "7,8-dhf"
    python src/run_dose_pipeline.py     --db data/posts.db --drug "7,8-dhf" --exclude-compound "4'-DMA-7,8-DHF"
    python src/run_effects_pipeline.py  --db data/posts.db --drug "7,8-dhf" --exclude-compound "4'-DMA-7,8-DHF"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pipeline.effects import run_effects_extraction  # noqa: E402
from pipeline.report_context import add_step_arguments, read_list_file, step_kwargs  # noqa: E402
from prompts.effects_config import DOMAINS  # noqa: E402
from utilities import get_client, log  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract stated effects per treatment report")
    add_step_arguments(parser)
    parser.add_argument("--domains-file", type=str, default=None,
                        help="Text file of effect domains, one per line (default: the built-in list)")
    args = parser.parse_args()
    options = step_kwargs(parser, args)  # list-file errors surface before a client is built
    domains = read_list_file(parser, args, "domains_file") or DOMAINS

    summary = run_effects_extraction(get_client(), Path(args.db), args.drug, domains=domains, **options)
    log.info(
        f"Run {summary.run_id}: {summary.reports} reports, {summary.reports_with_rows} with effects, "
        f"{summary.rows} effect rows, {summary.failed} failed, "
        f"{summary.quote_drops} quotes not in report, {summary.dose_link_drops} dose links dropped"
    )


if __name__ == "__main__":
    main()
