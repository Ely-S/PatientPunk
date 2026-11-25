"""All numbers and figures in the blog post. Reads ../data (from extract.py) plus the X API
count files and, for spike-day term lists only, tweet text from tweets.db.

    uv run python twitter_data_news_blog/analysis/analyze.py

Writes ../data/results.json and ../figures/*.svg. No text, usernames or ids are written.
"""
import collections, json, pathlib, re, sqlite3, zlib, datetime as dt
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy import stats
from stats import (START, END, full_index, alpha, alpha_boot, baseline, spikes, spike_share,
                   top_share, rate_ratio_ci)

HERE = pathlib.Path(__file__).resolve().parent
BLOG = HERE.parent
DATA, FIG = BLOG / "data", BLOG / "figures"
TD = BLOG.parent / "twitter_data"
COV = TD / "coverage_test_2026-11"
RNG = np.random.default_rng(7)

TW_C, RD_C, INK, MUTED, GRID = "#2563a8", "#d0632a", "#1f2328", "#6b7280", "#e5e7eb"
plt.rcParams.update({
    "svg.fonttype": "none", "font.family": "sans-serif",
    "font.sans-serif": ["Inter", "Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK, "axes.titlesize": 11,
    "axes.titleweight": "bold", "axes.titlelocation": "left", "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.axisbelow": True, "legend.frameon": False, "figure.dpi": 100,
})
R = {}   # everything the post quotes


def save(fig, name):
    plt.rcParams["svg.hashsalt"] = name
    fig.savefig(FIG / f"{name}.svg", bbox_inches="tight", transparent=True)
    import os
    if os.environ.get("PREVIEW_DIR"):
        fig.savefig(pathlib.Path(os.environ["PREVIEW_DIR"]) / f"{name}.png", bbox_inches="tight", dpi=110)
    plt.close(fig)


def months(s):
    return s.index.to_period("M").astype(str).values


# ---------------------------------------------------------------- load
daily = pd.read_csv(DATA / "daily_counts.csv", parse_dates=["date"])
tot = pd.read_csv(DATA / "reddit_totals.csv", parse_dates=["date"]).set_index("date")
RTOT = full_index(tot.posts)


def series(drug, plat, col="authors"):
    m = (daily.drug == drug) & (daily.platform == plat)
    return full_index(daily[m].set_index("date")[col])


def census(path):
    rows = json.load(open(path))
    rows = rows["by_day"] if isinstance(rows, dict) else rows
    return pd.Series({pd.Timestamp(r["start"][:10]): r["tweet_count"] for r in rows})


CEN = {
    "narrow": census(COV / "run_ldn_20261113T231941Z/counts_full_span/by_day.json"),
    "wide": census(COV / "run_ldn_counts_wide_20261117T233925Z/counts_wide.json"),
    "synonyms": census(COV / "run_ldn_counts_synonyms_20261118T014148Z/counts_synonyms.json"),
}
CEN_Q = {
    "narrow": json.load(open(COV / "run_ldn_20261113T231941Z/manifest.json"))["queries"]["drug_plus_co"],
    "wide": json.load(open(COV / "run_ldn_counts_wide_20261117T233925Z/counts_wide.json"))["query"],
    "synonyms": json.load(open(COV / "run_ldn_counts_synonyms_20261118T014148Z/counts_synonyms.json"))["query"],
}
for k in CEN:
    CEN[k] = full_index(CEN[k])
pd.DataFrame(CEN).rename_axis("date").to_csv(DATA / "x_census_ldn_daily.csv")


R["window"] = [START, END]
R["sizes"] = {
    "reddit_posts_total": int(RTOT.sum()),
    "ldn_census_total": int(CEN["narrow"].sum()),
    "ldn_corpus_posts": int(series("LDN", "twitter", "posts").sum()),
    "ldn_reddit_posts": int(series("LDN", "reddit", "posts").sum()),
    "ldn_reddit_authordays": int(series("LDN", "reddit").sum()),
}

# ---------------------------------------------------------------- 1. LDN: census vs Reddit
cen = CEN["narrow"]; rd_a = series("LDN", "reddit"); rd_p = series("LDN", "reddit", "posts")
f_c, b_c = spikes(cen); f_r, b_r = spikes(rd_a)

con = sqlite3.connect(TD / "databases/tweets.db")
LDN_RE = re.compile(r"\bldn\b|naltrex\w*|naltexone|naltraxone")
IVM_RE = re.compile(r"ivermectin\w*|stromectol|ivomec|horse paste|horse dewormer")
STOP = set("the and for with that this have has been are was were but not you your from about they them their "
           "can just what when will would more some than all who its it's also into out our one any amp how "
           "his her had did does don't i'm i've get got very only now new long covid low dose naltrexone ldn "
           "people like being there here which may could after over".split())


ALL_TW = [(dt.datetime.fromtimestamp(ts, dt.UTC).date(), uid, (t or "").lower())
          for ts, uid, t in con.execute("select post_date, user_id, body_text from posts")]


def tweets_matching(rx, with_author=False):
    return [(d, u, t) if with_author else (d, t) for d, u, t in ALL_TW if rx.search(t)]


def norm_text(t):
    return " ".join(re.sub(r"https?://\S+", " ", t).split())


def tokens(t):
    t = re.sub(r"https?://\S+|@\w+|#", " ", t)
    return set(re.findall(r"[a-z][a-z\-']{2,}", t)) - STOP


def distinctive(rows, days, k=6):
    """Words over-represented on the given days relative to all of the drug's tweets
    (log ratio of document frequencies, word must appear in >=15% of that day's tweets)."""
    allc = collections.Counter(); [allc.update(tokens(t)) for _, t in rows]
    day = [t for d, t in rows if d in days]
    dc = collections.Counter(); [dc.update(tokens(t)) for t in day]
    sc = {w: np.log((dc[w] + .5) / len(day)) - np.log((allc[w] + .5) / len(rows))
          for w in dc if dc[w] >= max(4, .15 * len(day))}
    return sorted(sc, key=lambda w: -sc[w])[:k], len(day)


ldn_rows = tweets_matching(LDN_RE)

# placebo distribution: every 3-day window's ratio to its own baseline
def window_ratio(y, b, start, n=3):
    w = slice(start, start + pd.Timedelta(days=n - 1))
    return y[w].sum() / b[w].sum()


def all_window_ratios(y, b, n=3):
    yy = y.rolling(n).sum().shift(-(n - 1)); bb = b.rolling(n).sum().shift(-(n - 1))
    return (yy / bb).dropna()


placebo_c = all_window_ratios(cen, b_c); placebo_r = all_window_ratios(rd_a, b_r)

# events = census spike days clustered within 7 days, ranked by excess posts
ex = (cen - b_c).where(f_c, 0)
events, used = [], set()
for d0 in ex.sort_values(ascending=False).index:
    if ex[d0] <= 0 or len(events) >= 8:
        break
    if any(abs((d0 - u).days) <= 7 for u in used):
        continue
    used.add(d0)
    # start the 3-day window at the first spike day of the cluster
    clus = [d for d in f_c[f_c].index if abs((d - d0).days) <= 3]
    s0 = min(clus)
    terms, ntw = distinctive(ldn_rows, {(s0 + pd.Timedelta(days=i)).date() for i in range(3)})
    tw_ratio = window_ratio(cen, b_c, s0); rd_ratio = window_ratio(rd_a, b_r, s0)
    rp_ratio = window_ratio(rd_p, baseline(rd_p), s0)
    events.append({
        "start": str(s0.date()), "peak": str(d0.date()), "peak_posts": int(cen[d0]),
        "peak_baseline": float(b_c[d0]), "peak_ratio": float(cen[d0] / b_c[d0]),
        "x_3d": int(cen[s0:s0 + pd.Timedelta(days=2)].sum()), "x_3d_ratio": float(tw_ratio),
        "x_3d_pct": float((placebo_c < tw_ratio).mean() * 100),
        "reddit_3d_authors": int(rd_a[s0:s0 + pd.Timedelta(days=2)].sum()),
        "reddit_3d_ratio": float(rd_ratio), "reddit_posts_3d_ratio": float(rp_ratio),
        "reddit_3d_pct": float((placebo_r < rd_ratio).mean() * 100),
        "terms": terms, "corpus_tweets": ntw,
    })
R["ldn_events"] = events

# Monthly view of the readme's Reuters claim, done properly: Oct 2022 vs Jul-Sep 2022
def month_ratio(y, m, base_months):
    n1 = y[m].sum(); n0 = sum(y[b].sum() for b in base_months)
    t1 = len(y[m]); t0 = sum(len(y[b]) for b in base_months)
    return rate_ratio_ci(n1, t1, n0, t0)

bm = ["2022-07", "2022-08", "2022-09"]
R["reuters_month"] = {
    "x_census": month_ratio(cen, "2022-10", bm), "x_corpus_posts": month_ratio(series("LDN", "twitter", "posts"), "2022-10", bm),
    "reddit_posts": month_ratio(rd_p, "2022-10", bm), "reddit_authors": month_ratio(rd_a, "2022-10", bm),
    "reddit_all_activity": month_ratio(RTOT, "2022-10", bm),
}

# The Reuters weeks: each week from publication day against the mean of the 4 weeks before.
# A centred baseline (as in the events table) absorbs a lasting level change; this does not.
REUTERS = pd.Timestamp("2022-10-18")
rdb = sqlite3.connect(f"file:{TD / 'databases/clh_ldn_twmatch.db'}?mode=ro&immutable=1", uri=True)
rrep = pd.read_sql("select p.post_date ts, r.user_id from treatment_reports r join posts p using(post_id) where r.run_id = 2", rdb)
rrep["date"] = pd.to_datetime(rrep.ts, unit="s").dt.normalize()
RD_REPORTS = full_index(rrep.groupby("date").size())
RD_REPORTERS = full_index(rrep.groupby("date").user_id.nunique())
ldn_auth_rows = tweets_matching(LDN_RE, with_author=True)
X_TEXTS = full_index(pd.Series(collections.Counter(pd.Timestamp(d) for d, _ in {(d, norm_text(t)) for d, _, t in ldn_auth_rows})))
lp = pd.read_csv(DATA / "twitter_ldn_posts.csv", parse_dates=["date"])
X_REPORTS = full_index(lp[lp.report.fillna("") != ""].groupby("date").size())


def weeks_around(y, d0, before=4, after=3):
    w = [float(y[d0 + pd.Timedelta(days=7 * i): d0 + pd.Timedelta(days=7 * i + 6)].sum()) for i in range(-before, after)]
    pre = np.mean(w[:before])
    return {"pre_week": pre, "weeks": w[before:], "lift": [x / pre for x in w[before:]]}


R["reuters_weeks"] = {k: weeks_around(y, REUTERS) for k, y in [
    ("x_census", cen), ("x_corpus_posts", series("LDN", "twitter", "posts")), ("x_corpus_authors", series("LDN", "twitter")),
    ("x_corpus_texts", X_TEXTS), ("x_reports", X_REPORTS), ("reddit_authors", rd_a), ("reddit_posts", rd_p),
    ("reddit_reports", RD_REPORTS), ("reddit_reporters", RD_REPORTERS), ("reddit_all_activity", RTOT)]}
R["reuters_weeks"]["census_day0"] = int(cen[REUTERS])
R["reuters_weeks"]["census_week_before"] = int(cen[REUTERS - pd.Timedelta(days=7):REUTERS - pd.Timedelta(days=1)].sum())
mon = lambda y: y["2022-04":"2023-03"].resample("MS").mean()
R["reuters_monthly_per_day"] = {"months": [str(m.date())[:7] for m in mon(cen).index], "x_census": mon(cen).round(2).tolist(),
                                "reddit_authors": mon(rd_a).round(2).tolist(), "reddit_reports": mon(RD_REPORTS).round(2).tolist()}
# identical text from many accounts on Reuters day (syndicated news accounts)
day0 = [(u, norm_text(t)) for d, u, t in ldn_auth_rows if d == REUTERS.date()]
top_text, n_top = collections.Counter(t for _, t in day0).most_common(1)[0]
R["reuters_syndication"] = {"day_posts": len(day0), "largest_identical_cluster": n_top,
                            "cluster_authors": len({u for u, t in day0 if t == top_text}),
                            "day_distinct_texts": len({t for _, t in day0})}

# Figure 1: LDN daily, X census vs Reddit
fig, axes = plt.subplots(2, 1, figsize=(9, 5.2), sharex=True, gridspec_kw={"hspace": .25})
for ax, y, b, c, lab in [(axes[0], cen, b_c, TW_C, "X/Twitter: posts naming LDN + long COVID (full X archive count)"),
                         (axes[1], rd_a, b_r, RD_C, "r/covidlonghaulers: people mentioning LDN that day")]:
    ax.fill_between(y.index, y.values, step="mid", color=c, alpha=.35, lw=0)
    ax.plot(y.index, y.values, drawstyle="steps-mid", color=c, lw=.6)
    ax.plot(b.index, b.values, color=INK, lw=.9, label="local baseline (28-day median)")
    ax.set_title(lab, fontsize=10.5)
    ax.set_ylim(0, y.max() * 1.18)
axes[0].legend(loc="upper left", fontsize=9)
for e, name, dx in [(events[1], "Reuters feature", -10), (events[0], "Griffith Univ. research (ABC)", 10)]:
    d0 = pd.Timestamp(e["peak"]); ha = "right" if dx < 0 else "left"
    axes[0].annotate(f"{name}, {d0:%-d %b %Y}\n{e['peak_posts']} posts, {e['peak_ratio']:.0f}× baseline", (d0, cen[d0]),
                     xytext=(dx, 0), textcoords="offset points", ha=ha, va="top", fontsize=8.5, color=INK)
    v = rd_a[d0 - pd.Timedelta(days=3):d0 + pd.Timedelta(days=3)].max()
    axes[1].annotate(f"same 3 days: {e['reddit_3d_ratio']:.1f}× baseline", (d0, v), xytext=(0, 8), textcoords="offset points",
                     ha="center", fontsize=8.5, color=INK, arrowprops=dict(arrowstyle="-", color=MUTED, lw=.6),
                     bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=.85))
axes[1].xaxis.set_major_locator(mdates.YearLocator()); axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
axes[1].set_xlim(pd.Timestamp(START), pd.Timestamp(END))
save(fig, "fig1_ldn_timeline")

# Figure 2: the two biggest events, ratio to baseline, +/- 21 days
fig, axes = plt.subplots(1, 2, figsize=(9, 3.2), sharey=True)
for ax, e, name in zip(axes, sorted(events[:2], key=lambda e: e["peak"]), ["Reuters feature", "Griffith University research coverage"]):
    d0 = pd.Timestamp(e["start"]); w = pd.date_range(d0 - pd.Timedelta(days=21), d0 + pd.Timedelta(days=28))
    pre = slice(d0 - pd.Timedelta(days=35), d0 - pd.Timedelta(days=8))
    lags = (w - d0).days
    ax.plot(lags, cen[w] / cen[pre].mean(), color=TW_C, lw=1.8, label="X/Twitter (census)")
    ax.plot(lags, rd_a[w] / rd_a[pre].mean(), color=RD_C, lw=1.8, label="Reddit (people/day)")
    ax.axhline(1, color=MUTED, lw=.8, ls="--"); ax.axvline(0, color=MUTED, lw=.6)
    ax.set_title(f"{name}, {d0:%-d %b %Y}", fontsize=10)
    ax.set_xlabel("days from first spike day")
axes[0].set_ylabel("× the 4 weeks before"); axes[0].legend(fontsize=9)
save(fig, "fig2_ldn_events")

# ---------------------------------------------------------------- 1c. dated releases, chosen by date not by volume
DATED = [("FDA social post", "Ivermectin", "2021-08-21"), ("TOGETHER results", "Ivermectin", "2022-03-30"),
         ("Reuters feature", "LDN", "2022-10-18"), ("ACTIV-6 results", "Ivermectin", "2022-10-21"),
         ("VA prevention study", "Paxlovid", "2022-11-06"), ("NIH RECOVER launch", "Paxlovid", "2023-07-31"),
         ("Griffith trial (ABC)", "LDN", "2024-05-06"), ("STOP-PASC results", "Paxlovid", "2024-06-07"),
         ("PAX LC results", "Paxlovid", "2025-04-03")]


def week_lifts(y):
    """For every start day: the 7-day count over the mean of the 4 weeks before, and the
    mean of weeks 2-4 over the same baseline."""
    w = y.rolling(7).sum()
    pre = sum(w.shift(7 * k) for k in range(1, 5)) / 4
    return (w / pre).shift(-6), (sum(w.shift(-7 * k) for k in range(1, 4)) / 3 / pre).shift(-6)


R["dated_events"] = []
for name, drug, day in DATED:
    d0, row = pd.Timestamp(day), {"name": name, "drug": drug, "date": day}
    for plat, col in [("twitter", "authors"), ("reddit", "authors"), ("twitter", "posts")]:
        wk1, later = week_lifts(series(drug, plat, col))
        row[f"{plat}_{col}"] = {"wk1": float(wk1[d0]), "pct": float((wk1.dropna() < wk1[d0]).mean() * 100),
                                "wks2to4": float(later[d0])}
    R["dated_events"].append(row)

fig, ax = plt.subplots(figsize=(7.2, 3.6))
yy = np.arange(len(DATED))[::-1]
for y0, e in zip(yy, R["dated_events"]):
    a, b = e["twitter_authors"]["wk1"], e["reddit_authors"]["wk1"]
    ax.plot([min(a, b), max(a, b)], [y0, y0], color=GRID, lw=2.2, zorder=1)
    ax.plot(b, y0, "o", color=RD_C, ms=6, label="Reddit" if y0 == yy[0] else None)
    ax.plot(a, y0, "o", color=TW_C, ms=6, label="X/Twitter" if y0 == yy[0] else None)
ax.set_yticks(yy); ax.set_yticklabels([f"{e['name']} ({e['drug']}, {pd.Timestamp(e['date']):%b %Y})" for e in R["dated_events"]], fontsize=8.5)
ax.set_xscale("log"); ax.set_xticks([0.5, 1, 2, 5, 10]); ax.set_xticklabels(["0.5×", "1×", "2×", "5×", "10×"]); ax.minorticks_off()
ax.axvline(1, color=MUTED, ls="--", lw=.8); ax.grid(axis="y", visible=False)
ax.set_xlabel("account-days in the first week, × the 4 weeks before"); ax.legend(loc="upper right", fontsize=9)
save(fig, "fig_dated_events")

# What filled the two busiest weeks per drug. Cue phrases were chosen after reading the peaks.
PEAK_CUES = {
    ("LDN", "2022-10-17"): {"“Reuters” or its headline": r"\breuters\b|addiction[ -]drug[ -]shows[ -]promise"},
    ("LDN", "2024-05-06"): {"“Griffith”": r"\bgriffith\b"},
    ("Ivermectin", "2024-05-06"): {"“Cuomo”": r"\bcuomo\b"},
    ("Ivermectin", "2021-05-31"): {"the opening “another study on ivermectin”": r"\banother study on ivermectin\b"},
    ("Paxlovid", "2022-11-07"): {"“VA study”": r"\bva study\b", "“risk of long COVID”": r"\brisk of long[ -]?covid\b"},
    ("Paxlovid", "2022-04-18"): {"the Reuters headline “the case for testing”": r"\bthe case for testing\b"},
}
R["peak_audit"] = []
for drug, rx in [("LDN", LDN_RE), ("Ivermectin", IVM_RE), ("Paxlovid", re.compile(r"paxlovid|nirmatrelvir"))]:
    rows_d = [(pd.Timestamp(d), u, t) for d, u, t in ALL_TW if rx.search(t)]
    wk = pd.Series(collections.Counter(d - pd.Timedelta(days=d.weekday()) for d, _, _ in rows_d)).sort_index()
    wk = wk[(wk.index >= START) & (wk.index <= END)]
    for w0 in wk.sort_values(ascending=False, kind="stable").index[:2]:
        g = [(u, t) for d, u, t in rows_d if w0 <= d < w0 + pd.Timedelta(days=7)]
        cues = {lab: sum(bool(re.search(p, t)) for _, t in g) for lab, p in PEAK_CUES.get((drug, str(w0.date())), {}).items()}
        R["peak_audit"].append({"drug": drug, "week": str(w0.date()), "posts": len(g), "authors": len({u for u, _ in g}),
                                "max_one_author": max(collections.Counter(u for u, _ in g).values()), "cues": cues})

# ---------------------------------------------------------------- 2. cross-drug volatility
drugs = sorted(daily.drug.unique())
rows = []
for drug in drugs:
    r = {"drug": drug}
    for plat in ["twitter", "reddit"]:
        for col in ["authors", "posts", "threads"]:
            if plat == "twitter" and col == "threads":
                continue
            s = series(drug, plat, col)
            r[f"{plat}_{col}_n"] = int(s.sum())
            r[f"{plat}_{col}_alpha"] = alpha(s.values, None, months(s))
            r[f"{plat}_{col}_spike_share"], r[f"{plat}_{col}_spike_days"] = spike_share(s)
            r[f"{plat}_{col}_top1"] = top_share(s)
    s = series(drug, "reddit")
    r["reddit_authors_sov_alpha"] = alpha(s.values, RTOT.values, months(s))
    rows.append(r)
X = pd.DataFrame(rows).set_index("drug")
keep = (X.twitter_posts_n >= 300) & (X.reddit_posts_n >= 300)
R["excluded_small"] = list(X.index[~keep])
X = X[keep].copy()

# bootstrap CIs on the primary unit (distinct authors per day)
for plat in ["twitter", "reddit"]:
    lo, hi = [], []
    for drug in X.index:
        _, l, h, _ = alpha_boot(series(drug, plat), n=1000, seed=zlib.crc32(f'{drug}|{plat}'.encode()))
        lo.append(l); hi.append(h)
    X[f"{plat}_authors_alpha_lo"] = lo; X[f"{plat}_authors_alpha_hi"] = hi
X.round(4).to_csv(DATA / "cross_drug.csv")


def paired(a, b, floor=0.005):
    la, lb = np.log(np.clip(a, floor, None)), np.log(np.clip(b, floor, None))
    d = la - lb
    w = stats.wilcoxon(d)
    bs = [np.median(RNG.choice(d, len(d))) for _ in range(5000)]
    return {"n": int(len(d)), "twitter_higher": int((d > 0).sum()),
            "median_ratio": float(np.exp(np.median(d))),
            "median_ratio_ci": [float(np.exp(np.percentile(bs, 2.5))), float(np.exp(np.percentile(bs, 97.5)))],
            "wilcoxon_p": float(w.pvalue),
            "sign_p": float(stats.binomtest(int((d > 0).sum()), len(d)).pvalue)}


R["cross_drug"] = {
    "authors": paired(X.twitter_authors_alpha, X.reddit_authors_alpha),
    "posts": paired(X.twitter_posts_alpha, X.reddit_posts_alpha),
    "tw_posts_vs_rd_threads": paired(X.twitter_posts_alpha, X.reddit_threads_alpha),
    "authors_sov": paired(X.twitter_authors_alpha, X.reddit_authors_sov_alpha),
    "spike_share_authors": paired(X.twitter_authors_spike_share, X.reddit_authors_spike_share, floor=0.001),
    "cv_ratio_authors": float(np.sqrt(paired(X.twitter_authors_alpha, X.reddit_authors_alpha)["median_ratio"])),
    "median_alpha": {k: float(X[k].median()) for k in ["twitter_authors_alpha", "reddit_authors_alpha",
                                                         "twitter_posts_alpha", "reddit_posts_alpha", "reddit_threads_alpha"]},
    "median_spike_share": {k: float(X[k].median()) for k in ["twitter_authors_spike_share", "reddit_authors_spike_share"]},
}
R["table_drugs"] = X[["twitter_authors_n", "reddit_authors_n", "twitter_authors_alpha", "twitter_authors_alpha_lo",
                      "twitter_authors_alpha_hi", "reddit_authors_alpha", "reddit_authors_alpha_lo",
                      "reddit_authors_alpha_hi", "twitter_authors_spike_share", "reddit_authors_spike_share",
                      "twitter_posts_alpha", "reddit_posts_alpha", "reddit_threads_alpha"]].round(4).reset_index().to_dict("records")

# Figure 3: scatter of latent CV (sqrt alpha), Twitter vs Reddit
fig, ax = plt.subplots(figsize=(6.4, 6.0))
cv = lambda a: np.sqrt(np.clip(a, 0.0025, None))
tx, ty = cv(X.twitter_authors_alpha), cv(X.reddit_authors_alpha)
ax.errorbar(ty, tx, xerr=[ty - cv(X.reddit_authors_alpha_lo), cv(X.reddit_authors_alpha_hi) - ty],
            yerr=[tx - cv(X.twitter_authors_alpha_lo), cv(X.twitter_authors_alpha_hi) - tx],
            fmt="o", ms=5, color=TW_C, ecolor="#9db7d8", elinewidth=.8, capsize=0)
lim = [0.12, 2.2]
ax.plot(lim, lim, color=MUTED, ls="--", lw=.9); ax.text(1.5, 1.32, "equal volatility", color=MUTED, fontsize=8.5, rotation=45)
ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlim(lim); ax.set_ylim(lim)
ticks = [0.1, 0.2, 0.5, 1, 2]
ax.set_xticks(ticks); ax.set_yticks(ticks); ax.set_xticklabels(ticks); ax.set_yticklabels(ticks)
ax.minorticks_off()
OFF = {"HBOT": (-6, 2, "right"), "Metformin": (5, 2, "left"), "Interferon": (5, 2, "left"), "Hydroxychloroquine": (5, -4, "left"),
       "Paxlovid": (0, 6, "center"), "Maraviroc": (5, 0, "left"), "IVIG": (5, 0, "left"), "LDN": (-6, 0, "right"),
       "Fluvoxamine": (-6, -9, "right"), "Statins": (-6, 0, "right"), "Lumbrokinase": (5, 0, "left"),
       "Ivermectin": (5, -6, "left"), "Omega-3": (-6, -8, "right"), "Vitamin D": (5, -1, "left"), "CoQ10": (5, -3, "left"),
       "Melatonin": (5, -9, "left"), "Vitamin C": (-6, 0, "right"), "H1 antihistamines": (-6, 0, "right"),
       "Famotidine": (5, 0, "left"), "Nattokinase": (-6, -6, "right"), "Aspirin": (5, -2, "left"),
       "Quercetin": (-6, -2, "right"), "Serrapeptase": (5, -4, "left"), "Zinc": (5, -2, "left")}
for d in X.index:
    ox, oy, ha = OFF.get(d, (4, 2, "left"))
    ax.annotate(d, (ty[d], tx[d]), xytext=(ox, oy), textcoords="offset points", fontsize=7.5, color=INK, ha=ha)
ax.set_xlabel("Reddit: day-to-day volatility of attention (√α)")
ax.set_ylabel("X/Twitter: day-to-day volatility of attention (√α)")
save(fig, "fig3_cross_drug")

# Figure 4: spike share dumbbell
Xs = X.sort_values("twitter_authors_spike_share")
fig, ax = plt.subplots(figsize=(6.4, 6.4))
yy = np.arange(len(Xs))
ax.hlines(yy, Xs.reddit_authors_spike_share * 100, Xs.twitter_authors_spike_share * 100, color=GRID, lw=2.2)
ax.plot(Xs.reddit_authors_spike_share * 100, yy, "o", color=RD_C, label="Reddit", ms=6)
ax.plot(Xs.twitter_authors_spike_share * 100, yy, "o", color=TW_C, label="X/Twitter", ms=6)
ax.set_yticks(yy); ax.set_yticklabels(Xs.index, fontsize=8.5); ax.grid(axis="y", visible=False)
ax.set_xlabel("% of all author-days that are excess on spike days")
ax.legend(loc="lower right")
save(fig, "fig4_spike_share")

# ---------------------------------------------------------------- 3. event-locked averages
def pick_events(y, min_excess=4, sep=14):
    f, b = spikes(y)
    e = (y - b).where(f, 0)
    out = []
    for d0 in e.sort_values(ascending=False).index:
        if e[d0] < min_excess:
            break
        if all(abs((d0 - u).days) > sep for u in out):
            out.append(d0)
    return out


LAGS = np.arange(-7, 15)


def epoch(lock_plat):
    ev = []
    for drug in X.index:
        y_lock = series(drug, lock_plat)
        for d0 in pick_events(y_lock):
            if d0 - pd.Timedelta(days=35) < pd.Timestamp(START) or d0 + pd.Timedelta(days=14) > pd.Timestamp(END):
                continue
            row = {}
            for plat in ["twitter", "reddit"]:
                y = series(drug, plat)
                pre = y[d0 - pd.Timedelta(days=35): d0 - pd.Timedelta(days=8)].mean()
                row[plat] = (np.array([y[d0 + pd.Timedelta(days=int(l))] for l in LAGS]), pre)
            ev.append((drug, d0, row))
    def prof(sub, plat):
        num = np.sum([r[plat][0] for _, _, r in sub], axis=0); den = np.sum([r[plat][1] for _, _, r in sub])
        return num / den
    out = {}
    for plat in ["twitter", "reddit"]:
        est = prof(ev, plat)
        bs = np.array([prof([ev[i] for i in RNG.integers(0, len(ev), len(ev))], plat) for _ in range(2000)])
        out[plat] = {"est": est, "lo": np.percentile(bs, 2.5, axis=0), "hi": np.percentile(bs, 97.5, axis=0)}
    return ev, out


R["epoch"] = {}
fig, axes = plt.subplots(1, 2, figsize=(9, 3.4), sharey=True)
for ax, lock, title in [(axes[0], "twitter", "Locked on X/Twitter spikes"), (axes[1], "reddit", "Locked on Reddit spikes")]:
    ev, out = epoch(lock)
    i0 = list(LAGS).index(0)
    R["epoch"][lock] = {"events": len(ev), "drugs": len({d for d, _, _ in ev}),
                        **{f"{p}_day0": float(out[p]["est"][i0]) for p in out},
                        **{f"{p}_day0_ci": [float(out[p]["lo"][i0]), float(out[p]["hi"][i0])] for p in out},
                        **{f"{p}_days0to2": float(out[p]["est"][i0:i0 + 3].mean()) for p in out},
                        **{f"{p}_days7to14": float(out[p]["est"][i0 + 7:].mean()) for p in out},
                        **{f"{p}_pre": float(out[p]["est"][:i0 - 1].mean()) for p in out}}
    for p, c, lab in [("twitter", TW_C, "X/Twitter"), ("reddit", RD_C, "Reddit")]:
        ax.fill_between(LAGS, out[p]["lo"], out[p]["hi"], color=c, alpha=.18, lw=0)
        ax.plot(LAGS, out[p]["est"], color=c, lw=1.8, marker="o", ms=3, label=lab)
    ax.axhline(1, color=MUTED, lw=.8, ls="--")
    ax.set_title(f"{title} (n = {len(ev)} events)", fontsize=10)
    ax.set_xlabel("days from spike")
axes[0].set_ylabel("people posting, × pre-event level"); axes[0].legend(fontsize=9)
save(fig, "fig5_epoch")

# lead/lag for LDN: correlation of daily surprise, census vs Reddit
def surprise(y, b):
    return np.log((y + 1) / (b + 1))

sc, sr = surprise(cen, b_c), surprise(rd_a, b_r)
R["ldn_xcorr"] = {int(l): float(sc.corr(sr.shift(-l))) for l in range(-5, 6)}

# ---------------------------------------------------------------- 4. who posts during a spike (Twitter)
def composition(posts_csv, spike_days, n_boot=2000, drop=None):
    """Spike-day posts vs posts on ordinary days within 28 days of a spike. Posts on one day are
    not independent (one story, one thread), so intervals come from resampling whole days.
    `drop` is an optional boolean mask over the CSV's rows (e.g. posts flagged as bots)."""
    P = pd.read_csv(posts_csv, parse_dates=["date"])
    if drop is not None:
        P = P[~drop]
    P = P[(P.date >= START) & (P.date <= END)]
    sp = set(spike_days)
    near = set()
    for d in sp:
        near |= {d + pd.Timedelta(days=i) for i in range(-28, 29)}
    P["spike"] = P.date.isin(sp)
    P = P[P.spike | P.date.isin(near)].copy()
    has_rep = P.report.fillna("") != ""
    P["first_time_author"] = P.first_post.astype(float)
    P["report_yield"] = has_rep.astype(float)
    P["positive_among_reports"] = (P.report == "positive").astype(float).where(has_rep)
    P["own_use_among_labelled"] = (P.personal_use == "author").astype(float).where(P.labelled == 1)
    cols = ["first_time_author", "report_yield", "positive_among_reports"] + (["own_use_among_labelled"] if P.labelled.sum() else [])
    days = P.date.unique(); by_day = {d: g for d, g in P.groupby("date")}

    def means(Q):
        g = Q.groupby("spike")[cols]
        return g.mean(), g.count()

    est, n = means(P)
    bs = []
    for _ in range(n_boot):
        Q = pd.concat([by_day[d] for d in RNG.choice(days, len(days))])
        bs.append(means(Q)[0].reindex([False, True]).values)
    bs = np.array(bs)   # boot x [control, spike] x cols
    out = {"posts_spike": int(P.spike.sum()), "posts_control": int((~P.spike).sum()), "spike_days": len(sp)}
    for k, c in enumerate(cols):
        lo, hi = np.nanpercentile(bs[:, :, k], [2.5, 97.5], axis=0)
        dlo, dhi = np.nanpercentile(bs[:, 1, k] - bs[:, 0, k], [2.5, 97.5])
        out[c] = {"control": [float(est.loc[False, c]), float(lo[0]), float(hi[0])],
                  "spike": [float(est.loc[True, c]), float(lo[1]), float(hi[1])],
                  "n": [int(n.loc[True, c]), int(n.loc[False, c])],
                  "diff": float(est.loc[True, c] - est.loc[False, c]), "diff_ci": [float(dlo), float(dhi)]}
    S, C = P[P.spike], P[~P.spike]
    out["likes_median"] = [float(S.likes.median()), float(C.likes.median())]
    out["likes_mean"] = [float(S.likes.mean()), float(C.likes.mean())]
    return out


f_tw_ivm, _ = spikes(series("Ivermectin", "twitter"))
R["composition"] = {
    "ldn": composition(DATA / "twitter_ldn_posts.csv", f_c[f_c].index),
    "ivermectin": composition(DATA / "twitter_ivm_posts.csv", f_tw_ivm[f_tw_ivm].index),
}

# Figure 6: composition forest plot
items = [("first_time_author", "first post about the drug"), ("report_yield", "becomes a treatment report"),
         ("own_use_among_labelled", "describes own use (labelled subset)"), ("positive_among_reports", "positive, among reports")]
fig, axes = plt.subplots(1, 2, figsize=(9, 2.9), sharey=True)
for ax, key, title in [(axes[0], "ldn", "LDN"), (axes[1], "ivermectin", "Ivermectin")]:
    comp = R["composition"][key]
    for i, (k, lab) in enumerate(items):
        if k not in comp:
            ax.text(50, i, "not labelled for this drug", ha="center", va="center", fontsize=8, color=MUTED)
            continue
        for g, c in [("control", MUTED), ("spike", TW_C)]:
            p, lo, hi = comp[k][g]
            y = i + (0.15 if g == "spike" else -0.15)
            ax.plot([lo * 100, hi * 100], [y, y], color=c, lw=2)
            ax.plot(p * 100, y, "o", color=c, ms=5, label=("spike days" if g == "spike" else "nearby normal days") if i == 0 else None)
    ax.set_yticks(range(len(items))); ax.set_yticklabels([l for _, l in items], fontsize=9)
    ax.invert_yaxis(); ax.set_xlim(0, 100); ax.set_xlabel("% of X/Twitter posts")
    ax.set_title(f"{title} (spike n = {comp['posts_spike']:,}, nearby n = {comp['posts_control']:,})", fontsize=10)
    ax.grid(axis="y", visible=False)
fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=2, fontsize=9, bbox_to_anchor=(0.5, -0.17))
save(fig, "fig6_composition")

# ---------------------------------------------------------------- 4b. bots, marketers and copy-paste
# Roles come from dedupe.roles: near-duplicate clusters (MinHash, Jaccard >= 0.6) classified by who
# posted them, plus a commercial-intent word list. "Bots and marketers" = vendor + flood + coordinated.
# Validated against account age (decoded from X user ids) and 220 hand-labelled posts.
import zipfile
import dedupe
from extract import PATS

BOT_ROLES = ["vendor", "flood", "coordinated"]
ROLE_ORDER = ["organic", "headline relay", "other repeat", "bots and marketers"]
AUTHOR_ID = {}
with zipfile.ZipFile(TD / "source_corpus/twitter_dataset.zip") as z:
    for f in z.namelist():
        if f.endswith(".json") and "__MACOSX" not in f:
            AUTHOR_ID.update({t["tweet_id"]: t["author_id"] for t in json.load(z.open(f)).get("tweets", [])})

day_ts = lambda ts: pd.Timestamp(dt.datetime.fromtimestamp(ts, dt.UTC).date())
XP = pd.DataFrame([(pid, uid, day_ts(ts), t or "", json.loads(m or "{}")) for pid, uid, ts, t, m in
                   con.execute("select post_id, user_id, post_date, body_text, metadata from posts")],
                  columns=["pid", "uid", "date", "raw", "meta"])
XP = XP[(XP.date >= START) & (XP.date <= END)].copy()
XP["likes"] = XP.meta.map(lambda m: m.get("metrics", {}).get("like_count", 0))
XP["digit_handle"] = XP.meta.map(lambda m: bool(re.fullmatch(r"[A-Za-z_]+\d{6,}", m.get("author_username", ""))))
XP["created"] = XP.pid.map(lambda p: dedupe.account_created(AUTHOR_ID[p]) if p in AUTHOR_ID else None)
XP["young_account"] = (XP.date - pd.to_datetime(XP.created)).dt.days < 90
XP["key"] = XP.raw.map(dedupe.key)
XP = XP.drop(columns="meta")
XB = dedupe.roles(XP)
XB["group"] = np.where(XB.bot, "bots and marketers", XB.role)

RP = pd.DataFrame([(pid, uid, day_ts(ts), t) for pid, uid, ts, t in
                   ((pid, uid, ts, (ti or "") + " " + (bo or ""))
                    for pid, uid, ts, ti, bo in rdb.execute("select post_id, user_id, post_date, title, body_text from posts"))
                   if any(p.search(t.lower()) for p in PATS.values())], columns=["pid", "uid", "date", "raw"])
RP = RP[(RP.date >= START) & (RP.date <= END)].copy()
RP["key"] = RP.raw.map(dedupe.key)
RB = dedupe.roles(RP)
RB["group"] = np.where(RB.bot, "bots and marketers", RB.role)
XB["low"], RB["low"] = XB.raw.str.lower(), RB.raw.str.lower()


def drug_rows(P, drug):
    return P[P.low.str.contains(PATS[drug])]


# Composition again without bot/marketer posts. The per-post CSVs hold no ids, but their rows follow
# the same query order as extract.py, so the post ids can be rebuilt here.
BOT_PIDS = set(XB.pid[XB.bot])
csv_bot_mask = lambda pat: np.array([pid in BOT_PIDS for pid, t in con.execute("select post_id, body_text from posts order by post_date")
                                     if pat.search((t or "").lower())])
R["composition_no_bots"] = {
    "ldn": composition(DATA / "twitter_ldn_posts.csv", f_c[f_c].index, n_boot=500, drop=csv_bot_mask(PATS["LDN"])),
    "ivermectin": composition(DATA / "twitter_ivm_posts.csv", f_tw_ivm[f_tw_ivm].index, n_boot=500, drop=csv_bot_mask(PATS["Ivermectin"])),
}


def apd(P):
    return full_index(P.groupby("date").uid.nunique())


# Sampling check: require a long COVID term on Reddit too, as every X query did.
LC_RE = r"long[ -]?covid|long[ -]?hauler|\bpasc\b|\blc\b"
RB_LC = RB[RB.low.str.contains(LC_RE)]
lc_alpha = pd.Series({d: (lambda y: alpha(y.values, None, months(y)))(apd(drug_rows(RB_LC, d))) for d in X.index})
R["matched_keyword"] = {"term_regex": LC_RE, "reddit_posts": len(RB_LC),
                        "paired": paired(X.twitter_authors_alpha, lc_alpha)}


def cleaned(P, how):
    keep = {"raw": P.index == P.index, "no_bots": ~P.bot, "relays_collapsed": ~P.later_relay,
            "both": ~P.bot & ~P.later_relay}[how]
    return apd(P[keep])


VARIANTS = ["raw", "no_bots", "relays_collapsed", "both"]
brows = []
for drug in X.index:
    M, MR = drug_rows(XB, drug), drug_rows(RB, drug)
    r = {"drug": drug, "posts": len(M), "reddit_posts": len(MR),
         **{f"x_{g}": float((M.group == g).mean()) for g in ROLE_ORDER},
         **{f"reddit_{g}": float((MR.group == g).mean()) for g in ROLE_ORDER}}
    for v in VARIANTS:
        s, sr = cleaned(M, v), cleaned(MR, v)
        r[f"alpha_{v}"] = alpha(s.values, None, months(s)); r[f"ss_{v}"] = spike_share(s)[0]
        r[f"reddit_alpha_{v}"] = alpha(sr.values, None, months(sr)); r[f"reddit_ss_{v}"] = spike_share(sr)[0]
    brows.append(r)
BX = pd.DataFrame(brows).set_index("drug")

# Does each X spike survive cleaning? Re-run the detector on the cleaned series; a spike survives if
# the cleaned series still has a spike within a day of it.
surv = collections.Counter(); spike_days_by_drug = {}
for drug in X.index:
    M = drug_rows(XB, drug)
    ev = pick_events(series(drug, "twitter")); spike_days_by_drug[drug] = ev
    for v in VARIANTS[1:]:
        f, _ = spikes(cleaned(M, v))
        surv[v] += sum(bool(f[d0 - pd.Timedelta(days=1):d0 + pd.Timedelta(days=1)].any()) for d0 in ev)
n_spikes = sum(len(v) for v in spike_days_by_drug.values())

# Composition of X posts on spike days vs ordinary days within 28 days (drug-post pairs), and Reddit overall
pairs = []
for drug, ev in spike_days_by_drug.items():
    M = drug_rows(XB, drug)[["date", "group", "pid"]].copy()
    sp = set(ev); near = {d + pd.Timedelta(days=i) for d in sp for i in range(-28, 29)} - sp
    M["when"] = np.where(M.date.isin(sp), "spike", np.where(M.date.isin(near), "nearby", None))
    pairs.append(M.dropna(subset=["when"]).assign(drug=drug))
PAIRS = pd.concat(pairs)
REDDIT_PAIRS = pd.concat([drug_rows(RB, d)[["date", "group"]] for d in X.index])


def comp_with_ci(n_boot=2000):
    by_day = {k: g for k, g in PAIRS.groupby(["when", "date"])}
    keys = {w: [k for k in by_day if k[0] == w] for w in ["spike", "nearby"]}
    est = {w: PAIRS[PAIRS.when == w].group.value_counts(normalize=True).reindex(ROLE_ORDER, fill_value=0) for w in keys}
    bs = []
    for _ in range(n_boot):
        sh = {}
        for w, ks in keys.items():
            Q = pd.concat([by_day[ks[i]] for i in RNG.integers(0, len(ks), len(ks))])
            sh[w] = Q.group.value_counts(normalize=True).reindex(ROLE_ORDER, fill_value=0)
        bs.append(sh["spike"] - sh["nearby"])
    bs = pd.DataFrame(bs)
    return {w: est[w].to_dict() for w in est} | {
        "n": {w: int((PAIRS.when == w).sum()) for w in keys},
        "diff_ci": {g: [float(bs[g].quantile(.025)), float(bs[g].quantile(.975))] for g in ROLE_ORDER}}


COMP = comp_with_ci()
COMP["reddit"] = REDDIT_PAIRS.group.value_counts(normalize=True).reindex(ROLE_ORDER, fill_value=0).to_dict()

# Validation 1: hand labels (M marketing, A automated/repetitive, N news share, P personal)
LAB = pd.read_csv(COV / "bot_validation/labels.csv", dtype={"post_id": str}).merge(
    XB[["pid", "role"]], left_on="post_id", right_on="pid")


def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [float((c - h) / d), float((c + h) / d)]


val = {}
for role, ok in [("vendor", "M"), ("flood", "MA"), ("coordinated", "MA"), ("headline relay", "N"), ("organic", "MA")]:
    g = LAB[LAB.role == role]; k = int(g.label.isin(list(ok)).sum())
    val[role] = {"n": len(g), "hits": k, "share": k / len(g), "ci": wilson(k, len(g)), "labels": g.label.value_counts().to_dict()}
fl = LAB[LAB.role.isin(["flood", "coordinated"])]
val["flood_or_coordinated"] = {"n": len(fl), "hits": int(fl.label.isin(["M", "A"]).sum()),
                               "marketing": int((fl.label == "M").sum()), "personal": int((fl.label == "P").sum())}
val["organic_missed_posts_est"] = [x * int((XB.role == "organic").sum()) for x in val["organic"]["ci"]]

# Validation 2: account signals by role (one row per post)
acct = XB.groupby("group").agg(posts=("pid", "size"), accounts=("uid", "nunique"), young=("young_account", "mean"),
                               digit_handle=("digit_handle", "mean"), med_likes=("likes", "median"),
                               likes=("likes", "sum")).reindex(ROLE_ORDER)
acct["share_of_posts"] = acct.posts / len(XB); acct["share_of_likes"] = acct.likes / XB.likes.sum()

# Validation 3: recall of the earlier ivermectin vendor list (tier1) by the word list
T1 = {h["post_id"] for h in json.load(open(COV / "tier1/vendor_regex_hits.json"))}
t1 = XB[XB.pid.isin(T1)]

# Sensitivity: cross-drug paired test under other clustering choices
sens = []
for th in [None, 0.6, 0.8]:
    for few in [1 / 5, 1 / 3, 1 / 2]:
        for mc in [3, 5]:
            S = dedupe.roles(XP, th, few, mc); S["low"] = S.raw.str.lower()
            a = {v: pd.Series({d: (lambda s: alpha(s.values, None, months(s)))(cleaned(drug_rows(S, d), v)) for d in X.index})
                 for v in ["no_bots", "relays_collapsed"]}
            sens.append({"jaccard": th, "few": few, "min_copies": mc, "bot_share": float(S.bot.mean()),
                         "no_bots": paired(a["no_bots"], X.reddit_authors_alpha),
                         "relays_collapsed": paired(a["relays_collapsed"], BX.reddit_alpha_relays_collapsed)})

# Treatment reports by role
rep_all = pd.read_sql("select post_id pid, run_id, sentiment from treatment_reports", con).merge(XB[["pid", "role", "bot"]], on="pid")
bot_reports = {}
for name, runs in [("ldn", [4]), ("ivermectin", [6, 7])]:
    q = rep_all[rep_all.run_id.isin(runs)]
    bot_reports[name] = {"reports": len(q), "from_bots": int(q.bot.sum()), "by_role": q[q.bot].role.value_counts().to_dict(),
                         "positive": float((q.sentiment == "positive").mean()),
                         "positive_bots": float((q[q.bot].sentiment == "positive").mean()) if q.bot.any() else None,
                         "positive_clean": float((q[~q.bot].sentiment == "positive").mean())}

R["bots"] = {
    "x_posts": len(XB), "reddit_drug_posts": len(RB),
    "x_roles": XB.role.value_counts().to_dict(), "reddit_roles": RB.role.value_counts().to_dict(),
    "x_bot_share": float(XB.bot.mean()), "reddit_bot_share": float(RB.bot.mean()),
    "x_relay_share": float((XB.role == "headline relay").mean()), "reddit_relay_share": float((RB.role == "headline relay").mean()),
    "bot_accounts": int(XB[XB.bot].uid.nunique()), "vendor_accounts": int(XB[XB.role == "vendor"].uid.nunique()),
    "relay_clusters": int(XB[XB.role == "headline relay"].cid.nunique()),
    "account_signals": acct.reset_index().to_dict("records"),
    "account_signals_by_role": XB.groupby("role").agg(posts=("pid", "size"), young=("young_account", "mean"),
                                                   digit_handle=("digit_handle", "mean")).reset_index().to_dict("records"),
    "tier1_recall": {"n": len(t1), "caught": int((t1.role == "vendor").sum()), "any_bot": int(t1.bot.sum())},
    "validation": val,
    "paired": {v: paired(BX[f"alpha_{v}"], BX[f"reddit_alpha_{v}"]) for v in VARIANTS}
              | {"no_bots_vs_reddit_raw": paired(BX.alpha_no_bots, X.reddit_authors_alpha),
                 "ss_no_bots": paired(BX.ss_no_bots, BX.reddit_ss_no_bots, floor=0.001),
                 "ss_relays_collapsed": paired(BX.ss_relays_collapsed, BX.reddit_ss_relays_collapsed, floor=0.001)},
    "spike_survival": {"n": n_spikes, **{v: int(surv[v]) for v in VARIANTS[1:]}},
    "composition": COMP,
    "sensitivity": sens,
    "reports": bot_reports,
    "table": BX.round(4).reset_index().to_dict("records"),
}

# Figure 7: what X posts are made of on spike days, nearby days, and on Reddit
GROUP_C = {"organic": "#d1d5db", "headline relay": TW_C, "other repeat": "#9ca3af", "bots and marketers": "#9d174d"}
fig, ax = plt.subplots(figsize=(8, 2.4))
bars = [("X, spike days", COMP["spike"]), ("X, ordinary days nearby", COMP["nearby"]), ("Reddit, all days", COMP["reddit"])]
for i, (lab, sh) in enumerate(bars[::-1]):
    left = 0
    for g in ROLE_ORDER:
        w = sh[g] * 100
        ax.barh(i, w, left=left, color=GROUP_C[g], height=.62, label=g if i == 0 else None)
        if w >= 3:
            ax.text(left + w / 2, i, f"{w:.0f}%", ha="center", va="center", fontsize=8.5,
                    color="white" if g in ("headline relay", "bots and marketers") else INK)
        left += w
ax.set_yticks(range(len(bars))); ax.set_yticklabels([b[0] for b in bars[::-1]], fontsize=9)
ax.set_xlim(0, 100); ax.set_xlabel("% of posts naming one of the 24 drugs"); ax.grid(axis="y", visible=False)
ax.legend(ncol=4, fontsize=8.5, loc="lower center", bbox_to_anchor=(0.45, 1.0))
save(fig, "fig7_bots")

# ---------------------------------------------------------------- 4c. do spikes become steps? who arrives on spike days?
from statsmodels.stats.contingency_tables import StratifiedTable

RTOT_ = RTOT.reindex(full_index(series("LDN", "reddit")).index, fill_value=0)


def sov_lift(y, d0):
    """Reddit people per subreddit post in days 7-56 after d0, over days -56..-8 before."""
    pre = slice(d0 - pd.Timedelta(days=56), d0 - pd.Timedelta(days=8)); post = slice(d0 + pd.Timedelta(days=7), d0 + pd.Timedelta(days=56))
    return float(y[pre].sum()), float(y[post].sum()), float(RTOT_[pre].sum()), float(RTOT_[post].sum())


def step_frame(rows):
    D = pd.DataFrame(rows, columns=["drug", "date", "a0", "a1", "t0", "t1"])
    D["log_lift"] = np.log((D.a1 + .5) / D.t1) - np.log((D.a0 + .5) / D.t0)
    D["step"] = (np.exp(D.log_lift) >= 1.3) & (D.a0 + D.a1 >= 30) & np.array(
        [stats.binomtest(int(a1), int(a0 + a1), t1 / (t0 + t1)).pvalue < .01 if a0 + a1 else False
         for a0, a1, t0, t1 in zip(D.a0, D.a1, D.t0, D.t1)])
    return D


lo_d, hi_d = pd.Timestamp(START) + pd.Timedelta(days=60), pd.Timestamp(END) - pd.Timedelta(days=60)
ev_rows, pl_rows = [], []
for drug in X.index:
    ra = series(drug, "reddit")
    days = [d for d in pick_events(series(drug, "twitter")) if lo_d <= d <= hi_d]
    ev_rows += [(drug, d, *sov_lift(ra, d)) for d in days]
    cand = ra.index[(ra.index >= lo_d) & (ra.index <= hi_d)]
    pl_rows += [(drug, pd.Timestamp(d), *sov_lift(ra, pd.Timestamp(d))) for d in RNG.choice(cand, 40 * len(days))]
SE, SP_ = step_frame(ev_rows), step_frame(pl_rows)


def local_placebo(n=40, window=90):
    """Sensitivity: placebo dates within +/-window days of each spike (same drug, same era).
    Each spike minus the mean of its own placebos; CI resamples calendar quarters."""
    diffs = []
    for drug, d0 in zip(SE.drug, SE.date):
        ra = series(drug, "reddit")
        cand = [d for d in pd.date_range(d0 - pd.Timedelta(days=window), d0 + pd.Timedelta(days=window))
                if lo_d <= d <= hi_d and abs((d - d0).days) > 14]
        pl = step_frame([(drug, pd.Timestamp(d), *sov_lift(ra, pd.Timestamp(d))) for d in RNG.choice(cand, n)])
        diffs.append(float(SE.log_lift[(SE.drug == drug) & (SE.date == d0)].iloc[0] - pl.log_lift.mean()))
    D = pd.DataFrame({"q": SE.date.dt.to_period("Q").astype(str).values, "d": diffs})
    qs = D.q.unique(); by_q = {q: g.d.values for q, g in D.groupby("q")}
    bs = [np.concatenate([by_q[q] for q in RNG.choice(qs, len(qs))]).mean() for _ in range(2000)]
    return {"lift": float(np.exp(D.d.mean())), "ci": [float(np.exp(np.percentile(bs, 2.5))), float(np.exp(np.percentile(bs, 97.5)))]}


bs =[RNG.choice(SE.log_lift.values, len(SE)).mean() - RNG.choice(SP_.log_lift.values, len(SP_)).mean() for _ in range(2000)]
R["spike_to_step"] = {
    "events": len(SE), "step_rate": float(SE.step.mean()), "placebo_step_rate": float(SP_.step.mean()),
    "lift_vs_placebo": float(np.exp(SE.log_lift.mean() - SP_.log_lift.mean())),
    "lift_vs_placebo_ci": [float(np.exp(np.percentile(bs, 2.5))), float(np.exp(np.percentile(bs, 97.5)))],
    "top_steps": SE[SE.step].sort_values("log_lift", ascending=False).head(8).assign(
        lift=lambda d: np.exp(d.log_lift), date=lambda d: d.date.astype(str))[["drug", "date", "lift"]].to_dict("records"),
    "reuters_lift": float(np.exp(step_frame([("LDN", REUTERS, *sov_lift(series("LDN", "reddit"), REUTERS))]).log_lift[0])),
    "local_placebo": local_placebo(),
}

# The Reuters step: newcomers or regulars? Who went on to report LDN use?
LR = drug_rows(RB, "LDN")[["uid", "date"]]
first_ldn = LR.groupby("uid").date.min()
rrep_first = rrep.groupby("user_id").date.min()
sub_first = pd.read_sql("select user_id, min(post_date) ts from posts group by user_id", rdb).set_index("user_id").ts
sub_first = pd.to_datetime(sub_first, unit="s").dt.normalize()
LR = LR.assign(w=(LR.date - REUTERS).dt.days // 7)
LR = LR[(LR.w >= -8) & (LR.w <= 7)]
LR["first_time"] = ((LR.uid.map(first_ldn) - REUTERS).dt.days // 7) == LR.w
wk_tbl = LR.groupby("w").agg(people=("uid", "nunique"))
wk_tbl["first_time"] = LR[LR.first_time].groupby("w").uid.nunique()
wk_tbl = wk_tbl.fillna(0).astype(int); wk_tbl["returning"] = wk_tbl.people - wk_tbl.first_time


def cohort(start, days=21):
    c = first_ldn[(first_ldn >= start) & (first_ldn < start + pd.Timedelta(days=days))]
    fr = rrep_first.reindex(c.index)
    return {"start": str(start.date()), "n": len(c), "reported_within_180d": float(((fr >= c) & (fr <= c + pd.Timedelta(days=180))).mean()),
            "reported_later_day_180d": float(((fr > c) & (fr <= c + pd.Timedelta(days=180))).mean()),
            "reported_before": float((fr < c).mean()),
            "new_to_sub_30d": float((sub_first.reindex(c.index) >= start - pd.Timedelta(days=30)).mean())}


others = pd.DataFrame([cohort(REUTERS + pd.Timedelta(days=21 * k)) for k in range(-12, 13) if k != 0])
pre_w, post_w = wk_tbl.loc[-8:-1], wk_tbl.loc[0:2]
R["reuters_newcomers"] = {
    "weeks": wk_tbl.reset_index().to_dict("records"),
    "first_time_per_week_before": float(pre_w.first_time.mean()), "first_time_per_week_wk1to3": float(post_w.first_time.mean()),
    "returning_per_week_before": float(pre_w.returning.mean()), "returning_per_week_wk1to3": float(post_w.returning.mean()),
    "cohort": cohort(REUTERS), "other_cohorts": {k: [float(others[k].median()), float(others[k].min()), float(others[k].max())]
                                                 for k in ["n", "reported_within_180d", "reported_later_day_180d", "new_to_sub_30d"]},
}

fig, ax = plt.subplots(figsize=(8, 3))
ax.bar(wk_tbl.index, wk_tbl.returning, color="#f2c3a6", label="had mentioned LDN before", width=.8)
ax.bar(wk_tbl.index, wk_tbl.first_time, bottom=wk_tbl.returning, color=RD_C, label="first time mentioning LDN", width=.8)
ax.axvline(-.5, color=INK, lw=.8); ax.text(-.4, wk_tbl.people.max() * 1.02, "Reuters feature", fontsize=8.5, color=INK, va="bottom")
ax.set_xticks(wk_tbl.index); ax.set_xticklabels([str(w + 1) if w >= 0 else str(w) for w in wk_tbl.index], fontsize=8.5)
ax.set_xlabel("week (week 1 starts 18 Oct 2022)"); ax.set_ylabel("people on r/covidlonghaulers"); ax.grid(axis="x", visible=False)
ax.set_ylim(0, wk_tbl.people.max() * 1.15); ax.legend(fontsize=8.5, loc="upper left")
save(fig, "fig_reuters_newcomers")

# Spike tourists: do people whose first post about a drug falls on a spike day come back (days 8-180)?
end_obs = pd.Timestamp(END) - pd.Timedelta(days=180)


def tourists(P_all, plat):
    tabs, rows = [], []
    for drug in X.index:
        g = drug_rows(P_all, drug)[["uid", "date"]]
        f, _ = spikes(series(drug, plat)); sd = set(f[f].index)
        first = g.groupby("uid").date.min()
        lat = g.join(first.rename("d0"), on="uid")
        back = set(lat[(lat.date > lat.d0 + pd.Timedelta(days=7)) & (lat.date <= lat.d0 + pd.Timedelta(days=180))].uid)
        F = first[first <= end_obs].to_frame("d0"); F["spike"] = F.d0.isin(sd); F["back"] = F.index.isin(back)
        a, b = int((F.spike & F.back).sum()), int((F.spike & ~F.back).sum())
        c, d = int((~F.spike & F.back).sum()), int((~F.spike & ~F.back).sum())
        rows.append({"drug": drug, "spike_n": a + b, "spike_back": a / (a + b) if a + b else None, "other_n": c + d, "other_back": c / (c + d)})
        if a + b and c + d:
            tabs.append(np.array([[a, b], [c, d]]) + .5)
    st_ = StratifiedTable(tabs); D = pd.DataFrame(rows)
    return {"newcomers": int(D.spike_n.sum() + D.other_n.sum()), "spike_newcomers": int(D.spike_n.sum()),
            "spike_share_of_newcomers": float(D.spike_n.sum() / (D.spike_n.sum() + D.other_n.sum())),
            "back_spike": float((D.spike_back.fillna(0) * D.spike_n).sum() / D.spike_n.sum()),
            "back_other": float((D.other_back * D.other_n).sum() / D.other_n.sum()),
            "mh_odds_ratio": float(st_.oddsratio_pooled), "mh_ci": [float(x) for x in st_.oddsratio_pooled_confint()],
            "mh_p": float(st_.test_null_odds().pvalue),
            "drugs_lower": int((D.spike_back < D.other_back).sum()), "drugs_with_spike_newcomers": int(D.spike_back.notna().sum()),
            "rows": D.round(4).to_dict("records")}


R["tourists"] = {"x": tourists(XB, "twitter"), "reddit": tourists(RB, "reddit")}

# Long run: each drug's share of its platform's drug talk, 2021 vs 2025
def shares(P_all, year):
    c = pd.Series({d: drug_rows(P_all[P_all.date.dt.year == year], d).uid.nunique() for d in X.index})
    return c / c.sum()


LS = pd.DataFrame({"x_2021": shares(XB, 2021), "x_2025": shares(XB, 2025), "reddit_2021": shares(RB, 2021), "reddit_2025": shares(RB, 2025)})
LS["x_change"], LS["reddit_change"] = LS.x_2025 - LS.x_2021, LS.reddit_2025 - LS.reddit_2021
R["long_run"] = {"same_direction": int((np.sign(LS.x_change) == np.sign(LS.reddit_change)).sum()), "n": len(LS),
                 "change_spearman": stats.spearmanr(LS.x_change, LS.reddit_change)._asdict(),
                 "table": LS.round(4).reset_index(names="drug").to_dict("records")}

# ---------------------------------------------------------------- 5. robustness
R["robust_ldn"] = {}
for k, s in CEN.items():
    sh, nd = spike_share(s)
    R["robust_ldn"][f"x_census_{k}"] = {"query": CEN_Q[k], "n": int(s.sum()), "alpha": alpha(s.values, None, months(s)),
                                         "spike_share": sh, "top1": top_share(s)}
for lab, s, e in [("x_corpus_posts", series("LDN", "twitter", "posts"), None), ("x_corpus_authors", series("LDN", "twitter"), None),
                  ("x_corpus_texts", X_TEXTS, None),
                  ("reddit_posts", rd_p, None), ("reddit_authors", rd_a, None), ("reddit_threads", series("LDN", "reddit", "threads"), None),
                  ("reddit_authors_share_of_voice", rd_a, RTOT)]:
    sh, nd = spike_share(s)
    R["robust_ldn"][lab] = {"n": int(s.sum()), "alpha": alpha(s.values, None if e is None else e.values, months(s)),
                            "spike_share": sh, "top1": top_share(s)}
# weekly aggregation removes day-of-week effects
wk = lambda s: s.resample("W-MON").sum()
for lab, s in [("x_census_weekly", cen), ("reddit_authors_weekly", rd_a)]:
    w = wk(s); q = w.index.to_period("Q").astype(str).values
    R["robust_ldn"][lab] = {"alpha_within_quarter": alpha(w.values, None, q)}
# alpha should not depend on volume: thin Reddit down to Twitter's volume and re-estimate
# Own seed and enough repeats that these numbers don't move when code above draws more randoms.
TRNG = np.random.default_rng(11)
thin = []
for drug in X.index:
    y = series(drug, "reddit").values.astype(int); q = min(1.0, series(drug, "twitter").sum() / y.sum())
    a = [alpha(TRNG.binomial(y, q).astype(float), None, months(series(drug, "reddit"))) for _ in range(400)]
    thin.append((drug, float(X.loc[drug, "reddit_authors_alpha"]), float(np.mean(a)), q))
R["thinning"] = {"rows": thin, "median_abs_change": float(np.median([abs(b - a) for _, a, b, _ in thin])),
                 "paired_after_thinning": paired(X.twitter_authors_alpha, pd.Series({d: b for d, _, b, _ in thin}))}
# spike share is NOT volume-free: a quiet series gets "spikes" from counting noise alone
null = {}
for lam in [0.5, 5.0]:
    null[lam] = float(np.mean([spike_share(pd.Series(TRNG.poisson(lam, 1929).astype(float),
                                                     index=pd.date_range(START, periods=1929)))[0] for _ in range(20)]))
thin_sh = {}
for drug, _, _, q in thin:
    y = series(drug, "reddit")
    thin_sh[drug] = float(np.mean([spike_share(pd.Series(TRNG.binomial(y.values.astype(int), q).astype(float), index=y.index))[0]
                                   for _ in range(100)]))
thin_sh = pd.Series(thin_sh)
R["spike_share_volume"] = {"poisson_null": null, "reddit_thinned_median": float(thin_sh.median()),
                           "paired_after_thinning": paired(X.twitter_authors_spike_share, thin_sh, floor=0.001)}
R["alpha_vs_volume_spearman"] = {
    "twitter": stats.spearmanr(X.twitter_authors_n, X.twitter_authors_alpha)._asdict(),
    "reddit": stats.spearmanr(X.reddit_authors_n, X.reddit_authors_alpha)._asdict()}
R["twitter_reddit_alpha_spearman"] = stats.spearmanr(X.twitter_authors_alpha, X.reddit_authors_alpha)._asdict()
R["corpus_vs_census_monthly_r"] = float(series("LDN", "twitter", "posts").resample("MS").sum().corr(cen.resample("MS").sum()))
R["reddit_all_activity_alpha"] = alpha(RTOT.values, None, months(RTOT))

json.dump(R, open(DATA / "results.json", "w"), indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else float(o))
print(json.dumps({k: R[k] for k in ["cross_drug", "epoch", "ldn_xcorr", "reuters_month", "corpus_vs_census_monthly_r"]}, indent=1, default=str))
