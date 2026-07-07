# Broader-recall discovery — web-search provenance

## What this documents

17 of the threads in this corpus (see `Scrapers/phoenixrising_recall_targets.txt`) were **not**
found by the deterministic sitemap/tag methods. They were discovered by **external,
site-scoped web search** to catch threads that discuss LDN/pyridostigmine in the post *body*
but not the thread title (e.g. "recovery story" and "what treatments helped" threads).

## How — and by whom

**This discovery step was performed by Claude (Anthropic's LLM), interactively, using its
web-search tool — not by a committed script.** Claude authored the queries below (each scoped
to `forums.phoenixrising.me`), read the results, and selected the forum `/threads/` URLs, which
were then de-duplicated against the 276 sitemap-discovered threads to yield 17 new ones.

> **Reproducibility / AI caveat.** Unlike the sitemap discovery (`discover_from_sitemap()` in
> `Scrapers/scrape_phoenixrising.py`) and the `/tags/` crawl — both deterministic and AI-free —
> this web-search step is **AI-assisted and not deterministically reproducible**: results depend
> on the search engine's index at query time and on Claude's manual selection of relevant
> threads. It is recorded here purely for transparency. The *scraping* of the resulting threads
> is deterministic (same `scrape_phoenixrising.py` as everything else); only their *discovery*
> was AI-assisted.

## The exact queries Claude ran (all with `site:forums.phoenixrising.me`)

1. `"low dose naltrexone" OR LDN experience helped`
2. `LDN recovery protocol ME/CFS improved`
3. `mestinon OR pyridostigmine tried experience POTS orthostatic`
4. `naltrexone OR LDN "long covid" fatigue`
5. `"what helped" ME/CFS treatments medications list LDN`
6. `low dose naltrexone fibromyalgia pain success`
7. `naltrexone OR LDN autoimmune thyroid hashimoto experience`
8. `mestinon OR pyridostigmine fatigue energy improvement Systrom`
9. `naltrexone OR LDN started added "my protocol" supplements recovery`
10. `best treatments poll survey ME/CFS what worked naltrexone mestinon`
11. `naltrexone OR mestinon "i started" OR "i tried" side effects stopped`
12. `naltrexone OR mestinon doctor prescribed dysautonomia treatment plan`
13. `things that helped me recovery story LDN naltrexone improvement`
14. `mestinon OR pyridostigmine combination ivabradine midodrine florinef`
15. `success stories recovery ME/CFS what helped medications naltrexone`
16. `naltrexone OR LDN brain fog cognitive improvement helped`
17. `POTS orthostatic recovery what helped mestinon pyridostigmine beta blocker`

## To reproduce (approximately)

Run each query above on a search engine restricted to `forums.phoenixrising.me`, collect the
`/threads/{slug}.{id}/` result URLs, de-duplicate against `Scrapers/phoenixrising_targets.txt`
(by numeric thread id), and scrape the new ones:

```bash
python Scrapers/scrape_phoenixrising.py --thread-list Scrapers/phoenixrising_recall_targets.txt \
    --out output/phoenixrising_recall_posts.json
```

Because search-engine indexes drift, the exact set of returned threads may differ over time.
