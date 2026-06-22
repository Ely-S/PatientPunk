# -*- coding: utf-8 -*-
"""Descriptive-statistics table (Table 1) for the two patient-forum LDN corpora.
Numbers verified by descstats.py against ldn_2yr.db and phoenixrising.db."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import os

OUT = r"C:\Users\scgee\OneDrive\Documents\Projects\PatientPunk\FDA_analysis\figures"
os.makedirs(OUT, exist_ok=True)

# (kind, label, reddit, phoenix)   kind: 'sec' header band, 'row' data
ROWS = [
    ("sec", "Source", "", ""),
    ("row", "Platform", "Public subreddit", "Web forum (est. 2008)"),
    ("row", "Observation window", "Oct 2020 – Dec 2022", "Jul 2009 – Jun 2026"),
    ("sec", "Corpus", "", ""),
    ("row", "Posts analysed", "1,316 LDN reports", "6,657 posts (2,538 mention LDN)"),
    ("row", "Distinct LDN authors", "321", "539"),
    ("row", "Posts per author — mean (median)", "4.1  (2)", "4.7"),
    ("sec", "Self-reported dosing", "", ""),
    ("row", "Authors stating a dose", "79  (25%)", "182  (34%)"),
    ("row", "Median stated dose (mg)", "1.5", "1.5"),
    ("row", "Using ≤ 4.5 mg", "76  (96%)", "170  (93%)"),
]

DARK, BLUE, GREY = "#1c2833", "#1f618d", "#566573"
xL, xR1, xR2 = 0.015, 0.595, 0.835     # label, reddit col center, phoenix col center
n = len(ROWS) + 1                       # +1 header
row_h = 1.0 / (n + 1.2)
fig, ax = plt.subplots(figsize=(11.2, 0.46 * n + 1.4))
ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

def y_of(i): return 1.0 - (i + 1.1) * row_h

# title
ax.text(0.0, 1.0, "Descriptive statistics of the two patient-forum corpora",
        fontsize=14, fontweight="bold", color=DARK, va="top")

# column headers
yh = y_of(0)
ax.text(xL, yh, "", fontsize=11)
ax.text(xR1, yh, "r/covidlonghaulers", ha="center", fontsize=11.5, fontweight="bold", color=BLUE)
ax.text(xR2, yh, "Phoenix Rising", ha="center", fontsize=11.5, fontweight="bold", color=BLUE)
ax.plot([0, 1], [yh - 0.45*row_h, yh - 0.45*row_h], color=DARK, lw=1.6)

for i, (kind, label, rd, ph) in enumerate(ROWS, start=1):
    y = y_of(i)
    if kind == "sec":
        ax.add_patch(Rectangle((0, y - 0.5*row_h), 1, row_h, color="#eaeef2", zorder=0))
        ax.text(xL, y, label, fontsize=10.5, fontweight="bold", color=DARK, va="center")
    else:
        ax.text(xL, y, label, fontsize=10, color=DARK, va="center")
        ax.text(xR1, y, rd, ha="center", fontsize=10, color="#212f3c", va="center")
        ax.text(xR2, y, ph, ha="center", fontsize=10, color="#212f3c", va="center")

# bottom rule
yb = y_of(len(ROWS)) - 0.6*row_h
ax.plot([0, 1], [yb, yb], color=DARK, lw=1.6)
ax.text(0.0, yb - 0.5*row_h,
        "Doses are self-reported; '≤4.5 mg' = author's lowest stated dose ≤4.5 mg. Phoenix Rising corpus is the LDN-related scrape (posts in threads mentioning LDN).\n"
        "Sources: ldn_2yr.db (r/covidlonghaulers, vetted 2020–2022 window) and phoenixrising.db (Phoenix Rising; github.com/Ely-S/PatientPunk).",
        fontsize=7.4, color=GREY, va="top", style="italic")

plt.subplots_adjust(left=0.015, right=0.985, top=0.93, bottom=0.02)
fig.savefig(os.path.join(OUT, "paper_descriptive_stats.png"), dpi=200, bbox_inches="tight")
fig.savefig(os.path.join(OUT, "paper_descriptive_stats.svg"), bbox_inches="tight")
print("saved paper_descriptive_stats")
