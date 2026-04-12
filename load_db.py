#!/usr/bin/env python3
"""Load both pipeline outputs into a unified SQLite database.

Combines Shaun's demographic/clinical extraction (records.csv) with
Polina's drug sentiment analysis (sentiment_cache.json) into a single
queryable database joined on author_hash.

Usage:
    python load_db.py
    python load_db.py --db my_output.db

Then query via Marimo:
    marimo run PatientPunk_v2/apps/query.py
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "variable_extraction"))

try:
    from patientpunk.db import (
        init_db,
        load_corpus,
        load_extractions,
        load_sentiment,
        query_treatment_outcomes,
        list_drugs,
        list_conditions,
    )
except ImportError:
    sys.exit(
        "ERROR: variable_extraction/patientpunk/ package not found.\n"
        "This loader requires the variable_extraction package.\n"
        "See: https://github.com/Ely-S/PatientPunk/tree/shaun/presentation/variable_extraction"
    )

HERE = Path(__file__).parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", type=Path, default=HERE / "patientpunk.db",
        help="Output database path (default: patientpunk.db)",
    )
    args = parser.parse_args()

    schema_sql = HERE / "schema.sql"
    data_dir = HERE / "data"
    drug_dir = data_dir / "drug_pipeline"

    # Validate inputs exist
    for path, label in [
        (schema_sql, "schema.sql"),
        (data_dir / "subreddit_posts.json", "subreddit_posts.json"),
        (data_dir / "records.csv", "records.csv (run Shaun's pipeline first)"),
        (drug_dir / "sentiment_cache.json", "sentiment_cache.json (run Polina's pipeline first)"),
        (drug_dir / "canonical_map.json", "canonical_map.json (run Polina's pipeline first)"),
    ]:
        if not path.exists():
            sys.exit(f"Missing: {path}\n  ({label})")

    # Initialize database
    print(f"Database: {args.db}")
    conn = init_db(args.db, schema_sql=schema_sql)

    # Load corpus (posts -> users + posts tables)
    n_posts = load_corpus(conn, data_dir)
    print(f"  Corpus:     {n_posts} posts loaded")

    # Load demographics first (clean, focused LLM pass for age/sex/location).
    # This goes first because records.csv age values are noisy multi-value
    # extractions from full user histories (mentions of OTHER people's ages).
    demographics_csv = data_dir / "demographics_deductive.csv"
    if demographics_csv.exists():
        run_id = load_extractions(conn, demographics_csv)
        print(f"  Demographics: loaded from demographics_deductive.csv (run_id={run_id})")
    else:
        run_id = None

    # Load conditions from records.csv (the main pipeline output).
    # INSERT OR REPLACE will only overwrite demographics if records.csv
    # has a value -- but records.csv age/sex are empty (noisy multi-values
    # were already cleaned out by our prompt improvements).
    run_id = load_extractions(conn, data_dir / "records.csv", run_id=run_id)
    print(f"  Conditions:  loaded from records.csv")

    # Load Polina's sentiment output
    load_sentiment(
        conn,
        drug_dir / "sentiment_cache.json",
        drug_dir / "canonical_map.json",
        run_id,
    )
    drugs = list_drugs(conn)
    conditions = list_conditions(conn)
    print(f"  Sentiment:  {len(drugs)} drugs, {len(conditions)} conditions")

    # Quick sanity check
    results = query_treatment_outcomes(conn)
    print(f"\n  Total treatment reports: {sum(r['n_reports'] for r in results)}")
    print(f"  Unique drugs with reports: {len(results)}")

    if results:
        print(f"\n  Top drugs by report count:")
        for r in results[:5]:
            print(f"    {r['drug']:<25} {r['n_reports']:>3} reports  "
                  f"(+{r['pct_positive']:.0f}% / -{r['pct_negative']:.0f}%)")

    conn.close()
    print(f"\nDone. Query with: marimo run PatientPunk_v2/apps/query.py")


if __name__ == "__main__":
    main()
