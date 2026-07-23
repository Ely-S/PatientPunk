"""The attribution basis must be recorded, not decided in the prompt.

Judgement 5 measured that crediting a collective outcome ("this stack helped") to every named
treatment inflates the per-drug positive rate ~5%. Suppressing it instead (the group guard) loses
the outcome entirely. Recording WHY the outcome is attached to the drug keeps both readings
available, so the group/no-group choice happens at query time.
"""
from pathlib import Path

import pytest
from pydantic import ValidationError

from models import ClassificationResult
from prompts.intervention_config import system_prompt



def test_attribution_defaults_to_specific():
    # a model that omits the field must behave exactly as before
    r = ClassificationResult(sentiment="positive", signal="strong")
    assert r.attribution == "specific"


def test_a_model_inventing_parse_failed_cannot_suppress_its_own_classification():
    """parse_failed is ours, not the model's — it means "we could not read this reply".

    ClassificationResult was validated straight from LLM JSON, so a model echoing the schema
    back (or hallucinating the key) set the flag on a perfectly good classification. The writer
    gate then dropped the row while the audit filed it as a parse failure. Raised by the
    grok-4.5 review panel.
    """
    from models import ClassificationResult

    result = ClassificationResult.from_llm(
        {"sentiment": "positive", "signal": "strong", "parse_failed": True}
    )
    assert result.parse_failed is False
    assert result.sentiment == "positive"
