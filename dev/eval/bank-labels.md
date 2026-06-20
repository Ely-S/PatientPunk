# Eval Bank — Labels & Reasoning (human spot-check)

Companion to `dev/eval/bank.json`. Every text is **verbatim** from `output/subreddit_posts.json`
(posts trimmed only where marked `...`; for posts, the `text` field prepends the Reddit `title` to the
`body`). The `labels` block is filled **only** where the `system_prompt` rules in
`src/prompts/intervention_config.py` give a confident per-drug answer; ambiguous drugs are deliberately
left unlabeled (and called out in `notes`). A wrong label corrupts the eval, so labeling is conservative.

**Source-id map** (bank id → Reddit id): p1→t3_1tyd1cr, p2→t1_oq2v9l6, p3→t1_oq558rj, p4→t1_oq3v0d6,
p5→t1_oq57g5e, p6→t1_oq39o0j, p7→t1_oq4cgsb, p8→t1_oq7mwah, p9→t3_1ty9loi, p10→t1_oq5omz7,
p11→t1_oq6w33h, p12→t1_oq78xys, p13→t3_1tymnad, p14→t1_oq7ltc5, p15→t1_oq6uyh4, p16→t1_oq5nxl1,
p17→t1_oq4371d, p18→t3_1tym05b, p19→t3_1tyq9ky, p20→t1_oq578ew, p21→t1_oq32msx, p22→t1_oq5aj5w.

**Rule legend** (from the classifier system prompt): KEY-Q = "did this person personally use it?";
LIST-FANOUT = a symptom said of a *drug list* attaches to every drug in the list; INTERACTIONS = a
combo-only problem belongs to the modifying drug, tolerated drug gets `[]`; CAUSE-vs-EFFECT = the
condition being treated is not a side effect; LDN-vs-LDA = similar abbreviations in one thread must not
cross-attribute; partial improvement / side-effects-during-benefit = **positive**, not mixed.

---

## p1 — Full-Time School with ME/CFS (post) — *OBSERVED FAILURE #2: side-effect over-attribution*
> "... I also started taking **fluvoxamine** this week, and **my sleep has been worse** since then. My
> current medications are LDN, LDA, amifampridine, and fluvoxamine. In addition, I regularly use a red
> light mat, nicotine patches, and do HBOT twice a week. ..."

- **fluvoxamine → negative, side_effects=["worse sleep"]** — the worse sleep is attributed *only* to the
  drug the author just started ("started taking fluvoxamine this week, and my sleep has been worse since
  then").
- **red light mat / nicotine patches / hbot → neutral, side_effects=[]** — a stable pre-existing stack
  ("I regularly use…"); no benefit and no symptom attributed to them. This is **NOT a LIST-FANOUT** (the
  worse-sleep symptom is tied to one started drug, not predicated of a list), so "worse sleep" must not
  spread to them.
- **ldn / lda / amifampridine → UNLABELED** — named in the stack with no individual outcome, and the week
  went badly (PEM, crying), so per-drug sentiment is genuinely ambiguous.
- **Why it matters:** the prior pipeline run (in `data/posts.db`) wrongly wrote `side_effects=["worse
  sleep"]` onto **red light mat + nicotine patches + hbot** and gave them `positive/weak`. This row pins
  the exact bug. `expected_drugs` also forces extract to keep **LDA** distinct from LDN.

## p2 — "more energy due to ldn" (comment, upstream = trauma/improvement thread)
> "Once I started to have **more energy due to ldn** … it's a relief to feel it all moving through my body."
- **ldn → positive, side_effects=[]** — first-person benefit (energy) credited to LDN (KEY-Q = yes →
  outcome). The emotional surfacing is a *downstream consequence of regaining energy*, not a side effect
  blamed on LDN (CAUSE-vs-EFFECT). Matches the prior DB run (ldn positive/strong).

## p3 — "beta blockers always made me cry more" (comment)
> "Also, **beta blockers always made me cry more.**"
- **beta blockers → negative, side_effects=["crying more"]** — first-person adverse effect; "always" is
  emphatic (strong signal defensible). Wording trimmed to the symptom.

## p4 — "Antihistamines didn't do anything for me" (comment)
> "**Antihistamines didn't do anything for me.** … it depends on if you have MCAS or not"
- **antihistamines → negative, side_effects=[]** — personal use, no benefit. Emphatic "didn't do
  anything" (strong defensible). Matches prior DB run (antihistamines negative/strong).

## p5 — "all they did was help me with sleep" (comment, upstream = antihistamine thread)
> "**all they did was help me with sleep and helped me feel a bit better.** thats about it"
- **antihistamines → positive, side_effects=[]** — reply-chain pronoun "they" = antihistamines. Partial
  improvement is **positive** per the rule (not mixed); "that's about it" only downplays scope.

## p6 — Ketotifen / antihistamines mechanism explainer (comment) — *NEUTRAL stress case*
> "Ketotifen it's the first line treatment here … Ketotifen actually stabilises the mast cells and treats
> the actual cause. Desloratadine can also be mast cell stabilising. … Zyrtec would make you tired…"
- **ketotifen / antihistamines / desloratadine → neutral, side_effects=[]** — pure mechanism/education,
  no first-person "I tried X and it did Y" (KEY-Q = no → neutral).
- **zyrtec → UNLABELED** — general third-person aside; left out to keep labels cleanest, but extract
  should still capture it.

## p7 — MCAS+ADHD stack, "there's no interaction" (comment) — *INTERACTIONS / tolerability*
> "I take 2mg **ketotifen** … 5mg **desloratadine** and 20mg **Famotidine** … for MCAS. This was fine with
> 70mg lisdex and amfexa … **there's no interaction**"
- **famotidine / ketotifen / desloratadine → neutral, side_effects=[]** — personal use but reports
  *tolerability*, not efficacy ("totally fine", "there's no interaction"). INTERACTIONS rule → a tolerated
  combo yields `side_effects=[]` (the load-bearing assertion). lisdex/amfexa/guanfacine/betaine HCL named
  without outcome → not labeled.

## p8 — "just started trying Lumbrokinase … I read that it can help" (comment, upstream = vision thread)
> "**I just started trying Lumbrokinase recently** (similar to Nattokinase) and **I read that it can
> help** get rid of the 'floaters' … it seems to have a few other benefits too."
- **lumbrokinase → neutral, side_effects=[]** — used but no personal outcome yet; the benefit is
  read-about/hedged, not experienced. **nattokinase** is only a comparison ("similar to") → extract finds
  it, not labeled.

## p9 — "Tollovid … Has anyone tried it?" (post) — *question / third-party evidence*
> "**Has anyone tried it?** … one of the things that got a good response was Tollovid … **Anyone here take
> it?**"
- **tollovid → neutral, side_effects=[]** — author has not used it; the "good response" is from a
  spreadsheet of what *others* reported. Question-only (may be dropped at extract), but the correct
  classify outcome is neutral.

## p10 — Ferrous Sulfate "no difference" vs iron glycinate "haven't started" (comment)
> "I used to take **Ferrous Sulfate** … **never noticed any difference** … No difference. … my doctors is
> asking me to try **iron glycinate** instead (which **I haven't started yet**)"
- **ferrous sulfate → negative, side_effects=[]** — personal use, no effect.
- **iron glycinate → neutral, side_effects=[]** — explicitly not yet used. Clean tried-vs-not-tried
  contrast in one comment.

## p11 — Iron supplements helped tremors/headache (comment)
> "my **tremors** and … **headache** … went down and gave me a generally good feeling when I took **iron
> supplements**/ate beef."
- **iron → positive, side_effects=[]** — first-person named-symptom improvement (strong defensible). The
  tremors/headache are the *treated* conditions, not side effects (CAUSE-vs-EFFECT). "ate beef" is diet,
  not a drug.

## p12 — Mitochondrial support supplement resolved OH (comment) — *CAUSE-vs-EFFECT trap on guanfacine*
> "my naturopath just put me on a **mitochondrial support supplement** which has **resolved my OH for the
> last 3 days** … much more physical and cognitive energy … the supp is SFI Mitothera."
- **mitochondrial support supplement → positive, side_effects=[]** — named-symptom + clear temporal
  (strong defensible); OH is the treated condition.
- **guanfacine → UNLABELED** — described earlier as *causing* the OH ("taking guanfacine … leading to
  orthostatic hypotension") that the supplement fixed; complex framing, so omitted from labels but kept in
  `expected_drugs` for extract scoring.

## p13 — "control it with creatine and magnesium" + B12 (post excerpt)
> "brain fog … I can mostly **control it with creatine and magnesium** … **B12 injections** every other
> week (**they helped initially**) … omega 3, magnesium, B1,B6, D3 and a probiotic."
- **creatine / magnesium / b12 → positive, side_effects=[]** — each is individually credited (brain-fog
  control; "they helped"). Brain fog is the treated condition (CAUSE-vs-EFFECT → `[]`).
- **omega 3 / b1 / b6 / d3 / probiotics → UNLABELED** — regimen-list mentions with no individual outcome.

## p14 — "almost all my symptoms are gone after months of … b12 injections" (comment)
> "**almost all my symptoms are gone after months of every other day [b12] injections.**"
- **b12 → positive, side_effects=[]** — temporal + dramatic outcome (strong defensible); deficiency
  symptoms are the treated condition.

## p15 — H1 blockers / EpiPens / hydroxyzine (comment) — *prefilter=yes but outcome unclear*
> "I needed **H1 blockers** for this. … getting a prescription for 3 **EpiPens**. I also have refills on
> **hydroxyzine**. I need a lot once a week or so of the H1 blocker."
- **all UNLABELED** — clearly personal *use* (so prefilter should say yes), but the comment states dosing
  *need*, not whether it relieved the tight throat → sentiment genuinely ambiguous. Kept for extract value
  (EpiPen + hydroxyzine + H1 blockers) and as a "personal-use yes / outcome unclear" case.

## p16 — "Try pepsid/famitodine and gaviscon advance" (comment) — *advice to others*
> "**Try pepsid/famitodine and gaviscon advance** and see if it helps."
- **famotidine / gaviscon → neutral, side_effects=[]** — recommending to the OP, no first-person outcome.
  ("pepsid"/"famitodine" are misspellings of pepcid/famotidine — same drug; canonicalize should merge
  pepcid → famotidine, so both forms are in `expected_drugs`.)

## p17 — Celiac / gluten (comment) — *TRUE NEGATIVE (diet, not a drug)*
> "If I eat **gluten** now I am bedridden … It's **PEM on steroids**."
- **expected_drugs = []** — gluten/celiac is diet (EXTRACT_PROMPT excludes diet/lifestyle). "PEM on
  steroids" is an idiom, not the drug *steroids* (a distractor extract must not bite on).

## p18 — Blood draining / POTS (post) — *TRUE NEGATIVE (symptom-only)*
> "… the blood is literally draining out of their head … Likely my POTS … intense depressions, intrusive
> thoughts and anxiety …"
- **expected_drugs = []** — pure symptom description, no treatment named. Extract must not hallucinate one.

## p19 — "You are the strongest people I know" (post) — *TRUE NEGATIVE (support-only)*
> "From my own experiences, I know just how incredibly strong you are. … You are not alone."
- **expected_drugs = []** — emotional support, no treatments (prefilter "just encouragement" = no).

## p20 — "it highly correlates with pem for me" (comment) — *TRUE NEGATIVE (short reply, no drug)*
> "**it highly correlates with pem for me**"  (upstream: "Anybody get tight throat at times?")
- **expected_drugs = []** — terse reply, no drug in reply or parent → nothing to attribute. Tests that the
  short-reply / upstream machinery doesn't fabricate a drug.

## p21 — Reinfection "felt better at the beginning … now only worse" (comment) — *TRUE NEGATIVE (non-drug)*
> "**i felt better at the beginning but now i get only worse** with something else added" (upstream =
> deliberate-cold-reinfection thread)
- **expected_drugs = []** — the "intervention" is deliberate reinfection with the common cold (not a
  drug). Mixed personal experience but **no drug to attach it to** → no labels. Guards against the
  classifier inventing a drug to carry a sentiment.

## p22 — "I tried this. definitely didnt work for me." (comment) — *TRUE NEGATIVE (lifestyle referent)*
> "**I tried this. definitely didnt work for me.**" (upstream = "ignore the pain / brain-retraining" idea)
- **expected_drugs = []** — "this" = a psychological/lifestyle approach, not a drug. A short negative reply
  whose referent is a non-drug intervention; ensures upstream propagation doesn't manufacture a drug.

---

## Counts
- **Texts:** 22 (5 posts, 17 comments).
- **Drug mentions (sum of `expected_drugs`):** 46.
- **Labeled per-drug sentiments:** 26 — positive 8, negative 4, neutral 14.
- **Labeled side_effects:** 2 non-empty (`fluvoxamine`→worse sleep, `beta blockers`→crying more), 24 empty.
- **True-negative texts (`expected_drugs == []`):** 6 (p17, p18, p19, p20, p21, p22).
- **Comments carrying upstream context:** p2, p3, p4, p5, p6, p7, p8, p10, p11, p12, p14, p15, p16, p20, p21, p22.

## Observed-failure cases included
- **FORMAT failure (prose-instead-of-JSON-array on classify batches):** not encoded as a *label* (it's a
  transport/format defect, not a ground-truth disagreement). The drug-dense, multi-item posts **p1, p7,
  p13** are the texts most likely to trigger the narration-instead-of-JSON behavior in a classify batch, so
  they exercise it in the harness.
- **SIDE-EFFECT OVER-ATTRIBUTION:** **p1** is the exact `t3_1tyd1cr` stack post. The corrected labels
  (worse sleep on fluvoxamine only; red light mat / nicotine patches / hbot = `side_effects=[]`) directly
  contradict the buggy prior run in `data/posts.db`, which is what makes this row a regression check.
- **Adjacent guards** for the same class of bug: p7 (INTERACTIONS → tolerated stack = `[]`), p12
  (CAUSE-vs-EFFECT trap on guanfacine), p11/p13/p14 (treated-condition symptoms must not become
  side_effects).
