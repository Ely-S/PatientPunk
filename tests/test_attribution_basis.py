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


def test_attribution_accepts_collective():
    r = ClassificationResult(sentiment="positive", signal="weak", attribution="collective")
    assert r.attribution == "collective"


def test_attribution_rejects_unknown_values():
    with pytest.raises(ValidationError):
        ClassificationResult(sentiment="positive", signal="weak", attribution="maybe")


def test_prompt_defines_both_attribution_values():
    p = system_prompt("ldn")
    assert "attribution: specific | collective" in p
    # the model must still report the sentiment — the field records the basis, it does not suppress
    assert "do NOT downgrade or suppress a collective" in p


def test_trailing_response_schema_includes_attribution():
    """Models mirror the final schema line; omitting attribution there means the key is dropped
    and ClassificationResult silently defaults it to "specific" — re-baking the bias the field
    exists to expose."""
    tail = system_prompt("ldn").rsplit("Respond ONLY with JSON:", 1)[-1]
    assert "attribution" in tail
