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

from utilities import _ORClient, _ORMessages  # noqa: E402


class _FakeChunk:
    def __init__(self, text=None, finish=None):
        delta = SimpleNamespace(content=text)
        self.choices = [SimpleNamespace(delta=delta, finish_reason=finish)]


class _FakeCompletions:
    """Records the kwargs it was called with, replays a canned stream."""

    def __init__(self, chunks):
        self.chunks, self.seen = chunks, {}

    def create(self, **kwargs):
        self.seen = kwargs
        return iter(self.chunks)


def _client(chunks):
    comp = _FakeCompletions(chunks)
    inner = SimpleNamespace(chat=SimpleNamespace(completions=comp))
    return _ORClient(inner), comp


def test_reasoning_is_disabled_on_every_call():
    """The whole point. Without this the model thinks first and the answer is
    truncated by a budget sized only for the answer."""
    client, comp = _client([_FakeChunk("ok", finish="stop")])
    with client.messages.stream(model="m", messages=[{"role": "user", "content": "hi"}],
                                max_tokens=100) as s:
        s.get_final_message()
    assert comp.seen["extra_body"]["reasoning"] == {"effort": "none"}


def test_it_streams():
    """A canonicalization batch has run 710s; a non-streaming call would hit the
    client timeout well before that."""
    client, comp = _client([_FakeChunk("a"), _FakeChunk("b", finish="stop")])
    with client.messages.stream(model="m", messages=[{"role": "user", "content": "hi"}],
                                max_tokens=100) as s:
        msg = s.get_final_message()
    assert comp.seen["stream"] is True
    assert msg.content[0].text == "ab", "chunks are concatenated in order"


def test_truncation_is_reported_in_the_anthropic_spelling():
    """check_response keys off stop_reason == 'max_tokens'. OpenAI says 'length',
    so a mistranslation here would make every truncation invisible."""
    client, _ = _client([_FakeChunk("partial", finish="length")])
    with client.messages.stream(model="m", messages=[{"role": "user", "content": "hi"}],
                                max_tokens=10) as s:
        assert s.get_final_message().stop_reason == "max_tokens"


def test_a_normal_finish_is_end_turn():
    client, _ = _client([_FakeChunk("done", finish="stop")])
    with client.messages.stream(model="m", messages=[{"role": "user", "content": "hi"}],
                                max_tokens=10) as s:
        assert s.get_final_message().stop_reason == "end_turn"


def test_the_system_prompt_becomes_a_system_message():
    """Anthropic passes `system` beside the messages; OpenAI wants it inside them."""
    client, comp = _client([_FakeChunk("ok", finish="stop")])
    with client.messages.stream(model="m", messages=[{"role": "user", "content": "q"}],
                                system="be terse", max_tokens=10) as s:
        s.get_final_message()
    assert comp.seen["messages"] == [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "q"},
    ]


def test_caller_supplied_extra_body_survives():
    client, comp = _client([_FakeChunk("ok", finish="stop")])
    msgs = _ORMessages(SimpleNamespace(chat=SimpleNamespace(completions=comp)))
    with msgs.stream(model="m", messages=[{"role": "user", "content": "hi"}],
                     max_tokens=10, extra_body={"seed": 7}) as s:
        s.get_final_message()
    assert comp.seen["extra_body"]["seed"] == 7
    assert comp.seen["extra_body"]["reasoning"] == {"effort": "none"}


def test_empty_chunks_do_not_crash_the_accumulator():
    """Real streams contain keep-alive chunks with no choices."""
    empty = SimpleNamespace(choices=[])
    client, _ = _client([empty, _FakeChunk("x", finish="stop")])
    with client.messages.stream(model="m", messages=[{"role": "user", "content": "hi"}],
                                max_tokens=10) as s:
        assert s.get_final_message().content[0].text == "x"
