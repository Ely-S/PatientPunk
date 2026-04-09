# LDN (Low Dose Naltrexone) -- Analysis Notes
**Source:** `subreddit_posts.json` (100 posts, ~1,100 comments from r/covidlonghaulers)
**Full data:** `ldn_mentions.json` (29 classified entries, 24 users)

---

## Detection Method

LDN mentions were captured via:
1. **Direct keyword**: `\bldn\b` or `\bnaltrex`
2. **Implied dose**: comments in LDN-post threads containing doses in the 0.1–4.9mg range (characteristic of LDN; standard naltrexone is 50mg)
3. **Reply chain propagation**: comments that reply to an LDN comment, even without naming LDN -- e.g. *"I do 1mg and like it"* replying to *"I like LDN at 0.5mg"*

Alternate spellings checked: `LND` (transposition), `naltrexene`, `naltrexon` -- none found in this sample.

---

## Coverage

| | Count |
|---|---|
| Posts directly about LDN | 4 |
| Posts where LDN surfaces in comments (contextual) | 6 |
| Total users with LDN mentions | 24 |
| Total classified entries | 29 |

The 6 contextual posts -- where LDN wasn't the topic but appeared in comments -- tend to carry higher signal. Users volunteering LDN unprompted (e.g. in a symptoms post, a recovery AMA) often have a strong opinion about it.

---

## Classification Definitions

### Sentiment

| Label | Meaning | Examples |
|---|---|---|
| **positive** | LDN helped this person -- symptoms improved, quality of life better, or currently using it without complaint as part of a treatment protocol | "All my symptoms improved dramatically", "holy trinity", "went from housebound to walking", "I use LDN and propranolol for my nervous system" |
| **negative** | LDN made things worse, caused side effects not worth tolerating, or produced zero effect after genuine trial | "Put me in a crash", "no changes unfortunately after 6mg" |
| **mixed** | Partially helped but also caused problems, stopped working over time, or benefit is real but limited | "Worked for a while then stopped", "helped with fevers but stomach pain", "doing better but PEM still triggers" |
| **neutral** | No personal experience claim -- the comment is a question, access info, social reply, research summary, or future intent. Nothing to classify. | "What is LDN?", "I will try it soon", "you can get it via AgelessRx" |

Key rules:
- Improvement in baseline counts as positive, even if not cured
- A comment is negative even if the person plans to retry -- the experience itself was negative
- **Currently using LDN without complaint = positive (weak)** -- continuing use implies it's working well enough to stay on
- **LDN mentioned as part of a recovery protocol = positive (weak minimum)** -- if the person is recovering and LDN is part of what they're doing, that's an implicit endorsement
- **LDN in a list that led to improvement = positive (moderate)** -- e.g. "took LDN + ketotifen + ivabradine and went from 1500 to 7000 steps"
- **LDN explicitly ranked as "most successful" or "holy trinity" = positive (strong)** -- even in a list context

### Signal Strength

Signal strength measures how much we can trust the sentiment claim -- how clear, specific, and attributable it is.

| Label | Meaning | Examples |
|---|---|---|
| **strong** | Clear, unambiguous personal outcome. Specific before/after, named symptoms, duration, or explicit "best" ranking | "Housebound → walking neighborhood in 2 weeks", "PEM threshold higher, HRV improved", "most successful for me" list |
| **moderate** | Real outcome but with meaningful uncertainty -- early results (days/weeks), effect that stopped, dose still being found, or one symptom only | "Noticed improvement after 3 days", "worked for a while", "doing better on 0.75mg, still increasing" |
| **weak** | Small, vague, or partial effect -- or simply continued use without complaint. If someone is still taking LDN and doesn't flag a problem, that persistence is itself a weak positive signal. | "Minor improvements", "helps a bit with fevers", "helps with cognitive stuff", "I use LDN and propranolol for my nervous system" |
| **confounded** | Person is on multiple medications simultaneously and explicitly says they can't tell which one helped | "I'm also on LDN, so I'm not sure which medication helped" |

Signal strength is independent of sentiment -- a negative can be strong (HRV-verified crash) or moderate (felt terrible briefly). A positive can be weak (minor improvements) or strong (dramatic baseline shift).

---

## Sentiment × Signal Matrix (entry-level, 29 entries)

| | strong | moderate | weak | confounded | **TOTAL** |
|---|---|---|---|---|---|
| **positive** | 12 | 4 | 6 | 0 | **22** |
| **mixed** | 0 | 3 | 0 | 1 | **4** |
| **negative** | 2 | 1 | 0 | 0 | **3** |
| **TOTAL** | **14** | **8** | **6** | **1** | **29** |

---

## User-Level Summary (24 users)

| Sentiment | Users | % |
|---|---|---|
| Positive | 17 | 71% |
| Mixed | 4 | 17% |
| Negative | 3 | 12% |

**All 24 users expressed a personal experience signal. 71% positive.**

---

## Notable Examples

### Strong Positive

> *"All of my symptoms improved dramatically [at 0.5mg]. I started noticing improvement after 3 days. It's the only thing that has helped me."*
> -- 3-year LC patient, neurological symptoms (head/eye pressure, tinnitus, brain fog, insomnia)

> *"I went from completely housebound to being able to comfortably walk around my neighborhood, go shopping, out for dinner within a couple weeks. Three years after starting I am still firmly moderate... but it definitely improved my baseline."*
> -- Still moderate/PEM after 3 years, but LDN shifted the floor dramatically

> *"With every additional 0.5mg, week on week, my musculoskeletal function seems to de-age by a year."*
> -- Vivid framing; titrating up incrementally

> *"I sleep through the night for the first time in 30 years. Only been a week of this -- I better not say too much 🤫"*
> -- Cautiously optimistic; sleep as first signal at 1.5mg / 9 months

> *"Sleep meds, antihistamines and LDN. My holy trinity."*
> -- MCAS patient; LDN as one of three cornerstone treatments

> *"LDN listed in 'most successful ones for me' for MCAS"* (alongside antihistamines, Ketotifen, DAO enzymes)
> -- List context but explicitly ranked

### Mixed

> *"LDN worked for me for a while. When you're in a space of taking one day to the next with no assumptions about tomorrow, anything that can get you from day to day is worth it even if it only works for a few weeks."*
> -- Stopped working but pragmatically endorses trying

> *"Doing better on 0.75mg, still increasing -- but PEM triggers still need to be avoided so far."*
> -- Partial improvement in progress; dose still being titrated

> *"LDN helped a bit, not much, mostly with fevers... stomach pain (think this is LDN)"*
> -- Weak positive on one symptom, possible GI side effect

### Negative

> *"LDN actually put me in a crash. Moved up slowly to 1.5 then 2mg -- was in an 8-week crash verified by wearable HRV monitor. HRV returned to baseline after cutting dose back under 1mg."*
> -- Dose-sensitive; strong negative with objective data. Notably still on LDN at <1mg.

> *"Got to 6mg for 4-5 months after 1.5, 3 and 4.5mg for awhile. No changes unfortunately."*
> -- Thorough, patient titration with no effect

> *"I tried a tiny amount before and felt terrible. I might try it again after crashing recently."*
> -- Negative first experience, still open to retry

---

## Patterns & Observations

**Dose sensitivity is prominent.** Multiple users describe a narrow therapeutic window -- one user crashed at 1.5–2mg but is fine at <1mg; another found no effect even at 6mg. The "start low, go slow" advice appears repeatedly.

**Most positive responders mention neurological or MCAS symptoms.** Head pressure, brain fog, gut issues, and sleep appear most frequently as areas of improvement. Autonomic symptoms (POTS) seem less responsive based on comments.

**The contextual mentions carry strong signal.** Users who volunteer LDN unprompted -- in a recovery AMA, a symptom thread -- tend to be enthusiastic. The "Is LDN worth it?" megathread is valuable but also surfaces more neutral/uncertain voices.

**Both negatives are data-rich.** Neither negative reporter is vague -- one used HRV wearables, the other titrated methodically across months. This suggests the negatives are trustworthy signals, not just bad experiences from incorrect use.

**LDN + antihistamines is the most common combination.** Appears together in multiple strong-positive reports (holy trinity, MCAS protocol, ketotifen + LDN stacks).

---

## User-Level Matrix -- Sentiment × Max Signal Strength (n=24)

Max signal = the strongest signal that user ever expressed across all their entries.

| | strong | moderate | weak | confounded | **TOTAL** |
|---|---|---|---|---|---|
| **positive** | 10 | 2 | 5 | 0 | **17** |
| **mixed** | 0 | 3 | 0 | 1 | **4** |
| **negative** | 2 | 1 | 0 | 0 | **3** |
| **TOTAL** | **12** | **6** | **5** | **1** | **24** |

- **10 users positive/strong** -- clear unambiguous benefit at their peak
- **Both negatives are strong signal** -- one used HRV wearable to verify crash, the other systematically titrated to 6mg
- **5 weak positives** -- modest effects, currently using without complaint, or recovery-context mentions
- **2 positive/moderate** -- one early responder (3 days in), one in a multi-drug protocol that produced major improvement

---

## Entries Per User

Most users appear once -- a single strong statement, then gone.

| Entries | Users |
|---|---|
| 1 | 22 |
| 2 | 1 |
| 5 | 1 |

The user with 5 entries (`b32bd65b82ec`) is a 3-year LC patient with neurological symptoms who made multiple follow-up comments in the "Is LDN worth it?" thread as their improvement unfolded -- all consistently positive/strong. The user with 2 entries (`f10fee3b6241`) gave both a before/after account and a separate endorsement; also consistently positive/strong.

---

## Classification Script

To classify new entries added to `ldn_mentions.json`:
```bash
source /Users/pbinder/n5env/bin/activate
export ANTHROPIC_API_KEY=your_key_here
python scripts/classify_ldn.py
```

Options: `--reclassify-all`, `--dry-run`
