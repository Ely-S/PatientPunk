#!/usr/bin/env python3
"""
run_dose_pipeline.py — Extract every dose the author states they took, one row per dose per report.

Run after run_sentiment_pipeline.py with the same --db and --drug. Reads the latest
treatment report per post for that drug, sends each report (with its parent post as
context) to the model, and writes report_doses rows under a new extraction_runs row; a rerun
replaces a report's rows. Without --exclude-compound / --exclude-file the exclusions recorded
by the sentiment run are used. Cached model replies make reruns free.

Usage:
    python src/run_sentiment_pipeline.py --db data/posts.db --output-dir outputs --drug "7,8-dhf"
    python src/run_dose_pipeline.py --db data/posts.db --drug "7,8-dhf" --exclude-compound "4'-DMA-7,8-DHF" --exclude-file names.txt
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pipeline.doses import run_dose_extraction  # noqa: E402
from pipeline.report_context import add_step_arguments, step_kwargs  # noqa: E402
from utilities import get_client, log  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract stated doses per treatment report")
    add_step_arguments(parser)
    args = parser.parse_args()
    options = step_kwargs(parser, args)  # list-file errors surface before a client is built

    summary = run_dose_extraction(get_client(), Path(args.db), args.drug, **options)
    log.info(
        f"Run {summary.run_id}: {summary.reports} reports, {summary.reports_with_rows} with doses, "
        f"{summary.rows} dose rows, {summary.failed} failed"
    )


if __name__ == "__main__":
    main()
