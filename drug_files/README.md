# Drug files

Spelling lists the sentiment pipeline reads through `--drug-file` and `--drug-exclude-file`.
One file per compound, one spelling per line, first line the canonical name. Spellings are
matched literally: case-insensitive, word-bounded, with curly apostrophes and dash look-alikes
normalised. Nothing here is a pattern, and nothing in `src/` knows any of these names.

There is no separate exclusion file. To run a compound whose name occurs inside another
compound's name, pass the other compound's list as the exclusions: a match that sits inside
one of those spellings does not count, while a post that names both separately still does.

```bash
python src/run_sentiment_pipeline.py --db data/posts.db --output-dir outputs \
    --drug-file drug_files/78dhf.txt --drug-exclude-file drug_files/4dma-78dhf.txt
```

| file | lines | notes |
|---|---|---|
| `78dhf.txt` | 65 | 7,8-DHF. Contains bare `dhf`, which also matches dihydrofolate ("DHFR reduces DHF") and dengue text; rare in nootropics corpora, worth knowing elsewhere. |
| `4dma-78dhf.txt` | 195 | 4'-DMA-7,8-DHF; the exclude input for a 7,8-DHF run. |
| `9-mbc.txt` | 29 | 9-MBC. |

Provenance: all three lists come from PR #146, derived from the spellings observed across nine
nootropics subreddit corpora (`comparator_cohort.json` in the tropoflavin study). Add a spelling
by appending a line.
