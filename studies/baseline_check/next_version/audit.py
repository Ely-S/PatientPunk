"""Audit the v0.2 questionnaire coverage ratings and informal percent-self repeats."""

import argparse
from collections import defaultdict
from contextlib import closing
import json
from pathlib import Path
import random
import sqlite3
import statistics


STUDY = Path(__file__).resolve().parents[1]
V02 = STUDY / "v02_analysis"
V03 = STUDY / "v03_rechecks" / "c_coverage"


def read_jsonl(path):
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                yield json.loads(line)


def read_ratings(*paths):
    ratings = {}
    for path in paths:
        for row in read_jsonl(path):
            if row["id"] in ratings:
                raise ValueError(f"Duplicate post in {path.name}")
            ratings[row["id"]] = row
    return ratings


def summarize_coverage(database):
    designer = read_ratings(V02 / "coverage" / "coded.jsonl")
    blind = read_ratings(V03 / "blind_0.jsonl", V03 / "blind_1.jsonl")
    if blind.keys() != {post for post, row in designer.items() if row["describes_change"]}:
        raise ValueError("Blind ratings must cover all posts screened in by the designer")
    with (V02 / "sample_change.json").open(encoding="utf-8") as source:
        discovery_posts = {row["id"] for row in json.load(source)}

    requested = sorted(designer.keys() | discovery_posts)
    placeholders = ", ".join("?" for _ in requested)
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        authors = dict(db.execute(f"SELECT id, author FROM posts WHERE id IN ({placeholders})", requested))
    if set(authors) != set(requested) or any(a in (None, "", "[deleted]", "[removed]") for a in authors.values()):
        raise ValueError("Expected an identifiable corpus author for every sampled post")

    coverage_authors = {authors[post] for post in designer}
    discovery_authors = {authors[post] for post in discovery_posts}
    print(f"Title-screened discovery sample: {len(discovery_posts)} posts, {len(discovery_authors)} authors")
    print(f"Coverage sample: {len(designer)} posts, {len(coverage_authors)} authors")
    print(f"Shared with title-screened discovery sample: {len(designer.keys() & discovery_posts)} posts, "
          f"{len(coverage_authors & discovery_authors)} authors")

    eligible = sorted(post for post, row in blind.items() if row["describes_change"])
    questions = {
        post: {tag.split(":", 1)[0] for tag in blind[post]["captured_by"] or []}
        for post in eligible
    }
    print(f"Eligible for paired analysis: {len(eligible)}/{len(blind)} designer-screened posts")
    print("stratum | screened in by designer | eligible | blind fully | partly | not | "
          "designer fully | Q1 or Q2 tagged | Q3 tagged without Q1/Q2 | Q4/Q5 tagged without Q1–Q3")
    author_rows = defaultdict(list)
    for stratum in ("all", "severe", "mild_moderate"):
        screened = {post for post in blind if stratum == "all" or designer[post]["stratum"] == stratum}
        kept = [post for post in eligible if post in screened]
        totals = [0] * 7
        for post in kept:
            tags = questions[post]
            rating = blind[post]["captured"]
            blind_fully = rating == "fully"
            designer_fully = designer[post]["captured"] == "fully"
            has_primary_tag = bool(tags & {"Q1", "Q2"})
            adds_q3 = "Q3" in tags and not has_primary_tag
            values = (
                blind_fully, rating == "partly", rating == "not", designer_fully, has_primary_tag, adds_q3,
                bool(tags & {"Q4", "Q5"}) and not tags & {"Q1", "Q2", "Q3"},
            )
            totals = [total + value for total, value in zip(totals, values)]
            if stratum == "all":
                author_rows[authors[post]].append((1, blind_fully, designer_fully, designer_fully - blind_fully,
                                                   has_primary_tag, adds_q3))
        print(" | ".join(map(str, (stratum, len(screened), len(kept), *totals))))

    clusters = [tuple(map(sum, zip(*rows))) for rows in author_rows.values()]
    print(f"\nPaired author-cluster bootstrap ({len(clusters)} authors, 10,000 draws, seed 42)")
    labels = ("Blind fully", "Designer fully", "Designer minus blind fully (pp)",
              "Q1 or Q2 tagged", "Q3 tagged without Q1/Q2")
    resample_intervals(clusters, labels)


def resample_intervals(clusters, labels):
    randomizer = random.Random(42)
    draws = [[] for _ in labels]
    for _ in range(10_000):
        sample = randomizer.choices(clusters, k=len(clusters))
        denominator, *numerators = map(sum, zip(*sample))
        for stat, numerator in zip(draws, numerators):
            stat.append(100 * numerator / denominator)

    denominator, *numerators = map(sum, zip(*clusters))
    for label, numerator, stat in zip(labels, numerators, draws):
        cuts = statistics.quantiles(stat, n=40, method="inclusive")
        print(f"{label}: {100 * numerator / denominator:.1f} [{cuts[0]:.1f}, {cuts[-1]:.1f}]")


def summarize_percent_self():
    same_text = defaultdict(list)
    for row in read_jsonl(V02 / "level.jsonl"):
        same_text[row["a"], row["id"], row["ts"]].append(row["v"])
    by_author = defaultdict(list)
    for (author, post, timestamp), ratings in same_text.items():
        by_author[author].append((timestamp, post, statistics.median(ratings)))

    short_pairs = []
    author_summaries = []
    for ratings in by_author.values():
        ratings.sort()
        differences = [abs(right[2] - left[2]) for left, right in zip(ratings, ratings[1:])
                       if 0.5 * 86_400 <= right[0] - left[0] <= 14 * 86_400]
        if differences:
            short_pairs.extend(differences)
            author_summaries.append((differences.count(0) / len(differences),
                                     sum(d >= 20 for d in differences) / len(differences)))

    print(f"\nPercent-self repeats within 0.5–14 days: {len(short_pairs)} pairs, {len(author_summaries)} authors")
    print(f"Pair-weighted: identical {short_pairs.count(0) / len(short_pairs):.1%}; "
          f"difference >=20 points {sum(d >= 20 for d in short_pairs) / len(short_pairs):.1%}")
    identical, large = map(statistics.mean, zip(*author_summaries))
    print(f"Equal author weight: identical {identical:.1%}; difference >=20 points {large:.1%}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path, help="Path to the study's read-only Reddit SQLite corpus")
    args = parser.parse_args()
    summarize_coverage(args.corpus)
    summarize_percent_self()


if __name__ == "__main__":
    main()
