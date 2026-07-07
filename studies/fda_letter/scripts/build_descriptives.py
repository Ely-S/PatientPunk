# -*- coding: utf-8 -*-
"""Descriptive statistics per corpus -> corpus_stats table in fda_evidence.db.
Total posts/users, date span, per-drug user/report/mention counts + Mestinon
sentiment breakdown. Used by the FDA evidence notebook's data-inventory section.
"""
from __future__ import annotations
import os
import sqlite3, sys, datetime
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_DATA = os.environ.get("PP_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))

CORPORA = [
    ("covidlonghaulers", "long COVID",      os.path.join(_DATA, "covidlonghaulers_full.db")),
    ("dysautonomia",     "POTS/dysautonomia", os.path.join(_DATA, "dysautonomia.db")),
    ("r/cfs",            "ME/CFS (Reddit)",  os.path.join(_DATA, "rcfs_run.db")),
    ("Phoenix Rising",   "ME/CFS (forum)",   os.path.join(_DATA, "phoenix_eli_ourpipeline.db")),
]
EV = os.path.join(_DATA, "fda_evidence.db")


def ymd(ts):
    try: return datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc).strftime("%Y-%m")
    except Exception: return "?"


def drug_counts(con, name):
    row = con.execute("select id from treatment where lower(canonical_name)=?", (name,)).fetchone()
    if not row: return 0, 0, {"positive": 0, "mixed": 0, "negative": 0, "neutral": 0}
    rid = row[0]
    reps = con.execute("select count(*), count(distinct user_id) from treatment_reports where drug_id=?", (rid,)).fetchone()
    sent = {s: n for s, n in con.execute(
        "select sentiment, count(*) from treatment_reports where drug_id=? group by sentiment", (rid,))}
    for k in ("positive", "mixed", "negative", "neutral"): sent.setdefault(k, 0)
    return reps[0], reps[1], sent


# LDN mention-posts per corpus from the barriers table (already computed, ours)
evcon = sqlite3.connect(EV)
ldn_mentions = {c: n for c, n in evcon.execute(
    "select corpus, max(n_drug_posts) from barriers where drug='LDN' group by corpus")}
mest_mentions = {c: n for c, n in evcon.execute(
    "select corpus, max(n_drug_posts) from barriers where drug='Mestinon' group by corpus")}

rows = []
for corpus, pop, db in CORPORA:
    con = sqlite3.connect(db)
    total_posts = con.execute("select count(*) from posts").fetchone()[0]
    total_users = con.execute("select count(*) from users").fetchone()[0]
    mn, mx = con.execute("select min(post_date), max(post_date) from posts").fetchone()
    m_reports, m_users, m_sent = drug_counts(con, "pyridostigmine")
    l_reports, l_users, _ = drug_counts(con, "naltrexone")
    con.close()
    rows.append((corpus, pop, total_posts, total_users, ymd(mn), ymd(mx),
                 m_users, m_reports, m_sent["positive"], m_sent["mixed"], m_sent["negative"], m_sent["neutral"],
                 mest_mentions.get(corpus, 0), ldn_mentions.get(corpus, 0), l_users, l_reports))
    print(f"{corpus:<16} posts={total_posts:>9,} users={total_users:>7,} {ymd(mn)}..{ymd(mx)} "
          f"| Mest users={m_users:<5} reports={m_reports:<5} | LDN mentions={ldn_mentions.get(corpus,0):<6} users={l_users}")

evcon.execute("drop table if exists corpus_stats")
evcon.execute("""create table corpus_stats (corpus text, population text, total_posts int, total_users int,
    date_min text, date_max text, mest_users int, mest_reports int,
    mest_pos int, mest_mixed int, mest_neg int, mest_neutral int,
    mest_mentions int, ldn_mentions int, ldn_users int, ldn_reports int)""")
evcon.executemany("insert into corpus_stats values (" + ",".join("?" * 16) + ")", rows)
evcon.commit(); evcon.close()
print(f"\nwrote corpus_stats to {EV}")
