# Coding Instructions — PatientPunk IRR Pilot (v1.5)

**Workflow:**
1. Open `reading_packet.html` in a browser — this has all 300 posts rendered as cards, each labeled with its `sample_id`.
2. Open `coder_output_template.csv` alongside (in Excel, Sheets, or your editor of choice). The CSV has one row pre-filled per `sample_id`.
3. For each sample, look up the matching `sample_id` in the HTML packet, read the post, and:
   - **If the post mentions one drug** → fill in the pre-filled row.
   - **If the post mentions multiple drugs** → use the pre-filled row for the first drug, then **add additional rows with the same `sample_id`** for each additional drug. One row per drug.
   - **If the post mentions no drug** → set `drug_mention_verbatim = NONE` and leave the rest of the annotation columns blank.

**One row per drug per sample.** Same `sample_id` repeats across rows when multiple drugs are mentioned. `sample_id` is what joins back to the post; `drug_mention_verbatim` is what distinguishes rows within a sample.

Rules below are adapted from the AI pipeline's prompts. Disagreement between coders should come from genuinely ambiguous posts, not from different interpretations of these rules.

## Columns you fill in

| Column | Values | Captures |
|---|---|---|
| `coder_id` | your name (`eli`, `tj`) | Who coded this row |
| `drug_mention_verbatim` | free text, or `NONE` | Drug/treatment as written or referenced in the post (don't canonicalize). Use `NONE` if no drug mentioned. |
| `personal_use` | `yes` / `no` | Did the author personally use this drug? `yes` only when the author describes their own experience with this specific drug. `no` for questions, hearsay, advice to others, hypothetical or planned use, or citing studies. |
| `sentiment` | `positive` / `negative` / `mixed` / `neutral` | Author's sentiment about THIS DRUG specifically. Only filled when `personal_use = yes`. Use `neutral` only when personal use is unclear or the author explicitly takes no position despite using the drug. |
| `signal_strength` | `strong` / `moderate` / `weak` / `n/a` | **About the post:** how emphatic/specific/quantified is the author's report on this drug? Use `n/a` when `personal_use = no`. |
| `confidence` | 1–5 | **About your coding:** how sure are you the labels you picked are right? Always filled, even when `personal_use = no`. |
| `side_effects_reported` | `yes` / `no` | Does the author report any side effects they personally experienced from THIS DRUG? Only filled when `personal_use = yes`; leave blank when `personal_use = no`. |
| `side_effects_description` | free text | Brief description of what side effects, if any. Leave blank if `side_effects_reported = no` or `personal_use = no`. |
| `notes` | free text | Reasoning, ambiguity flags, anything worth recording (optional) |

> **⚠️ STOP rule.** If `personal_use = no`, leave `sentiment`,
> `signal_strength`, `side_effects_reported`, and `side_effects_description`
> blank (or set to `n/a` where applicable) and move on. The classifier and
> the analysis only count personal-use reports, so non-personal-use rows
> contribute to inter-coder reliability on the `personal_use` decision and
> nothing further.

> **⚠️ Don't confuse `signal_strength` with `confidence`.** They are independent.
> `signal_strength` rates **the post's language** — a brief mention is `weak` even
> if it's trivial to code. `confidence` rates **your certainty in your own labels** —
> a very emphatic post can still be hard to code if the outcome is genuinely
> ambiguous.

---

## Multi-drug example (read this first)

Sample `irr-pilot-003` says: *"I'm on LDN and magnesium. LDN gave me insomnia first 2 weeks but settled. About 40% better than a year ago."*

Two rows, both with `sample_id = irr-pilot-003`:

| sample_id | coder_id | drug_mention_verbatim | personal_use | sentiment | signal_strength | confidence | side_effects_reported | side_effects_description | notes |
|---|---|---|---|---|---|---|---|---|---|
| irr-pilot-003 | eli | LDN | yes | positive | strong | 4 | yes | insomnia first 2 weeks | in stack |
| irr-pilot-003 | eli | magnesium | yes | positive | weak | 4 | no | | in stack |

Same sample_id, one row per drug, each drug gets its own per-drug
`personal_use` / `sentiment` / `signal_strength` / `side_effects_*`.

---

## Step 1 — Identify each drug mention

**Include:** prescription drugs (LDN, gabapentin), OTC (ibuprofen, Tylenol), supplements (magnesium, B12), enzymes (DAO, nattokinase), drug *categories* (antihistamines, SSRIs), generic references ("an oral antibiotic"), non-drug treatments (PT, infrared sauna, compression, specific diets), devices (CPAP, IV saline).

**Exclude:** vague references ("medication", "something"), condition names (unless being treated), food (unless framed therapeutically).

**Record verbatim — written or referenced.** If the author wrote a name, use their exact wording ("LDN" stays "LDN" — don't expand to "low dose naltrexone"). If they only referenced indirectly ("the shot I got", "her prescription for the nerve pain"), record the best short phrase from the sample.

**One row per distinct drug.** Same drug mentioned multiple times in the same sample = ONE row. Different drugs = different rows. A drug class and a specific drug from it (e.g., "antihistamines, specifically Zyrtec") = TWO rows.

**Reply chains** — the reading packet shows upstream context if the sample is a reply. Use it only to resolve pronouns ("it" = whatever the parent was about). The signal must come from the reply itself, not the upstream.

---

## Step 2 — personal_use (per drug)

Decide first: did the author personally use this drug?

- **`yes`** — author describes their own experience with this drug (taking it, having taken it, side effects from it, results from it).
- **`no`** — questions to others, hearsay, advice, citing studies, hypothetical or planned use, mentions of someone else's experience, or a reply that doesn't itself express personal use even if the parent did.

If `personal_use = no`, **stop here for this drug-row**: leave `sentiment` and `signal_strength` blank (or `n/a`), still record `confidence` (how sure are you the personal-use call is right?), and move on. Non-personal-use rows are useful for IRR on the personal-use decision but don't enter the per-drug sentiment analysis.

## Step 3 — sentiment (per drug, only when personal_use = yes)

Pick one for each drug-row:

- **`positive`** — author personally used this drug and it helped them. Includes partial improvement ("helped but wasn't a miracle" = **positive, not mixed**).
- **`negative`** — author personally used this drug and it didn't help, made things worse, or they stopped because it wasn't working.
- **`mixed`** — genuinely conflicting outcomes ("helped pain but worsened sleep"), author explicitly can't decide. Use sparingly.
- **`neutral`** — author personally used this drug but explicitly takes no position on whether it helped (rare; usually means `personal_use = no` was the right call).

---

## Step 4 — signal_strength (per drug, only when personal_use = yes)

*A property of the **post**, not of your coding. Measures how informative the author's report on this drug is to a reader.*

- **`strong`** — any one of: quantified improvement, named specific symptom improving, clear temporal attribution, dramatic outcome, emphatic endorsement ("game changer", "wish I started sooner", "nothing else worked"), or emphatic effect language ("helps a lot", "did nothing"). **Hedging doesn't downgrade** — "I'm still sick but LDN changed my life" is `strong`.
- **`moderate`** — simple affirm/deny without emphasis ("it works for me", "yes", "it helps").
- **`weak`** — drug named in a stack without specific credit, slight or uncertain effect, or still using without complaint.
- **`n/a`** — when `personal_use = no` (no personal use to rate).

---

## Step 5 — confidence (1–5)

*A property of **your coding**, not of the post. Independent of signal strength. Always filled, including when `personal_use = no`.*

| Situation | `personal_use` | `signal_strength` | `confidence` |
|---|---|---|---|
| "LDN 4.5mg cut my fatigue 70% in 6 weeks" | yes | `strong` | 5 |
| "LDN helped some things but I honestly can't tell if it's the drug or pacing" | yes | `strong` | 2 |
| "I take LDN, magnesium, and H1 blockers. Doing okay." | yes | `weak` | 5 |
| "My doctor mentioned LDN but I'm not sure if I started yet" | no | `n/a` | 2 |

Use the full range — **5** unambiguous, **3** reasonable people could disagree, **1** very uncertain.

---

## Step 6 — side effects (per drug, only when personal_use = yes)

### `side_effects_reported` (yes / no)

**`yes`** when the author personally reports any side effect they experienced from THIS DRUG specifically. Includes:

- Physical side effects ("Paxlovid gave me terrible metallic taste")
- Mental/mood side effects ("SSRI made me emotionally numb")
- Dose-titration issues attributed to the drug
- Discontinuation because of intolerable side effects

**`no`** when:
- No side effects mentioned for this drug
- Side effects mentioned hypothetically or for other people
- Side effects implied but not attributed to this specific drug

Leave **blank** when `personal_use = no`.

### `side_effects_description` (free text)

Short phrase capturing what side effects, if any. Examples:

- "metallic taste, diarrhea during 5-day course"
- "insomnia first week"
- "moon face, weight gain on long-term use"

Leave blank if `side_effects_reported = no` or `personal_use = no`.

**Important — do NOT conflate side effects with lack of efficacy.** "Didn't work" is a negative `sentiment` but not a side effect. Side effects are distinct adverse experiences.

---

## Special cases

**Causal-context drugs** — author blames a treatment for causing their condition (e.g., "the Moderna shot is what gave me long COVID"): `personal_use = yes` (they did receive it), `sentiment = negative`, `signal_strength = weak`, side_effects_reported per the actual experience described, `notes = causal-context`.

**Multi-drug stacks** — one row per drug. Each gets its own `personal_use` and (if yes) its own sentiment + side-effects based on what the author says about that specific drug. If overall improvement is mentioned but no drug is specifically credited, default to `personal_use = yes` / `positive` / `weak` / no side effects per drug.

**Questions / advice / hearsay** — `personal_use = no`; sentiment, signal_strength, side_effects fields blank.

**No treatments mentioned at all** — single row with `drug_mention_verbatim = NONE`, all other annotation fields blank, `confidence = 5`.

**Irrelevant mentions** (drug mentioned only in a subreddit name, URL, signature) — don't code.

---

## Worked examples

Format: `drug / personal_use / sentiment / signal_strength / confidence / side_effects_reported / side_effects_description / notes`

**1 — personal use, positive, strong, no side effects:**
*"I started LDN 4.5mg 6 months ago and my fatigue dropped by probably 70%."*
→ LDN / yes / positive / strong / 5 / no / (blank) / *quantified improvement*

**2 — multi-drug stack (one row per drug):**
*"I'm on LDN, H1 blockers, and magnesium. Probably 40% better than a year ago. LDN made me jittery the first week."*
→ Three rows, same sample_id:
- LDN / yes / positive / weak / 4 / yes / "jittery first week" / in stack
- H1 blockers / yes / positive / weak / 4 / no / (blank) / in stack
- magnesium / yes / positive / weak / 4 / no / (blank) / in stack

**3 — question, no personal use:**
*"Has anyone tried paxlovid late — like, more than 5 days after onset?"*
→ paxlovid / no / (blank) / n/a / 5 / (blank) / (blank) / *question to others*

**4 — mixed with side effect:**
*"LDN definitely helped my pain — but tanked my sleep for the first 2 months. Still worth it."*
→ LDN / yes / mixed / strong / 5 / yes / "sleep disruption first 2 months" / *helped pain, hurt sleep*

**5 — causal-context:**
*"I was fine until my second Pfizer shot. That's when everything started."*
→ Pfizer / yes / negative / weak / 4 / no / (blank) / *causal-context*

**6 — negative, side-effect-driven:**
*"Took Paxlovid for 5 days. Terrible metallic taste, couldn't finish. Didn't notice any improvement either."*
→ Paxlovid / yes / negative / strong / 5 / yes / "metallic taste, stopped early" / *no perceived effect*

**7 — no drugs:**
*"Today was really rough. Spent most of the day in bed."*
→ NONE / (blank) / (blank) / (blank) / 5 / (blank) / (blank) / *no drug mentioned*

**8 — reply without personal use:**
Parent: "LDN has been a game-changer for my PEM."
Reply: "How did you get your doctor to prescribe it?"
→ LDN / no / (blank) / n/a / 5 / (blank) / (blank) / *reply doesn't express personal use*

---

## Process reminders

Code blind — don't look at AI coder outputs, don't discuss with other coders until everyone's done. Code in one sitting if possible. When stuck, code your best guess with `confidence = 1 or 2` plus a note explaining the ambiguity.

## Decision tree per drug-row

```
For each drug in the post:

personal_use = ?
├── no  (question / hearsay / advice / hypothetical /  → no
│       reply doesn't express personal use)              / sentiment blank
│                                                        / signal_strength = n/a
│                                                        / side_effects_* blank
│                                                        / record confidence
│
└── yes  (author describes own experience)             → yes / fill all below

           sentiment = ?
           ├── this drug helped (even partially)       → positive
           ├── this drug didn't help or made worse     → negative
           ├── opposing effects from this drug         → mixed
           └── personal use but no position taken      → neutral (rare)

           signal_strength = ?
           ├── quantified / named symptom / dramatic /
           │     emphatic endorsement / emphatic effect → strong
           ├── simple affirm or deny, no detail         → moderate
           └── in a stack, no specific credit           → weak

           side_effects_reported = ?
           ├── author describes adverse experience
           │     from THIS drug                         → yes (+ describe)
           └── no side effects mentioned for this drug  → no

           confidence = 1..5
           (always — including for personal_use = no)
```

---

## What changed from v1.3 / v1.4

- **v1.4 (draft, never shipped) experimentally dropped `side_effects_reported` and `side_effects_description` in favour of just adding `personal_use`.** Reviewer feedback was to keep the side-effects pair in addition to the new `personal_use` column.
- **v1.5 is the union:** `personal_use` (added in v1.4) is kept, AND `side_effects_reported` / `side_effects_description` (from v1.3) are kept. Final schema has 10 coder-filled columns: `sample_id, coder_id, drug_mention_verbatim, personal_use, sentiment, signal_strength, confidence, side_effects_reported, side_effects_description, notes`.
- **`personal_use` gates everything else.** When `personal_use = no`, sentiment, signal_strength, side_effects_reported, and side_effects_description are all blank (or `n/a` where applicable). Confidence is always recorded.
- **Single-schema templates.** Both the 300-pilot and 500-pilot `coder_output_template.csv` files share the v1.5 schema.
- Updated worked examples (8 cases, all show the side-effects columns) and decision tree (now includes the side-effects branch).

*v1.5 · pilot run with explicit `personal_use` flag plus per-drug side-effects dimension. Matches `coder_output_template.csv` schema in both `docs/irr_pilot/` and `docs/irr_pilot_500/`.*
