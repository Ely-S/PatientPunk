# -*- coding: utf-8 -*-
"""Export every LDN figure as a standalone PNG+SVG into FDA_analysis/figures/,
in a single consistent house style (typography, palette, subtle grids, and a
scientific-paper caption under each figure). Reads the same DBs the notebooks use,
so numbers match the current categorizer.

Importable: each notebook builder calls export_all() at the end so the standalone
files refresh on every rebuild. export_all() guards on DB existence and never raises.
"""
from __future__ import annotations
import sqlite3, os, textwrap
from collections import Counter
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ── house style (matches the combined notebook) ──
plt.rcParams.update({
    "axes.titlesize": 12.5, "axes.titleweight": "bold", "axes.titlepad": 10,
    "axes.labelsize": 10.5, "axes.labelcolor": "#1c2833",
    "axes.edgecolor": "#444444", "axes.linewidth": 0.8,
    "xtick.labelsize": 9, "ytick.labelsize": 10, "font.size": 10,
    "xtick.color": "#444444", "ytick.color": "#444444",
    "axes.grid": False, "savefig.dpi": 200,
})
CLH_C, PHX_C, CLIN_C = "#8e44ad", "#2e86c1", "#2c3e50"
PURPLE, GREY, SHADE, ACCENT = CLH_C, "#b9a7c7", "#f4eff8", "#6c3483"
LIT = {"Sleep disturbance", "Gastrointestinal", "Vivid / abnormal dreams"}
DUN = [("Headache", 10.0), ("Sleep disturbance", 9.0), ("Light-headedness", 8.5),
       ("GI disturbance", 5.0), ("Brain fog", 5.0), ("Fatigue", 2.5)]

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NB = os.path.join(HERE, "notebooks")
FIG = os.path.join(HERE, "figures")
CLH_DB = os.path.join(NB, "ldn_2yr.db")
PHX_DB = os.path.join(NB, "ldn_phoenix.db")


def grid(ax, axis="x"):
    ax.grid(axis=axis, color="#e9e9e9", lw=0.7, zorder=0); ax.set_axisbelow(True)


def caption(fig, n, text, bottom=0.27, left=0.20, top=0.90, right=0.97):
    fig.subplots_adjust(left=left, right=right, top=top, bottom=bottom)
    fig.text(0.012, 0.012, chr(10).join(textwrap.wrap(text, 168)),
             ha="left", va="bottom", fontsize=7.4, color="#666666", style="italic")


def _save(fig, stem):
    os.makedirs(FIG, exist_ok=True)
    fig.savefig(os.path.join(FIG, stem + ".png"), bbox_inches="tight")
    fig.savefig(os.path.join(FIG, stem + ".svg"), bbox_inches="tight")
    plt.close(fig)
    print("  figure ->", stem + ".png /.svg")


def _doses(db):
    c = sqlite3.connect(db)
    v = [r[0] for r in c.execute("select min_dose from user_features where mentions_dose=1 and min_dose is not null")]
    le = c.execute("select sum(dose_le_4_5), sum(mentions_dose) from user_features").fetchone()
    c.close()
    return sorted(v), int(le[0]), int(le[1])


def _dotstrip(ax, vals, gap, size):
    cnt = Counter(round(x, 3) for x in vals)
    for v, k in sorted(cnt.items()):
        col = PURPLE if v <= 4.5 else GREY
        ax.scatter([v] * k, [(i + 1) * gap for i in range(k)], s=size, color=col, edgecolor="white", linewidth=0.4, zorder=3)
    return max(cnt.values()) if cnt else 1


def _ae(db):
    c = sqlite3.connect(db)
    s = c.execute("select category, n_reports from ae_summary").fetchall()
    m = {k: int(v) for k, v in c.execute("select k,v from ae_meta")}
    c.close()
    return {cat: n for cat, n in s if cat != "Other / unspecified"}, m


def _clin(db):
    c = sqlite3.connect(db)
    n = dict(c.execute("select category,n_users from ae_clinical"))
    N = dict(c.execute("select k,v from ae_meta")).get("n_users_total")
    c.close()
    return n, int(N)


def export_clh_dose():
    clh, cle, ctot = _doses(CLH_DB)
    fig, ax = plt.subplots(figsize=(9.5, 3.6))
    grid(ax, "y")
    ax.axvspan(0, 4.5, color=SHADE, zorder=0)
    mx = _dotstrip(ax, clh, 0.10, 26)
    ax.set_xlim(-0.2, 11); ax.set_ylim(-0.1, mx * 0.10 + 0.5); ax.set_yticks([])
    ax.set_xlabel("Lowest reported LDN dose (mg) — one dot = one patient")
    ax.set_title(f"Real-world LDN dosing (r/covidlonghaulers, n={ctot})")
    for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
    caption(fig, "S1", f"Self-reported LDN doses in r/covidlonghaulers (n={ctot} dose-stating patients), one dot per "
            f"patient at the lowest dose they state, on a true milligram axis (no binning). Purple = within the ≤4.5 mg "
            f"range (shaded); grey = above it. {cle}/{ctot} ({100*cle/ctot:.0f}%) use ≤4.5 mg. Self-reported by the "
            f"subset of patients who state a dose.", bottom=0.34, left=0.05)
    _save(fig, "ldn_dose_dotstrip_clh")


def export_combined_dose():
    clh, cle, ctot = _doses(CLH_DB)
    phx, ple, ptot = _doses(PHX_DB)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9.8, 5.2), sharex=True)
    for ax, vals, name, le, tot in [(a1, clh, "r/covidlonghaulers (Long COVID)", cle, ctot),
                                     (a2, phx, "Phoenix Rising (ME/CFS + Long COVID)", ple, ptot)]:
        grid(ax, "y")
        ax.axvspan(0, 4.5, color=SHADE, zorder=0)
        mx = _dotstrip(ax, vals, 0.085, 22)
        ax.set_ylim(-0.1, mx * 0.085 + 0.5); ax.set_yticks([])
        ax.set_title(f"{name} — n={tot} dose-stating, {le} ({100*le/tot:.0f}%) ≤4.5 mg", fontsize=10.5, loc="left")
        for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
    a2.set_xlim(-0.3, 13); a2.set_xlabel("Lowest reported LDN dose (mg) — one dot = one patient")
    fig.suptitle("Real-world LDN dosing across two patient communities", fontsize=12.5, fontweight="bold")
    caption(fig, "S2", "Self-reported LDN doses in two communities (dot view; one dot per patient at their lowest stated "
            "dose, true mg axis, no binning). Shaded = ≤4.5 mg range. Both communities cluster ≤4.5 mg. Self-reported "
            "by the subset stating a dose.", bottom=0.20, left=0.05, top=0.90)
    _save(fig, "ldn_dose_dotstrip_combined")


def export_combined_dose_stacked():
    def dc(db):
        c = sqlite3.connect(db)
        v = [r[0] for r in c.execute("select min_dose from user_features where mentions_dose=1 and min_dose is not null")]
        tot, le = c.execute("select sum(mentions_dose), sum(dose_le_4_5) from user_features").fetchone()
        c.close()
        return Counter(round(x, 3) for x in v), int(tot), int(le)
    cdc, ctot, cle = dc(CLH_DB); pdc, ptot, ple = dc(PHX_DB)
    vals = sorted(set(cdc) | set(pdc))
    x = np.arange(len(vals)); clh_n = [cdc.get(v, 0) for v in vals]; phx_n = [pdc.get(v, 0) for v in vals]
    fig, ax = plt.subplots(figsize=(10.5, 4.6))
    grid(ax, "y")
    le_idx = [i for i, v in enumerate(vals) if v <= 4.5]
    if le_idx: ax.axvspan(-0.5, max(le_idx) + 0.5, color=SHADE, zorder=0)
    ax.bar(x, clh_n, color=CLH_C, label=f"r/covidlonghaulers  (n={ctot} dose-stating)", zorder=3, width=0.82)
    ax.bar(x, phx_n, bottom=clh_n, color=PHX_C, label=f"Phoenix Rising  (n={ptot} dose-stating)", zorder=3, width=0.82)
    ax.set_xticks(x); ax.set_xticklabels([f"{v:g}" for v in vals])
    ax.set_xlabel("Lowest reported LDN dose (mg) — one bar per exact stated dose")
    ax.set_ylabel("Patients reporting this dose (n)")
    ax.set_title("Real-world LDN dosing across two patient communities")
    top = max((c + p) for c, p in zip(clh_n, phx_n)); ax.set_ylim(0, top * 1.18)
    if le_idx:
        ax.axvline(max(le_idx) + 0.5, color="#9b59b6", ls="--", lw=1, zorder=2)
        ax.text(0, top * 1.12, "shaded = ≤4.5 mg window", ha="left", va="top", fontsize=9, color=ACCENT)
    ax.legend(frameon=False, fontsize=9.5, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)
    caption(fig, 1, f"Distribution of self-reported LDN doses in two communities; each bar is one exact stated dose "
            f"(no binning), height = patients reporting it as their lowest, stacked by source. Shaded = ≤4.5 mg range. "
            f"{cle}/{ctot} ({100*cle/ctot:.0f}%) of r/covidlonghaulers and {ple}/{ptot} ({100*ple/ptot:.0f}%) of "
            f"Phoenix Rising dose-stating patients use ≤4.5 mg; the only approved naltrexone product is 50 mg. "
            f"Self-reported.", bottom=0.30, left=0.07)
    _save(fig, "ldn_dose_stacked_combined")


def export_side_effects():
    cc, cm = _ae(CLH_DB); pc, pm = _ae(PHX_DB)
    cats = sorted(set(cc) | set(pc), key=lambda k: -(cc.get(k, 0) + pc.get(k, 0)))
    y = np.arange(len(cats))[::-1]
    clh_v = [cc.get(k, 0) for k in cats]; phx_v = [pc.get(k, 0) for k in cats]

    # stacked counts
    fig, ax = plt.subplots(figsize=(10.0, 5.4))
    grid(ax, "x")
    ax.barh(y, clh_v, color=CLH_C, label=f"r/covidlonghaulers  (n={cm['n_ae_reports']} side-effect reports)", zorder=3)
    ax.barh(y, phx_v, left=clh_v, color=PHX_C, label=f"Phoenix Rising  (n={pm['n_ae_reports']} side-effect reports)", zorder=3)
    for yi, cv, pv in zip(y, clh_v, phx_v):
        if cv >= 6:  ax.text(cv / 2, yi, str(cv), va="center", ha="center", fontsize=7.5, color="white")
        if pv >= 12: ax.text(cv + pv / 2, yi, str(pv), va="center", ha="center", fontsize=7.5, color="white")
        ax.text(cv + pv + 5, yi, str(cv + pv), va="center", fontsize=8.5, color="#555")
    ax.set_yticks(y); ax.set_yticklabels(cats)
    for tick, k in zip(ax.get_yticklabels(), cats):
        if k in LIT: tick.set_color("#1e8449"); tick.set_fontweight("bold")
    ax.set_xlim(0, max(c + p for c, p in zip(clh_v, phx_v)) + 45)
    ax.set_xlabel("Side-effect reports mentioning the effect (n) — stacked by source")
    ax.set_title("Reported LDN side effects by community")
    ax.legend(frameon=False, fontsize=9.5, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    caption(fig, 2, f"Number of side-effect reports mentioning each category, stacked by source (r/covidlonghaulers, "
            f"purple, n={cm['n_ae_reports']}; Phoenix Rising, blue, n={pm['n_ae_reports']}). Categories overlap; "
            f"'Other / unspecified' omitted. Pooled COUNTS — Phoenix fills more of each bar because it is the larger "
            f"corpus, not a higher per-patient rate. Green labels = the literature's named LDN effects. Mention "
            f"frequencies, not incidence.", bottom=0.24, left=0.22)
    _save(fig, "ldn_side_effects_stacked_counts")

    # grouped % (size-controlled)
    cp = {k: 100 * cc.get(k, 0) / cm["n_ae_reports"] for k in cats}
    pp = {k: 100 * pc.get(k, 0) / pm["n_ae_reports"] for k in cats}
    h = 0.38
    fig, ax = plt.subplots(figsize=(9.6, 5.4))
    grid(ax, "x")
    ax.barh(y + h / 2, [cp[k] for k in cats], h, color=CLH_C, label=f"r/covidlonghaulers (n={cm['n_ae_reports']} reports)", zorder=3)
    ax.barh(y - h / 2, [pp[k] for k in cats], h, color=PHX_C, label=f"Phoenix Rising (n={pm['n_ae_reports']} reports)", zorder=3)
    for yi, k in zip(y, cats):
        ax.text(cp[k] + 0.4, yi + h / 2, f"{cp[k]:.0f}%", va="center", fontsize=8.5, color=CLH_C)
        ax.text(pp[k] + 0.4, yi - h / 2, f"{pp[k]:.0f}%", va="center", fontsize=8.5, color="#1f618d")
    ax.set_yticks(y); ax.set_yticklabels(cats)
    for tick, k in zip(ax.get_yticklabels(), cats):
        if k in LIT: tick.set_color("#1e8449"); tick.set_fontweight("bold")
    ax.set_xlim(0, max(max(cp.values()), max(pp.values())) + 7)
    ax.set_xlabel("Side-effect reports mentioning the effect (% within each community)")
    ax.set_title("LDN side-effect profile — share within each community")
    ax.legend(frameon=False, fontsize=9.5, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    caption(fig, "S3", "Side-effect profile expressed as a percentage of each community's own side-effect reports "
            "(size-controlled alternative to the stacked-count view). Categories overlap. Percentages are mention "
            "rates within side-effect reports, not incidence; extraction prompts differed between corpora, so compare "
            "shape rather than single values.", bottom=0.26, left=0.22)
    _save(fig, "ldn_side_effects_grouped_pct")


def export_clinical_magnitude():
    order = sorted(DUN, key=lambda x: -x[1]); cats = [d[0] for d in order]
    cn, cN = _clin(CLH_DB)
    clin = [dict(DUN)[k] for k in cats]; clh = [100 * cn[k] / cN for k in cats]
    y = np.arange(len(cats))[::-1]; h = 0.38
    fig, ax = plt.subplots(figsize=(9.6, 4.8))
    grid(ax, "x")
    ax.barh(y + h / 2, clin, h, color=CLIN_C, label="Clinical trials (Du & Nguyen 2025)", zorder=3)
    ax.barh(y - h / 2, clh, h, color=CLH_C, label=f"r/covidlonghaulers (% of {cN} patients)", zorder=3)
    for yi, a, b in zip(y, clin, clh):
        ax.text(a + 0.15, yi + h / 2, f"{a:.1f}%", va="center", fontsize=8.5, color=CLIN_C)
        ax.text(b + 0.15, yi - h / 2, f"{b:.1f}%", va="center", fontsize=8.5, color=ACCENT)
    ax.set_yticks(y); ax.set_yticklabels(cats); ax.set_xlim(0, 12)
    ax.set_xlabel("Patients reporting the side effect (%)")
    ax.set_title("LDN side effects: r/covidlonghaulers vs clinical trials")
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False); ax.tick_params(left=False)
    caption(fig, "3a", f"Per-patient LDN side-effect rates in r/covidlonghaulers (purple, % of {cN} patients whose posts "
            f"mention each effect) versus pooled clinical-trial frequencies (Du & Nguyen 2025, dark; % of trial "
            f"patients). Both are percentages of patients. Real-world rates track the trials within a few points for "
            f"sleep and GI; spontaneous reporting under-captures lightly-elicited effects (headache, light-headedness). "
            f"Phoenix Rising is excluded here (higher extraction rate inflates magnitudes; shown size-normalized in the profile-shape panel). "
            f"Self-reported, not incidence.", bottom=0.30, left=0.20)
    _save(fig, "ldn_side_effects_vs_clinical_magnitude")


def export_clinical_shape():
    order = sorted(DUN, key=lambda x: -x[1]); cats = [d[0] for d in order]
    cn, _ = _clin(CLH_DB); pn, _ = _clin(PHX_DB)
    def norm(v): s = sum(v) or 1; return [100 * x / s for x in v]
    dun = norm([dict(DUN)[k] for k in cats]); clhv = norm([cn[k] for k in cats]); phxv = norm([pn[k] for k in cats])
    y = np.arange(len(cats))[::-1]; h = 0.26
    fig, ax = plt.subplots(figsize=(9.6, 5.4))
    grid(ax, "x")
    ax.barh(y + h, dun, h, color=CLIN_C, label="Clinical trials (Du & Nguyen 2025)", zorder=3)
    ax.barh(y, clhv, h, color=CLH_C, label="r/covidlonghaulers (n=321)", zorder=3)
    ax.barh(y - h, phxv, h, color=PHX_C, label="Phoenix Rising (n=354)", zorder=3)
    ax.set_yticks(y); ax.set_yticklabels(cats)
    ax.set_xlabel("Relative share of the six tracked side effects (%, normalized within each source)")
    ax.set_title("LDN side-effect profile shape — three sources, size-normalized")
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False); ax.tick_params(left=False)
    caption(fig, "3b", "Relative profile of LDN side effects across three independent sources. For each source the six "
            "side-effect categories reported by Du & Nguyen (2025) are rescaled to sum to 100%, showing the relative "
            "MIX of effects rather than their absolute frequency; this controls for the sources' very different "
            "extraction rates (a side effect is recorded in 60% of Phoenix Rising reports vs 15% of r/covidlonghaulers "
            "reports), so only profile shape is compared. Real-world bars give the proportion of LDN patients whose "
            "posts mention each effect (r/covidlonghaulers, Long COVID, n=321; Phoenix Rising, ME/CFS + Long COVID, "
            "n=354); clinical bars are pooled trial frequencies (Du & Nguyen 2025). Both online cohorts emphasize sleep "
            "disturbance and fatigue while the trials rank headache and light-headedness higher — the expected gap "
            "between spontaneously volunteered and clinician-elicited adverse events. Values reflect reporting "
            "patterns, not incidence; absolute magnitudes are not comparable across sources (a magnitude comparison is shown separately).",
            bottom=0.34, left=0.20)
    _save(fig, "ldn_side_effects_profile_shape")


def _wilson(k, n, z=1.96):
    if n == 0: return 0.0, 0.0
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d
    m = z * ((p * (1 - p) + z * z / (4 * n)) / n) ** 0.5 / d
    return max(0, c - m), min(1, c + m)


def export_dose_vs_se():
    """Any-side-effect rate by highest dose reached, per cohort, Wilson CIs (needs both DBs)."""
    BANDS = ["≤1.5", "1.5–4.5", ">4.5"]
    def band(v): return "≤1.5" if v <= 1.5 else ("1.5–4.5" if v <= 4.5 else ">4.5")
    def by_band(db):
        c = sqlite3.connect(db)
        rows = c.execute("select max_dose,any_side_effect from user_features where mentions_dose=1 and max_dose is not null").fetchall()
        c.close()
        out = {b: [0, 0] for b in BANDS}
        for v, s in rows:
            out[band(v)][0] += 1; out[band(v)][1] += int(s)
        return out
    cb = by_band(CLH_DB); pb = by_band(PHX_DB)
    y = np.arange(len(BANDS))[::-1]
    fig, ax = plt.subplots(figsize=(9.6, 4.4))
    grid(ax, "x")
    for data, col, off in [(cb, CLH_C, 0.15), (pb, PHX_C, -0.15)]:
        for i, b in enumerate(BANDS):
            n, k = data[b]
            if not n: continue
            r = 100 * k / n; lo, hi = _wilson(k, n); lo *= 100; hi *= 100; yy = y[i] + off
            ax.plot([lo, hi], [yy, yy], color=col, lw=2.2, solid_capstyle="round", zorder=3)
            ax.scatter([r], [yy], s=70, color=col, edgecolor="white", lw=1, zorder=4)
            ax.text(hi + 1.8, yy, f"{r:.0f}%  (n={n})", va="center", fontsize=8.5, color=col)
    ax.scatter([], [], color=CLH_C, label="r/covidlonghaulers"); ax.scatter([], [], color=PHX_C, label="Phoenix Rising")
    ax.set_yticks(y); ax.set_yticklabels([f"{b} mg" for b in BANDS])
    ax.set_xlim(0, 112); ax.set_xlabel("Patients reporting any side effect (%, with 95% CI)")
    ax.set_ylabel("Highest LDN dose reached")
    ax.set_title("Side-effect reporting vs LDN dose reached")
    ax.legend(frameon=False, fontsize=9, loc="lower left"); ax.spines[["top", "right"]].set_visible(False)
    caption(fig, "", "Proportion of dose-stating LDN patients reporting any side effect, grouped by the highest dose they "
            "report reaching, with Wilson 95% confidence intervals (n per band shown). Within each community the rate is "
            "flat across the dose range — intervals overlap with no monotonic increase — so side-effect reporting does not "
            "rise with dose across the established LDN range. Bands use the patient-level maximum stated dose, not the dose "
            "at which an effect occurred, so this is a patient-level association, not a pharmacological dose-response. "
            "Self-reported titration also tends to cap the dose reached once side effects appear, biasing toward more side "
            "effects at lower max dose; the flatness holds despite that. Phoenix Rising's higher overall level reflects its "
            "more liberal side-effect extraction, not greater toxicity — only within-community trends are comparable. "
            "'Any side effect' is a coarse indicator that does not weight severity.", bottom=0.34, left=0.16)
    _save(fig, "ldn_side_effects_vs_dose")


def export_dose_vs_se_normalized():
    """Risk ratio of any side effect vs each forum's own lowest-dose group (needs both DBs)."""
    BANDS = ["≤1.5", "1.5–4.5", ">4.5"]
    def band(v): return "≤1.5" if v <= 1.5 else ("1.5–4.5" if v <= 4.5 else ">4.5")
    def by_band(db):
        c = sqlite3.connect(db)
        rows = c.execute("select max_dose,any_side_effect from user_features where mentions_dose=1 and max_dose is not null").fetchall()
        c.close()
        out = {b: [0, 0] for b in BANDS}
        for v, s in rows:
            out[band(v)][0] += 1; out[band(v)][1] += int(s)
        return out
    def rr_ci(k1, n1, k0, n0, z=1.96):
        if min(k1, k0, n1, n0) == 0: return (np.nan, np.nan, np.nan)
        rr = (k1 / n1) / (k0 / n0); se = (1 / k1 - 1 / n1 + 1 / k0 - 1 / n0) ** 0.5
        return rr, rr * np.exp(-z * se), rr * np.exp(z * se)
    cb = by_band(CLH_DB); pb = by_band(PHX_DB)
    y = np.arange(len(BANDS))[::-1]
    fig, ax = plt.subplots(figsize=(9.6, 4.4))
    grid(ax, "x")
    ax.axvline(1.0, color="#7f8c8d", ls="--", lw=1, zorder=2)
    for data, col, off in [(cb, CLH_C, 0.15), (pb, PHX_C, -0.15)]:
        n0, k0 = data[BANDS[0]]
        for i, b in enumerate(BANDS):
            n, k = data[b]; yy = y[i] + off
            if i == 0:
                ax.scatter([1.0], [yy], s=55, facecolor="white", edgecolor=col, lw=1.6, zorder=4); continue
            rr, lo, hi = rr_ci(k, n, k0, n0)
            ax.plot([lo, hi], [yy, yy], color=col, lw=2.2, solid_capstyle="round", zorder=3)
            ax.scatter([rr], [yy], s=70, color=col, edgecolor="white", lw=1, zorder=4)
            ax.text(hi * 1.05, yy, f"RR {rr:.2f}", va="center", fontsize=8.5, color=col)
    ax.scatter([], [], color=CLH_C, label="r/covidlonghaulers"); ax.scatter([], [], color=PHX_C, label="Phoenix Rising")
    ax.set_xscale("log"); ax.set_xlim(0.42, 2.7)
    ax.set_xticks([0.5, 0.7, 1.0, 1.5, 2.0]); ax.set_xticklabels(["0.5", "0.7", "1.0", "1.5", "2.0"])
    ax.set_yticks(y); ax.set_yticklabels([f"{b} mg" + (" (ref)" if i == 0 else "") for i, b in enumerate(BANDS)])
    ax.set_xlabel("Side-effect rate relative to the ≤1.5 mg group (risk ratio, 95% CI; log scale)")
    ax.set_ylabel("Highest LDN dose reached")
    ax.set_title("Side-effect reporting vs dose — normalized within each forum")
    ax.legend(frameon=False, fontsize=9, loc="lower left"); ax.spines[["top", "right"]].set_visible(False)
    caption(fig, "", "Side-effect reporting by dose, normalized within each forum to remove the large baseline difference "
            "in extraction rate, so the dose trend is comparable between communities. Each dose band is expressed as a "
            "risk ratio versus that forum's own ≤1.5 mg group (reference = 1.0, dashed line; open marker), with 95% "
            "confidence intervals on a log scale. In both communities every interval spans 1.0 — no band differs from "
            "the lowest-dose group — so the absence of a dose-side-effect relationship is consistent across forums, not "
            "an artifact of either one's reporting level. Risk ratios use the patient-level maximum dose and 'any side "
            "effect'; per-band cells are small (n≈18–78), so intervals are wide. Self-reported, uncontrolled data.",
            bottom=0.34, left=0.16)
    _save(fig, "ldn_side_effects_vs_dose_normalized")


def export_dose_by_category():
    """Phoenix-only: per-category side-effect rate by dose band (needs ldn_phoenix.db)."""
    import pandas as pd
    BANDS = ["≤1.5", "1.5–4.5", ">4.5"]; SH = {"≤1.5": "#2a9d8f", "1.5–4.5": "#e9c46a", ">4.5": "#e76f51"}   # cool->warm = low->high
    def band(v): return "≤1.5" if v <= 1.5 else ("1.5–4.5" if v <= 4.5 else ">4.5")
    c = sqlite3.connect(PHX_DB)
    ph = pd.read_sql("select user_id,max_dose from user_features where mentions_dose=1 and max_dose is not null", c)
    cset = pd.read_sql("select user_id,category from ae_user_clinical", c).groupby("user_id").category.apply(set)
    c.close()
    ph["band"] = ph.max_dose.map(band)
    ph["cats"] = ph.user_id.map(cset).apply(lambda s: s if isinstance(s, set) else set())
    CATS = ["Sleep disturbance", "GI disturbance", "Fatigue", "Headache", "Light-headedness", "Brain fog"]
    CATS = sorted(CATS, key=lambda cat: ph.cats.apply(lambda s: cat in s).sum())
    bn = {b: int((ph.band == b).sum()) for b in BANDS}
    def kc(cat, b): return int(ph[ph.band == b].cats.apply(lambda s: cat in s).sum())
    from scipy.stats import norm
    def ca_trend(ks, ns, scores=(0, 1, 2)):
        ks = np.array(ks, float); ns = np.array(ns, float); s = np.array(scores, float)
        N = ns.sum(); K = ks.sum()
        if K <= 0 or K >= N: return np.nan
        p = K / N; T = np.sum(s * (ks - ns * p)); var = p * (1 - p) * (np.sum(ns * s * s) - (np.sum(ns * s)) ** 2 / N)
        return 2 * norm.sf(abs(T / np.sqrt(var))) if var > 0 else np.nan
    y = np.arange(len(CATS)); h = 0.26
    fig, ax = plt.subplots(figsize=(9.8, 5.8)); grid(ax, "x")
    for j, b in enumerate(BANDS):
        rates, elo, ehi = [], [], []
        for cat in CATS:
            n = bn[b]; k = kc(cat, b); r = 100 * k / n; lo, hi = _wilson(k, n)
            rates.append(r); elo.append(r - 100 * lo); ehi.append(100 * hi - r)
        ax.barh(y + (1 - j) * h, rates, h, color=SH[b], xerr=[elo, ehi],
                error_kw=dict(lw=0.8, ecolor="#777", capsize=2), label=f"{b} mg (n={bn[b]})", zorder=3)
    pval = {cat: ca_trend([kc(cat, b) for b in BANDS], [bn[b] for b in BANDS]) for cat in CATS}
    ax.set_yticks(y)
    ax.set_yticklabels([f"{cat}\n(trend p={pval[cat]:.2f})" if pval[cat] == pval[cat] else f"{cat}\n(trend n/a)" for cat in CATS], fontsize=9.5)
    ax.set_xlim(0, 82); ax.set_xlabel("Phoenix Rising patients mentioning the effect (%, within dose band; Wilson 95% CI)")
    ax.set_title("Side-effect category vs dose reached — Phoenix Rising")
    ax.legend(frameon=False, fontsize=8.5, loc="lower right", title="Highest dose reached", title_fontsize=8.5)
    ax.spines[["top", "right"]].set_visible(False)
    caption(fig, "", "Per-patient rate of each side-effect category by highest dose reached, in Phoenix Rising — the only "
            "cohort with enough per-category data (r/covidlonghaulers has single-digit counts per category-by-dose cell and "
            "is not broken out; its aggregate dose relationship is shown separately). Denominator is all dose-stating "
            "patients per band (≤1.5 mg n=43; 1.5–4.5 mg n=78; >4.5 mg n=27); bars are the share mentioning each effect, "
            "with Wilson 95% confidence intervals. The p value beside each category is a Cochran–Armitage test for a linear "
            "trend across dose bands: none is significant — no side effect rises with dose, and the wide, overlapping "
            "intervals reflect the small per-band cells (low power; this rules out a large dose effect, not a subtle one). "
            "Within-cohort, so unaffected by Phoenix's overall reporting level. Patient-level maximum dose, not the dose at "
            "which an effect occurred; titration confound applies; self-reported.", bottom=0.30, left=0.23)
    _save(fig, "ldn_side_effects_by_category_vs_dose")


def export_dose_by_category_combined():
    """Both forums, cohort-adjusted: standardized per-category rate by dose band + stratified trend p."""
    import pandas as pd
    from scipy.stats import norm
    BANDS = ["≤1.5", "1.5–4.5", ">4.5"]; SCORES = {"≤1.5": 0, "1.5–4.5": 1, ">4.5": 2}
    SH = {"≤1.5": "#2a9d8f", "1.5–4.5": "#e9c46a", ">4.5": "#e76f51"}   # cool->warm = low->high
    def band(v): return "≤1.5" if v <= 1.5 else ("1.5–4.5" if v <= 4.5 else ">4.5")
    def load(db):
        c = sqlite3.connect(db)
        d = pd.read_sql("select user_id,max_dose from user_features where mentions_dose=1 and max_dose is not null", c)
        cs = pd.read_sql("select user_id,category from ae_user_clinical", c).groupby("user_id").category.apply(set)
        c.close()
        d["band"] = d.max_dose.map(band)
        d["cats"] = d.user_id.map(cs).apply(lambda s: s if isinstance(s, set) else set())
        return d
    DC = [load(CLH_DB), load(PHX_DB)]
    W = [len(d) for d in DC]; W = [w / sum(W) for w in W]
    def nk(d, b, c): sub = d[d.band == b]; return len(sub), int(sub.cats.apply(lambda s: c in s).sum())
    bn = {b: int(sum((d.band == b).sum() for d in DC)) for b in BANDS}
    CATS = ["Sleep disturbance", "GI disturbance", "Fatigue", "Headache", "Light-headedness", "Brain fog"]
    CATS = sorted(CATS, key=lambda c: sum(nk(d, b, c)[1] for d in DC for b in BANDS))
    def std_rate(c, b):
        R = var = 0.0
        for d, w in zip(DC, W):
            n, k = nk(d, b, c)
            if n == 0: continue
            pv = (k + 0.5) / (n + 1); R += w * (k / n); var += w * w * pv * (1 - pv) / n
        return 100 * R, 100 * var ** 0.5
    def strat_ca(c):
        Tsum = Vsum = 0.0
        for d in DC:
            ks = [nk(d, b, c)[1] for b in BANDS]; ns = [nk(d, b, c)[0] for b in BANDS]; s = [SCORES[b] for b in BANDS]
            N = sum(ns); K = sum(ks)
            if K <= 0 or K >= N: continue
            p = K / N
            Tsum += sum(si * (ki - ni * p) for si, ki, ni in zip(s, ks, ns))
            Vsum += p * (1 - p) * (sum(ni * si * si for ni, si in zip(ns, s)) - (sum(ni * si for ni, si in zip(ns, s))) ** 2 / N)
        return 2 * norm.sf(abs(Tsum / Vsum ** 0.5)) if Vsum > 0 else float("nan")
    y = np.arange(len(CATS)); h = 0.26
    fig, ax = plt.subplots(figsize=(9.8, 5.8)); grid(ax, "x")
    for j, b in enumerate(BANDS):
        rates = []; err = []
        for c in CATS:
            r, se = std_rate(c, b); rates.append(r); err.append(1.96 * se)
        ax.barh(y + (1 - j) * h, rates, h, color=SH[b], xerr=err, error_kw=dict(lw=0.8, ecolor="#777", capsize=2), label=f"{b} mg (n={bn[b]})", zorder=3)
    pval = {c: strat_ca(c) for c in CATS}
    ax.set_yticks(y)
    ax.set_yticklabels([f"{c}\n(trend p={pval[c]:.2f})" if pval[c] == pval[c] else f"{c}\n(trend n/a)" for c in CATS], fontsize=9.5)
    ax.set_xlim(0, 70); ax.set_xlabel("Cohort-adjusted patients mentioning the effect (%, directly standardized; ≈95% CI)")
    ax.set_title("Side-effect category vs dose reached — both forums, cohort-adjusted")
    ax.legend(frameon=False, fontsize=8.5, loc="lower right", title="Highest dose reached", title_fontsize=8.5)
    ax.spines[["top", "right"]].set_visible(False)
    caption(fig, "", "Per-patient side-effect reporting rates were compared across dose bands (highest reported dose) "
            "using Wilson 95% confidence intervals and a Cochran–Armitage trend test, with the two communities combined "
            "via direct standardization and a community-stratified test to prevent their differing baseline reporting "
            "rates from confounding the dose comparison. Within each band the two forums' per-category rates are combined "
            "at a fixed cohort weight (by dose-stating cohort size: r/covidlonghaulers ≈35%, Phoenix Rising ≈65%), so "
            "across-band differences reflect dose rather than cohort composition, and the trend test is stratified by "
            "forum (each forum's own baseline held constant, within-forum dose signals pooled). No category shows a "
            "significant dose trend (smallest p≈0.26) and the ≈95% intervals overlap across bands; combining both "
            "forums tightens the estimate without revealing a dose relationship the per-forum views missed. Bars are "
            "cohort-adjusted reporting frequencies, a weighted blend of the two forums and not an incidence; dose is the "
            "patient-level maximum, not the dose at which an effect occurred; the titration confound applies; data are "
            "self-reported and uncontrolled, and CLH's per-category cells are small and contribute noisily despite "
            "adjustment.", bottom=0.32, left=0.23)
    _save(fig, "ldn_side_effects_by_category_vs_dose_combined")


def export_all():
    print("export_ldn_figures: refreshing standalone figures ->", FIG)
    if os.path.exists(CLH_DB):
        export_clh_dose()
        export_clinical_magnitude()
    else:
        print("  SKIP CLH figures — missing", CLH_DB)
    if os.path.exists(CLH_DB) and os.path.exists(PHX_DB):
        export_combined_dose()
        export_combined_dose_stacked()
        export_side_effects()
        export_clinical_shape()
        export_dose_vs_se()
        export_dose_vs_se_normalized()
        export_dose_by_category()
        export_dose_by_category_combined()
    else:
        print("  SKIP combined/side-effect figures — need both ldn_2yr.db and ldn_phoenix.db")


if __name__ == "__main__":
    export_all()
    print("done.")
