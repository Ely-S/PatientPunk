#!/usr/bin/env python3
"""
run_dose_pipeline.py — Extract every dose the author states they took, one row per dose per report.

Run after run_sentiment_pipeline.py with the same --db and --drug. Reads the latest
treatment report per post for that drug, sends each report (with its parent post and the
thread title as context) to the model, and appends report_doses rows under a new
extraction_runs row; report_doses_latest shows each report's most recent run. Without
--exclude-compound / --exclude-file the exclusions recorded by the sentiment run are used.

Usage:
    python src/run_sentiment_pipeline.py --db data/posts.db --output-dir outputs --drug "7,8-dhf"
    python src/run_dose_pipeline.py --db data/posts.db --drug "7,8-dhf" --exclude-compound "4'-DMA-7,8-DHF"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pipeline.doses import run_dose_extraction  # noqa: E402
from pipeline.report_context import DEFAULT_PARENT_CHARS, DEFAULT_THREAD_CHARS, read_list_file  # noqa: E402
from utilities import MODEL_STRONG, get_client, log  # noqa: E402


def _lines(parser: argparse.ArgumentParser, path: str, flag: str) -> list[str]:
    lines = read_list_file(path)
    if not lines:
        parser.error(f"{flag} {path} contains no non-blank lines")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract stated doses per treatment report")
    parser.add_argument("--db", required=True, help="SQLite database with treatment_reports for the drug")
    parser.add_argument("--drug", required=True, help="Canonical treatment name as stored in the treatment table")
    parser.add_argument("--drug-file", type=str, default=None,
                        help="Text file of spellings for the drug, one per line (default: aliases from the treatment table)")
    parser.add_argument("--exclude-compound", action="append", default=[],
                        help="Name of a different compound whose doses must not be attributed to the drug (repeatable)")
    parser.add_argument("--exclude-file", type=str, default=None,
                        help="Text file of such compound names, one per line (added to --exclude-compound). "
                             "With neither flag, the exclusions recorded by the sentiment run are used")
    parser.add_argument("--model", type=str, default=MODEL_STRONG, help=f"Model for the extraction (default: {MODEL_STRONG})")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--parent-chars", type=int, default=DEFAULT_PARENT_CHARS,
                        help="Characters of the parent post sent as context; 0 sends none")
    parser.add_argument("--thread-chars", type=int, default=DEFAULT_THREAD_CHARS,
                        help="Characters of the thread's root title sent as context; 0 sends none")
    parser.add_argument("--solo-above-chars", type=int, default=3000,
                        help="Reports longer than this go one per call; 0 disables")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N reports (0 = all)")
    args = parser.parse_args()

    aliases = _lines(parser, args.drug_file, "--drug-file") if args.drug_file else None
    excluded = list(args.exclude_compound) + (_lines(parser, args.exclude_file, "--exclude-file") if args.exclude_file else [])

    summary = run_dose_extraction(
        get_client(),
        Path(args.db),
        args.drug,
        aliases=aliases,
        excluded_compounds=excluded or None,
        model=args.model,
        workers=args.workers,
        batch_size=args.batch_size,
        parent_chars=args.parent_chars or None,
        thread_chars=args.thread_chars or None,
        solo_above_chars=args.solo_above_chars or None,
        limit=args.limit or None,
    )
    log.info(
        f"Run {summary.run_id}: {summary.reports} reports, {summary.reports_with_doses} with doses, "
        f"{summary.dose_rows} dose rows, {summary.failed_reports} failed"
    )


if __name__ == "__main__":
    main()
