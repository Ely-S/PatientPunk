"""Refresh the generated tables inside post.md, then render post.md to post.html with every
figure inlined as SVG (the HTML is a single self-contained file).

    uv run --with markdown python twitter_data_news_blog/analysis/render.py
"""
import json, pathlib, re
import numpy as np
import markdown

BLOG = pathlib.Path(__file__).resolve().parents[1]
R = json.load(open(BLOG / "data/results.json"))


def sq(a):
    return np.sqrt(max(a, 0))


def ordinal(x):
    n = int(round(x))
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def events_table():
    rows = ["| Spike (UTC) | X posts that day (baseline) | X, 3 days vs baseline | Reddit account-days, same 3 days | Distinctive words in the X posts |",
            "|---|---|---|---|---|"]
    for e in sorted(R["ldn_events"], key=lambda e: -e["x_3d_ratio"]):
        words = ", ".join(e["terms"]) if e["terms"] else "*none: no scraped posts that day*"
        rows.append(f"| {e['peak']} | {e['peak_posts']} ({e['peak_baseline']:.1f}) | **{e['x_3d_ratio']:.1f}×** "
                    f"({ordinal(e['x_3d_pct'])} pct) | {e['reddit_3d_ratio']:.2f}× ({ordinal(e['reddit_3d_pct'])} pct) | {words} |")
    return "\n".join(rows)


def drugs_table():
    rows = ["| Drug | X account-days | Reddit account-days | X volatility √α (95% CI) | Reddit volatility √α (95% CI) | X spike share | Reddit spike share |",
            "|---|---:|---:|---|---|---:|---:|"]
    for r in sorted(R["table_drugs"], key=lambda r: -r["twitter_authors_alpha"]):
        rows.append(
            f"| {r['drug']} | {r['twitter_authors_n']:,} | {r['reddit_authors_n']:,} | "
            f"{sq(r['twitter_authors_alpha']):.2f} ({sq(r['twitter_authors_alpha_lo']):.2f}–{sq(r['twitter_authors_alpha_hi']):.2f}) | "
            f"{sq(r['reddit_authors_alpha']):.2f} ({sq(r['reddit_authors_alpha_lo']):.2f}–{sq(r['reddit_authors_alpha_hi']):.2f}) | "
            f"{r['twitter_authors_spike_share'] * 100:.1f}% | {r['reddit_authors_spike_share'] * 100:.1f}% |")
    return "\n".join(rows)


def robust_table():
    L = R["robust_ldn"]
    spec = [("x_census_narrow", "X archive count, LDN + long COVID terms (primary)"),
            ("x_census_synonyms", "X archive count, expanded LDN synonyms"),
            ("x_census_wide", "X archive count, adds ME/CFS and long-hauler terms"),
            ("x_corpus_posts", "X scraped corpus, posts"),
            ("x_corpus_authors", "X scraped corpus, distinct people per day"),
            ("x_corpus_texts", "X scraped corpus, distinct texts per day"),
            ("reddit_posts", "Reddit, posts and comments"),
            ("reddit_authors", "Reddit, distinct people per day (primary)"),
            ("reddit_authors_share_of_voice", "Reddit, people per day, adjusted for total subreddit activity"),
            ("reddit_threads", "Reddit, distinct threads per day")]
    rows = ["| Series | Units | √α | Spike share | Busiest 1% of days hold |", "|---|---:|---:|---:|---:|"]
    for k, lab in spec:
        v = L[k]
        rows.append(f"| {lab} | {v['n']:,} | {sq(v['alpha']):.2f} | {v['spike_share'] * 100:.1f}% | {v['top1'] * 100:.1f}% |")
    return "\n".join(rows)


def reuters_weeks_table():
    W = R["reuters_weeks"]
    spec = [("x_census", '<span class="tw">X full count</span>, posts'), ("x_corpus_authors", '<span class="tw">X scraped corpus</span>, account-days'),
            ("x_reports", '<span class="tw">X</span>, posts that became treatment reports'),
            ("reddit_authors", '<span class="rd">Reddit</span>, account-days mentioning LDN'),
            ("reddit_reports", '<span class="rd">Reddit</span>, LDN treatment reports'),
            ("reddit_all_activity", '<span class="rd">Reddit</span>, <em>all</em> subreddit activity')]
    rows = ["| Series | Weekly baseline | Week 1 | Week 2 | Week 3 |", "|---|---:|---:|---:|---:|"]
    for k, lab in spec:
        v = W[k]
        cells = " | ".join(f"{n:,.0f} (**{l:.1f}×**)" if i == 0 else f"{n:,.0f} ({l:.1f}×)" for i, (n, l) in enumerate(zip(v["weeks"], v["lift"])))
        rows.append(f"| {lab} | {v['pre_week']:,.1f} | {cells} |")
    return "\n".join(rows)


def dated_table():
    rows = ["| Release | Drug | Date | X account-days, week 1 | Reddit account-days, week 1 | X, weeks 2–4 | Reddit, weeks 2–4 |",
            "|---|---|---|---:|---:|---:|---:|"]
    for e in R["dated_events"]:
        x, r = e["twitter_authors"], e["reddit_authors"]
        rows.append(f"| {e['name']} | {e['drug']} | {e['date']} | **{x['wk1']:.1f}×** ({ordinal(x['pct'])} pct) | "
                    f"{r['wk1']:.1f}× ({ordinal(r['pct'])} pct) | {x['wks2to4']:.1f}× | {r['wks2to4']:.1f}× |")
    return "\n".join(rows)


def peaks_table():
    rows = ["| Drug | Week starting | Posts | Accounts | Most from one account | What was circulating |", "|---|---|---:|---:|---:|---|"]
    for p in R["peak_audit"]:
        cues = "; ".join(f"{n} contain {k}" for k, n in p["cues"].items())
        rows.append(f"| {p['drug']} | {p['week']} | {p['posts']:,} | {p['authors']:,} | {p['max_one_author']} | {cues} |")
    return "\n".join(rows)


def bots_table():
    rows = ["| Drug | X posts | Bots and marketers, X | Headline relays, X | Bots and marketers, Reddit | X √α as measured | X √α, bots removed | X √α, relays collapsed | Reddit √α |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    top = sorted(R["bots"]["table"], key=lambda r: -(r["x_bots and marketers"] + r["x_headline relay"]))[:12]
    for r in top:
        rows.append(f"| {r['drug']} | {r['posts']:,} | {r['x_bots and marketers'] * 100:.1f}% | {r['x_headline relay'] * 100:.1f}% | "
                    f"{r['reddit_bots and marketers'] * 100:.1f}% | {sq(r['alpha_raw']):.2f} | "
                    f"{sq(r['alpha_no_bots']):.2f} | {sq(r['alpha_relays_collapsed']):.2f} | {sq(r['reddit_alpha_raw']):.2f} |")
    return "\n".join(rows)


def bots_validation_table():
    V, A = R["bots"]["validation"], {a["role"]: a for a in R["bots"]["account_signals_by_role"]}
    spec = [("vendor", "Vendor", "selling something"), ("flood", "Flood", "marketing or repetitive campaigning"),
            ("coordinated", "Coordinated", "marketing or repetitive campaigning"), ("headline relay", "Headline relay", "a news or paper share"),
            ("organic", "Organic", "marketing or repetitive campaigning we missed")]
    rows = ["| Role | Posts on X | Labelled | Read as | Share (95% CI) | Handle ends in 6+ digits | Account under 90 days old |",
            "|---|---:|---:|---|---:|---:|---:|"]
    for k, lab, what in spec:
        v, a = V[k], A[k]
        rows.append(f"| {lab} | {a['posts']:,} | {v['n']} | {what} | {v['hits']}/{v['n']} ({v['ci'][0] * 100:.0f}–{v['ci'][1] * 100:.0f}%) | "
                    f"{a['digit_handle'] * 100:.1f}% | {a['young'] * 100:.1f}% |")
    return "\n".join(rows)


TABLES = {"events": events_table, "drugs": drugs_table, "robust": robust_table,
          "reuters_weeks": reuters_weeks_table, "dated": dated_table, "peaks": peaks_table, "bots": bots_table, "bots_validation": bots_validation_table}


def refresh_tables(md):
    def sub(m):
        return f"<!-- table:{m.group(1)} -->\n{TABLES[m.group(1)]()}\n<!-- /table -->"
    return re.sub(r"<!-- table:(\w+) -->.*?<!-- /table -->", sub, md, flags=re.S)


def inline_svg(html):
    def sub(m):
        alt, src = m.group(1), m.group(2)
        svg = (BLOG / src).read_text()
        svg = re.sub(r"<\?xml.*?\?>|<!DOCTYPE.*?>", "", svg, flags=re.S).strip()
        svg = re.sub(r'<svg([^>]*?)\swidth="[^"]*"\sheight="[^"]*"', r'<svg\1', svg, count=1)
        svg = svg.replace("<svg", f'<svg role="img" aria-label="{alt}"', 1)
        return f'<figure class="chart">{svg}</figure>'
    return re.sub(r'<p><img alt="([^"]*)" src="(figures/[^"]+\.svg)" ?/?></p>', sub, html)


CSS = """
:root { --ink:#1f2328; --muted:#5b6370; --rule:#e5e7eb; --bg:#fbfaf7; --card:#ffffff; --tw:#2563a8; --rd:#d0632a; color-scheme: light; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font: 17px/1.65 "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif; }
main { max-width: 760px; margin: 0 auto; padding: 48px 16px 96px; }
h1 { font: 700 2.1rem/1.2 "Inter", "Helvetica Neue", Arial, sans-serif; letter-spacing:-.02em; margin:0 0 .4em; }
h2 { font: 700 1.35rem/1.3 "Inter", "Helvetica Neue", Arial, sans-serif; margin: 2.4em 0 .6em; padding-top:.6em; border-top:1px solid var(--rule); }
h3 { font: 600 1.05rem/1.3 "Inter", "Helvetica Neue", Arial, sans-serif; margin: 1.8em 0 .4em; }
p.dek { font-size:1.15rem; color:var(--muted); margin-top:0; }
p.byline { font: 13px "Inter", "Helvetica Neue", Arial, sans-serif; color:var(--muted); }
a { color: var(--tw); }
strong { font-weight: 700; }
code { font: 13.5px/1.4 ui-monospace, Menlo, monospace; background:#f0efe9; padding:1px 4px; border-radius:3px; }
pre { background:#f0efe9; padding:12px 14px; border-radius:6px; overflow-x:auto; }
pre code { background:none; padding:0; }
blockquote { margin:1.6em 0; padding:14px 18px; background:var(--card); border-left:4px solid var(--tw); border-radius:0 6px 6px 0;
             font: 15.5px/1.6 "Inter", "Helvetica Neue", Arial, sans-serif; }
blockquote p { margin:.4em 0; }
blockquote ul { margin:.3em 0; padding-left:1.2em; }
figure.chart { margin: 1.6em -8px .4em; padding: 14px 10px 6px; background: var(--card); border:1px solid var(--rule); border-radius:8px; }
figure.chart svg { width:100%; height:auto; display:block; }
p.caption { font: 13.5px/1.5 "Inter", "Helvetica Neue", Arial, sans-serif; color: var(--muted); margin: .3em 0 1.8em; }
.tablewrap { overflow-x:auto; margin: 1.2em 0 1.8em; }
table { border-collapse: collapse; width:100%; font: 13px/1.4 "Inter", "Helvetica Neue", Arial, sans-serif; font-variant-numeric: tabular-nums; }
th, td { padding: 6px 8px; border-bottom: 1px solid var(--rule); vertical-align: top; }
th { text-align:left; font-weight:600; color:var(--muted); border-bottom:1.5px solid var(--ink); }
.tw { color: var(--tw); font-weight:600; } .rd { color: var(--rd); font-weight:600; }
hr { border:0; border-top:1px solid var(--rule); margin:2.5em 0; }
@media (max-width: 600px) { body { font-size:16px; } h1 { font-size:1.6rem; } figure.chart { margin-left:0; margin-right:0; } }
"""


def main():
    src = BLOG / "post.md"
    md = refresh_tables(src.read_text())
    src.write_text(md)
    body = markdown.markdown(md, extensions=["tables", "fenced_code", "attr_list", "md_in_html", "footnotes"])
    body = inline_svg(body)
    body = re.sub(r"<table>", '<div class="tablewrap"><table>', body).replace("</table>", "</table></div>")
    title = re.search(r"^# (.+)$", md, re.M).group(1)
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>{CSS}</style></head>
<body><main>
{body}
</main></body></html>
"""
    (BLOG / "post.html").write_text(html)
    print("wrote", BLOG / "post.html", f"{len(html) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
