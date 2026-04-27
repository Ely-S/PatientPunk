# intervention_config.py
# Prompts for the drug mention pipeline

# Used by extract_mentions.py
# Note: in the future we may include diet and lifestyle changes. 
EXTRACT_PROMPT = """\
For each text below, list all drugs, medications, supplements, and medical interventions mentioned.
Include brand names, generic names, abbreviations (e.g. LDN, LDA), informal names,
drug categories (e.g. "antihistamines", "h1 blocker", "beta blocker"), enzymes/supplements
(e.g. "DAO", "probiotics", "nattokinase"), and generic references (e.g. "an oral antibiotic").
Do not include diet and lifestyle changes!!!
Return ONLY a JSON array of arrays — one inner array per text, each containing lowercase strings.
If none are mentioned, use an empty array [].
Example: [["ldn", "low dose naltrexone"], ["h1 antihistamines", "dao", "nattokinase"], ["oral antibiotic", "probiotic"], []]
"""


# Used by canonicalize.py
#TODO: potentially change this with: https://github.com/Ely-S/PatientPunk/pull/2#discussion_r3047716889
CANONICALIZE_COMPOUND_PROMPT = """\
You are given a list of drug/supplement/intervention names extracted from Reddit posts.
Your job is to identify true synonyms — names that refer to the exact same drug or compound.

Rules:
- Only group names if they refer to the EXACT same drug or compound.
- Do NOT group a specific drug into a broader category.
  e.g. "famotidine" and "antihistamines" are related but NOT the same — keep separate.
- Brand names and generic names for the same drug ARE synonyms.
  e.g. "pepcid" and "famotidine" → same drug → merge.
- Abbreviations for the same drug ARE synonyms.
  e.g. "ldn" and "low dose naltrexone" → same drug → merge.
- Choose the most common/recognizable name as the canonical form.

Return a JSON object containing ONLY synonym merges.
For each group of synonymous names, map the non-canonical name(s) to the canonical form.
Omit any name that has no synonyms in the list — it will be treated as canonical by default.
The canonical form itself does NOT need to appear as a key unless it also maps to another canonical.
Example input: ["ldn", "low dose naltrexone", "pepcid", "famotidine", "aspirin", "ibuprofen"]
Example output: {"low dose naltrexone": "ldn", "pepcid": "famotidine"}
(aspirin and ibuprofen are omitted because they have no synonyms in the input.)
"""

# Used by get_drug_aliases() in utilities/__init__.py — single-drug mode alias lookup
def drug_aliases_prompt(target: str) -> str:
    return (
        f"List common names, abbreviations, brand names, generic names, "
        f"and plausible misspellings/typos for the drug, supplement, or intervention "
        f"'{target}'. Return ONLY a JSON array of lowercase strings — no prose. "
        f"Include the canonical name. Only include names a reader might plausibly "
        f"write for this exact substance; do not enumerate every dosage variant. "
        f"Return at most 30 entries."
    )


# Used by classify_sentiment.py (prefilter step)
# Note: in the future we may include diet and lifestyle changes. 
# Additionally, we may want to change the semantics of the reply. 
PREFILTER_PROMPT = """\
For each item below, answer ONLY 'yes' or 'no':
Does the AUTHOR express personal experience with the specified treatment?
"Treatment" includes drugs, supplements, but not diet and lifestyle changes!!!
IMPORTANT: Use the "Replying to" context to resolve what the comment refers to.
Short replies like "Helps me", "wasn't for me", "same here" count as YES if the
upstream comment establishes the treatment and the reply expresses personal experience.
Answer 'no' if:
- The author is asking someone else if they have tried it (e.g. "Have you tried X?")
- The author is discussing research, articles, or studies rather than personal use
- The reply is just encouragement, thanks, or off-topic (e.g. "Congrats!", "Ok thanks")
Return a JSON array of strings, each 'yes' or 'no', in order.
"""

# Used by classify_sentiment.py
def system_prompt(drug: str, synonyms: list[str] | None = None, subreddit: str = "Long COVID") -> str:
    """Generate system prompt for sentiment classification."""
    # Keep acronyms uppercase, title-case regular words
    name = drug.upper() if drug.isalpha() and len(drug) <= 4 else drug.title()
    synonym_note = ""
    if synonyms:
        synonym_note = f"\nAlso known as: {', '.join(synonyms)}"
    return f"""\
Classify Reddit posts/comments about {name} from r/{subreddit}.

You are identifying whether the author has personally used or tried: {name}{synonym_note}

sentiment: positive | negative | mixed | neutral
  positive = {name} helped them personally
  negative = {name} didn't help or made things worse
  mixed    = reserved for genuine ambiguity. Use ONLY when:
             - a symptom actively WORSENED on one axis while improving on another,
               e.g. "helped my fatigue but made my anxiety worse"
             - OR the author explicitly cannot tell if it helped overall
             NOT mixed — these are POSITIVE:
             - side effects during benefit: "it helped but caused insomnia at first"
             - dose-titration struggles: "4.5mg was bad, 3mg is good for me"
             - some symptoms responded, others didn't improve: "works for inflammation, this foot pain is stubborn"
             - partial improvement: "it helped but wasn't a miracle"
             - using it "on and off" in a medication stack
  neutral  = the author has NOT personally used or tried {name} — includes:
             questions, advice to others, citing studies or statistics,
             discussing the evidence base, expressing opinions about the research
             or skepticism about efficacy WITHOUT reporting personal use,
             posts about OTHER drugs that happen to appear in a {name} thread,
             third-person framing ("works for some people", "many find it helpful")
             WITHOUT a first-person outcome statement in this reply,
             author has used {name} but this post/reply does not state whether it helped
             (e.g. logistical questions about dosage, quitting, interactions)

  THE KEY QUESTION: has this person personally used or tried {name}?
  If no → neutral, regardless of how strong their opinion about the evidence is.
  If yes → positive / negative / mixed based on their outcome.

signal: strong | moderate | weak | n/a
  strong   = any of:
             - quantified improvement (steps, HRV, named symptoms improving)
             - named specific symptom improvement (cognitive, sleep, PEM threshold, fatigue, pain)
             - clear temporal attribution ("after 6 weeks I was certain", "after 3 months improved")
             - dramatic outcome ("sleep through the night for the first time in 30 years")
             - emphatic personal endorsement placing it among the author's most important
               treatments: "holy trinity", "game changer", "best thing I've tried",
               "wish I started sooner", "nothing else worked", "this is what finally helped",
               "changed my life", naming it as one of a small defining set of treatments,
               or any similarly strong personal framing
             - emphatic language about the effect even without specifics:
               "helps me a lot", "really helps", "did nothing", "no effect at all",
               "tried X times and it never worked", "a lot", "so much better"
             NOTE: hedging ("still sick", "cautiously optimistic") does NOT downgrade strong
  moderate = simple affirmation or negation without emphasis or detail
             ("it works for me", "for me it is", "yes", "it helps")
             OR listed explicitly among the author's most successful treatments
  weak     = still using without complaint, mentioned in a stack without ranking,
             slight or uncertain effect, or improvement noted while on multiple drugs
             where {name} is named but not specifically credited
  n/a      = neutral entry

MULTIPLE DRUGS: If the author takes {name} alongside other treatments and reports
  improvement, classify as positive/weak if {name} is named in the stack.
  Only use mixed if the author themselves expresses uncertainty about whether it helped.

REPLY CHAIN: Upstream comment text is context only — use it to understand what pronouns refer to.
  Signal must come from the reply itself.
  - Reply expresses a personal reaction or experience, even without naming {name} → use upstream comment for context
    e.g. "I love it too", "same here, it helped me a lot" → positive (upstream comment establishes what "it" is)
  - Reply contains NO personal experience or opinion about {name} → neutral / n/a
    e.g. "How did you get reinfected?", "Which doctor prescribed it?", "Hope you feel better" → neutral
  - Reply discusses a DIFFERENT treatment or topic than {name} → neutral / n/a
    Even if {name} appears in upstream comments, if the reply has moved on to a different subject,
    the author is NOT expressing experience with {name}.
    WATCH FOR SIMILAR-ABBREVIATION CONFUSION: drugs with similar names or abbreviations
    (e.g. LDN = low-dose naltrexone vs LDA = low-dose abilify) often appear together in
    the same thread. If the reply only discusses one of them, do NOT attribute it to the other.
    e.g. parent mentions both LDN and LDA; reply says "I tried LDA at 0.02mg and everything was
    worse" → if {name} is LDN, this is neutral/n/a (the reply is about LDA, not LDN).
  KEY: ask — does this reply express how the AUTHOR feels about {name}? If no → neutral/n/a.

side_effects: list of short lowercase strings naming any side effects the author attributes to {name}
  Include only effects the author reports experiencing personally from {name} — not hypothetical,
  not things they read about, not effects from other drugs.
  Use the author's wording, trimmed to the symptom: "gave me insomnia" → "insomnia",
  "made my anxiety way worse" → "anxiety", "brain fog got bad" → "brain fog".
  Collapse obvious duplicates within a single entry. If none reported, use [].
  This applies to positive/negative/mixed entries alike — a positive report can still list
  tolerable side effects ("it helped but caused insomnia at first" → positive/strong, side_effects=["insomnia"]).

  LIST FANOUT: when a symptom description applies to multiple drugs in a list, attribute it to
  EVERY drug in that list, including {name} if it appears.
  e.g. "Effexor, Pristiq, and Cymbalta all made me feel really bad" → if {name} is Cymbalta,
  side_effects=["felt really bad"]. Do not drop {name} just because other drugs share the symptom.

  GENERIC SIDE-EFFECT REFERENCES: when the author says they experienced side effects from {name}
  but doesn't name a specific symptom, capture the phrase they used.
  e.g. "couldn't tolerate the side effects" → ["side effects"], "I had a bad reaction" → ["bad reaction"],
  "I reacted badly to it" → ["bad reaction"]. Do NOT invent a specific symptom if none was named.

  INTERACTIONS: if a symptom arises only from combining {name} with another drug and {name} alone
  is tolerated, side_effects=[] for {name}. Attribute the problem to the MODIFYING drug instead.
  e.g. "I'm on Vyvanse and fluvoxamine enhances the effects, not in a positive way" →
  side_effects=[] for Vyvanse (it was fine alone); the issue belongs on fluvoxamine.

  CAUSE vs EFFECT: do NOT list symptoms caused by the CONDITION being treated, or by a DEFICIENCY
  of {name}, as side effects of {name}. A side effect is something the drug/substance CAUSED in
  the author, not something it was used to treat.
  e.g. "vitamin D deficiency gave me depression before fixing it" → side_effects=[] for vitamin D
  (depression was caused by the deficiency, and vitamin D resolved it — it is not a side effect).
  e.g. "LDN helped my fatigue" → side_effects=[] (fatigue is the condition being treated, not a side effect).

Respond ONLY with JSON: {{"sentiment":"...","signal":"...","side_effects":[...]}}"""
