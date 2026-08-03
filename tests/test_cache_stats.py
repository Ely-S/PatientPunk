"""Report how much prompt input came from OpenRouter's cache. No API calls.

DeepSeek caches implicitly, so there is nothing to switch on and no way to tell
whether it fired without asking. Whether it fires depends on the workload's
shape rather than any setting: classify sends a per-drug system prompt, and a
drug with a single batch can never hit its own cache. On a 19,275-item probe,
1,581 of 1,755 drugs made exactly one call.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

os.environ["LLM_PROVIDER"] = "anthropic"

from utilities import _CacheStats, _ORClient  # noqa: E402


def _usage(prompt, cached):
    return SimpleNamespace(prompt_tokens=prompt,
                           prompt_tokens_details=SimpleNamespace(cached_tokens=cached))


def test_it_reports_the_hit_rate_and_the_saving():
    s = _CacheStats()
    s.record(_usage(1000, 0))     # cold
    s.record(_usage(1000, 900))   # warm
    out = s.summary()
    assert "2 calls" in out and "2,000 prompt tokens" in out
    assert "900 served from cache (45.0%)" in out
    # cached input bills at 0.1x, so the saving is 90% of the hit rate
    assert "~40.5% off input cost" in out


def test_no_calls_is_not_a_division_by_zero():
    assert _CacheStats().summary() == "no LLM calls"


def test_a_provider_that_omits_the_detail_block_is_not_a_crash():
    """Not every provider returns prompt_tokens_details."""
    s = _CacheStats()
    s.record(SimpleNamespace(prompt_tokens=500))
    assert "0 served from cache" in s.summary()


def test_counting_is_thread_safe():
    """The pipeline runs 50-250 workers; a lost update would understate the rate."""
    s = _CacheStats()
    def hammer():
        for _ in range(200):
            s.record(_usage(10, 5))
    ts = [threading.Thread(target=hammer) for _ in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert s.calls == 1600
    assert s.prompt_tokens == 16000 and s.cached_tokens == 8000


class _FakeCompletions:
    def __init__(self, chunks): self.chunks, self.seen = chunks, {}
    def create(self, **kw):
        self.seen = kw
        return iter(self.chunks)


def test_usage_is_requested_and_read_off_the_final_chunk():
    """The usage chunk carries no choices, so it must be read before the
    choices-less skip -- and include_usage is what makes it arrive at all."""
    from utilities import CACHE_STATS
    before = CACHE_STATS.calls
    content = SimpleNamespace(choices=[SimpleNamespace(
        delta=SimpleNamespace(content="ok"), finish_reason="stop")])
    usage_chunk = SimpleNamespace(choices=[], usage=_usage(300, 250))
    comp = _FakeCompletions([content, usage_chunk])
    client = _ORClient(SimpleNamespace(chat=SimpleNamespace(completions=comp)))
    with client.messages.stream(model="m", messages=[{"role": "user", "content": "hi"}],
                                max_tokens=10) as s:
        msg = s.get_final_message()
    assert comp.seen["stream_options"] == {"include_usage": True}
    assert msg.content[0].text == "ok", "the usage chunk must not break accumulation"
    assert CACHE_STATS.calls == before + 1
