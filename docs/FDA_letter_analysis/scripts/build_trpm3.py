# -*- coding: utf-8 -*-
"""Conceptual schematic of the replicated LDN mechanism: TRPM3 ion-channel
restoration in NK cells. Cabanas 2019/2021; Sasso 2025 (Griffith/NCNED).
Schematic only — not to scale, no quantitative conductances implied."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Circle, RegularPolygon
import os

OUT = r"C:\Users\scgee\OneDrive\Documents\Projects\PatientPunk\FDA_analysis\figures"
os.makedirs(OUT, exist_ok=True)
GREEN, RED, GREY, ORANGE, BLUE, CA = "#27ae60", "#c0392b", "#95a5a6", "#e67e22", "#2e86c1", "#2980b9"

fig, ax = plt.subplots(figsize=(12.2, 4.9))
ax.set_xlim(0, 12); ax.set_ylim(0, 10); ax.axis("off")


def ca_arrows(cx, n, strong):
    xs = {1: [cx], 2: [cx - 0.18, cx + 0.18], 3: [cx - 0.28, cx, cx + 0.28]}[n]
    for x in xs:
        ax.annotate("", xy=(x, 4.35), xytext=(x, 7.0),
                    arrowprops=dict(arrowstyle="-|>", lw=2.4 if strong else 1.2,
                                    color=CA if strong else "#aed6f1", alpha=1 if strong else 0.8))
    ax.text(cx, 7.35, "Ca²⁺", ha="center", fontsize=10, color=CA, fontweight="bold")


def inhib(x0, x1, y, color, lw, dashed=False):
    ax.plot([x0, x1], [y, y], color=color, lw=lw, ls="--" if dashed else "-", solid_capstyle="round")
    ax.plot([x1, x1], [y - 0.22, y + 0.22], color=color, lw=lw, solid_capstyle="round")  # ⊣ bar


def panel(cx, title, state, caption):
    ax.add_patch(FancyBboxPatch((cx - 1.78, 1.15), 3.56, 7.7, boxstyle="round,pad=0.02,rounding_size=0.18",
                                fc="#fbfcfc", ec="#d5d8dc", lw=1.3))
    ax.text(cx, 8.35, title, ha="center", fontsize=12.5, fontweight="bold", color="#1c2833")
    # membrane band
    ax.add_patch(Rectangle((cx - 1.55, 4.55), 3.1, 0.9, fc="#e9eef2", ec="#cdd6dd", lw=0.8))
    ax.text(cx - 1.5, 4.18, "cell membrane", fontsize=6.5, color="#95a5a6", style="italic")
    chan_col = GREEN if state in ("healthy", "ldn") else GREY
    # channel (TRPM3) crossing the membrane
    ax.add_patch(FancyBboxPatch((cx - 0.4, 3.95), 0.8, 2.05, boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc=chan_col, ec="white", lw=1.4, alpha=1 if state != "impaired" else 0.55))
    ax.text(cx, 3.55, "TRPM3", ha="center", fontsize=8.5, fontweight="bold", color=chan_col)
    # µ-opioid receptor
    ax.add_patch(Circle((cx + 1.0, 5.0), 0.32, fc=ORANGE, ec="white", lw=1.2))
    ax.text(cx + 1.0, 5.0, "µOR", ha="center", va="center", fontsize=6.6, color="white", fontweight="bold")
    if state == "healthy":
        ca_arrows(cx, 3, True)
        inhib(cx + 0.66, cx + 0.42, 5.0, GREY, 1.4)
    elif state == "impaired":
        ca_arrows(cx, 1, False)
        inhib(cx + 0.66, cx + 0.42, 5.0, RED, 3.0)              # over-inhibition
        ax.text(cx + 0.95, 5.7, "over-\ninhibition", ha="center", fontsize=7, color=RED, fontweight="bold")
    else:  # ldn
        ca_arrows(cx, 3, True)
        inhib(cx + 0.66, cx + 0.42, 5.0, GREY, 1.4, dashed=True)  # inhibition relieved
        ax.add_patch(RegularPolygon((cx + 1.0, 5.92), 6, radius=0.34, fc=BLUE, ec="white", lw=1.2))
        ax.text(cx + 1.0, 5.92, "LDN", ha="center", va="center", fontsize=6.6, color="white", fontweight="bold")
        ax.annotate("", xy=(cx + 1.0, 5.36), xytext=(cx + 1.0, 5.62),
                    arrowprops=dict(arrowstyle="-|>", lw=1.6, color=BLUE))
    ax.text(cx, 2.35, caption, ha="center", va="top", fontsize=8.6, color="#34495e", wrap=True)


panel(2.0, "Healthy NK cell", "healthy",
      "TRPM3 channel functions normally —\nnormal calcium entry.")
panel(6.0, "ME/CFS / Long COVID", "impaired",
      "The µ-opioid receptor over-inhibits\nTRPM3; channel function is impaired.\n(p < 0.0001 vs healthy)")
panel(10.0, "+ Low-dose naltrexone", "ldn",
      "LDN blocks the receptor, relieving the\ninhibition — TRPM3 function restored.\n(≈ healthy; p > 0.9999)")

ax.text(6.0, 9.55, "How low-dose naltrexone may work: restoring TRPM3 ion-channel function",
        ha="center", fontsize=13.5, fontweight="bold", color="#1c2833")
fig.text(0.5, 0.005, "Conceptual schematic (not to scale). Replicated mechanism: Cabanas et al. 2019, 2021; Sasso et al. 2025 (Griffith University / NCNED).",
         ha="center", fontsize=7.8, color="#7f8c8d", style="italic")
fig.savefig(os.path.join(OUT, "letter_fig_trpm3.png"), dpi=200, bbox_inches="tight")
fig.savefig(os.path.join(OUT, "letter_fig_trpm3.svg"), bbox_inches="tight")
print("saved letter_fig_trpm3")
