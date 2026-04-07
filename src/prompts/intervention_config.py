# intervention_config.py
# Prompts for the drug mention pipeline

SIGNAL_WEIGHTS = {
    "strong":     3,
    "moderate":   2,
    "weak":       1,
}


# Used by extract_mentions.py
EXTRACT_PROMPT = """\
For each text below, list all drugs, medications, supplements, and medical interventions mentioned.
Include brand names, generic names, abbreviations (e.g. LDN, LDA), and informal names.
Return ONLY a JSON array of arrays — one inner array per text, each containing lowercase strings.
If none are mentioned, use an empty array [].
Example: [["ldn", "low dose naltrexone"], ["famotidine", "pepcid"], []]
"""


# Used by canonicalize.py
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

Return a JSON object mapping every input name to its canonical form.
Every input name must appear as a key. If a name has no synonyms in the list, map it to itself.
Example: {"ldn": "ldn", "low dose naltrexone": "ldn", "pepcid": "famotidine", "famotidine": "famotidine"}
"""

# Used by classify_sentiment.py (prefilter step)
PREFILTER_PROMPT = """\
For each item below, answer ONLY 'yes' or 'no':
Does the AUTHOR express personal experience with the specified drug/intervention?
Also 'yes' if the reply implies it works by saying NOT doing it made things worse.
Answer 'no' if:
- The author is asking someone else if they have tried it (e.g. "Have you tried X?")
- The author is discussing research, articles, or studies rather than personal use
Return a JSON array of strings, each 'yes' or 'no', in order.
"""

# Used by classify_sentiment.py
def system_prompt(drug: str, synonyms: list[str] | None = None) -> str:
    """Generate system prompt for sentiment classification."""
    # Keep acronyms uppercase, title-case regular words
    name = drug.upper() if drug.isalpha() and len(drug) <= 4 else drug.title()
    synonym_note = ""
    if synonyms:
        synonym_note = f"\nAlso known as: {', '.join(synonyms)}"
    return f"""\
Classify Reddit posts/comments about {name} from a Long COVID subreddit.

You are identifying whether the author has personally used or tried: {name}{synonym_note}

sentiment: positive | negative | mixed | neutral
  positive = {name} helped them personally
  negative = {name} didn't help or made things worse
  mixed    = genuinely conflicting outcomes (helped some symptoms but worsened others)
             or the author explicitly can't decide whether it helped.
             NOTE: partial improvement is still positive, not mixed.
             "it helped but wasn't a miracle" = positive. "it helped X but worsened Y" = mixed.
  neutral  = the author has NOT personally used or tried {name} — includes:
             questions, advice to others, citing studies or statistics,
             discussing the evidence base, expressing opinions about the research
             or skepticism about efficacy WITHOUT reporting personal use,
             posts about OTHER drugs that happen to appear in a {name} thread

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

REPLY CHAIN: Ancestor text is context only — use it to understand what pronouns refer to.
  Signal must come from the reply itself.
  - Reply expresses a personal reaction or experience, even without naming {name} → use ancestor for context
    e.g. "I love it too", "same here, it helped me a lot" → positive (ancestor establishes what "it" is)
  - Reply contains NO personal experience or opinion about {name} → neutral / n/a
    e.g. "How did you get reinfected?", "Which doctor prescribed it?", "Hope you feel better" → neutral
  KEY: ask — does this reply express how the AUTHOR feels about {name}? If no → neutral/n/a.

Respond ONLY with JSON: {{"sentiment":"...","signal":"..."}}"""
