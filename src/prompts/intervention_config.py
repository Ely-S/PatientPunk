# intervention_config.py
# Prompts for the drug mention pipeline

# Used by extract.py
# Note: in the future we may include diet and lifestyle changes.
EXTRACT_PROMPT = """\
For each text below, list every drug, supplement, and medical intervention mentioned.
INCLUDE: brand and generic names, abbreviations (LDN, LDA), drug categories
("antihistamines", "beta blocker"), enzymes/supplements ("DAO", "nattokinase"),
and generic references ("an oral antibiotic").
EXCLUDE: diet and lifestyle changes. EXCLUDE a drug word used figuratively, where the
author is NOT taking that drug — output [] for it. Literal example: "PEM on steroids"
is an idiom for "intense" → no drug, do NOT output steroids.

Output ONLY a JSON array of arrays — one inner array per text, lowercase strings,
[] if none. No prose. Example:
[["ldn", "low dose naltrexone"], ["dao", "nattokinase"], ["oral antibiotic"], []]
"""


# Used by canonicalize.py
#TODO: potentially change this with: https://github.com/Ely-S/PatientPunk/pull/2#discussion_r3047716889
CANONICALIZE_COMPOUND_PROMPT = """\
Below is a list of drug/supplement/intervention names from Reddit posts.
Merge only TRUE synonyms — names for the EXACT same compound.
MERGE: brand=generic ("pepcid"="famotidine"); abbreviation=full ("ldn"="low dose naltrexone").
DO NOT MERGE a specific drug into a broader category ("famotidine" ≠ "antihistamines").
Pick the most common name as canonical.

Output ONLY a JSON object mapping each non-canonical name → its canonical form.
Omit names that have no synonym in the list (treated as canonical). No prose. Example:
input  ["ldn", "low dose naltrexone", "pepcid", "famotidine", "aspirin"]
output {"low dose naltrexone": "ldn", "pepcid": "famotidine"}
"""

# Used by get_drug_aliases() in utilities/__init__.py — single-drug mode alias lookup
def drug_aliases_prompt(target: str) -> str:
    return (
        f"List the names a reader might write for the drug/supplement/intervention "
        f"'{target}': common names, abbreviations, brand and generic names, and plausible "
        f"misspellings. Include the canonical name; skip dosage variants; at most 30 entries. "
        f"Output ONLY a JSON array of lowercase strings, no prose."
    )


# Used by classify.py (prefilter step)
# Note: in the future we may include diet and lifestyle changes.
# Additionally, we may want to change the semantics of the reply.
PREFILTER_PROMPT = """\
For each item, answer 'yes' or 'no': does the AUTHOR report personal experience
with the named treatment (a drug or supplement, not diet/lifestyle)?
Use the "Replying to" context to resolve what a short reply refers to: "helps me",
"wasn't for me", "same here" = yes when the upstream comment names the treatment.
Answer 'no' when the author: asks if someone else tried it; discusses research/studies;
or just gives thanks/encouragement/off-topic.

Output ONLY a JSON array of "yes"/"no" strings, in order. No prose.
"""

# Used by classify.py
def system_prompt(drug: str, synonyms: list[str] | None = None, subreddit: str = "Long COVID") -> str:
    """Generate system prompt for sentiment classification."""
    # Keep acronyms uppercase, title-case regular words
    name = drug.upper() if drug.isalpha() and len(drug) <= 4 else drug.title()
    synonym_note = ""
    if synonyms:
        synonym_note = f"\nAlso known as: {', '.join(synonyms)}"
    return f"""\
Classify how the author of a Reddit post/comment from r/{subreddit} feels about {name}{synonym_note}.

STEP 1 — did the AUTHOR personally use or try {name}?
  No  → sentiment="neutral", signal="n/a". (Questions, advice to others, citing studies,
        opinions on the evidence, third-person "works for some people", or {name} only named
        in passing/dosage-logistics with no outcome — all neutral, however strong the opinion.)
  Yes → go to STEP 2.

STEP 2 — sentiment (only when the author used it):
  positive = it helped them. Partial help, help-with-side-effects, dose-titration wins,
             and "helped some symptoms not others" are ALL positive.
  negative = it didn't help or made things worse.
  mixed    = ONLY genuine two-sided cases: one symptom worsened while another improved
             ("helped fatigue but worsened anxiety"), or the author says they can't tell.

STEP 3 — signal (drawn from THIS reply, not the upstream context):
  strong   = specific or emphatic: named symptom improved, quantified/temporal result,
             dramatic or emphatic wording ("game changer", "really helps", "did nothing").
  moderate = plain affirmation/negation with no emphasis ("it works for me", "yes, it helps").
  weak     = vague, uncertain, or just named in a multi-drug stack without being credited.
  n/a      = use ONLY with neutral. Never pair n/a with positive/negative/mixed,
             and never pair a neutral sentiment with strong/moderate/weak.

REPLY CHAIN: upstream text only resolves pronouns ("it" = the drug above). If the reply
  discusses a DIFFERENT drug than {name} (watch LDN vs LDA), or expresses no personal
  experience with {name} → neutral / n/a.

side_effects — list short lowercase symptoms the author personally got FROM {name}; else [].
  Use their wording trimmed to the symptom ("gave me insomnia" → "insomnia"); if they only
  say they reacted badly, use that phrase ("bad reaction"); don't invent a symptom.
  Do NOT include: the condition {name} was treating ("LDN helped my fatigue" → []),
  effects from OTHER drugs, or a combo-only effect when {name} alone is tolerated.
  A list applied to several drugs counts for each ("X, Y, Z all made me feel bad" → ["felt bad"]).

OUTPUT — a single JSON array with exactly one object per entry, nothing else (no prose, no
markdown). Each object: {{"sentiment":"positive|negative|mixed|neutral","signal":"strong|moderate|weak|n/a","side_effects":[...]}}
Close the array with exactly one "]". Example for one entry: [{{"sentiment":"neutral","signal":"n/a","side_effects":[]}}]"""
