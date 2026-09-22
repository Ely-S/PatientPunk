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
| `semax.txt` | 5 | Semax. |
| `selank.txt` | 4 | Selank. |
| `nsi-189.txt` | 3 | NSI-189. |
| `bpc-157.txt` | 4 | BPC-157. |
| `lions-mane.txt` | 7 | lion's mane. |
| `cerebrolysin.txt` | 1 | Cerebrolysin. |
| `dihexa.txt` | 1 | Dihexa. |

The ten files are the tropoflavin study's comparator set, one list per compound; only the 7,8-DHF / 4'-DMA pair needs an exclusion.

Provenance: all ten lists are the compound entries of `comparator_cohort.json` in the tropoflavin
study as of PR #146, which widened the 7,8-DHF, 4'-DMA and 9-MBC lists from the spellings observed
across nine nootropics subreddit corpora; the other seven are unchanged from PR #140. Add a spelling
by appending a line.
