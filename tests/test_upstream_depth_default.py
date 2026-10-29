"""The inheritance depth defaults to 1: a reply inherits the drug only from a parent that names it."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from run_sentiment_pipeline import _upstream_depth
from utilities import PipelineConfig


def test_cli_default_is_one_and_unlimited_is_spelled_out() -> None:
    assert _upstream_depth("1") == 1 and _upstream_depth("0") == 0
    assert _upstream_depth("unlimited") is None
    with pytest.raises(Exception):
        _upstream_depth("-1")


def test_config_default_is_one() -> None:
    assert PipelineConfig.__dataclass_fields__["max_upstream_depth"].default == 1
