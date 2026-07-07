# -*- coding: utf-8 -*-
"""Figure for the LDN real-world-evidence paragraph: our patient-reported cohort
(n=321, 68.5% positive) against the clinical Long COVID LDN study cohorts."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np, os

OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "figures")
os.makedirs(OUTDIR, exist_ok=True)

# Long COVID LDN cohorts (clinical) + our real-world cohort
studies = [
    ("Isman / O'Kelly 2024  (LDN + NAD+)", 36, "#b0b8bf"),
    ("O'Kelly 2022", 52, "#b0b8bf"),
    ("Bonilla 2023", 59, "#b0b8bf"),
    ("This study\n(r/covidlonghaulers, 2020–2022)", 321, "#1e8449"),
]
labels = [s[0] for s in studies]
vals = [s[1] for s in studies]
cols = [s[2] for s in studies]
y = np.arange(len(studies))

fig, ax = plt.subplots(figsize=(9.2, 4.3))
ax.barh(y, vals, color=cols, height=0.62, edgecolor="white")
for i, v in enumerate(vals):
    bold = (i == len(vals) - 1)
    ax.text(v + 5, y[i], f"n = {v}", va="center", fontsize=11,
            fontweight="bold" if bold else "normal", color="#1c2833")
# response-rate callout inside our bar
ax.text(160, y[-1], "68.5% reported a positive outcome\n(95% CI 63–73%)",
        va="center", ha="center", fontsize=11, color="white", fontweight="bold")

ax.set_yticks(y)
ax.set_yticklabels(labels, fontsize=10.5)
ax.set_xlabel("Patients in cohort", fontsize=11)
ax.set_xlim(0, 372)
ax.set_title("A real-world cohort larger than every prior clinical Long COVID LDN study",
             fontsize=12.5, fontweight="bold", pad=12)
ax.spines[["top", "right"]].set_visible(False)
ax.tick_params(left=False)
fig.text(0.012, 0.015, "Patient-reported outcomes (self-reported, uncontrolled). Clinical cohorts shown for scale comparison.",
         fontsize=8, color="#7f8c8d", style="italic")
plt.tight_layout(rect=[0, 0.03, 1, 1])
png = os.path.join(OUTDIR, "ldn_rwe_cohort.png")
svg = os.path.join(OUTDIR, "ldn_rwe_cohort.svg")
fig.savefig(png, dpi=200, bbox_inches="tight")
fig.savefig(svg, bbox_inches="tight")
print("saved:", png)
print("saved:", svg)
