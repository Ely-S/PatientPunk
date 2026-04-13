---
name: research-assistant
description: Use this skill whenever the user says "run the research assistant skill", asks to generate a research notebook, analyze a patient community database, run a research question against PatientPunk data, or requests analysis involving .db files. Also triggers on drug comparisons, treatment outcome questions, or community sentiment analysis. Generates reproducible Jupyter notebooks with statistical tests, charts, patient quotes, and HTML export.
---

# Research Assistant v2

## Modes

This skill supports two modes. The researcher specifies which mode when asking a question:

- **Default mode** — concise analysis, focused charts, binary comparisons when subgroups are small. Suitable for most questions.
- **Verbose mode** — deeper analysis with more complex tests, larger comparison matrices, additional subgroup breakdowns, and more charts. Use when the researcher says "verbose", "detailed", "deep dive", or "comprehensive." In verbose mode: include logistic regression with covariates, pairwise comparisons across all groups (not just binary), co-occurrence heatmaps, signal-strength stratification, and Shannon entropy for user agreement. Prefer multi-group comparisons over collapsing into binary. Include intermediate processing summaries for methodology review.

## Workflow

1. **Explore** — inspect schema, run sample queries, note gaps and limitations
2. **Report** — tell the researcher what data is available, date range, sample sizes
3. **Propose plan** — bullet-point analysis plan. Wait for approval before coding.
4. **Build notebook** — write, execute, export to code-free HTML
5. **Report results** — summarize findings, flag caveats, ask if they want to go deeper

## Notebook Rules

### Narrative structure

The notebook is an argument, not a dashboard. Each section must follow logically from the previous one. If you can rearrange the sections without losing coherence, the narrative is too weak.

Build the analysis as a story with five beats:

1. **Set up the question** — why does this matter? Who are we looking at? What's the context a reader needs before seeing any data?
2. **Establish baseline** — what does the overall picture look like before we dig in? This grounds the reader so the specific findings that follow have meaning.
3. **Test the hypothesis** — does the data support or contradict the question? This is the core analysis.
4. **Complicate the story** — what's surprising, contradictory, or nuanced? This is the **"Counterintuitive Findings Worth Investigating"** section and it is REQUIRED in every notebook. This is where the analysis earns trust by being honest about what's messy. Actively search for:
   - Treatments where community sentiment contradicts clinical guidelines (e.g., a first-line treatment showing negative sentiment despite being the standard of care)
   - Treatments where the same compound shows opposite results at different doses or in different contexts
   - Subgroups that respond opposite to the population
   - Highly-discussed treatments that underperform their reputation (e.g., a treatment the community recommends frequently but that shows mediocre positive rates in the data)
   - Treatments that are conspicuously absent despite being commonly prescribed
   - Results that contradict what the community believes about itself
   **Do not invent causal mechanisms to explain correlations.** If two text-mining signals co-occur (e.g., users who mention kind staff also mention fear more), report the correlation honestly: "Users who describe positive staff interactions mention fear at higher rates (25.9% vs 18.4%)." Do NOT then invent a mechanism: "kind staff convert fear into relief." You have no evidence for that — the correlation could reflect verbosity bias (detailed posters write about both), selection (frightened patients notice staff quality more), or confounding. State the observation. Let the reader interpret.
   
   **Counterintuitive findings must be surprising to a human reader, not just to a text-mining algorithm.** "People who write 'regret' often mean they don't feel it" is a data-processing observation, not a research finding — any human reading those posts would understand the negation immediately. Similarly, "sentiment scores don't capture mixed emotions" is a known limitation, not a discovery. The bar is: would a clinician, patient, or researcher say "huh, I wouldn't have expected that" upon reading this finding? If not, it's not counterintuitive — it's methodology commentary. Put methodology observations in the limitations section, not the findings.
   **It is better to have no counterintuitive findings than bad ones.** A weak or forced "counterintuitive" finding (circular comparisons, methodology artifacts, things any human would expect) actively damages the notebook's credibility. If you genuinely cannot find anything counterintuitive, say so explicitly and keep the section to one sentence: "All findings aligned with community consensus and clinical expectations." Do not pad with pipeline observations dressed up as insights. A short honest section earns more trust than a long section full of reaches.
5. **Land the conclusion** — what should the reader take away? Tiered recommendations, plain-language verdict, and limitations.

Each section's opening markdown cell must connect to the previous section with a brief factual transition — not a rhetorical flourish. Good: "Subgroup X reports worse outcomes overall (mean 0.18 vs 0.39). Which treatments buck that trend?" Bad: "Having painted the broad strokes, we now zoom in to examine..." 

**No circular comparisons.** Never compare a subgroup to a superset that contains it ("monotherapy users do worse than the broader community" — the broader community IS those users plus multi-treatment users). If you split a population into groups A and B, you can compare A to B, but not A to "the overall population" since the overall population is just A+B. This sounds insightful but is mathematically trivial.

**Every chart must be consistent with the narrative.** If the text says "Group A does worse than Group B overall," but a chart shows Group A outperforming Group B on every individual item, something is wrong — either the chart is mislabeled, the data is filtered in a way that reverses the overall pattern, or the narrative is incorrect. Check that charts support the story being told, not contradict it.

**Every claim must be consistent with its own numbers.** If you write "32% positive — barely above the 50% baseline," that is wrong: 32% is below 50%, not above it. Before writing any interpretive sentence, check the direction: is the number higher or lower than the comparison? Does "outperform" match a higher rate? Does "underperform" match a lower rate? This sounds obvious but LLMs routinely write template phrases ("above baseline", "better than chance") without verifying the arithmetic. Read your own numbers.

**Null and negative findings are real findings.** Report them honestly. Don't spin a null into a positive, don't bury non-significant results, don't omit treatments because they performed poorly. Include them in the narrative and recommendations where relevant. But keep the tone measured — "this treatment did not reach significance in our sample" rather than "this treatment is useless." The data may be underpowered rather than definitive.

**No aphorisms, epigrams, or inspirational framing.** Lines like "Statistics tell us *what*; quotes tell us *why*", "The numbers above describe *rates*, but quotes illustrate the lived experience behind those numbers", or "The numbers speak, but the patients speak louder" are filler. Write plain, direct prose. The data is interesting enough without dressing it up. If a sentence exists only to justify the section's existence rather than convey information, delete it. A section header and a brief factual introduction ("Quotes illustrating these findings:") is sufficient.

### Required elements
- **Research question** — the very first element of the notebook (before the abstract) must be a markdown cell stating the exact research question that was asked, formatted as: `**Research Question:** "Your question here"` This makes the notebook self-documenting — anyone opening it knows exactly what question it answers without reading the filename or the abstract.
- **Abstract** at top: 3-5 sentences covering question, key finding, method, sample size, main recommendation. Someone reads only this and knows the answer.
- **Date range** in Data Exploration: "Data covers: YYYY-MM-DD to YYYY-MM-DD (N months)"
- **Chart in every section** after Setup. The chart is the primary output; tables are supporting detail. **Do not use the same chart type more than twice in one notebook.** If you've already shown two diverging bars, the next comparison needs a different visualization — heatmap, scatter, grouped bar, slope chart, etc. Force variety.
- **Plain-language verdict** after every research question — never leave the reader to interpret p-values alone.
- **Plain-language explanation** after every chart — call out key takeaway, outliers, surprises.
- **Counterintuitive findings** — actively look for and highlight results that contradict clinical guidelines, community assumptions, or common sense. Frame as "worth investigating further," not as conclusions. If nothing is counterintuitive, say so — that itself is a finding.
- **Qualitative evidence — high bar** — after the quantitative analysis, add a "What patients are saying" section. Approach this as an expert qualitative researcher would: every quote is evidence, not decoration. Query `posts.body_text` joined with `posts.post_date` for users who reported on the top treatments. Pull 3-5 quotes (1-2 sentences each, up to 40 words). Include the date. At least one quote must contradict or complicate the main narrative. Every quote must be self-contained (no ambiguous pronouns — add [bracketed clarifications] if needed), must contain a specific treatment outcome (not meta-commentary or social validation), and must match the claim in its category header. If you cannot find quotes that directly demonstrate a claim, omit quotes for that claim entirely. A qualitative researcher would never include a quote that doesn't advance the argument — neither should you.
- **Tiered recommendations** after the analysis sections: Strong (n>=30, p<0.05) / Moderate (n>=15 or p<0.10) / Preliminary (n<15). Include a visual summary chart.
- **Conclusion** — a 2-4 paragraph narrative synthesis that answers the original research question directly. This is not a bullet list of findings — it's the "so what?" that ties everything together. What did we learn? What surprised us? What should a patient or researcher take away? What questions remain unanswered? Write it as if you're explaining the results to a colleague over coffee. **Take a position.** "Based on this data, a patient asking about [symptom] should consider [top treatments]. [Poorly performing treatment class] should be approached with caution." Do not end with "further research is needed" — that's a non-answer.
- **Research limitations** section after the conclusion covering all 8 biases: selection, reporting, survivorship, recall, confounding, no control group, sentiment vs efficacy, temporal snapshot. Do not abbreviate.
- End with the following disclaimer, formatted as bold, italic, and larger text (use `display(HTML(...))`  with `font-size: 1.2em; font-weight: bold; font-style: italic`): ***"These findings reflect reporting patterns in online communities, not population-level treatment effects. This is not medical advice."***

### Output quality
- **The setup cell must produce ZERO output.** No `print("Setup complete")`, no `print(f"Connected to {db}")`, no `print(f"Loaded {n} rows")`. The setup cell imports libraries, connects to the database, defines constants, and produces nothing visible.
- **No print() statements in any cell.** Code cells are hidden in HTML export but their output is visible. Every print statement shows up in the final report as raw terminal text. Use `display(HTML(...))` or styled DataFrames only in analysis cells where the output is meaningful to the reader.
- **No code cell should produce output that looks like code.** If the reader sees variable names, debug labels, file paths, or unformatted numbers, something is wrong. Every visible output must look like it belongs in a report.
- **No intermediate processing summaries** (default mode). "Filtering Summary: 15 merges applied, 14 causal exclusions, 25 generic terms removed, 517 reports remaining" is bookkeeping, not a finding. Mention exclusions briefly in a markdown cell ("Causative drugs were excluded — see methodology") and move on. The notebook is a report, not a processing log. In **verbose mode**, include these summaries.
- **No full DataFrames.** Truncate with `.head(20)` or `.head(30)` sorted by the most meaningful column.
- **Suppress warnings:** `import warnings; warnings.filterwarnings("ignore")` in setup cell.
- **DB_PATH as a variable** at the top of the setup cell.
- **Define medical terms on first use.** The reader may not know specialized abbreviations. First mention should include a brief parenthetical explanation.

### Statistical methods
Choose whatever tests, models, or approaches best fit the data. You are not limited to any predefined set. scipy, statsmodels, sklearn, pingouin, lifelines — your call. Justify your choice briefly in the notebook.

Good defaults: Wilson score CI for rankings with small n. Bayesian shrinkage when comparing treatments with very different sample sizes. Fisher's exact or chi-squared for categorical comparisons. Mann-Whitney for two-group sentiment. Kruskal-Wallis for 3+ groups. Logistic regression for multivariate predictors. Shannon entropy for measuring user agreement.

**Required for every comparison:**
- **Effect size**, not just p-values. The reader needs to know if a difference is large or trivially small. Use Cohen's h for proportion comparisons, rank-biserial correlation for Mann-Whitney, eta-squared for Kruskal-Wallis.
- **NNT (number needed to treat)** for patient-facing recommendations where applicable. "You'd need 3 people to try this for 1 additional person to report benefit" is more actionable than "p=0.002." Calculate as 1 / (treatment positive rate - baseline positive rate).
- **Sensitivity check** — does the main conclusion survive if you drop the 3 most extreme users, or restrict to strong-signal reports only? One sentence confirming robustness or flagging fragility.

**Sample size discipline:**
- When comparing groups, prefer binary comparisons (e.g., monotherapy vs polypharmacy) over splitting into 3+ tiers if any tier has n<20.
- If you must show a multi-group comparison where CIs overlap, say so explicitly: "The wide overlapping confidence intervals mean we cannot distinguish between these groups at this sample size."
- Never present a non-significant comparison as a finding. If p>0.05 and CIs overlap, the honest answer is "we don't have enough data to tell."
- In **verbose mode**, multi-group comparisons are acceptable even with smaller groups, but must always include CIs and explicit power caveats.

**Every visual comparison requires a statistical comparison.** If a chart shows two or more groups side by side (treatments, cohorts, tiers), there MUST be a corresponding statistical test (Fisher's exact, Mann-Whitney, chi-squared) with a p-value reported in the accompanying text. Placing bars or dots next to each other without testing the difference invites the reader to draw conclusions that may not be supported. If the comparison is not significant, say so: "While Drug A appears to outperform Drug B in this chart (6/6 vs 4/10 positive), the sample sizes are too small for a reliable comparison (Fisher's exact p=0.07)." Never show a visual comparison and let the reader assume significance.

### Tools available

`app/analysis/stats.py` provides pre-built functions for common analyses. These handle user-level aggregation, sentiment string conversion, and structured warnings automatically. **Use them when they fit your analysis. Use raw scipy/statsmodels when they don't.** Don't reinvent what already exists, but don't force a pre-built function into a question it wasn't designed for.

Available functions (import from `app.analysis.stats`):
- `get_user_sentiment(conn, drug, condition=None)` — user-level DataFrame for a drug, with optional condition filter
- `run_binomial_test(df)` — positive rate vs 50% baseline with Wilson CI
- `summarize_drug(df)` — descriptive stats with Wilson CI
- `run_comparison(df_a, df_b)` — Mann-Whitney U + Fisher's exact with effect sizes
- `run_wilcoxon(df)` — paired within-subject comparison for users who tried both drugs
- `run_kruskal_wallis(groups)` — 3+ group comparison with BH FDR post-hoc
- `run_logit(conn, drug, predictors)` — logistic regression with odds ratios
- `run_time_trend(conn, drug)` — Kendall's tau + OLS for temporal trends
- `run_survival(conn, drug, predictors)` — Cox PH survival analysis
- `run_spearman(x, y)` — rank correlation
- `run_propensity_match(conn, drug, predictors)` — matched causal comparison

All return dataclass results with a `.warnings` list of `AnalysisWarning(code, severity, message)`. Check and surface warnings with severity "caution" or "unreliable."

### Visualization principles

Every chart must tell a story. If a chart does not have a clear takeaway that you can state in one sentence, it should not exist. A notebook with 5 charts that each say something is better than one with 12 charts where half are filler.

**Before creating any chart, answer these three questions:**
1. What claim does this chart support or refute?
2. Can the reader identify the key finding within 5 seconds?
3. Would removing this chart lose information that the text alone cannot convey?

If the answer to any of these is "no," use a table or inline text instead.

**Chart selection by data type:**
- Comparing treatments by outcome rate → diverging bar chart or Wilson-score forest plot
- Showing precision/uncertainty → forest plot (dot + CI)
- Showing group composition → stacked or grouped bar chart
- Showing relationships between two continuous variables → scatter plot
- Showing co-occurrence or cross-tabulation → heatmap
- Showing proportions of a whole (≤6 categories) → pie or donut chart
- Showing change over time → line chart

**Do not use:**
- Box plots or strip plots for sentiment data (discrete values produce degenerate output)
- Volcano plots (designed for 20K+ features in genomics, not 30-100 treatments)
- Any chart where 90% of data points occupy the same position
- Bar charts comparing groups without error bars when sample sizes differ
- Dumbbell/slope charts where all lines slope the same direction — if every item shows the same pattern (Group A always higher than Group B), the chart conveys one fact repeated N times. Use a single summary statistic instead, or only show the chart if some items slope differently (which IS interesting)

**Readability rules:**
- Max 30 items on any single axis. If you have more, show the top 30 and note "N additional items in full table above."
- Y-axis labels must be readable — 9pt minimum. If labels overlap, you have too many items.
- Split recommendation charts by tier — one compact chart per tier, not one 80-row mega-chart.
- Legends go outside the data area via `bbox_to_anchor`. Never use `loc="best"`.
- **Legends must explain every visual encoding.** If dots or bars are colored differently (green vs grey, sized differently, shaped differently), the legend must explain what each color/size/shape means. A chart with unexplained color coding is confusing. If green means "statistically significant" and grey means "not significant," the legend must say so.
- **Nothing may overlap anything else — check and fix.** Legends must not overlap axis labels. Colorbars must not overlap annotations. Annotation text must not overlap bars or other annotations. After generating any chart, **visually inspect the saved figure** by checking the rendered output. If any element collides with another, fix it by: increasing margins (`fig.subplots_adjust`), moving the element, reducing font size, or using `fig.tight_layout(rect=[0, 0, 0.85, 1])` to reserve space for colorbars/legends on the right. When placing annotations (n=, [CAUSAL], etc.) next to bars, check that the text fits within the figure bounds — if it doesn't, move it inside the bar or omit it and use a table instead. **Overlapping elements are a bug, not a cosmetic issue.** After generating any chart with text labels (scatter plots, slope charts, forest plots with annotations, heatmaps), run an overlap check:

```python
# After placing text labels, check for overlaps
from matplotlib.transforms import Bbox
renderer = fig.canvas.get_renderer()
texts = [t for t in ax.texts]
for i, t1 in enumerate(texts):
    bb1 = t1.get_window_extent(renderer)
    for t2 in texts[i+1:]:
        bb2 = t2.get_window_extent(renderer)
        if bb1.overlaps(bb2):
            # Offset the second label
            t2.set_position((t2.get_position()[0], t2.get_position()[1] + offset))
```

If overlap is detected after execution, fix the code and re-execute. **Retry up to 2 times.** Common fixes: use `adjustText` library (`from adjustText import adjust_text`), manually offset y-coordinates, reduce font size, rotate labels, or switch to a table for dense data. If 2 retries still produce overlap, switch to a different chart type that doesn't require point labels (e.g., a ranked table instead of a labeled scatter).

**Common overlap scenarios:** scatter plot annotations clustering at similar x/y values; slope chart labels at endpoints; colorbar ticks overlapping annotations; axis titles colliding with tick labels; **legends overlapping data lines or points** — always place legends in a dedicated space (below chart, above chart, or in a cleared corner) never floating over plotted data.

**Diverging bar charts — CRITICAL stacking order (gets wrong often):**

The correct visual order left-to-right is: `← [Negative | Mixed] 0% [Positive] →`

Mixed/neutral MUST be adjacent to the center line. Negative MUST be outermost on the left. This is a semantic requirement — mixed sentiment is between negative and positive, so it goes in the middle.

In matplotlib, plot mixed FIRST (from zero leftward), then negative from the edge of mixed:
```python
ax.barh(y, -mixed_pct,    left=0,           color=GRAY)   # mixed innermost
ax.barh(y, -negative_pct, left=-mixed_pct,  color=RED)    # negative outermost
ax.barh(y,  positive_pct, left=0,           color=GREEN)  # positive right of center
```

If you plot negative first and mixed second, mixed ends up on the far left outside negative — **this is wrong and misrepresents the data.**

**Confidence intervals and error bars:**
- **Every bar chart comparing groups must have error bars** (95% CI or SEM). No exceptions. A bar chart without error bars invites false comparisons. If matplotlib makes error bars difficult for a particular chart type, switch to a forest plot (dot + CI) which shows uncertainty by design. **Error bars must be applied symmetrically** — if the positive bars have CIs, the negative bars must too. Showing uncertainty on one direction but not the other implies false precision.
- When comparing groups with different sample sizes, the error bars make the uncertainty visible — n=49 will have wider bars than n=1055, and the reader can eyeball whether the difference is reliable.
- If all group CIs overlap substantially, say so explicitly. Do not present overlapping CIs as a meaningful difference.

**Seaborn:** always pass `hue=` parameter, not the deprecated `palette` without `hue`.

### Filtering (4 rules)
1. **Generic terms:** filter "supplements", "medication", "treatment", "therapy", "drug" from results. These are categories, not actionable treatments.
2. **Causal-context contamination:** filter treatments whose negative sentiment reflects WHY users are in the community, not treatment response. Examples: a drug that caused the condition the community is about, a contraceptive that failed (in a community about unplanned pregnancy), a vaccine perceived as causing the illness. Explain each exclusion in the notebook.
3. **Community-defining conditions:** filter the primary condition that defines the subreddit from co-occurring condition charts. The condition the subreddit is named after is not a co-occurrence — it is the reason the community exists. Filter it and show only genuinely co-occurring conditions.
4. **Duplicate canonicals:** merge obvious duplicates (dxm/dextromethorphan, weed/cannabis/marijuana, tylenol/acetaminophen).

### Community experience analysis

Not every subreddit is primarily about drugs. When treatment_reports are sparse or uninteresting for a community, pivot to text-based experience analysis. Search `posts.body_text` for experiential themes — support systems, access barriers, provider interactions, emotional trajectory, fear, relief, regret — and analyze those instead. The posts table often has richer signal than the treatment_reports table.

### Audience
The audience is patients AND researchers. Every statistical result must appear twice: formal (p-value, CI, effect size, test name) and plain language a patient can act on. Example: "72% of people who tried [treatment] reported positive outcomes — significantly better than chance (p=0.002, Cohen's h=0.45). In practical terms, roughly 1 in 3 patients who try this can expect to report benefit beyond what we'd see by chance alone."

## Notebook builder

Use `notebooks/build_notebook.py` to build notebooks efficiently. It handles setup boilerplate, DB connection, imports, sentiment mapping, helper functions, and execution/export automatically.

```python
import sys; sys.path.insert(0, "notebooks")
from build_notebook import build_notebook, execute_and_export

nb = build_notebook(
    cells=[
        ("md", "# Title\n\nAbstract..."),
        ("code", "df = pd.read_sql('SELECT ...', conn)\ndisplay(df)"),
        ("md", "**What this means:** ..."),
    ],
    db_path="polina_onemonth.db",  # resolved to absolute automatically
)

html = execute_and_export(nb, "notebooks/v2/1_overview")
# Produces: 1_overview.ipynb, 1_overview_executed.ipynb, 1_overview.html
```

The setup cell is injected automatically with: warnings suppressed, sqlite3/pandas/numpy/matplotlib/seaborn/scipy imported, DB connected, SENTIMENT_SCORE dict, classify_outcome(), wilson_ci(), nnt(), GENERIC_TERMS set, COLORS dict. **The setup cell produces zero output.**

Agent code just provides the analysis cells as `("md", ...)` or `("code", ...)` tuples — no .ipynb JSON boilerplate needed.

If execution fails, fix the error in the cell content and re-run. Never deliver an unexecuted notebook.

## Database profiles

Pre-generated database profiles are at `notebooks/profiles/{db_name}.json`. Read the profile instead of exploring the database from scratch. It contains: user/post/report counts, date range, top 30 treatments with positive rates, conditions, text theme counts, identified generic terms, and causal-context candidates.

```python
import json
profile = json.loads(open("notebooks/profiles/polina_onemonth.json").read())
```

Use the profile to skip the exploration step and go straight to the analysis plan.

## Database

Sentiment is stored as TEXT strings ('positive', 'negative', 'mixed', 'neutral'). Convert to numeric with:
```sql
CASE tr.sentiment WHEN 'positive' THEN 1.0 WHEN 'mixed' THEN 0.5 WHEN 'neutral' THEN 0.0 WHEN 'negative' THEN -1.0 ELSE 0.0 END
```

All tables join on `user_id`. Always aggregate to user level (one data point per user per drug) for statistical independence.
