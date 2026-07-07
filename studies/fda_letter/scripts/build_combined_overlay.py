# -*- coding: utf-8 -*-
"""One combined graph: the side-effect profile (bars, bottom axis) with the
Du & Nguyen symptom relative-risk MARKED on each symptom row (green diamond,
top axis). Benefit and side-effect for each symptom in a single chart."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np, os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "figures")
os.makedirs(OUT, exist_ok=True)

# (symptom, clinical SE %, reddit SE %, RR, RR lo, RR hi)  RR=None where Du&Nguyen has no datum
rows = [("Headache",         10.0, 3.7, 0.75, 0.61, 0.91),
        ("Sleep disturbance", 9.0, 9.3, 0.62, 0.49, 0.78),
        ("Light-headedness",  8.5, 2.5, None, None, None),
        ("GI disturbance",    5.0, 4.4, None, None, None),
        ("Brain fog",         5.0, 2.2, 0.68, 0.56, 0.82),
        ("Fatigue",           2.5, 5.0, 0.61, 0.51, 0.72)]
MATCH = {"Sleep disturbance", "GI disturbance"}
DARK, ORANGE, GREEN = "#2c3e50", "#e67e22", "#1e8449"
y = np.arange(len(rows))[::-1]
h = 0.30

fig, ax = plt.subplots(figsize=(11.5, 6.4))
# ── side-effect bars (bottom axis, %) ──
ax.barh(y + h/2, [r[1] for r in rows], h, color=DARK, label="Side effect, clinical (Du & Nguyen, %)")
ax.barh(y - h/2, [r[2] for r in rows], h, color=ORANGE, label="Side effect, Reddit (this analysis, %)")
for yi, r in zip(y, rows):
    ax.text(r[1] + 0.12, yi + h/2, f"{r[1]:.1f}%", va="center", fontsize=8, color=DARK)
    ax.text(r[2] + 0.12, yi - h/2, f"{r[2]:.1f}%", va="center", fontsize=8, color="#b9620a")
ax.set_xlim(0, 13)
ax.set_xlabel("Patients reporting it as a SIDE EFFECT (%)  —  shorter = better", fontsize=10)
ax.set_yticks(y); ax.set_yticklabels([r[0] for r in rows], fontsize=11)
for tick, r in zip(ax.get_yticklabels(), rows):
    if r[0] in MATCH:
        tick.set_color(GREEN); tick.set_fontweight("bold")
ax.tick_params(left=False); ax.spines[["top", "right"]].set_visible(False)

# ── efficacy relative-risk marked on each row (top axis) ──
axt = ax.twiny()
axt.set_xlim(1.18, 0.42)   # reversed: lower RR (more improvement) sits to the RIGHT
for yi, r in zip(y, rows):
    rr, lo, hi = r[3], r[4], r[5]
    if rr is None:
        axt.text(0.62, yi, "no efficacy datum", va="center", ha="center", fontsize=7.5,
                 color="#aab2bd", style="italic")
        continue
    axt.scatter(rr, yi, marker="D", s=120, color=GREEN, edgecolor="white", lw=1.5, zorder=5)
    axt.text(rr, yi + 0.30, f"RR {rr:.2f}", ha="center", fontsize=8.5, color=GREEN, fontweight="bold", zorder=6)
axt.axvline(1.0, color=GREEN, ls=":", lw=1.0, alpha=0.4)
axt.text(1.0, len(rows) - 0.55, "RR 1.0\nno effect", ha="center", va="top", fontsize=7.3, color=GREEN, alpha=0.8)
axt.set_xlabel("◆  LDN efficacy: relative risk of persistent symptom (Du & Nguyen)  —  further right = more improvement",
               color=GREEN, fontsize=10)
axt.tick_params(axis="x", colors=GREEN)
for s in ("top",): axt.spines[s].set_color(GREEN)

ax.set_title("Low-dose naltrexone, per symptom: how often it's a side effect (bars) vs how much it improves (◆)",
             fontsize=12.5, fontweight="bold", pad=30)
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.11), ncol=2, frameon=False, fontsize=9)
fig.text(0.012, 0.015,
         "Two readings per symptom — bars = % reporting it as a SIDE EFFECT (bottom axis, shorter is better); green ◆ = relative risk of that symptom persisting on LDN\n"
         "(top axis, further right = more improvement; CIs exclude 1.0). Not contradictory: e.g. headache improves for most (RR 0.75) yet is a minor side effect for a few.\n"
         "Bold green labels (sleep, GI) = side-effect rates that match the trials almost exactly. Efficacy: Du & Nguyen 2025 — O'Kelly 2022 (1–2 mg/day) + Bonilla 2023\n"
         "(0.5–6 mg/day), observational. Side-effect denominators: pooled trial patients (clinical) vs our 321 LDN patients (Reddit).",
         fontsize=7.3, color="#7f8c8d", style="italic", linespacing=1.5)
fig.subplots_adjust(left=0.12, right=0.97, top=0.85, bottom=0.30)
fig.savefig(os.path.join(OUT, "letter_fig_combined_overlay.png"), dpi=200, bbox_inches="tight")
fig.savefig(os.path.join(OUT, "letter_fig_combined_overlay.svg"), bbox_inches="tight")
print("saved letter_fig_combined_overlay")
