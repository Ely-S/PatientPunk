from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import openai
import pytest

import utilities
from patientpunk import llm_cache
from patientpunk._utils import LLMContentFilteredError, LLMResponseError, is_transient_failure


def test_get_client_uses_openrouter_openai_endpoint(monkeypatch):
    backend = Mock()
    constructor = Mock(return_value=backend)
    monkeypatch.setattr(utilities, "LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(openai, "OpenAI", constructor)

    client = utilities.get_client()

    constructor.assert_called_once_with(
        api_key="test-key",
        base_url="https://openrouter.ai/api/v1",
        max_retries=4,
        timeout=600.0,
    )
    assert client.messages._client is backend


def test_openrouter_adapter_contract(monkeypatch):
    backend = Mock()
    backend.chat.completions.create.return_value = iter([
        SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content="ok"), finish_reason="length",
        )]),
    ])
    monkeypatch.setattr(utilities, "_REASONING_OFF", True)
    monkeypatch.setattr(utilities, "LLM_PROVIDER_ORDER", [])
    client = utilities._ORClient(backend)

    with client.messages.stream(
        model="model",
        max_tokens=100,
        system="be terse",
        messages=[{"role": "user", "content": "hi"}],
    ) as stream:
        message = stream.get_final_message()

    backend.chat.completions.create.assert_called_once_with(
        stream=True,
        model="model",
        messages=[
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "hi"},
        ],
        max_tokens=100,
        temperature=0.0,
        extra_body={"reasoning": {"effort": "none"}},
    )
    assert message.content[0].text == "ok"
    assert message.stop_reason == "max_tokens"


def test_a_pinned_upstream_provider_is_sent_without_fallback(monkeypatch):
    backend = Mock()
    backend.chat.completions.create.return_value = iter([
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="ok"), finish_reason="stop")])])
    monkeypatch.setattr(utilities, "_REASONING_OFF", True)
    monkeypatch.setattr(utilities, "LLM_PROVIDER_ORDER", ["together"])

    with utilities._ORClient(backend).messages.stream(model="m", messages=[{"role": "user", "content": "hi"}]) as s:
        s.get_final_message()

    assert backend.chat.completions.create.call_args.kwargs["extra_body"] == {
        "reasoning": {"effort": "none"}, "provider": {"order": ["together"], "allow_fallbacks": False}}


def test_llm_call_sends_the_pinned_provider_through_its_retries(monkeypatch):
    # llm_call reaches the client through with_retries and _request_once (#232): the pin must
    # survive that path, on the retried request too.
    reply = [SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="ok"), finish_reason="stop")])]
    backend = Mock()
    backend.chat.completions.create.side_effect = [httpx.ConnectError("dropped"), iter(reply)]
    monkeypatch.setattr(utilities, "_REASONING_OFF", True)
    monkeypatch.setattr(utilities, "LLM_PROVIDER_ORDER", ["together"])
    monkeypatch.setattr("patientpunk._utils.RETRY_DELAYS", (0, 0, 0, 0))
    llm_cache.set_cache_enabled(False)
    try:
        assert utilities.llm_call(utilities._ORClient(backend), "hi", model="m") == "ok"
    finally:
        llm_cache.set_cache_enabled(None)
    pins = [c.kwargs["extra_body"]["provider"] for c in backend.chat.completions.create.call_args_list]
    assert pins == [{"order": ["together"], "allow_fallbacks": False}] * 2


@pytest.mark.parametrize(
    ("content", "finish_reason", "refusal"),
    [
        ('{"age": null, "conditions": []}', "content_filter", None),
        (None, "content_filter", None),
        (None, "stop", "Request refused"),
    ],
    ids=["filtered-json", "filtered-empty", "refusal-delta"],
)
def test_openrouter_refusals_raise_before_caching(monkeypatch, content, finish_reason, refusal):
    monkeypatch.setenv("LLM_CACHE", "1")
    backend = Mock()
    backend.chat.completions.create.return_value = iter([
        SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content=content, refusal=refusal), finish_reason=finish_reason,
        )]),
    ])

    with pytest.raises(LLMContentFilteredError):
        utilities.llm_call(utilities._ORClient(backend), "Synthetic demographics prompt")

    assert not list(llm_cache.cache_root().rglob("*.json"))


def _chunk(content=None, finish_reason=None):
    return SimpleNamespace(choices=[SimpleNamespace(
        delta=SimpleNamespace(content=content, refusal=None), finish_reason=finish_reason)])


def test_openrouter_stream_that_errors_midway_is_not_cached(monkeypatch):
    monkeypatch.setenv("LLM_CACHE", "1")
    backend = Mock()
    backend.chat.completions.create.return_value = iter([_chunk('{"age": 3'), _chunk(None, "error")])

    with pytest.raises(LLMResponseError):
        utilities.llm_call(utilities._ORClient(backend), "Synthetic partial stream")

    assert not list(llm_cache.cache_root().rglob("*.json"))


def test_openrouter_http_content_filter_fails_the_item(monkeypatch):
    monkeypatch.setenv("LLM_CACHE", "0")
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    backend = Mock()
    backend.chat.completions.create.side_effect = openai.BadRequestError(
        "Input blocked by content filter", response=httpx.Response(400, request=request), body=None)

    with pytest.raises(LLMContentFilteredError):
        utilities.llm_call(utilities._ORClient(backend), "Synthetic filtered prompt")


@pytest.mark.parametrize(
    ("message", "transient"),
    [("provider_unavailable: upstream overloaded", True), ("something else broke", False)],
)
def test_openrouter_in_band_errors_are_transient_only_when_the_provider_says_so(message, transient):
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    assert is_transient_failure(openai.APIError(message, request=request, body=None)) is transient
