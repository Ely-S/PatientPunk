# Drug files

Spelling lists the sentiment pipeline reads through `--drug-file` and `--drug-exclude-file`.
One spelling per line, matched literally (case-insensitive, word-bounded, curly apostrophes
normalised). Nothing here is a pattern, and nothing in `src/` knows any of these names.

- `<drug>.txt` — first line is the canonical name, the rest are spellings that count as the drug.
- `<drug>.exclude.txt` — spellings of *other* compounds that must not count as `<drug>` when
  they enclose one of its spellings ("4'-DMA-7,8-DHF" contains "7,8-DHF"). A post that names
  both compounds separately still counts.

```bash
python src/run_sentiment_pipeline.py --db data/posts.db --output-dir outputs \
    --drug-file drug_files/78dhf.txt --drug-exclude-file drug_files/78dhf.exclude.txt
```

Provenance: the 7,8-DHF, 4'-DMA-7,8-DHF and 9-MBC lists were derived in PR #146 from the
spellings observed across nine nootropics subreddit corpora (`comparator_cohort.json` in the
tropoflavin study). Two additions on top of #146: `78dhf.txt` restores the bare
`dihydroxyflavone` spelling (12 genuine 7,8-DHF posts on r/Nootropics use only that word),
and `78dhf.exclude.txt` therefore also lists other dihydroxyflavones (6,7-, 5,7-, 3,7-…) so
they do not match it. Add a spelling by appending a line; keep lists sorted only if you like.
