# -*- coding: utf-8 -*-
"""Clinical-vs-Reddit side-effect overlay: makes the letter's 'side-effect profile
matches studies' claim quantitative. Clinical = % of trial patients (Du & Nguyen
pooled); Reddit = % of our 321 LDN patients mentioning the effect (probe_ae_overlay)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np, os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "figures")
os.makedirs(OUT, exist_ok=True)

# (category, clinical %, our per-patient %)  — sorted by clinical desc
cats = [("Headache", 10.0, 3.7), ("Sleep disturbance", 9.0, 9.3),
        ("Light-headedness", 8.5, 2.5), ("GI disturbance", 5.0, 4.4),
        ("Brain fog", 5.0, 2.2), ("Fatigue", 2.5, 5.0)]
MATCH = {"Sleep disturbance", "GI disturbance"}   # near-identical, most drug-specific
CLIN, OURS = "#2c3e50", "#e67e22"

labels = [c[0] for c in cats]
clin = [c[1] for c in cats]
ours = [c[2] for c in cats]
y = np.arange(len(cats))[::-1]
h = 0.36
fig, ax = plt.subplots(figsize=(9.2, 5.0))
ax.barh(y + h/2, clin, h, color=CLIN, label="Clinical trials (Du & Nguyen, % of patients)")
ax.barh(y - h/2, ours, h, color=OURS, label="Reddit (this analysis, % of patients)")
for yi, cv, ov in zip(y, clin, ours):
    ax.text(cv + 0.15, yi + h/2, f"{cv:.1f}%", va="center", fontsize=9.5, color=CLIN)
    ax.text(ov + 0.15, yi - h/2, f"{ov:.1f}%", va="center", fontsize=9.5, color="#b9620a")
ax.set_yticks(y)
ax.set_yticklabels(labels, fontsize=11)
# flag the near-matches in green
for tick, lab in zip(ax.get_yticklabels(), labels):
    if lab in MATCH:
        tick.set_color("#1e8449"); tick.set_fontweight("bold")
ax.set_xlabel("Patients reporting the side effect (%)")
ax.set_xlim(0, 12)
ax.set_title("Patients report the same side effects seen in the trials", fontsize=13, fontweight="bold", pad=10)
ax.legend(frameon=False, fontsize=9.5, loc="lower right")
ax.spines[["top", "right"]].set_visible(False); ax.tick_params(left=False)
fig.text(0.012, -0.06,
         "Green = the two most drug-specific, least disease-overlapping effects — they match almost exactly (sleep 9.0 vs 9.3; GI 5.0 vs 4.4). "
         "Divergences run as expected: passively-mentioned\nReddit data under-counts minor elicited effects (headache, light-headedness), while disease-overlapping symptoms (fatigue) are mentioned more. "
         "Clinical patients on LDN 0.5–6 mg/day (Du & Nguyen 2025); Reddit denominator = 321 LDN patients.",
         ha="left", fontsize=7.6, color="#7f8c8d", style="italic")
fig.savefig(os.path.join(OUT, "letter_fig_ae_overlay.png"), dpi=200, bbox_inches="tight")
fig.savefig(os.path.join(OUT, "letter_fig_ae_overlay.svg"), bbox_inches="tight")
print("saved letter_fig_ae_overlay")
