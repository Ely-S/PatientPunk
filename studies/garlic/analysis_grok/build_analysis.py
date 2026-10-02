"""Build and execute the high-level garlic beliefs-and-use analysis notebook.

Produces, under this directory:
  garlic_beliefs_and_use.ipynb
  garlic_beliefs_and_use_executed.ipynb
  garlic_beliefs_and_use.html
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "notebooks"))
from build_notebook import build_notebook, execute_and_export  # noqa: E402

OUT = Path(__file__).resolve().parent / "garlic_beliefs_and_use"

# Probe DB is opened read-only by studies/garlic/garlic.py. The injected setup
# still needs DB_PATH / conn; we point both at the same file and never write.
DB_PATH_BLOCK = r"""
import sys
from pathlib import Path
from collections import OrderedDict
import json
import re
from datetime import datetime, timezone

from scipy.stats import fisher_exact, chi2_contingency
from statsmodels.stats.contingency_tables import Table2x2
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import proportion_confint

_HERE = Path.cwd().resolve()
_REPO = None
for _d in [_HERE, *_HERE.parents]:
    if (_d / "studies" / "garlic" / "garlic.py").is_file():
        _REPO = _d
        break
if _REPO is None:
    raise FileNotFoundError("Could not locate studies/garlic/garlic.py walking up from cwd")
sys.path.insert(0, str(_REPO / "studies" / "garlic"))
import garlic as G  # noqa: E402

G.apply_style(plt)
plt.rcParams.update({"figure.figsize": (9.2, 5.0), "figure.dpi": 120, "font.size": 10})
pd.set_option("future.no_silent_downcasting", True)

DB_PATH = str(G.db_path())
conn = G.open_db()
F = G.load_frames()

COMPLETE = pd.Index(F.units.loc[F.units.status == "complete", "reporter"].unique())
N_REP = int(len(COMPLETE))
N_MEMBERS = int(len(F.members))
USE = F.claims.loc[F.claims.use_payload_allowed].copy()
N_USE = int(USE.reporter.nunique())
BELIEF = F.claims.loc[F.claims.polarity.notna() & F.claims.included.astype(bool)].copy()
N_BELIEF = int(BELIEF.reporter.nunique())
ACTS = (
    G.reporter_matrix(F, "speech_act", G.SPEECH_ACTS)
    .reindex(COMPLETE, fill_value=False)
    .astype(bool)
)
ONLY_FL = ACTS["food_list"] & ~ACTS["actual_use"]
ONLY_AU = ACTS["actual_use"] & ~ACTS["food_list"]
BOTH_FL_AU = ACTS["food_list"] & ACTS["actual_use"]
POL = pd.crosstab(BELIEF["reporter"], BELIEF["polarity"]).gt(0)
MECH = pd.crosstab(F.mechanisms["reporter"], F.mechanisms["mechanism"]).gt(0)
ALLICIN_SYS = ["antimicrobial", "gut_or_biofilm", "immune", "herx_or_dieoff"]
HIST_SYS = ["histamine_or_mcas_trigger", "allium_intolerance"]
HAS_ALLICIN = MECH[[c for c in ALLICIN_SYS if c in MECH.columns]].any(axis=1)
HAS_HIST = MECH[[c for c in HIST_SYS if c in MECH.columns]].any(axis=1)
HAS_CARDIO = (
    MECH["cardiovascular_or_bleeding"]
    if "cardiovascular_or_bleeding" in MECH.columns
    else pd.Series(False, index=MECH.index)
)

JSON_PATH = _REPO / "data" / "full_corpus_2026-07-31" / "records_covidlonghaulers_v2.json"
REDDIT_PATH = _REPO / "reddit_2026-06-13.db"
JSON_GARLIC_RE = re.compile(
    r"\bgarlic\b|\ballicin\b|\bkyolic\b|\ballium sativum\b", re.IGNORECASE
)

PALETTE = {
    "pro": "#2b6cb0",
    "anti": "#c53030",
    "mixed": "#dd6b20",
    "unclear": "#a0aec0",
    "accent": "#2c5282",
    "food": "#c53030",
    "use": "#2b6cb0",
    "cardio": "#319795",
    "other": "#718096",
    "json": "#6b46c1",
    "fts": "#2b6cb0",
}


def show(df, caption=None, percent_cols=(), int_cols=(), float_cols=(), drop_cols=()):
    out = df.copy()
    drop = [c for c in drop_cols if c in out.columns]
    if drop:
        out = out.drop(columns=drop)
    for c in percent_cols:
        if c in out.columns:
            out[c] = out[c].map(lambda x: "—" if pd.isna(x) else f"{100 * x:.1f}%")
    for c in int_cols:
        if c in out.columns:
            out[c] = out[c].map(lambda x: "—" if pd.isna(x) else f"{int(x):,}")
    for c in float_cols:
        if c in out.columns:
            out[c] = out[c].map(lambda x: "—" if pd.isna(x) else f"{float(x):.2f}")
    if "headline" in out.columns:
        out["n ≥ 30"] = out["headline"].map(lambda x: "yes" if bool(x) else "no")
        out = out.drop(columns=["headline"])
    html = out.to_html(index=False, escape=True)
    cap = f"<p style='margin:0 0 6px 0;color:#4a5568;font-size:0.95em'>{caption}</p>" if caption else ""
    display(HTML(cap + html))


def callout(kind, text):
    colors = {
        "caution": ("#c53030", "#fff5f5"),
        "note": ("#2b6cb0", "#ebf8ff"),
        "finding": ("#276749", "#f0fff4"),
    }
    border, bg = colors[kind]
    display(HTML(
        f"<div style='border-left:4px solid {border};background:{bg};"
        f"padding:10px 14px;margin:8px 0'>{text}</div>"
    ))


def wilson_k(k, n):
    est, lo, hi = G.wilson(int(k), int(n))
    return est, lo, hi


def fisher_html(k1, n1, k2, n2, a, b, outcome):
    table = np.array([[k1, n1 - k1], [k2, n2 - k2]], dtype=int)
    or_, p = fisher_exact(table)
    t2 = Table2x2(table)
    lo, hi = t2.oddsratio_confint()
    h = G.cohens_h(k1 / n1, k2 / n2)
    warn = []
    if min(n1, n2) < 15:
        warn.append("unreliable: small_sample")
    elif min(n1, n2) < 20:
        warn.append("caveat: small_sample")
    if max(n1, n2) / max(min(n1, n2), 1) > 4:
        warn.append("caveat: imbalanced_samples")
    if (table < 5).any():
        warn.append("caveat: sparse_cells")
    p_txt = f"p = {p:.3g}" if p >= 1e-4 else f"p = {p:.2e}"
    display(HTML(
        "<p><b>Test.</b> Fisher’s exact on "
        f"{outcome}: {a} {k1}/{n1} ({100*k1/n1:.1f}%) vs {b} {k2}/{n2} "
        f"({100*k2/n2:.1f}%). Odds ratio {or_:.2f} (95% CI {lo:.2f}–{hi:.2f}), "
        f"{p_txt}, Cohen’s h = {h:.2f}."
        + (f" <i>{'; '.join(warn)}</i>." if warn else "")
        + "</p>"
    ))
    return {"or": or_, "or_lo": lo, "or_hi": hi, "p": p, "h": h}


def polarity_counts(mask):
    ids = mask[mask].index
    sub = POL.reindex(ids).fillna(False).astype(bool)
    sub = sub.loc[sub.any(axis=1)]
    out = {"n_group": int(mask.sum()), "n_polarity": int(len(sub))}
    for col in ("pro_use", "anti_use", "mixed", "unclear"):
        out[col] = int(sub[col].sum()) if col in sub.columns else 0
    return out, sub


def fig_show(fig):
    fig.tight_layout()
    display(fig)
    plt.close(fig)


def forest(ax, labels, rates, los, his, ns, color, xlabel):
    y = np.arange(len(labels))[::-1]
    rates, los, his = np.asarray(rates, float), np.asarray(los, float), np.asarray(his, float)
    ax.barh(
        y, rates,
        xerr=np.vstack([np.clip(rates - los, 0, None), np.clip(his - rates, 0, None)]),
        height=0.62, color=color, error_kw={"lw": 0.9, "ecolor": "#2d3748", "capsize": 2},
    )
    ax.set_yticks(y, [f"{lab}   n={n:,}" for lab, n in zip(labels, ns)])
    ax.set_xlabel(xlabel)
    ax.set_xlim(0, min(1.0, max(his) * 1.18 if len(his) else 1))
    return ax
"""


def cells():
    return [
        ("md", r"""**Research Question:** "What does this long-COVID / ME-CFS Reddit community claim garlic *does*, who is speaking (self-use, food-list, hearsay, protocol), and how does allicin / biofilm talk differ from histamine / food-list talk — including what people labelled as self + actual use say they took?"
"""),
        ("md", r"""# Garlic use and folk-medicine belief in the long-COVID / ME-CFS community

**Abstract.** Garlic in this corpus is two (really three) folk systems sharing a word, not one treatment. Among 1,927 accounts with a complete extraction, 650 (33.7%) are labelled as reporting actual use and 355 (18.4%) as putting garlic on a trigger / diet list. Restricting to mutually exclusive camps, 79.6% of food-list accounts with a polarity are anti-use versus 9.1% of actual-use accounts (Fisher’s exact OR 38.8, 95% CI 23.6–63.9, p = 9.1×10⁻⁶⁵, Cohen’s h = 1.59). A first-pass `treatment_outcome` field would have kept the use camp and dropped most of the list camp: 80.0% of the 500 JSON-garlic accounts are labelled actual_use, against 17.5% of the 1,427 FTS-only accounts. This notebook is a share of extractable reports at the **reporter** level (a Reddit account). It is not efficacy, incidence, or dose-response. Main recommendation: read the speech act before reading the plant.
"""),
        ("md", r"""## What every number is — and is not

A **share of extractable reports**, with its denominator on the figure. “Reporter” means a Reddit account, not a verified person. Mixed-act accounts are expected: someone who posts a histamine list and also reports taking an allicin capsule counts in both cuts.

| Not this | Why |
|---|---|
| Efficacy or a causal effect | Self-selected posters; no control; no exposure ascertainment |
| Incidence or prevalence | The denominator is people whose *text* yielded an extractable claim |
| Dose-response | Out of scope (DESIGN §8). Amounts are not commensurable across cloves and milligrams |
| “Garlic worsened long COVID” | A food list is not personal avoidance and not a negative outcome |
| A count of people who quit garlic | Personal avoidance is a rare, provisionally labelled third category |

`not_stated` is silence. Only `explicit_none` is a denial. Timestamps date the source windows; they are not a treatment timeline.

**Terms.** *Allicin* is the sulfur compound formed when garlic is crushed or wait-activated. *MCAS* is mast cell activation syndrome, often discussed here as histamine intolerance. *Herx* (Jarisch–Herxheimer-like “die-off”) is a claimed flare during antimicrobial protocols, not a verified diagnosis.
"""),
        ("md", r"""> **Caution (GATE 4).** A blind labelling pass on 80 windows agreed with the model on only **5 of 12** rows where either party assigned `food_list`, `avoidance`, or `culinary`. Human adjudication was deferred; GATE 4 was marked complete by decision. Every figure that leans on those three values is **provisional**. Personal-avoidance n = 109 is reported as a count, without contrast tests.
"""),
        ("md", r"""## 1. Who is in the cohort, and when they wrote

The cohort is every non-bot Reddit account in `reddit_2026-06-13.db` whose text matches `garlic OR allicin OR kyolic` — not the first-pass JSON garlic field. That choice is the study. `patientpunk.db` / `treatment_reports` has zero garlic rows and is not used.
"""),
        ("code", r"""
vol = pd.DataFrame([
    {"item": "Cohort members (FTS, non-bot)", "value": f"{N_MEMBERS:,}"},
    {"item": "Accounts with ≥1 complete unit", "value": f"{N_REP:,}"},
    {"item": "Units complete / failed / planned",
     "value": f"{int((F.units.status=='complete').sum()):,} / "
              f"{int((F.units.status=='failed').sum()):,} / {len(F.units):,}"},
    {"item": "Source windows (paragraph + neighbor, per-author dedup)",
     "value": f"{int(F.units.windows.sum()):,}"},
    {"item": "Claims (included / excluded)",
     "value": f"{len(F.claims):,} ({int(F.claims.included.sum()):,} / "
              f"{int((~F.claims.included.astype(bool)).sum()):,})"},
    {"item": "Included-claim accounts",
     "value": f"{F.claims.loc[F.claims.included, 'reporter'].nunique():,}"},
    {"item": "Self + actual-use accounts (use-payload denominator)",
     "value": f"{N_USE:,}"},
    {"item": "Pinned run", "value": G.RUN_ID[:16] + "…"},
    {"item": "Source snapshot", "value": G.SOURCE_SNAPSHOT},
])
show(vol, "Extraction volume for run c05891b6… . Excluded claims stay as the inspectable denominator (culinary, planned-only, other-person use).")

# Window timestamps from the Reddit snapshot — aggregates only, no source ids kept.
year_counts = None
date_lo = date_hi = None
sub_rows = None
if REDDIT_PATH.is_file():
    rcon = sqlite3.connect(f"file:{REDDIT_PATH}?mode=ro", uri=True)
    wins = pd.DataFrame(
        conn.execute(
            "SELECT source_type, source_id FROM source_window WHERE run_id = ?",
            (G.RUN_ID,),
        ).fetchall(),
        columns=["source_type", "source_id"],
    )
    def _year_sub(table, ids):
        years, subs = {}, {}
        ids = [str(x) for x in ids]
        for i in range(0, len(ids), 800):
            chunk = ids[i:i + 800]
            qin = ",".join("?" * len(chunk))
            for y, n in rcon.execute(
                f"SELECT strftime('%Y', created_utc, 'unixepoch'), COUNT(*) "
                f"FROM {table} WHERE id IN ({qin}) GROUP BY 1", chunk,
            ):
                years[y] = years.get(y, 0) + n
            for s, n in rcon.execute(
                f"SELECT subreddit, COUNT(*) FROM {table} WHERE id IN ({qin}) GROUP BY 1",
                chunk,
            ):
                subs[s] = subs.get(s, 0) + n
        mm = rcon.execute(
            f"SELECT MIN(created_utc), MAX(created_utc) FROM {table} "
            f"WHERE id IN ({','.join('?'*len(ids))})", ids,
        ).fetchone() if len(ids) <= 900 else (None, None)
        return years, subs, mm
    # comments/posts in chunks already; extrema separately
    yp, sp, _ = _year_sub("posts", wins.loc[wins.source_type == "post", "source_id"])
    yc, sc, _ = _year_sub("comments", wins.loc[wins.source_type == "comment", "source_id"])
    years = sorted(set(yp) | set(yc))
    year_counts = pd.DataFrame({
        "year": [int(y) for y in years],
        "windows": [yp.get(y, 0) + yc.get(y, 0) for y in years],
    })
    mn, mx = 10**18, 0
    for table, mask in (("posts", wins.source_type == "post"),
                        ("comments", wins.source_type == "comment")):
        ids = [str(x) for x in wins.loc[mask, "source_id"]]
        for i in range(0, len(ids), 800):
            chunk = ids[i:i + 800]
            row = rcon.execute(
                f"SELECT MIN(created_utc), MAX(created_utc) FROM {table} "
                f"WHERE id IN ({','.join('?'*len(chunk))})", chunk,
            ).fetchone()
            if row[0] is not None:
                mn, mx = min(mn, row[0]), max(mx, row[1])
    date_lo = datetime.fromtimestamp(mn, timezone.utc).date().isoformat()
    date_hi = datetime.fromtimestamp(mx, timezone.utc).date().isoformat()
    months = (mx - mn) / (30.44 * 86400)
    subs = {}
    for d in (sp, sc):
        for k, v in d.items():
            subs[k] = subs.get(k, 0) + v
    sub_rows = pd.DataFrame(
        [{"subreddit": k, "windows": v} for k, v in sorted(subs.items(), key=lambda x: -x[1])]
    ).head(6)
    rcon.close()
    n_post2021 = int(year_counts.loc[year_counts.year >= 2021, "windows"].sum())
    n_all = int(year_counts.windows.sum())
    n_windows = int(len(wins))
    n_unmatched = n_windows - n_all
    display(HTML(
        f"<p><b>Data covers:</b> {date_lo} to {date_hi} "
        f"({months:.0f} months of source timestamps). "
        f"{n_post2021:,} / {n_all:,} ({100*n_post2021/n_all:.0f}%) of windows that joined "
        f"the Reddit snapshot by source id are 2021–2026. "
        f"{n_unmatched:,} of {n_windows:,} probe windows did not join "
        f"(deleted or id-mismatched rows) and are excluded from the date line. "
        f"Chronology of illness or of dosing is not inferred from these dates.</p>"
    ))

if year_counts is not None:
    fig, ax = plt.subplots(figsize=(9.2, 4.2))
    ax.plot(year_counts.year, year_counts.windows, color=PALETTE["accent"], lw=2.2, marker="o", ms=5)
    ax.fill_between(year_counts.year, year_counts.windows, color=PALETTE["accent"], alpha=0.12)
    ax.set_xlabel("Year of source post or comment")
    ax.set_ylabel("Matched garlic windows")
    ax.set_title("Garlic talk is a 2021–2026 phenomenon; the pre-2020 ME-CFS tail is tiny")
    fig_show(fig)

if sub_rows is not None:
    show(sub_rows, "Subreddits contributing the most garlic windows (posts + comments). The community-defining condition is long COVID / ME-CFS; it is the reason the corpus exists, not a co-occurrence.", int_cols=("windows",))
"""),
        ("md", r"""**What this means:** The extraction is sized like a beliefs study, not like a 500-person supplement cohort. Six units failed after retries (long packed windows) and one cohort member produced no complete unit. Food-list and culinary windows are in-scope, not waste. Almost all of the talk is post-COVID-wave; a 2014–2019 ME-CFS tail exists and is small.
"""),
        ("md", r"""## 2. Baseline: who is saying what

Headline units are reporter-level presence of a speech act. An account may sit in more than one bar. Claim-level `actual_use` (1,412 / 3,723) is the wrong denominator — one account is not an independent observation, and 33 units carry 10 or more claims.
"""),
        ("code", r"""
speech = G.rate_table(ACTS, denominator=N_REP, priors=G.PRIORS["speech_act"])
speech_show = speech.copy()
speech_show["share"] = speech_show["rate"]
speech_show["95% CI"] = [
    f"{100*lo:.1f}–{100*hi:.1f}%" for lo, hi in zip(speech_show.ci_lo, speech_show.ci_hi)
]
speech_show["regex prior (authors)"] = speech_show["regex prior"]
disp = speech_show.rename(columns={"value": "speech act", "reporters": "accounts"})[
    ["speech act", "accounts", "denominator", "share", "95% CI", "headline", "regex prior (authors)"]
]
show(disp, "Reporter-level presence among 1,927 accounts with a complete unit. n ≥ 30 is the DESIGN §8 headline floor. Regex priors are keyword floors on the same 1,928 FTS authors, not labels.",
     percent_cols=("share",), int_cols=("accounts", "denominator", "regex prior (authors)"))

fig, ax = plt.subplots(figsize=(9.2, 5.6))
head = speech[speech.headline]
forest(
    ax, head["value"].tolist(), head["rate"].tolist(),
    head["ci_lo"].tolist(), head["ci_hi"].tolist(), head["reporters"].tolist(),
    PALETTE["accent"],
    "Share of accounts with ≥1 complete unit (Wilson 95% CI)",
)
ax.set_title("Actual-use is the largest labelled act; food-list is common (n ≥ 30 shown)")
fig_show(fig)

n_acts = ACTS.sum(axis=1)
mix = pd.DataFrame({
    "distinct speech acts on the account": n_acts.value_counts().sort_index().index.astype(int),
    "accounts": n_acts.value_counts().sort_index().values,
})
show(mix.head(20), "Most accounts do one labelled thing. A minority occupy more than one folk system.", int_cols=("accounts",))

overlap = pd.DataFrame([
    {"pair": "food_list ∩ actual_use", "accounts": int(BOTH_FL_AU.sum())},
    {"pair": "food_list ∩ avoidance", "accounts": int((ACTS.food_list & ACTS.avoidance).sum())},
    {"pair": "actual_use ∩ avoidance", "accounts": int((ACTS.actual_use & ACTS.avoidance).sum())},
    {"pair": "food_list ∩ culinary", "accounts": int((ACTS.food_list & ACTS.culinary).sum())},
    {"pair": "actual_use ∩ recommendation", "accounts": int((ACTS.actual_use & ACTS.recommendation).sum())},
    {"pair": "actual_use ∩ mechanism_belief", "accounts": int((ACTS.actual_use & ACTS.mechanism_belief).sum())},
])
show(overlap, "Overlapping speech acts are a finding, not a coding error (DESIGN §8). 43 accounts are in both the food-list bar and the actual-use bar.", int_cols=("accounts",))
"""),
        ("md", r"""**Plain-language verdict.** About one in three garlic-mentioning accounts is labelled as reporting that they took it. About one in five is labelled as naming it on a list. Personal avoidance is 109 / 1,927 (5.7%, Wilson 4.7–6.8%) — above the 10–37 regex band, below the old 302 overcount, and **provisional** because GATE 4 did not clear the three-way block. Culinary (408) overshoots its 201-author keyword floor; food-list (355) undershoots 536. Some list-shaped posts may be landing in `culinary`. `warning` (n = 15) is below the headline floor.

The 43 accounts in both food-list and actual-use are the people who live in both folk systems. They are not noise.
"""),
        ("md", r"""## 3. The hypothesis: two folk systems, not “avoidance versus use”

DESIGN §1 asked whether allicin-for-biofilm talk differs from histamine / food-list talk. Personal “I quit garlic” is a third category, reported as a count. The comparison below uses **mutually exclusive** camps — food-list without actual-use versus actual-use without food-list — so neither group is a subset of the other. Polarity is scored among accounts that have at least one belief-payload polarity.
"""),
        ("code", r"""
fl_c, fl_sub = polarity_counts(ONLY_FL)
au_c, au_sub = polarity_counts(ONLY_AU)
both_c, _ = polarity_counts(BOTH_FL_AU)

camp = pd.DataFrame([
    {"camp": "food_list only", **fl_c},
    {"camp": "actual_use only", **au_c},
    {"camp": "both speech acts", **both_c},
])
camp["anti_use share"] = camp["anti_use"] / camp["n_polarity"]
camp["pro_use share"] = camp["pro_use"] / camp["n_polarity"]
show(camp, "Polarity among exclusive camps (and the 43-account overlap). Shares use n_polarity as the denominator. An account may be both pro_use and anti_use if two events disagree. Personal avoidance (109 accounts) is a count only — GATE 4; it is not in this table.",
     percent_cols=("anti_use share", "pro_use share"),
     int_cols=("n_group", "n_polarity", "pro_use", "anti_use", "mixed", "unclear"))

# Grouped bars with Wilson error bars — exclusive food_list vs exclusive actual_use.
rows = []
for name, sub in (("food_list only", fl_sub), ("actual_use only", au_sub)):
    n = len(sub)
    for lab, col in (("anti-use", "anti_use"), ("pro-use", "pro_use")):
        k = int(sub[col].sum()) if col in sub.columns else 0
        est, lo, hi = wilson_k(k, n)
        rows.append({"camp": name, "polarity": lab, "k": k, "n": n, "rate": est, "lo": lo, "hi": hi})
g = pd.DataFrame(rows)

fig, ax = plt.subplots(figsize=(9.2, 4.6))
camps = ["food_list only", "actual_use only"]
x = np.arange(len(camps))
width = 0.36
for i, (lab, color) in enumerate((("anti-use", PALETTE["anti"]), ("pro-use", PALETTE["pro"]))):
    sub = g[g.polarity == lab].set_index("camp").loc[camps]
    xpos = x + (i - 0.5) * width
    ax.bar(xpos, sub.rate, width, color=color, label=lab,
           yerr=np.vstack([sub.rate - sub.lo, sub.hi - sub.rate]),
           capsize=3, error_kw={"lw": 0.9, "ecolor": "#2d3748"})
ax.set_xticks(x, [f"{c}\n(n_polarity = {int(g[g.camp==c].n.iloc[0])})" for c in camps])
ax.set_ylabel("Share of polarity-bearing accounts in the camp (Wilson 95% CI)")
ax.set_ylim(0, 1.05)
ax.legend(title="Belief polarity", bbox_to_anchor=(1.02, 1), loc="upper left", frameon=False)
ax.set_title("Food-list speech is anti-use; actual-use speech is pro-use")
fig_show(fig)

_ = fisher_html(
    fl_c["anti_use"], fl_c["n_polarity"],
    au_c["anti_use"], au_c["n_polarity"],
    "food_list only", "actual_use only", "any anti_use polarity",
)
_ = fisher_html(
    fl_c["pro_use"], fl_c["n_polarity"],
    au_c["pro_use"], au_c["n_polarity"],
    "food_list only", "actual_use only", "any pro_use polarity",
)

n_multi_pol = int((POL.sum(axis=1) > 1).sum())
display(HTML(
    f"<p>Intra-reporter polarity disagreement: <b>{n_multi_pol} / {N_BELIEF}</b> "
    f"({100*n_multi_pol/N_BELIEF:.1f}%) of polarity-bearing accounts carry more than one polarity. "
    f"That disagreement is counted, not averaged away.</p>"
))
"""),
        ("md", r"""**Plain-language verdict.** The two systems are not a mild lean. In the food-list-only camp, four in five polarity-bearing accounts are anti-use (144/181). In the actual-use-only camp, nine in ten are pro-use. The odds ratio is large (OR 38.8 for anti-use) and the effect size is huge by the usual Cohen’s h bands (h = 1.59). This is a difference in *what kind of speech garlic is*, not a difference in how well a capsule worked.

Avoidance (109 accounts) is reported, not tested: GATE 4 (b) is 5/12 on the three-way block that includes this label.
"""),
        ("md", r"""Exclusive food-list accounts with any mechanism (n = 79) versus exclusive actual-use accounts with any mechanism (n = 259) should load different closed-vocab mechanisms if the two-system story is right. Eight mechanisms were scanned; p-values below are Benjamini–Hochberg FDR-adjusted across those eight.
"""),
        ("code", r"""
fl_ids = ONLY_FL[ONLY_FL].index
au_ids = ONLY_AU[ONLY_AU].index
fl_m = MECH.reindex(fl_ids).fillna(False).astype(bool)
au_m = MECH.reindex(au_ids).fillna(False).astype(bool)
fl_m = fl_m.loc[fl_m.any(axis=1)]
au_m = au_m.loc[au_m.any(axis=1)]

mech_rows = []
heat = []
for m in G.MECHANISMS:
    ak = int(fl_m[m].sum()) if m in fl_m.columns else 0
    bk = int(au_m[m].sum()) if m in au_m.columns else 0
    table = np.array([[ak, len(fl_m) - ak], [bk, len(au_m) - bk]], dtype=int)
    or_, p = fisher_exact(table)
    h = G.cohens_h(ak / len(fl_m), bk / len(au_m))
    mech_rows.append({
        "mechanism": m,
        "food_list only": ak, "food_list n": len(fl_m),
        "actual_use only": bk, "actual_use n": len(au_m),
        "rate_fl": ak / len(fl_m), "rate_au": bk / len(au_m),
        "OR": or_, "p": p, "Cohen h": h,
    })
    heat.append([ak / len(fl_m), bk / len(au_m)])
mdf = pd.DataFrame(mech_rows)
mdf["q (BH-FDR)"] = multipletests(mdf["p"], method="fdr_bh")[1]
mdf["survives FDR"] = mdf["q (BH-FDR)"] < 0.05
mdf_disp = mdf.copy()
mdf_disp["p"] = mdf_disp["p"].map(lambda x: f"{x:.2e}" if x < 1e-4 else f"{x:.3g}")
mdf_disp["q (BH-FDR)"] = mdf_disp["q (BH-FDR)"].map(lambda x: f"{x:.2e}" if x < 1e-4 else f"{x:.3g}")
mdf_disp["Cohen h"] = mdf_disp["Cohen h"].map(lambda x: "—" if pd.isna(x) else f"{x:.2f}")
mdf_disp["OR"] = mdf_disp["OR"].map(lambda x: "—" if not np.isfinite(x) else f"{x:.2f}")
show(mdf_disp.drop(columns=["food_list n", "actual_use n", "survives FDR"]),
     "Mechanism presence among exclusive-camp accounts that have ≥1 mechanism. Hypothesis-generating scan of 8 mechanisms; q is BH-FDR across those 8.",
     percent_cols=("rate_fl", "rate_au"))

fig, ax = plt.subplots(figsize=(7.2, 5.8))
mat = np.array(heat)
im = ax.imshow(mat, cmap="RdBu_r", vmin=0, vmax=float(mat.max()), aspect="auto")
ax.set_xticks([0, 1], ["food_list only\n(n = 79 with a mechanism)", "actual_use only\n(n = 259 with a mechanism)"])
ax.set_yticks(range(len(G.MECHANISMS)), list(G.MECHANISMS))
for i in range(mat.shape[0]):
    for j in range(mat.shape[1]):
        ax.text(j, i, f"{100*mat[i, j]:.0f}%", ha="center", va="center",
                color="white" if mat[i, j] > 0.28 else "#1a202c", fontsize=9)
cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
cbar.set_label("Share of mechanism-bearing accounts in the camp")
ax.set_title("Histamine / allium load on lists; antimicrobial and circulation load on use")
fig.subplots_adjust(left=0.34, right=0.86, top=0.90, bottom=0.16)
display(fig)
plt.close(fig)

callout("note", "<b>Null that matters.</b> <code>gut_or_biofilm</code> does <i>not</i> distinguish the camps (14% vs 15%, Fisher p = 1.0, q = 1.0). Biofilm talk is not exclusive to the people who report taking garlic. Five mechanisms survive FDR: antimicrobial, cardiovascular/bleeding, allium intolerance, histamine/MCAS, and immune. <code>herx_or_dieoff</code> (q ≈ 0.10) and <code>other</code> do not.")
"""),
        ("md", r"""DESIGN framed two systems (allicin / biofilm versus histamine / food-list). The mechanism table supports a split, but cardiovascular / bleeding language is the second-largest mechanism overall — larger than gut/biofilm — and it sits with the use camp, mostly as pro-use (circulation, blood pressure, blood flow), not as an anticoagulant warning.
"""),
        ("code", r"""
anti_only = HAS_ALLICIN & ~HAS_HIST
hist_only = HAS_HIST & ~HAS_ALLICIN
both_sys = HAS_ALLICIN & HAS_HIST
cardio_only = HAS_CARDIO & ~HAS_ALLICIN & ~HAS_HIST
other_only = ~HAS_ALLICIN & ~HAS_HIST & ~HAS_CARDIO
parts = OrderedDict([
    ("Allicin-family only\n(antimicrobial / gut / immune / herx)", int(anti_only.sum())),
    ("Circulation / bleeding only", int(cardio_only.sum())),
    ("Histamine / allium only", int(hist_only.sum())),
    ("Allicin-family ∩ histamine", int(both_sys.sum())),
    ("Other mechanism only", int(other_only.sum())),
])
assert sum(parts.values()) == len(MECH)

fig, ax = plt.subplots(figsize=(8.6, 4.8))
colors = [PALETTE["use"], PALETTE["cardio"], PALETTE["food"], PALETTE["mixed"], PALETTE["other"]]
wedges, texts, autotexts = ax.pie(
    list(parts.values()),
    labels=None,
    colors=colors,
    autopct=lambda p: f"{p:.0f}%" if p >= 4 else "",
    startangle=90,
    pctdistance=0.72,
    wedgeprops={"width": 0.46, "edgecolor": "white", "linewidth": 1.5},
)
ax.legend(wedges, [f"{k.replace(chr(10), ' ')}  (n={v})" for k, v in parts.items()],
          bbox_to_anchor=(1.02, 0.5), loc="center left", frameon=False)
ax.set_title(f"Mechanism-bearing accounts (n = {len(MECH):,}): a third, circulation, camp")
fig.subplots_adjust(right=0.55)
display(fig)
plt.close(fig)

# Exclusive allicin-family vs exclusive histamine on polarity
a_mask = anti_only.reindex(POL.index).fillna(False).astype(bool)
h_mask = hist_only.reindex(POL.index).fillna(False).astype(bool)
a_sub = POL.loc[a_mask[a_mask].index]
h_sub = POL.loc[h_mask[h_mask].index]
a_sub = a_sub.loc[a_sub.any(axis=1)] if len(a_sub) else a_sub
h_sub = h_sub.loc[h_sub.any(axis=1)] if len(h_sub) else h_sub
_ = fisher_html(
    int(a_sub["pro_use"].sum()) if "pro_use" in a_sub.columns else 0, len(a_sub),
    int(h_sub["pro_use"].sum()) if "pro_use" in h_sub.columns else 0, len(h_sub),
    "allicin-family only", "histamine/allium only", "any pro_use polarity",
)

folk = pd.DataFrame([
    {"system": "allicin-family (any of 4)", "accounts": int(HAS_ALLICIN.sum())},
    {"system": "histamine / allium (any of 2)", "accounts": int(HAS_HIST.sum())},
    {"system": "both of the above", "accounts": int(both_sys.sum())},
    {"system": "cardiovascular / bleeding (any)", "accounts": int(HAS_CARDIO.sum())},
    {"system": "cardiovascular only (no allicin-family, no histamine)", "accounts": int(cardio_only.sum())},
])
show(folk, "Mechanism-system membership among 607 accounts with ≥1 mechanism. Fifteen accounts hold both allicin-family and histamine/allium labels.", int_cols=("accounts",))
"""),
        ("md", r"""**Plain-language verdict.** Allicin-family accounts are pro-use; histamine/allium accounts are anti-use (Cohen’s h ≈ 1.8 on exclusive groups). Only 15 accounts are labelled with both systems. Circulation is not a footnote: 100 mechanism-bearing accounts are circulation-only, comparable to the entire histamine/allium-only camp (90). Herx / die-off is 14 accounts — below the headline floor, coded, not contrasted.
"""),
        ("md", r"""## 4. Among accounts labelled self + actual use

The use payload is allowed only when `speech_act = actual_use` and `subject = self` (640 accounts, 1,401 claims). Stored claims have **zero** use-payload leakage onto food-list, avoidance, or culinary. Preparation mix is a descriptive stack: an account using two forms counts in both. Bins with reporter n < 30 are collapsed.
"""),
        ("code", r"""
prep_rows = []
for p in G.PREPARATIONS:
    k = int(USE.loc[USE.preparation == p, "reporter"].nunique())
    est, lo, hi = wilson_k(k, N_USE)
    prep_rows.append({"preparation": p, "accounts": k, "denominator": N_USE,
                      "share": est, "ci_lo": lo, "ci_hi": hi, "headline": k >= G.MIN_REPORTERS})
prep = pd.DataFrame(prep_rows).sort_values("accounts", ascending=False).reset_index(drop=True)
rare = prep.loc[~prep.headline, "preparation"].tolist()
rare_k = int(USE.loc[USE.preparation.isin(rare), "reporter"].nunique())
est_r, lo_r, hi_r = wilson_k(rare_k, N_USE)

head_prep = prep[prep.headline].copy()
collapsed = pd.concat([
    head_prep,
    pd.DataFrame([{
        "preparation": f"collapsed rare forms (n < 30): {', '.join(rare)}",
        "accounts": rare_k, "denominator": N_USE,
        "share": est_r, "ci_lo": lo_r, "ci_hi": hi_r, "headline": False,
    }]),
], ignore_index=True)
show(collapsed[["preparation", "accounts", "denominator", "share"]].assign(
    **{"95% CI": [f"{100*lo:.1f}–{100*hi:.1f}%" for lo, hi in zip(collapsed.ci_lo, collapsed.ci_hi)]}
), f"Preparation mix among {N_USE:,} self + actual-use accounts. Rare bins are coded but not headlined. Unspecified form is a real majority, not a leftover. <code>cooked_culinary</code> here is still self + actual_use (the author treated cooked garlic as an intervention), not garlic-bread-as-use.",
     percent_cols=("share",), int_cols=("accounts", "denominator"))

fig, ax = plt.subplots(figsize=(9.2, 5.2))
plot = collapsed.copy()
ylabels = []
for p in plot.preparation:
    if p.startswith("collapsed"):
        ylabels.append("rare forms (Kyolic, tea, oil, topical, black garlic)")
    else:
        ylabels.append(p)
forest(
    ax, ylabels,
    plot.share.tolist(), plot.ci_lo.tolist(), plot.ci_hi.tolist(), plot.accounts.tolist(),
    PALETTE["use"],
    f"Share of {N_USE:,} self + actual-use accounts (Wilson 95% CI)",
)
ax.set_title("Half of use-labelled accounts have no coded form; raw clove and allicin supplements clear n = 30")
fig_show(fig)

n_prep = USE.groupby("reporter")["preparation"].nunique()
display(HTML(
    f"<p>Accounts with exactly one coded preparation: <b>{int((n_prep==1).sum()):,}</b> / {N_USE:,}. "
    f"Two or more: <b>{int((n_prep>=2).sum()):,}</b>. Crush-and-wait allicin activation — the protocol "
    f"the biofilm camp describes — is 33 / {N_USE:,} ({100*33/N_USE:.1f}%), just over the headline floor. "
    f"Kyolic / aged extract is 22, below it.</p>"
))
"""),
        ("md", r"""**What this means:** The community’s use talk is not a clean eight-arm trial. The modal “preparation” is that the model could not code one. Among forms that clear n = 30, raw clove is larger than allicin supplements, and the crush-and-wait ritual is an order of magnitude smaller than raw clove. Protocol talk is louder than protocol practice.
"""),
        ("md", r"""Self-attributed effects and adverse events are shares among actual-use accounts. They are not treatment effects. Positive labels in this pipeline are known to be over-called (~10–20% false positives in validation of a related extractor); negative labels are more trustworthy. Silence is the majority for both effects and adverse events.
"""),
        ("code", r"""
# Reporter-level effect rollup among use accounts.
eff = F.effects.copy()
n_eff = int(eff.reporter.nunique())

def roll_dir(s):
    has_h, has_w = (s == "helped").any(), (s == "worsened").any()
    has_m, has_n = (s == "mixed").any(), (s == "no_effect").any()
    if has_h and has_w:
        return "mixed across events"
    if has_m:
        return "mixed"
    if has_h:
        return "helped"
    if has_w:
        return "worsened"
    if has_n:
        return "no_effect"
    return "other"

rep_dir = eff.groupby("reporter")["direction"].apply(roll_dir)
dir_rows = []
for lab in ["helped", "worsened", "no_effect", "mixed across events", "mixed"]:
    k = int((rep_dir == lab).sum())
    est, lo, hi = wilson_k(k, N_USE)
    dir_rows.append({"rolled direction": lab, "accounts": k,
                     "share of use accounts": est, "ci_lo": lo, "ci_hi": hi,
                     "share of effect-bearing accounts": k / n_eff})
show(pd.DataFrame(dir_rows).drop(columns=["ci_lo", "ci_hi"]).assign(
    **{"95% CI (of use accounts)": [f"{100*r['ci_lo']:.1f}–{100*r['ci_hi']:.1f}%" for r in dir_rows]}
),
     f"Effect direction rolled to the account, then scored against two denominators: all {N_USE:,} use accounts, and the {n_eff:,} who have ≥1 extractable effect. 11 accounts are labelled both helped and worsened.",
     percent_cols=("share of use accounts", "share of effect-bearing accounts"),
     int_cols=("accounts",))

sx = (
    eff.groupby("reporter")["symptom_class"]
    .apply(lambda s: set(s.dropna()) - {"not_stated"})
)
sx_counts = {}
for classes in sx:
    for c in classes:
        sx_counts[c] = sx_counts.get(c, 0) + 1
sx_df = pd.DataFrame(
    [{"symptom class": k, "accounts with ≥1 effect in class": v}
     for k, v in sorted(sx_counts.items(), key=lambda x: -x[1])]
).head(10)
show(sx_df, "Multilabel symptom class of free-text effect targets, account-level. Most effect rows have no coded target (`not_stated`).",
     int_cols=("accounts with ≥1 effect in class",))

def roll_ae(s):
    if (s == "reported").any():
        return "reported"
    if (s == "explicit_none").any():
        return "explicit_none"
    return "not_stated"

rep_ae = USE.groupby("reporter")["adverse_event_status"].apply(roll_ae)
ae_order = ["not_stated", "reported", "explicit_none"]
ae_k = [int((rep_ae == lab).sum()) for lab in ae_order]
ae_ci = [wilson_k(k, N_USE) for k in ae_k]

fig, ax = plt.subplots(figsize=(9.2, 2.6))
left = 0.0
cols = {"not_stated": PALETTE["other"], "reported": PALETTE["anti"], "explicit_none": PALETTE["pro"]}
labs = {"not_stated": "not stated (silence)", "reported": "reported", "explicit_none": "explicit none (denial)"}
for lab, k, (est, lo, hi) in zip(ae_order, ae_k, ae_ci):
    ax.barh(0, est, left=left, color=cols[lab], height=0.45, label=f"{labs[lab]}  {k:,} ({100*est:.1f}%)")
    left += est
ax.set_yticks([])
ax.set_xlim(0, 1)
ax.set_xlabel(f"Share of {N_USE:,} self + actual-use accounts (Wilson CIs in the table below)")
ax.legend(bbox_to_anchor=(0.5, 1.02), loc="lower center", ncol=3, frameon=False)
ax.set_title("Adverse-event status is mostly silence, not a clean safety signal")
fig_show(fig)

ae_tbl = pd.DataFrame([
    {"status": lab, "accounts": k, "share": est, "95% CI": f"{100*lo:.1f}–{100*hi:.1f}%"}
    for lab, k, (est, lo, hi) in zip(ae_order, ae_k, ae_ci)
])
show(ae_tbl, "Reporter-level rule: reported if any use-event is reported; else explicit_none if any denial; else not_stated.",
     percent_cols=("share",), int_cols=("accounts",))

ae_cat = (
    F.adverse.groupby("category")["reporter"].nunique()
    .reindex(G.AE_CATEGORIES, fill_value=0)
    .sort_values(ascending=False)
    .reset_index()
)
ae_cat.columns = ["adverse-event category", "accounts"]
ae_cat["share of use accounts"] = ae_cat["accounts"] / N_USE
ae_cat["headline"] = ae_cat["accounts"] >= G.MIN_REPORTERS
show(ae_cat, f"Adverse-event categories at the account level. Denominator for the share column is all {N_USE:,} use-labelled accounts (a reporting share, not incidence). Reporter n ≥ 30: other (43) and GI (38). Odor (21), herx (12), and histamine flare (4) do not clear the floor. Status = reported on {int((rep_ae=='reported').sum()):,} of those {N_USE:,} accounts.",
     percent_cols=("share of use accounts",), int_cols=("accounts",))

callout("caution", "<b>Do not read 16.6% as incidence.</b> 81.4% of use-labelled accounts say nothing about adverse events. Explicit denials are 13 accounts (2.0%). An adverse-event percentage here is a share of extractable reports.")
"""),
        ("md", r"""**Plain-language verdict.** 301 / 640 use-labelled accounts have any extractable effect direction. Rolled to the account and scored against all 640, 226 (35.3%) are helped-only and 34 (5.3%) are worsened-only. That helped share is **not** “garlic works”: it is a label on a sentence, in a pipeline that over-calls positive sentiment, among people who chose to write about garlic. The more trustworthy number is the worsened count, and even that is a reporting share. Two adverse-event categories clear n = 30 at the account level: residual `other` (43) and GI (38). Odor, herx, and histamine flare do not.

Dose-response is not analysed. 193 use-labelled accounts state an amount; 164 of 328 dose rows are whole-garlic (cloves / heads), 35 are a weight family, 31 a count of pills. Those are different substances. DESIGN §8 forbids pooling them.
"""),
        ("md", r"""## 5. Methods check: the first-pass JSON kept the use camp

DESIGN §4.1: 502 JSON patients have garlic in any field; JSON ∩ FTS is 500 / 502; two JSON-only rows have no garlic-family tokens in source (extractor hallucinations — not chased). The probe cohort is the 1,928 FTS authors. If the first pass were the study population, the food-list majority among FTS-only authors would disappear.
"""),
        ("code", r"""
json_tbl = None
if JSON_PATH.is_file():
    recs = json.loads(JSON_PATH.read_text())
    json_garlic = set()
    for rec in recs:
        blob = json.dumps(rec.get("fields", {}), ensure_ascii=False)
        if JSON_GARLIC_RE.search(blob):
            json_garlic.add(rec["record_meta"]["author_hash"])
    members = list(conn.execute(
        "SELECT author_hash FROM cohort_member WHERE run_id = ?", (G.RUN_ID,),
    ))
    hash_to_rep = {}
    for h, in members:
        hash_to_rep.setdefault(h, len(hash_to_rep))
    json_reps = {hash_to_rep[h] for h in json_garlic if h in hash_to_rep}
    json_complete = json_reps & set(COMPLETE)
    fts_only = set(COMPLETE) - json_reps
    # hashes dropped from here on
    del json_garlic, hash_to_rep, members, recs

    acts_json = ACTS.reindex(sorted(json_complete)).fillna(False).astype(bool)
    acts_fts = ACTS.reindex(sorted(fts_only)).fillna(False).astype(bool)
    keys = ["actual_use", "food_list", "culinary", "recommendation"]
    slope = []
    for k in keys:
        k1, n1 = int(acts_json[k].sum()), len(acts_json)
        k2, n2 = int(acts_fts[k].sum()), len(acts_fts)
        e1, lo1, hi1 = wilson_k(k1, n1)
        e2, lo2, hi2 = wilson_k(k2, n2)
        slope.append({
            "speech act": k,
            "JSON garlic (n)": k1, "JSON garlic share": e1, "json_lo": lo1, "json_hi": hi1,
            "FTS-only (n)": k2, "FTS-only share": e2, "fts_lo": lo2, "fts_hi": hi2,
            "JSON n": n1, "FTS n": n2,
        })
    json_tbl = pd.DataFrame(slope)
    show(json_tbl[["speech act", "JSON garlic (n)", "JSON garlic share", "FTS-only (n)", "FTS-only share"]],
         f"Reporter-level speech-act presence in JSON-garlic accounts with a complete unit (n = {len(json_complete):,}) versus FTS-only complete accounts (n = {len(fts_only):,}). GATE 1: JSON ∩ FTS = 500/502; two JSON-only rows are hallucinations and are not in this cohort.",
         percent_cols=("JSON garlic share", "FTS-only share"),
         int_cols=("JSON garlic (n)", "FTS-only (n)"))

    fig, ax = plt.subplots(figsize=(8.8, 5.2))
    y = np.arange(len(keys))[::-1]
    for i, row in json_tbl.iterrows():
        yi = y[i]
        ax.plot([row["JSON garlic share"], row["FTS-only share"]], [yi, yi],
                color="#cbd5e0", lw=2.5, zorder=1)
        ax.errorbar(row["JSON garlic share"], yi, xerr=[[row["JSON garlic share"]-row["json_lo"]],
                                                        [row["json_hi"]-row["JSON garlic share"]]],
                    fmt="o", color=PALETTE["json"], ms=8, capsize=3, label="JSON garlic field" if i == 0 else None)
        ax.errorbar(row["FTS-only share"], yi, xerr=[[row["FTS-only share"]-row["fts_lo"]],
                                                     [row["fts_hi"]-row["FTS-only share"]]],
                    fmt="s", color=PALETTE["fts"], ms=8, capsize=3, label="FTS-only (no JSON garlic field)" if i == 0 else None)
    ax.set_yticks(y, keys)
    ax.set_xlabel("Share of accounts in that slice (Wilson 95% CI)")
    ax.set_xlim(0, 1)
    ax.legend(bbox_to_anchor=(0.5, 1.02), loc="lower center", ncol=2, frameon=False)
    ax.set_title("First-pass garlic fields are a use cohort; FTS-only authors are a list-and-food cohort")
    fig_show(fig)

    j = json_tbl.set_index("speech act")
    for act in keys:
        _ = fisher_html(
            int(j.loc[act, "JSON garlic (n)"]), int(j.loc[act, "JSON n"]),
            int(j.loc[act, "FTS-only (n)"]), int(j.loc[act, "FTS n"]),
            "JSON garlic", "FTS-only", f"{act} presence",
        )
else:
    callout("caution", "JSON records file not found on disk; GATE 1 overlap table is in DESIGN.md and was not recomputed in this kernel.")
"""),
        ("md", r"""**Plain-language verdict.** This is the methods finding the design predicted. Accounts the first pass already tagged as garlic-related are mostly labelled actual-use by the probe (80%). Accounts the first pass did *not* tag, but FTS still retrieved, are mostly culinary and food-list. A study built on `treatment_outcome` would have answered a different question and called it garlic.
"""),
        ("md", r"""## 6. What accounts are saying

Short paraphrases of probe evidence quotes, not verbatim Reddit text. Dates are the year of the cited source window. Distinctive terms (allicin, Kyolic, histamine, cloves) are kept. At least one paraphrase cuts against the two-system story.

**Food-list / histamine (2024).** Garlic named on a histamine-trigger food list, without a personal dose.

**Allicin for gut bacteria (2023).** Author taking a large allicin (garlic) dose twice a day, framed as an antimicrobial for the gut.

**Circulation / raw clove (2024).** Chewing three raw cloves daily, attributed to chest-symptom relief rather than to infection.

**Personal avoidance (2025).** Author reports no longer being able to digest garlic — a personal stop, not a copied list.

**Culinary flare, not a copied list (2023).** Author reports a COVID-like symptom flare after eating garlicky food.

**Cuts against the main split (2022).** A recommendation treats garlic as a *low-histamine* seasoning — the opposite of the trigger-list system.
"""),
        ("code", r"""
quote_pts = pd.DataFrame([
    {"year": 2022, "label": "low-histamine seasoning (cuts against the split)"},
    {"year": 2023, "label": "allicin twice daily for gut bacteria"},
    {"year": 2023, "label": "COVID-like flare after garlicky food"},
    {"year": 2024, "label": "garlic on a histamine-trigger list"},
    {"year": 2024, "label": "three raw cloves, chest-symptom relief"},
    {"year": 2025, "label": "can no longer digest garlic"},
])
fig, ax = plt.subplots(figsize=(9.2, 3.6))
y = np.arange(len(quote_pts))[::-1]
ax.scatter(quote_pts.year, y, s=70, color=PALETTE["accent"], zorder=3)
ax.hlines(y, 2021.8, quote_pts.year, color="#e2e8f0", lw=1.2)
ax.set_yticks(y, quote_pts.label.tolist())
ax.set_xlim(2021.6, 2026.0)
ax.set_xlabel("Year of cited source window")
ax.set_title("Paraphrases span 2022–2025; one of six cuts against the two-system split")
fig_show(fig)
"""),
        ("md", r"""Those six lines are the qualitative check on the tables. Five of them match the camp they were drawn from. The sixth is the reminder that “histamine” in this community does not always point the same way, and that a closed vocabulary will miss intra-community disagreement.
"""),
        ("md", r"""## 7. Counterintuitive findings worth investigating

These are surprises for a clinician or a patient who thinks “garlic on a long-COVID forum means a supplement people try.” They are not pipeline trivia. Mechanism differences that came out of the eight-way scan are labelled with FDR; the others are single planned contrasts or descriptive counts.
"""),
        ("code", r"""
counter = pd.DataFrame([
    {
        "finding": "Circulation is a third folk system, not a bleeding warning",
        "why it surprises": "DESIGN’s two-system frame was allicin/biofilm vs histamine lists. Cardiovascular/bleeding is the 2nd-largest mechanism (152 accounts), 100 of them circulation-only, and polarity is mostly pro-use.",
        "n": 152,
        "status": "hypothesis-generating — size vs design prior of ~70 keyword authors",
    },
    {
        "finding": "Gut/biofilm talk does not belong to the use camp",
        "why it surprises": "The allicin-for-biofilm story predicted biofilm language would travel with dosing. Among mechanism-bearing exclusive camps it is 14% vs 15% (Fisher p = 1.0, q = 1.0).",
        "n": 79 + 259,
        "status": "null that survived the FDR scan",
    },
    {
        "finding": "Crush-and-wait is rare among people labelled as using garlic",
        "why it surprises": "Protocol posts describe crushing raw garlic and waiting for allicin. That preparation is 33/640 (5.2%) of use accounts, vs 168 raw clove and 104 allicin supplements.",
        "n": 33,
        "status": "descriptive; just over the n = 30 headline floor",
    },
    {
        "finding": "Garlic is both a high-histamine trigger and a low-histamine spice",
        "why it surprises": "The food-list system treats garlic as a trigger. At least one recommendation puts it on a low-histamine spice list. Closed-vocab polarity cannot hold both as a single community belief.",
        "n": "qualitative",
        "status": "hypothesis-generating — not a count",
    },
])
show(counter, "Not in this list: mixed-act overlap (already in §2), positive over-call, and quote verbatimness — methods, in limitations.")

# Scatter: mechanism share in exclusive food_list vs exclusive actual_use.
fig, ax = plt.subplots(figsize=(7.6, 6.4))
xs = mdf.rate_fl.to_numpy()
ys = mdf.rate_au.to_numpy()
ax.plot([0, 0.5], [0, 0.5], color="#cbd5e0", ls="--", lw=1, label="equal share")
ax.scatter(xs, ys, s=55, color=PALETTE["accent"], zorder=3)
short = {
    "antimicrobial": "antimicrobial",
    "gut_or_biofilm": "gut / biofilm",
    "immune": "immune",
    "cardiovascular_or_bleeding": "circulation / bleeding",
    "herx_or_dieoff": "herx",
    "histamine_or_mcas_trigger": "histamine / MCAS",
    "allium_intolerance": "allium intolerance",
    "other": "other",
}
offsets = {
    "antimicrobial": (6, 8), "gut_or_biofilm": (8, -12), "immune": (8, 2),
    "cardiovascular_or_bleeding": (6, 8), "herx_or_dieoff": (8, 6),
    "histamine_or_mcas_trigger": (8, -12), "allium_intolerance": (8, 6),
    "other": (8, -8),
}
for name, xi, yi in zip(mdf.mechanism, xs, ys):
    dx, dy = offsets.get(name, (6, 4))
    ax.annotate(short.get(name, name), (xi, yi), textcoords="offset points",
                xytext=(dx, dy), fontsize=8)
ax.set_xlabel("Share of food_list-only accounts with a mechanism")
ax.set_ylabel("Share of actual_use-only accounts with a mechanism")
ax.set_xlim(-0.03, 0.55)
ax.set_ylim(-0.03, 0.55)
ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", frameon=False)
ax.set_title("Off-diagonal: list vs use. On the diagonal: gut/biofilm (the null)")
fig_show(fig)
"""),
        ("md", r"""Personal avoidance is **not** the anti-garlic majority. The modal anti-garlic speech is a list, which is why a first-pass treatment extractor was right not to write those rows as `treatment_outcome` and why this probe exists.
"""),
        ("md", r"""## 8. Sensitivity: does the two-system split move?

The headline contrast is anti-use polarity in exclusive food-list versus exclusive actual-use. Re-run after dropping the four accounts with ≥32 claims (56, 34, 32, 32 — a tie at 32) and after restricting to accounts with exactly one labelled speech act. A preparation analog of “monotherapy”: adverse-event *reporting* among single-preparation raw-clove versus allicin-supplement accounts — a reporting comparison, not a safety trial.
"""),
        ("code", r"""
nclaims = F.claims.groupby("reporter").size()
top_heavy = set(nclaims[nclaims >= 32].index)
n_acts = ACTS.sum(axis=1)
single_act = n_acts == 1

def anti_in(mask, drop=()):
    ids = [i for i in mask[mask].index if i not in drop]
    sub = POL.reindex(ids).fillna(False).astype(bool)
    sub = sub.loc[sub.any(axis=1)]
    k = int(sub["anti_use"].sum()) if "anti_use" in sub.columns else 0
    return k, len(sub)

rows = []
plot_fl, plot_au = [], []
for label, drop, fl_mask, au_mask in [
    ("primary (exclusive camps)", set(), ONLY_FL, ONLY_AU),
    ("drop accounts with ≥32 claims (n = 4)", top_heavy, ONLY_FL, ONLY_AU),
    ("single speech-act accounts only", set(), ONLY_FL & single_act, ONLY_AU & single_act),
]:
    k1, n1 = anti_in(fl_mask, drop)
    k2, n2 = anti_in(au_mask, drop)
    or_, p = fisher_exact([[k1, n1 - k1], [k2, n2 - k2]])
    h = G.cohens_h(k1 / n1, k2 / n2)
    rows.append({
        "cut": label,
        "food_list anti-use": f"{k1}/{n1} ({100*k1/n1:.1f}%)",
        "actual_use anti-use": f"{k2}/{n2} ({100*k2/n2:.1f}%)",
        "OR": or_, "p": p, "Cohen h": h,
    })
    plot_fl.append(wilson_k(k1, n1))
    plot_au.append(wilson_k(k2, n2))
sens = pd.DataFrame(rows)
sens["p"] = sens["p"].map(lambda x: f"{x:.2e}")
sens["OR"] = sens["OR"].map(lambda x: f"{x:.1f}")
show(sens, "Anti-use polarity, exclusive camps. The split does not depend on the four highest-volume accounts or on mixed-act accounts.")

fig, ax = plt.subplots(figsize=(9.2, 4.6))
x = np.arange(3)
width = 0.36
for i, (lab, color, pts) in enumerate((
    ("food_list only", PALETTE["food"], plot_fl),
    ("actual_use only", PALETTE["use"], plot_au),
)):
    rates = np.array([p[0] for p in pts])
    los = np.array([p[1] for p in pts])
    his = np.array([p[2] for p in pts])
    xpos = x + (i - 0.5) * width
    ax.bar(xpos, rates, width, color=color, label=lab,
           yerr=np.vstack([rates - los, his - rates]),
           capsize=3, error_kw={"lw": 0.9, "ecolor": "#2d3748"})
ax.set_xticks(x, ["Primary", "Drop ≥32-claim\naccounts (n = 4)", "Single speech-act\naccounts"])
ax.set_ylabel("Anti-use share among polarity-bearing accounts (Wilson 95% CI)")
ax.set_ylim(0, 1.05)
ax.legend(title="Exclusive camp", bbox_to_anchor=(1.02, 1), loc="upper left", frameon=False)
ax.set_title("The two-system polarity split is stable under both sensitivity cuts")
fig_show(fig)

single_prep = set(USE.groupby("reporter")["preparation"].nunique().loc[lambda s: s == 1].index)
raw = set(USE.loc[USE.preparation == "raw_clove", "reporter"]) & single_prep
alli = set(USE.loc[USE.preparation == "allicin_supplement", "reporter"]) & single_prep
ae_rep = set(USE.loc[USE.adverse_event_status == "reported", "reporter"])
k_raw, k_alli = len(ae_rep & raw), len(ae_rep & alli)
display(HTML(
    f"<p><b>Single-preparation AE reporting</b> (not incidence): raw clove {k_raw}/{len(raw)} "
    f"({100*k_raw/len(raw):.1f}%) vs allicin supplement {k_alli}/{len(alli)} "
    f"({100*k_alli/len(alli):.1f}%).</p>"
))
_ = fisher_html(k_raw, len(raw), k_alli, len(alli),
                "single-prep raw clove", "single-prep allicin supplement",
                "any reported adverse-event status")
callout("note", "<b>Robustness.</b> The polarity split is stable (OR remains &gt; 30, Cohen’s h &gt; 1.5). The raw-clove vs allicin AE comparison is not significant (CIs overlap in spirit: Fisher p ≈ 0.19). We do not have enough data to tell those two forms apart on adverse-event <i>reporting</i>.")
"""),
        ("md", r"""## 9. How to read this community (not how to dose garlic)

Recommendations are about interpretation. A reporting-based NNT analog is not applicable: there is no control arm, and this study is not asking whether garlic works. Tiers follow the skill’s sample-size rules applied to *speech-act and belief* findings.
"""),
        ("code", r"""
recs = pd.DataFrame([
    {"tier": "Strong", "n rule": "n ≥ 30 and p < 0.05",
     "recommendation": "Treat ‘garlic’ as a speech-act problem first. Exclusive food-list vs exclusive actual-use polarity is a large, stable split (anti-use 79.6% vs 9.1%, OR 38.8, h = 1.59).",
     "n": fl_c["n_polarity"] + au_c["n_polarity"]},
    {"tier": "Strong", "n rule": "n ≥ 30 and p < 0.05",
     "recommendation": "Do not build a garlic-use cohort from first-pass treatment_outcome. JSON-garlic accounts are 80% actual_use; FTS-only accounts are 17.5% (OR 19).",
     "n": 500 + 1427},
    {"tier": "Strong", "n rule": "n ≥ 30 and p < 0.05",
     "recommendation": "Among self + actual-use, report unspecified form, raw clove, and allicin supplements as the mix. Collapse Kyolic, tea, oil, topical, black garlic.",
     "n": N_USE},
    {"tier": "Moderate", "n rule": "n ≥ 30, FDR-controlled",
     "recommendation": "Read antimicrobial + circulation as the use camp’s mechanisms, allium/histamine as the list camp’s. Do not assign gut/biofilm to only one camp.",
     "n": 79 + 259},
    {"tier": "Preliminary", "n rule": "provisional label or n < 30",
     "recommendation": "Personal avoidance n = 109 is a count only (GATE 4). Crush-and-wait n = 33 is barely headlined. Herx n = 14, warning n = 15, Kyolic n = 22: coded, not contrasted. AE reporting is mostly silence.",
     "n": 109},
])
show(recs.drop(columns=["n"]), "Patient-facing translation: if you see garlic on this forum, ask whether the writer is listing a trigger, describing a clove or capsule they took, or repeating a protocol. Those are different acts.")

# Lollipop of Cohen's h for the planned contrasts already tested above.
h_rows = [
    ("Anti-use polarity\nfood_list vs actual_use", G.cohens_h(fl_c["anti_use"]/fl_c["n_polarity"], au_c["anti_use"]/au_c["n_polarity"]), "Strong"),
    ("Pro-use polarity\nfood_list vs actual_use", G.cohens_h(fl_c["pro_use"]/fl_c["n_polarity"], au_c["pro_use"]/au_c["n_polarity"]), "Strong"),
]
if json_tbl is not None:
    j = json_tbl.set_index("speech act")
    h_rows.append(("actual_use presence\nJSON garlic vs FTS-only", G.cohens_h(j.loc["actual_use", "JSON garlic share"], j.loc["actual_use", "FTS-only share"]), "Strong"))
    h_rows.append(("food_list presence\nJSON garlic vs FTS-only", G.cohens_h(j.loc["food_list", "JSON garlic share"], j.loc["food_list", "FTS-only share"]), "Strong"))
h_rows.append(("gut/biofilm (null)\nfood_list vs actual_use", G.cohens_h(11/79, 39/259), "Moderate"))
tier_color = {"Strong": "#276749", "Moderate": "#2b6cb0", "Preliminary": "#dd6b20"}
labels, hs, tiers = zip(*h_rows)
y = np.arange(len(labels))[::-1]
fig, ax = plt.subplots(figsize=(9.2, 4.8))
ax.axvline(0, color="#4a5568", lw=0.8)
ax.axvline(0.8, color="#cbd5e0", ls="--", lw=0.8)
ax.axvline(-0.8, color="#cbd5e0", ls="--", lw=0.8)
ax.axvline(0.5, color="#e2e8f0", ls=":", lw=0.8)
ax.axvline(-0.5, color="#e2e8f0", ls=":", lw=0.8)
for yi, h, t in zip(y, hs, tiers):
    ax.plot([0, h], [yi, yi], color=tier_color[t], lw=2)
    ax.scatter([h], [yi], color=tier_color[t], s=60, zorder=3)
ax.set_yticks(y, labels)
ax.set_xlabel("Cohen’s h (positive = first group higher). Dashed |h| = 0.8 large; dotted |h| = 0.5 medium")
handles = [plt.Line2D([0], [0], marker="o", color=c, label=t, lw=2) for t, c in tier_color.items() if t in tiers]
ax.legend(handles=handles, title="Tier", bbox_to_anchor=(1.02, 1), loc="upper left", frameon=False)
ax.set_title("Strong findings are about who is speaking, not about whether garlic works")
fig_show(fig)
"""),
        ("md", r"""## 10. Conclusion

Garlic in this long-COVID / ME-CFS Reddit corpus is a word two (and a half) folk medicines share. One camp talks about allicin, antimicrobials, and — more than the design expected — circulation: they are the people the probe labels as actually using it, and their polarity is pro-use. The other camp puts garlic on a histamine, allium, or elimination list: they are not dosing it in the extractable text, and their polarity is anti-use. Personal “I quit garlic” exists (109 accounts) and is too poorly validated to be the story.

A researcher who starts from first-pass `treatment_outcome` will meet the first camp and can honestly say “these posts look like supplement talk.” They will miss most of the second camp, which is the modal anti-garlic speech. That is why this probe widened inclusion past self + actual use.

A patient reading the forum should not treat a garlic mention as a vote that garlic helps long COVID, nor as evidence that garlic caused their illness. Food-list speech is not an adverse event. Helped-labels on actual-use sentences are a reporting pattern in a pipeline that over-calls positive sentiment. The number that should change someone’s prior is the *split*: list versus use is a different kind of sentence, with a different mechanism vocabulary, and it is large enough that mixing them is the mistake.

What remains open is the label boundary GATE 4 did not clear, the circulation camp that the two-system frame did not budget for, and whether unspecified form (half of use accounts) is recoverable from text the model would not commit on. Dose-response is not among the open questions this database can answer.
"""),
        ("md", r"""## 11. Research limitations

**Selection.** These are people who posted about garlic on long-COVID / ME-CFS subreddits and passed a keyword gate. They are not people with long COVID, and they are not people who use garlic.

**Reporting.** People write about what is salient. Lists, protocols, and dramatic reactions are more writeable than uneventful culinary use. Silence is not absence: 81% of use-labelled accounts have `not_stated` adverse-event status.

**Survivorship.** Accounts that remain active, and posts that remain up, are the ones extracted. Deleted authors were excluded at cohort build. Failed units (6) were long packed windows, so loss is not random with respect to how much someone wrote.

**Recall.** Amounts, preparations, and “how long I took it” are whatever the author remembered and chose to write, often months later. They are not chart-review exposures. Duration is taken only when the author stated it; timestamps date windows and are not a course of treatment.

**Confounding.** Speech act, polarity, and mechanism are labelled from the same window. An account that writes a protocol will tend to get `recommendation` + `pro_use` + `antimicrobial` together because that is how the sentences are built, not because those variables were independently ascertained.

**No control group.** There is no matched set of garlic-silent long-COVID accounts in this notebook, and no untreated arm. Between-camp contrasts are contrasts of speech.

**Sentiment versus efficacy.** `helped` / `worsened` are directions on extracted effect spans. They are not outcome measurements. Positive labels in related PatientPunk extractors are over-called by roughly 10–20%; negative labels are more reliable. Absolute helped-rates are not headlined as benefit.

**Temporal snapshot.** Source windows run 2014-10-20 to 2026-06-10; 94% are 2021–2026. Community recipes change. This is one Reddit snapshot (`reddit_2026-06-13.db`) and one probe run.

**Pipeline-specific.** (1) Positive over-call, above. (2) Group attribution: a stacked “I took X, Y, and garlic and improved” outcome is kept only when the text attributes it to garlic; remaining leakage would inflate use-camp helped-labels. The single-preparation cut is the analog of a monotherapy check and was used for AE reporting, not for polarity. (3) GATE 4 (b) 5/12 on `food_list` / `avoidance` / `culinary` — load-bearing labels are provisional. (4) Stage 5b (temperature 0, 38 units complete in both stores) found 76.5% top-level field-set agreement and 79.4% `speech_act` agreement; `speech_act` still moved on 14/68 paired claims. That is a floor on instability, not a re-elicitation. (5) Quote contract is a short paraphrase with a 0.5 bag-of-words floor; payload quotes are often near-verbatim anyway. This notebook uses paraphrases and is a private-review document until a redaction pass. (6) Emoji-only garlic (8 authors) and bare `allium` (15 comments) are outside FTS recall by design. (7) Six units failed; one member has no complete unit.

A reporting-based NNT analog is omitted on purpose. It would dress a speech-act study up as a treatment effect.
"""),
        ("code", r"""
prov = G.provenance_table(F)
prov.loc[prov.item == "content date range", "value"] = (
    "2014-10-20 to 2026-06-10 (140 months); 94% of matched windows are 2021–2026"
)
prov.loc[prov.item == "inference", "value"] = (
    "Wilson intervals on reporter shares; Fisher exact + Cohen’s h on exclusive-camp "
    "contrasts; BH-FDR on 8 mechanisms; no efficacy tests, no dose-response, no NNT analog"
)
extra = pd.DataFrame([
    {"item": "skill version", "value": "research-assistant v2 (adapted: beliefs/use, not treatment ranking)"},
    {"item": "cohort members", "value": f"{N_MEMBERS:,}"},
    {"item": "complete-unit accounts", "value": f"{N_REP:,}"},
    {"item": "claims / included", "value": f"{len(F.claims):,} / {int(F.claims.included.sum()):,}"},
    {"item": "source windows / characters",
     "value": f"{int(F.units.windows.sum()):,} / {int(F.units.characters.sum()):,}"},
    {"item": "notebook", "value": "studies/garlic/analysis_grok/garlic_beliefs_and_use.ipynb"},
])
show(pd.concat([prov, extra], ignore_index=True), "Provenance for this execution. Database SHA-256 is of the probe store; do not commit that file.")

try:
    agr, ctx = G.repeat_agreement()
    agr_disp = agr.copy()
    agr_disp["rate"] = agr_disp["rate"]
    show(agr_disp, f"Stage 5b temperature-0 repeat (units complete in both stores: {ctx['units complete in both']}; claim pairs: {ctx['claim pairs']}). First-pass JSON prior was 36.5% field-set / 58.8% value agreement.",
         percent_cols=("rate",), int_cols=("n", "of"))
except FileNotFoundError:
    callout("note", "Repeat-pass database not found; Stage 5b agreement is in docs/garlic_probe_run_report.md.")

cost = G.attempt_summary(F)
show(cost.reset_index().rename(columns={"index": "metric"}), "Stage 5 realized cost and attempts for this run_id only. Validation retries are most of the spend. Billing-uncertain attempts are excluded from the dollar total.")
"""),
        ("code", r"""
display(HTML(
    "<p style='font-size:1.2em;font-weight:bold;font-style:italic;margin-top:1.2em'>"
    "These findings reflect reporting patterns in online communities, not population-level "
    "treatment effects. This is not medical advice.</p>"
))
"""),
    ]


def main():
    nb = build_notebook(
        cells=cells(),
        db_path_block=DB_PATH_BLOCK,
        title="Garlic beliefs and use",
    )
    html = execute_and_export(nb, str(OUT), timeout=900, kernel_name="python3")
    print(str(html))


if __name__ == "__main__":
    main()
