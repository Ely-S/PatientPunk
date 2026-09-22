# twitter_intervention_config.py
# Twitter variants of the drug-mention pipeline prompts.
#
# The sentiment/signal/side-effect rubric is platform-neutral, so rather than
# fork a near-identical copy (which would drift), these wrappers reuse the
# canonical prompts from intervention_config.py and swap only the
# platform-specific wording. If the canonical header changes shape, the
# assertion below fails loudly instead of silently shipping Reddit wording
# to a Twitter run.

from prompts import intervention_config as _base

_TWEET_NOTE = (
    "These are tweets: ignore @mention chains, hashtags (#LongCovid etc.), and "
    "t.co links when judging content — they are not part of the author's claim.\n"
)

# Prefilter: the canonical prompt has no Reddit-specific wording; prepend the
# tweet-artifact note so short/noisy tweets are judged on their substance.
PREFILTER_PROMPT = _TWEET_NOTE + _base.PREFILTER_PROMPT


def system_prompt(drug: str, synonyms: list[str] | None = None, source: str = "twitter") -> str:
    """Twitter-worded classifier system prompt; rubric identical to Reddit's."""
    name = drug.upper() if drug.isalpha() and len(drug) <= 4 else drug.title()
    base = _base.system_prompt(drug, synonyms, subreddit="__PLATFORM__")
    reddit_header = f"Classify Reddit posts/comments about {name} from r/__PLATFORM__."
    assert reddit_header in base, (
        "intervention_config.system_prompt header changed; "
        "update twitter_intervention_config.system_prompt to match"
    )
    twitter_header = (
        f"Classify Twitter posts (tweets) about {name}.\n{_TWEET_NOTE}"
    )
    return base.replace(reddit_header, twitter_header, 1) + _drug_effect_addendum(name)


def _drug_effect_addendum(name: str) -> str:
    """Rubric addendum separating drug-effect sentiment from circumstance.

    Each rule traces to an observed misclassification on the Twitter LDN
    corpus (price complaints coded negative, discontinuation-withdrawal coded
    negative, declined prescriptions coded as use, partial-benefit coded
    mixed). Twitter-only until validated; candidate for the canonical rubric.
    """
    return f"""

DRUG EFFECT vs CIRCUMSTANCE: sentiment describes only what {name} did to the
author's health — not their feelings about obtaining it.
- Complaints about cost, insurance, shortages, pharmacies, or prescribers are
  NOT drug sentiment. If the only negativity is access/logistics, classify from
  the stated health outcome ("been taking it for years" + price complaint →
  positive/weak, not negative).
- Symptoms RETURNING after stopping or running out of {name} is evidence it was
  WORKING → positive, not negative.
- Choosing NOT to take {name} (fear of side effects, waiting on a doctor,
  saving it for later) means no personal use → neutral. Balking is not a
  negative outcome.
- Clear reported benefit plus uncertainty about OTHER symptoms ("helped my pain
  tremendously, not sure about PEM") is positive, not mixed — reserve mixed for
  the cases already defined above."""
