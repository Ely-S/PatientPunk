# -*- coding: utf-8 -*-
"""Combined two-panel exhibit for the FDA letter:
  (A) clinical benefit  — Du & Nguyen 2025 symptom relative risks (efficacy)
  (B) side-effect profile — clinical vs real-world Reddit rates (tolerability)
Distinct titles + a note keep the shared symptom labels from reading as a contradiction."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np, os

OUT = r"C:\Users\scgee\OneDrive\Documents\Projects\PatientPunk\FDA_analysis\figures"
os.makedirs(OUT, exist_ok=True)

fig, (axA, axB) = plt.subplots(1, 2, figsize=(14.2, 5.3), gridspec_kw={"width_ratios": [1.0, 1.08]})

# ── Panel A: efficacy forest ─────────────────────────────────────────────────────
fr = [("Fatigue", 0.61, 0.51, 0.72), ("Brain fog", 0.68, 0.56, 0.82),
      ("Sleep disturbance", 0.62, 0.49, 0.78), ("Headache", 0.75, 0.61, 0.91)]
fr = sorted(fr, key=lambda r: r[1])
yA = np.arange(len(fr))[::-1]
axA.axvspan(0.3, 1.0, color="#eafaf1", zorder=0)
for yi, (lab, rr, lo, hi) in zip(yA, fr):
    axA.plot([lo, hi], [yi, yi], color="#1e8449", lw=2.6, solid_capstyle="round", zorder=2)
    axA.scatter(rr, yi, s=140, color="#1e8449", zorder=3, edgecolor="white", lw=1.4)
    axA.text(hi + 0.015, yi, f"RR {rr:.2f} [{lo:.2f}–{hi:.2f}]", va="center", fontsize=9, color="#1c2833")
axA.axvline(1.0, color="#7f8c8d", ls="--", lw=1.2)
axA.text(1.0, len(fr) - 0.42, " 1.0 — no effect", color="#7f8c8d", fontsize=8)
axA.set_yticks(yA); axA.set_yticklabels([r[0] for r in fr], fontsize=10.5)
axA.set_xlim(0.4, 1.2); axA.set_xlabel("Relative risk of persistent symptom vs no LDN (95% CI)", fontsize=9.5)
axA.set_title("(A)  Clinical benefit: symptoms improved on LDN", fontsize=11.5, fontweight="bold", loc="left")
axA.spines[["top", "right", "left"]].set_visible(False); axA.tick_params(left=False)

# ── Panel B: side-effect overlay ─────────────────────────────────────────────────
cats = [("Headache", 10.0, 3.7), ("Sleep disturbance", 9.0, 9.3), ("Light-headedness", 8.5, 2.5),
        ("GI disturbance", 5.0, 4.4), ("Brain fog", 5.0, 2.2), ("Fatigue", 2.5, 5.0)]
MATCH = {"Sleep disturbance", "GI disturbance"}
yB = np.arange(len(cats))[::-1]; h = 0.36
axB.barh(yB + h/2, [c[1] for c in cats], h, color="#2c3e50", label="Clinical trials (Du & Nguyen)")
axB.barh(yB - h/2, [c[2] for c in cats], h, color="#e67e22", label="Reddit (this analysis)")
for yi, c in zip(yB, cats):
    axB.text(c[1] + 0.15, yi + h/2, f"{c[1]:.1f}%", va="center", fontsize=8.5, color="#2c3e50")
    axB.text(c[2] + 0.15, yi - h/2, f"{c[2]:.1f}%", va="center", fontsize=8.5, color="#b9620a")
axB.set_yticks(yB); axB.set_yticklabels([c[0] for c in cats], fontsize=10.5)
for tick, c in zip(axB.get_yticklabels(), cats):
    if c[0] in MATCH:
        tick.set_color("#1e8449"); tick.set_fontweight("bold")
axB.set_xlim(0, 13); axB.set_xlabel("Patients reporting the side effect (%)", fontsize=9.5)
axB.set_title("(B)  Side-effect profile: clinical vs real-world", fontsize=11.5, fontweight="bold", loc="left")
axB.legend(frameon=False, fontsize=8.5, loc="lower right")
axB.spines[["top", "right"]].set_visible(False); axB.tick_params(left=False)

fig.suptitle("Low-dose naltrexone: lower symptom risk in the trials, and the same side effects reported in the real world",
             fontsize=13.5, fontweight="bold", y=0.99)
fig.text(0.012, 0.055,
         "The two panels share symptom names but measure different things — left: how much each pre-existing symptom improved on LDN; right: how often each was reported as a side effect. A symptom can appear in both (e.g. chronic headache improves for most, yet a few report headache as a side effect).",
         fontsize=7.5, color="#7f8c8d", style="italic")
fig.text(0.012, 0.012,
         "Left: Du & Nguyen 2025 meta-analysis — O'Kelly 2022 (1–2 mg/day) + Bonilla 2023 (0.5–6 mg/day), observational, all CIs exclude 1.0. Right: clinical % (same pool) vs our 321 LDN patients; green = near-exact match (sleep, GI).",
         fontsize=7.5, color="#7f8c8d", style="italic")
plt.tight_layout(rect=[0, 0.085, 1, 0.95])
fig.savefig(os.path.join(OUT, "letter_fig_combined_evidence.png"), dpi=200, bbox_inches="tight")
fig.savefig(os.path.join(OUT, "letter_fig_combined_evidence.svg"), bbox_inches="tight")
print("saved letter_fig_combined_evidence")
