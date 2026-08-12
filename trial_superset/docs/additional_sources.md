# Additional Long-COVID sources beyond CT.gov structured results

> **Framing ([method_and_scope.md](method_and_scope.md)):** these sources grow the Long-COVID
> **benchmark pool** (more LC trials with ground-truth outcomes to evaluate NATURAL against) — *not*
> "training data," since NATURAL trains no pooled model. Value = benchmark breadth + surfacing the
> occasional accessible-drug LC trial, not training volume.

Two **independent** explorers (separate files, separate outputs) for growing the Long-COVID benchmark
pool past CT.gov. Both emit **candidate CSVs for human review** — neither auto-injects into the
training set, because each crosses a boundary that needs a deliberate decision (non-CT.gov schema;
trusting a review's extraction).

| lever | file | output | what it adds |
|---|---|---|---|
| #1 non-CT.gov registries | `mine_registries.py` | `data/mined_registries.csv` | ISRCTN/EudraCT LC RCTs absent from CT.gov |
| #2 systematic reviews | `mine_reviews.py` | `data/mined_reviews.csv` | included-RCT evidence tables (trial + vetted outcome) |

Context — measured **dead ends** (so we don't relitigate them):
- **Relaxing `check_trial` criteria** doesn't help: on 201 pooled LC trials, the only sizable gains
  are `randomized=False` (+34, **breaks the causal frame**) and `nonhealthy=False` (+17, admits
  **healthy-volunteer** trials). `num_noncontrol`/`parallel`: +3/+0. Not a lever.
- **More CT.gov query tricks** are exhausted (scope already broadened to SARS-CoV-2/PASC; free-text
  `query.term` returns acute/non-COVID noise).

---

## Lever #1 — non-CT.gov registries (`mine_registries.py`)
**Why:** the LC RCT literature references trials registered on **ISRCTN (UK)** and **EudraCT (EU)** —
the UK runs many LC trials there — that our NCT-only harvest ignored.
**How:** harvest ISRCTN/EudraCT ids from Europe PMC LC RCT papers → fetch each ISRCTN record from the
ISRCTN API (structured XML, no LLM) → keep interventional + randomized + patient + genuinely-LC.
EudraCT ids are *recorded but not fetched* (EU CTR has no clean API — HTML scrape / WHO ICTRP, future).

**Result:** 64 ISRCTN + 27 EudraCT ids harvested → **13 usable ISRCTN LC RCTs** (all fetched). Skew
is behavioral/rehab (as expected for UK LC trials); **2 drug**, of which **ISRCTN10665760 = STIMULATE-ICP**
(loratadine + **famotidine** — famotidine has real corpus signal, ~3110 distinct authors). That trial
alone justifies the lever — it's a notable accessible-drug LC RCT invisible to a CT.gov-only pull.

**Adapter — BUILT (`adapt_registries.py`).** ISRCTN record (design) + linked results paper (per-arm
outcome) → LLM schema → clone a real CT.gov trial as a structural template and overwrite the semantic
fields → a CT.gov-shaped trial that loads in `ClinicalTrial`, passes `check_trial`, and whose
`Experiment` reads the label. **6 of 13 adapted + validated end-to-end** (the rest: no clean per-arm
numeric primary in the OA paper — incl. STIMULATE-ICP famotidine, a platform trial). The 6 are folded
into the `long_covid` Study via `build_augmented.py` (tagged `label_source=registry_adapted`):
**Long-COVID train+val 44 → 50; augmented total 249 → 255.** Covariates are neutralized (template
leakage) — same sparsity caveat as papers-as-labels. The 6 are behavioral/device/supplement, so the
**corpus-learnable** subset is unchanged (68 trials); raw base grew. Output: `data/adapted_registries/`
+ `data/adapted_registries_manifest.csv`. EudraCT still needs its own fetch (no API).

## Lever #2 — systematic-review evidence tables (`mine_reviews.py`)
**Why:** a Long-COVID-interventions review already lists every included RCT *and* extracts its primary
result — curated by domain experts. It finds trials and hands us vetted outcomes in one pass.
**How:** find OA LC intervention systematic reviews / meta-analyses in Europe PMC → fetch full text →
LLM-extract the included-RCT evidence table (trial id, intervention, outcome, reported result, favors)
→ flag which referenced trial ids we already have vs are new.

**Result:** 15 OA reviews → 8 usable → **83 included-trial outcome rows** extracted. **But the
reviews cite included trials by author-year, not registry id** (only 3 registry ids appear anywhere
in 8 full texts of 120–200k chars each) — so **0–2 rows are directly linkable to a trial record.**
So Lever #2 is **not** a source of structured training trials; its product is a curated **weak-label
table** (intervention → outcome direction, e.g. "SIM01 probiotic → 58% insomnia reduction, favors
intervention"). Useful as: a sanity-check/validation set, and a worklist for author-year→registry
resolution (a further build if wanted).

**Bonus find:** the review-embedded ids surfaced **NCT05946551** (cetirizine + famotidine LC trial,
*has results*) which we'd missed because it's **TERMINATED** — our filter is `status:com`. → a small
extra lever: **terminated/other-status trials that still posted results** (few, often underpowered, but
free to include by widening the status filter).

**Cost to actually use these:** the outcomes are second-hand (the review's extraction, not the source
record), and unlinked to a design. Weak labels / cross-checks only; do not promote to training without
resolving each to its trial record and confirming.

---

## Strict registry screen

`pull_non_ctgov_long_covid_structured_learnable.py` re-reads `data/mined_registries.csv`,
re-fetches ISRCTN XML, and applies the same project screen used for the CT.gov structured pull:
local Long COVID terms, completed randomized interventional patient trials, single-agent blinded
drug/supplement intervention, and patient-signal-relevant primary endpoint text. It writes
`data/non_ctgov_structured_learnable/long_covid_non_ctgov_structured_audit.csv` and
`data/non_ctgov_structured_learnable/long_covid_non_ctgov_structured_learnable.csv`. EudraCT rows
are kept as audit-only rows until a structured fetch path is added.

## Honest framing
Both levers grow the **raw** Long-COVID trial count, but the additions skew **behavioral/rehab** — so
the **corpus-learnable drug** subset (what matters for predicting from Reddit signal) grows only
modestly. The structural scarcity of self-experimentable-drug LC RCTs stands; these sources widen the
benchmark base and surface the occasional high-value drug trial (e.g. STIMULATE-ICP famotidine).
