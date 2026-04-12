#!/usr/bin/env python3
"""
Generate a database profile JSON for use in notebook generation prompts.

Usage:
    python notebooks/profile_db.py polina_onemonth.db
    python notebooks/profile_db.py pssd.db
    python notebooks/profile_db.py abortion.db

Output:
    notebooks/profiles/{db_name}.json
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def profile_database(db_path: Path) -> dict:
    conn = sqlite3.connect(str(db_path))

    # Basic counts
    users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]

    try:
        reports = conn.execute("SELECT COUNT(*) FROM treatment_reports").fetchone()[0]
        unique_reporters = conn.execute("SELECT COUNT(DISTINCT user_id) FROM treatment_reports").fetchone()[0]
        unique_drugs = conn.execute("SELECT COUNT(DISTINCT drug_id) FROM treatment_reports").fetchone()[0]
    except Exception:
        reports = 0
        unique_reporters = 0
        unique_drugs = 0

    # Date range (handles both Unix timestamps and ISO strings)
    from datetime import datetime, timezone
    try:
        date_row = conn.execute(
            "SELECT MIN(post_date), MAX(post_date) FROM posts WHERE post_date IS NOT NULL"
        ).fetchone()
        def parse_date(val):
            if val is None:
                return None
            if isinstance(val, (int, float)) or (isinstance(val, str) and val.isdigit()):
                return datetime.fromtimestamp(int(val) if isinstance(val, str) else val, tz=timezone.utc).strftime("%Y-%m-%d")
            return str(val)[:10]
        date_min = parse_date(date_row[0])
        date_max = parse_date(date_row[1])
    except Exception:
        date_min = date_max = None

    # Sentiment distribution
    sentiment_dist = {}
    try:
        for row in conn.execute(
            "SELECT sentiment, COUNT(*) FROM treatment_reports GROUP BY sentiment ORDER BY COUNT(*) DESC"
        ).fetchall():
            sentiment_dist[row[0]] = row[1]
    except Exception:
        pass

    # Top treatments (by unique users)
    top_treatments = []
    try:
        for row in conn.execute("""
            SELECT t.canonical_name, COUNT(DISTINCT tr.user_id) as n,
                   SUM(CASE tr.sentiment WHEN 'positive' THEN 1 ELSE 0 END) as pos,
                   SUM(CASE tr.sentiment WHEN 'negative' THEN 1 ELSE 0 END) as neg
            FROM treatment_reports tr
            JOIN treatment t ON t.id = tr.drug_id
            GROUP BY t.canonical_name
            HAVING n >= 5
            ORDER BY n DESC
            LIMIT 30
        """).fetchall():
            top_treatments.append({
                "name": row[0], "users": row[1], "pos": row[2], "neg": row[3],
                "pct_pos": round(row[2] / (row[2] + row[3]) * 100) if (row[2] + row[3]) > 0 else 0,
            })
    except Exception:
        pass

    # Conditions
    conditions = []
    try:
        for row in conn.execute("""
            SELECT condition_name, COUNT(DISTINCT user_id) as n
            FROM conditions
            GROUP BY condition_name
            ORDER BY n DESC
            LIMIT 20
        """).fetchall():
            conditions.append({"name": row[0], "users": row[1]})
    except Exception:
        pass

    # Subreddit
    try:
        subreddit = conn.execute(
            "SELECT source_subreddit FROM users WHERE source_subreddit IS NOT NULL LIMIT 1"
        ).fetchone()
        subreddit = subreddit[0] if subreddit else None
    except Exception:
        subreddit = None

    # Text-based theme counts (search body_text)
    themes = {}
    theme_keywords = {
        "fatigue": "fatigue",
        "pain": "pain",
        "brain_fog": "brain fog",
        "anxiety": "anxiety",
        "depression": "depression",
        "sleep": "sleep",
        "nausea": "nausea",
        "bleeding": "bleeding",
        "scared": "scared",
        "alone": "alone",
        "support": "support",
        "relief": "relief",
        "regret": "regret",
        "guilt": "guilt",
        "doctor": "doctor",
        "dismissed": "dismiss",
        "recovery": "recover",
        "improved": "improv",
    }
    for key, term in theme_keywords.items():
        try:
            n = conn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM posts WHERE body_text LIKE ?",
                (f"%{term}%",)
            ).fetchone()[0]
            if n >= 5:
                themes[key] = n
        except Exception:
            pass

    # Identify likely generic terms in the data
    generics_found = []
    generic_candidates = [
        "supplements", "medication", "treatment", "therapy", "drug",
        "vitamin", "antidepressant", "antihistamines", "antibiotics",
    ]
    try:
        for g in generic_candidates:
            row = conn.execute("""
                SELECT COUNT(DISTINCT tr.user_id)
                FROM treatment_reports tr
                JOIN treatment t ON t.id = tr.drug_id
                WHERE t.canonical_name = ? COLLATE NOCASE
            """, (g,)).fetchone()
            if row and row[0] >= 5:
                generics_found.append({"name": g, "users": row[0]})
    except Exception:
        pass

    # Identify likely causal-context candidates
    causal_candidates = []
    causal_keywords = {
        "vaccine": ["vaccine", "pfizer", "moderna", "johnson", "booster", "novavax"],
        "ssri": ["ssri", "sertraline", "fluoxetine", "paroxetine", "escitalopram",
                 "citalopram", "lexapro", "prozac", "zoloft", "paxil", "vortioxetine",
                 "duloxetine", "fluvoxamine", "snri"],
        "birth_control": ["birth control", "contracepti", "plan b", "iud"],
    }
    for category, terms in causal_keywords.items():
        for term in terms:
            try:
                row = conn.execute("""
                    SELECT t.canonical_name, COUNT(DISTINCT tr.user_id) as n,
                           SUM(CASE tr.sentiment WHEN 'negative' THEN 1 ELSE 0 END) as neg
                    FROM treatment_reports tr
                    JOIN treatment t ON t.id = tr.drug_id
                    WHERE t.canonical_name LIKE ? COLLATE NOCASE
                    GROUP BY t.canonical_name
                    HAVING n >= 3
                """, (f"%{term}%",)).fetchall()
                for r in row:
                    neg_rate = r[2] / r[1] if r[1] > 0 else 0
                    if neg_rate > 0.6:
                        causal_candidates.append({
                            "name": r[0], "category": category,
                            "users": r[1], "neg_rate": round(neg_rate, 2),
                        })
            except Exception:
                pass

    conn.close()

    return {
        "db_file": db_path.name,
        "subreddit": subreddit,
        "users": users,
        "posts": posts,
        "treatment_reports": reports,
        "unique_reporters": unique_reporters,
        "unique_drugs": unique_drugs,
        "date_range": [date_min, date_max],
        "sentiment_distribution": sentiment_dist,
        "top_treatments": top_treatments,
        "conditions": conditions,
        "text_themes": themes,
        "generics_found": generics_found,
        "causal_context_candidates": causal_candidates,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("db", type=Path, help="Path to SQLite database")
    args = parser.parse_args()

    if not args.db.exists():
        sys.exit(f"Database not found: {args.db}")

    profile = profile_database(args.db)

    out_dir = Path(__file__).parent / "profiles"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{args.db.stem}.json"
    out_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    print(f"Profile written to {out_path}")
    print(f"  {profile['users']} users, {profile['posts']} posts, {profile['treatment_reports']} reports")
    print(f"  Date range: {profile['date_range'][0]} to {profile['date_range'][1]}")
    print(f"  Top treatment: {profile['top_treatments'][0]['name']} (n={profile['top_treatments'][0]['users']})" if profile['top_treatments'] else "  No treatments")


if __name__ == "__main__":
    main()
