# Drug aliases used in extraction

**Generated:** 2026-05-07 17:32 UTC from `data/historical_validation_2020-07_to_2022-12.db`
**Generator:** `scripts/dump_drug_aliases.py`

This file is a static export of the `treatment.aliases` column from
the analysis SQLite DB. The lists are what every pipeline run
substring-matched posts and comments against during the extraction
step and what every canonicalization step normalized to.
Reviewers can audit these lists directly without running anything.

## How these aliases were generated

During the pipeline's canonicalization step (`src/pipeline/canonicalize.py`),
Claude Sonnet 4.6 was queried with `drug_aliases_prompt(target_drug)`
(see `src/utilities/__init__.py:drug_aliases_prompt`) to produce a list
of brand names, generic names, common abbreviations, misspellings, and
class synonyms for each of the six target drugs. The model's output
was inserted as JSON into `treatment.aliases` at run time and joined
on by the SQL queries that produce Figure 1, Table 2, and Table 3.

### Epistemic status

The alias lists are intentionally produced by the pipeline's LLM
canonicalization step rather than being manually curated, because
evaluating the LLM canonicalization step is part of the method this
paper demonstrates. We treat alias generation as a pipeline output
rather than a hand-authored input, and publish the generated aliases
here so that dependency is fully auditable — reviewers can see exactly
what the substring-match step ran against. The reviewer notes section
below flags entries worth a closer look; corrections to those entries
would propagate through canonicalization and classification, so any
change requires regenerating per-drug counts.

---

## Per-drug alias lists

### colchicine (29 aliases)


- `colchicin`  *(misspelling)*
- `colchisine`  *(misspelling)*
- `colchizine`  *(misspelling)*
- `colcichine`  *(misspelling)*
- `colchicene`  *(misspelling)*
- `colchicyne`  *(misspelling)*
- `colchicina`  *(misspelling)*
- `colchicum`  *(misspelling)*
- `colcrys`
- `mitigare`  *(misspelling)*
- `colchicine usp`  *(multi-word)*
- `col`  *(short)*
- `colch`
- `colchicin e`  *(multi-word)*
- `cochicine`  *(misspelling)*
- `colchicince`  *(misspelling)*
- `colchicnie`  *(misspelling)*
- `colcichne`  *(misspelling)*
- `autumn crocus extract`  *(multi-word)*
- `meadow saffron extract`  *(multi-word)*
- `colchimax`  *(misspelling)*
- `colchicine 0.6mg`  *(multi-word)*
- `kolchicin`  *(misspelling)*
- `colhicine`  *(misspelling)*
- `colchicien`  *(misspelling)*
- `cochicene`  *(misspelling)*
- `colcichine`  *(misspelling)*
- `colchisene`  *(misspelling)*
- `colchicibe`  *(misspelling)*

_Heuristic flag: 1 alias(es) at ≤4 characters. Short aliases can match unrelated words via substring; verify these are intentional._

---

### famotidine (28 aliases)


- `pepcid`
- `pepcid ac`  *(multi-word)*
- `pepcid complete`  *(multi-word)*
- `mylanta ar`  *(multi-word)*
- `fluxid`
- `famotidina`  *(misspelling)*
- `famotidin`  *(misspelling)*
- `famotadin`  *(misspelling)*
- `famotidene`  *(misspelling)*
- `famotodine`  *(misspelling)*
- `famotideine`  *(misspelling)*
- `famotidnine`  *(misspelling)*
- `famotidone`  *(misspelling)*
- `famatidine`  *(misspelling)*
- `famitidine`  *(misspelling)*
- `famotidien`  *(misspelling)*
- `famotdine`  *(misspelling)*
- `famotidins`  *(misspelling)*
- `h2 blocker`  *(multi-word)*
- `h2 antagonist`  *(multi-word)*
- `acid reducer`  *(multi-word)*
- `heartburn relief`  *(multi-word)*
- `pepcid ac maximum strength`  *(multi-word)*
- `famotidina generica`  *(multi-word)*
- `famcotidine`  *(misspelling)*
- `fomotidine`  *(misspelling)*
- `famotidne`  *(misspelling)*
- `famotidime`  *(misspelling)*

---

### loratadine (28 aliases)


- `claritine`  *(misspelling)*
- `claritin`  *(misspelling)*
- `alavert`
- `loratidine`  *(misspelling)*
- `loratadene`  *(misspelling)*
- `loratadin`  *(misspelling)*
- `loratadyne`  *(misspelling)*
- `loratadina`  *(misspelling)*
- `loratidane`  *(misspelling)*
- `loratedine`  *(misspelling)*
- `loratodine`  *(misspelling)*
- `loratadiene`  *(misspelling)*
- `non-drowsy claritin`  *(multi-word)*
- `claritin d`  *(multi-word)*
- `loradatine`  *(misspelling)*
- `loratadne`  *(misspelling)*
- `loratdine`  *(misspelling)*
- `loradatine`  *(misspelling)*
- `loratadinе`  *(misspelling)*
- `claritin redi-tabs`  *(multi-word)*
- `loratab`
- `loratin`
- `clariton`  *(misspelling)*
- `clairitin`  *(misspelling)*
- `loratadine hcl`  *(multi-word)*
- `desloratadine precursor`  *(multi-word)*
- `10mg loratadine`  *(multi-word)*
- `loratadine usp`  *(multi-word)*

---

### naltrexone (29 aliases)


- `naltrexone hydrochloride`  *(multi-word)*
- `naltrexone hcl`  *(multi-word)*
- `ntx`  *(short)*
- `revia`
- `vivitrol`  *(misspelling)*
- `depade`
- `low dose naltrexone`  *(multi-word)*
- `ldn`  *(short)*
- `naltraxone`  *(misspelling)*
- `naltexone`  *(misspelling)*
- `naltrexon`  *(misspelling)*
- `naltrexoine`  *(misspelling)*
- `naltreone`  *(misspelling)*
- `nalrexone`  *(misspelling)*
- `naltexrone`  *(misspelling)*
- `naltrezone`  *(misspelling)*
- `naltrexome`  *(misspelling)*
- `nalrtexone`  *(misspelling)*
- `naltreoxne`  *(misspelling)*
- `naltrexcone`  *(misspelling)*
- `naltrexoне`  *(misspelling)*
- `naltrexone hci`  *(multi-word)*
- `50mg naltrexone`  *(multi-word)*
- `oral naltrexone`  *(multi-word)*
- `injectable naltrexone`  *(multi-word)*
- `extended release naltrexone`  *(multi-word)*
- `naltrexone er`  *(multi-word)*
- `naltrexone xr`  *(multi-word)*
- `naltrekson`  *(misspelling)*

_Heuristic flag: 2 alias(es) at ≤4 characters. Short aliases can match unrelated words via substring; verify these are intentional._

---

### paxlovid (28 aliases)


- `nirmatrelvir/ritonavir`  *(multi-word)*
- `nirmatrelvir`
- `ritonavir`  *(misspelling)*
- `nirmatrelvir-ritonavir`  *(multi-word)*
- `paxlovid pill`  *(multi-word)*
- `pfizer paxlovid`  *(multi-word)*
- `paxlovid antiviral`  *(multi-word)*
- `paxlovid covid`  *(multi-word)*
- `paxlovic`  *(misspelling)*
- `paxlovid oral`  *(multi-word)*
- `nirmtrelvir`
- `niramatrelvir`
- `nirmatrelvir ritonavir`  *(multi-word)*
- `paxlovd`  *(misspelling)*
- `paxlovid treatment`  *(multi-word)*
- `paxlovid therapy`  *(multi-word)*
- `paxlovid tablets`  *(multi-word)*
- `paxloved`  *(misspelling)*
- `paxlovit`  *(misspelling)*
- `paxloviid`  *(misspelling)*
- `paxlovir`  *(misspelling)*
- `nirmatrelvir/rtv`  *(multi-word)*
- `nmv/r`  *(multi-word)*
- `nmv-r`  *(multi-word)*
- `pxlovid`  *(misspelling)*
- `paxlovad`  *(misspelling)*
- `paxlovide`
- `covid antiviral paxlovid`  *(multi-word)*

---

### prednisone (28 aliases)


- `prednizone`  *(misspelling)*
- `predisone`  *(misspelling)*
- `prednosone`  *(misspelling)*
- `prednisonе`  *(misspelling)*
- `pred`  *(short)*
- `deltasone`  *(misspelling)*
- `rayos`
- `sterapred`  *(misspelling)*
- `predni`
- `prednisona`  *(misspelling)*
- `corticosteroid`
- `steroid`
- `oral steroid`  *(multi-word)*
- `glucocorticoid`
- `pednisone`  *(misspelling)*
- `predniosone`  *(misspelling)*
- `predinson`  *(misspelling)*
- `prednisolone`  *(misspelling)*
- `predsone`  *(misspelling)*
- `prenisone`  *(misspelling)*
- `prednizone`  *(misspelling)*
- `prednsone`  *(misspelling)*
- `prednisome`  *(misspelling)*
- `prednione`  *(misspelling)*
- `deltacortene`  *(misspelling)*
- `meticorten`  *(misspelling)*
- `orasone`
- `liquid pred`  *(multi-word)*

_Heuristic flag: 1 alias(es) at ≤4 characters. Short aliases can match unrelated words via substring; verify these are intentional._

---

## Cross-drug alias collisions

Aliases that appear in more than one drug's list. An alias appearing in multiple drugs would mean the same string substring-matches into multiple per-drug filters, double-counting the post. Should be empty.

**No cross-drug collisions.** Each alias is unique to one drug. ✓

---

## Reviewer notes (manual)

These are observations from a reading-pass over the alias lists,
intended as starting points for review — not
adjudicated corrections. The historical-validation analysis used the
alias list as-is; any change here would require regenerating per-drug
counts.

- **prednisone** includes `prednisolone` (a related but distinct
  glucocorticoid metabolite — different active molecule); class-level
  terms like `steroid`, `corticosteroid`, `oral steroid`,
  `glucocorticoid` (would substring-match generic class mentions
  rather than prednisone-specific ones); and `pred` (4-character,
  could match prefixes of unrelated words).
- **loratadine** includes `loratab` — Lortab is a brand of
  hydrocodone/acetaminophen, a different (opioid) drug; this is
  likely an LLM error and should be reviewed.
- **famotidine** includes class-level terms `h2 blocker`,
  `h2 antagonist`, `acid reducer`, `heartburn relief` — not
  specific to famotidine; would match generic class mentions.
- **paxlovid** includes the standalone components `ritonavir`
  and `nirmatrelvir`. Ritonavir is also used in HIV antivirals,
  so unprefixed mentions could collapse those into paxlovid.
- **colchicine** entries (autumn crocus extract, meadow saffron
  extract) reference natural sources of colchicine — defensible
  but worth confirming.

To turn any of these into actual corrections, the path is: edit the
alias list, re-run canonicalization, re-run classification, regenerate
the analysis DB and figures. We have **not** run a quantitative
sensitivity analysis on individual flagged aliases (no per-alias
ablation table is checked in), so this file should not be read as
evidence that the headline numbers are robust to those choices —
only that the choices themselves are documented and inspectable.
Producing a per-drug sensitivity table (drop each flagged alias,
re-run, report shifted n / pos / pos_pct) is the open methodology
task before publication.

## Reproducibility

Re-running
```
python scripts/dump_drug_aliases.py --db data/historical_validation_2020-07_to_2022-12.db --out DRUG_ALIASES.md
```
against the same DB reproduces the same alias content (deterministic
ordering); only the `Generated` timestamp at the top of this file changes.
If the DB's `treatment.aliases` content changes, this file should be
regenerated and committed alongside the DB.