"""OpenRouter must be reached on the surface that honours `reasoning`. No API calls.

OpenRouter has two surfaces. Its Anthropic Skin silently DROPS the `reasoning`
parameter -- the request returns 200 and the field is ignored -- while its OpenAI
surface honours it. deepseek/deepseek-v4-flash spends output tokens thinking
before it answers, and those count against max_tokens, so unsuppressed reasoning
blew every per-stage budget in src/.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

os.environ["LLM_PROVIDER"] = "anthropic"

from utilities import _ORClient  # noqa: E402


def _chunk(text=None, finish=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=text),
                                 finish_reason=finish)])


def _client(chunks):
    """Returns the shim plus the fake completions object, which records kwargs."""
    comp = SimpleNamespace(seen={})
    comp.create = lambda **kw: (comp.seen.update(kw), iter(chunks))[1]
    return _ORClient(SimpleNamespace(chat=SimpleNamespace(completions=comp))), comp


def _run(client, **kw):
    kw.setdefault("messages", [{"role": "user", "content": "hi"}])
    with client.messages.stream(model="m", max_tokens=100, **kw) as s:
        return s.get_final_message()


def test_reasoning_is_disabled_and_the_call_still_streams():
    """The whole point. Streaming is kept because a canonicalization batch has
    run 710s -- a non-streaming call would hit the client timeout first."""
    client, comp = _client([_chunk("ok", finish="stop")])
    _run(client)
    assert comp.seen["extra_body"]["reasoning"] == {"effort": "none"}
    assert comp.seen["stream"] is True


@pytest.mark.parametrize("openai_reason, anthropic_reason",
                         [("length", "max_tokens"), ("stop", "end_turn")])
def test_finish_reason_is_translated(openai_reason, anthropic_reason):
    """check_response keys off stop_reason == 'max_tokens'. OpenAI says 'length',
    so a mistranslation here makes every truncation invisible."""
    client, _ = _client([_chunk("partial", finish=openai_reason)])
    assert _run(client).stop_reason == anthropic_reason


def test_the_system_prompt_becomes_a_system_message():
    """Anthropic passes `system` beside the messages; OpenAI wants it inside them.
    Get this wrong and every prompt silently loses its system block. The empty
    chunk is a keep-alive, which real streams contain."""
    client, comp = _client([_chunk(), _chunk("a"), _chunk("b", finish="stop")])
    msg = _run(client, messages=[{"role": "user", "content": "q"}], system="be terse")
    assert comp.seen["messages"] == [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "q"},
    ]
    assert msg.content[0].text == "ab", "chunks concatenate in order, empties skipped"
