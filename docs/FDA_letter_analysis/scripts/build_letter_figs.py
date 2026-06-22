# -*- coding: utf-8 -*-
"""Standalone figures for the FDA letter:
  §2  sex disparity (% female among patients)
  §2  scale of unmet need (US affected)
  §4  Du & Nguyen (2025) meta-analysis forest of symptom relative risks
All numbers are literature-sourced from the letter's own citations."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np, os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "figures")
os.makedirs(OUT, exist_ok=True)
def save(fig, stem):
    fig.savefig(os.path.join(OUT, stem + ".png"), dpi=200, bbox_inches="tight")
    fig.savefig(os.path.join(OUT, stem + ".svg"), bbox_inches="tight")
    print("saved", stem)

# ─── 1. Sex disparity: % female among patients ──────────────────────────────────
# Long COVID / ME/CFS derived from sex-specific prevalence (≈equal population sizes);
# POTS is a directly reported patient-composition figure.
lc = 16.5 / (16.5 + 10.5) * 100      # 61.1
me = 1.7 / (1.7 + 0.9) * 100         # 65.4
conds = ["Long COVID", "ME/CFS", "POTS"]
fempct = [lc, me, 80.0]
fig, ax = plt.subplots(figsize=(7.6, 4.2))
bars = ax.bar(conds, fempct, color="#b0335b", width=0.62, edgecolor="white")
ax.axhline(50, ls="--", lw=1.2, color="#7f8c8d")
ax.text(2.46, 51, "50% — parity", ha="right", va="bottom", fontsize=8.5, color="#7f8c8d")
for b, v in zip(bars, fempct):
    ax.text(b.get_x() + b.get_width() / 2, v + 1.2, f"{v:.0f}%", ha="center", fontsize=12, fontweight="bold", color="#1c2833")
ax.set_ylabel("Share of patients who are women (%)")
ax.set_ylim(0, 92)
ax.set_title("Every one of these conditions skews female", fontsize=13.5, fontweight="bold", pad=10)
ax.spines[["top", "right"]].set_visible(False)
fig.text(0.5, -0.02,
         "Long COVID & ME/CFS: derived from sex-specific prevalence (CDC/NCHS; AHRQ MEPS). POTS: reported ~80% female (Fedorowski 2019).",
         ha="center", fontsize=8, color="#7f8c8d", style="italic")
plt.tight_layout()
save(fig, "letter_fig_sex_disparity"); plt.close(fig)

# ─── 2. Scale of unmet need ─────────────────────────────────────────────────────
rows = [("Long COVID", 21.3, "21.3M"), ("ME/CFS", 3.3, "3.3M"),
        ("POTS", 2.0, "1–3M"), ("Lyme*", 0.476, "476k / yr*")]
labels = [r[0] for r in rows]; vals = [r[1] for r in rows]; vlab = [r[2] for r in rows]
y = np.arange(len(rows))[::-1]
fig, ax = plt.subplots(figsize=(8.6, 3.9))
ax.barh(y, vals, color="#1f7a8c", height=0.6, edgecolor="white")
for yi, v, t in zip(y, vals, vlab):
    ax.text(v + 0.4, yi, t, va="center", fontsize=11, fontweight="bold", color="#1c2833")
ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=11)
ax.set_xlabel("Americans affected (millions)")
ax.set_xlim(0, 24)
ax.set_title("Tens of millions of Americans — few or no approved therapies", fontsize=13, fontweight="bold", pad=10)
ax.spines[["top", "right"]].set_visible(False); ax.tick_params(left=False)
fig.text(0.012, -0.02,
         "*Lyme = new diagnoses per year (incidence); others = people currently or ever affected (prevalence). POTS shown at midpoint of a 1–3M range. Sources: CDC/NCHS; CDC Lyme; Fedorowski 2019.",
         ha="left", fontsize=7.6, color="#7f8c8d", style="italic")
plt.tight_layout()
save(fig, "letter_fig_scale"); plt.close(fig)

# ─── 3. Du & Nguyen meta-analysis forest (symptom relative risks) ────────────────
# RR < 1 = symptom reduction vs no-LDN. Pooled n=95 (O'Kelly 2022 + Bonilla 2023).
fr = [("Fatigue", 0.61, 0.51, 0.72), ("Brain fog", 0.68, 0.56, 0.82),
      ("Sleep disturbance", 0.62, 0.49, 0.78), ("Headache", 0.75, 0.61, 0.91)]
fr = sorted(fr, key=lambda r: r[1])  # strongest effect (lowest RR) at top
y = np.arange(len(fr))[::-1]
fig, ax = plt.subplots(figsize=(8.8, 3.8))
ax.axvspan(0.3, 1.0, color="#eafaf1", zorder=0)
for yi, (lab, rr, lo, hi) in zip(y, fr):
    ax.plot([lo, hi], [yi, yi], color="#1e8449", lw=2.6, solid_capstyle="round", zorder=2)
    ax.scatter(rr, yi, s=150, color="#1e8449", zorder=3, edgecolor="white", lw=1.4)
    ax.text(hi + 0.015, yi, f"RR {rr:.2f}  [{lo:.2f}–{hi:.2f}]", va="center", fontsize=10, color="#1c2833")
ax.axvline(1.0, color="#7f8c8d", ls="--", lw=1.2)
ax.text(1.0, len(fr) - 0.45, " 1.0 — no effect", color="#7f8c8d", fontsize=8.5)
ax.set_yticks(y); ax.set_yticklabels([r[0] for r in fr], fontsize=11)
ax.set_xlim(0.35, 1.18); ax.set_xlabel("Relative risk of persistent symptom vs no LDN (95% CI)")
ax.set_title("Pooled clinical evidence: lower symptom risk across every domain (Du & Nguyen 2025)",
             fontsize=12, fontweight="bold", pad=10)
ax.spines[["top", "right", "left"]].set_visible(False); ax.tick_params(left=False)
fig.text(0.012, -0.03,
         "Du & Nguyen 2025 (pooled n=95): O'Kelly 2022 at 1–2 mg/day + Bonilla 2023 at 0.5–6 mg/day; observational, all CIs exclude 1.0. Byambasuren 2025 corroborates fatigue (g = −0.74).",
         ha="left", fontsize=7.4, color="#7f8c8d", style="italic")
plt.tight_layout()
save(fig, "letter_fig_meta_forest"); plt.close(fig)
print("DONE")
