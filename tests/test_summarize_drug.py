"""summarize_drug counts authors once across databases and reads only the latest views."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from summarize_drug import load, merge, summarize

SCHEMA = (Path(__file__).parent.parent / "schema.sql").read_text(encoding="utf-8")


def _db(path: Path, rows: list[tuple], day0: int = 0) -> Path:
    """rows: (user, post, sentiment, [(direction, attribution, symptom)], [(low, unit, route)])."""
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO treatment (id, canonical_name) VALUES (1, 'drug x')")
    for run, kind in ((1, "treatment_sentiment"), (2, "report_doses"), (3, "report_effects")):
        conn.execute("INSERT INTO extraction_runs (run_id, run_at, commit_hash, extraction_type, config) VALUES (?, 0, 'x', ?, '{}')", (run, kind))
    for n, (user, post, sentiment, effects, doses) in enumerate(rows, 1):
        conn.execute("INSERT OR IGNORE INTO users (user_id, source_subreddit, scraped_at) VALUES (?, 's', 0)", (user,))
        conn.execute("INSERT INTO posts (post_id, user_id, body_text, post_date, scraped_at) VALUES (?, ?, 'text', ?, 0)", (post, user, day0 + n))
        conn.execute("INSERT INTO treatment_reports (report_id, run_id, post_id, user_id, drug_id, sentiment, signal_strength) VALUES (?, 1, ?, ?, 1, ?, 'strong')", (n, post, user, sentiment))
        for run in (2, 3):
            conn.execute("INSERT INTO report_runs (run_id, report_id) VALUES (?, ?)", (run, n))
        for i, effect in enumerate(effects):
            direction, attribution, symptom, *severity = effect
            conn.execute("INSERT INTO report_effects (report_id, run_id, ordinal, domain, symptom, direction, attribution, severity, quote) VALUES (?, 3, ?, 'overall', ?, ?, ?, ?, 'q')", (n, i, symptom, direction, attribution, severity[0] if severity else None))
        for i, (low, unit, route) in enumerate(doses):
            conn.execute("INSERT INTO report_doses (report_id, run_id, ordinal, low, high, unit, route, quote) VALUES (?, 2, ?, ?, ?, ?, ?, 'q')", (n, i, low, low, unit, route))
    conn.commit()
    conn.close()
    return path


def test_counts_and_cross_database_dedup(tmp_path: Path) -> None:
    a = _db(tmp_path / "a.db", [
        ("u1", "p1", "positive", [("improved", "target", "energy"), ("worsened", "target", "insomnia", "severe")], [(500, "mg", None)]),
        ("u2", "p2", "negative", [("no_change", "target", "nothing")], []),
        ("u3", "p3", "neutral", [("worsened", "target", "nausea", "severe")], [(1, "g", "swallowed oral")]),  # not eligible
    ])
    b = _db(tmp_path / "b.db", day0=10, rows=[
        ("u1", "p9", "negative", [("worsened", "stack", "headache")], []),  # same person, stack row ignored
        ("u4", "p4", "positive", [("improved", "target", "walking")], [(1000, "mg", None)]),
    ])
    cols = [("A", load(a, "drug x", "A")), ("B", load(b, "drug x", "B"))]
    merged = merge([c for _, c in cols])
    assert set(merged) == {"u1", "u2", "u4"} and merged["u1"]["reports"] == 2
    text = summarize("drug x", [("All", merged)] + cols)
    assert "| Authors | 3 | 2 | 2 |" in text
    assert "| Side-effect data points | 1 | 1 | 0 |" in text
    assert "| Dosage data points | 2 | 1 | 1 |" in text
    assert "| Positive, latest report | 1 (33%) | 1 (50%) | 1 (50%) |" in text  # u1's latest is the negative one
    assert "| 500 mg | 1 | 1 | 1 | 0 |" in text and "| 1000 mg | 1 | 0 | 1 | 1 |" in text
    # u1's insomnia is graded severe in database A; u3's severe nausea is on an ineligible report
    assert "| Called a side effect severe | 1 (33%) | 1 (50%) | 0 (0%) |" in text
    assert "| Stated any severity | 1 (33%) | 1 (50%) | 0 (0%) |" in text
