from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import openai
import pytest

import utilities
from patientpunk import llm_cache
from patientpunk._utils import LLMContentFilteredError


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


# --- Content-filter blocks through the real OpenAI SDK (#53) -----------------
# A fake OpenRouter answers with the bodies its errors reference documents
# (https://openrouter.ai/docs/api-reference/errors), so the SDK's own parsing
# decides what llm_call sees. Only metadata is matched, never message wording.

def _chunk(content=None, finish_reason=None, **extra) -> dict:
    return {"id": "gen-1", "object": "chat.completion.chunk", "created": 0, "model": "m",
            "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": finish_reason}],
            **extra}


def _error(code: int, message: str, **metadata) -> dict:
    return {"code": code, "message": message, "metadata": metadata}


MODERATION_403 = _error(403, "Your input was flagged", reasons=["violence"],
                        flagged_input="...", provider_name="OpenAI", model_slug="openai/gpt-4o")
POLICY_403 = _error(403, "Blocked by the provider", error_type="content_policy_violation",
                    provider_code="SAFETY")
REFUSAL_403 = _error(403, "The model declined", error_type="refusal")
BUDGET_403 = _error(403, "Budget limit exceeded (weekly limit). Contact your org admin.",
                    limit_source="openrouter_key_limit", scope="key", limit_usd=50,
                    spend_usd=52, resets_at=None, remedy_hint="raise the limit")
CREDITS_402 = {"code": 402, "message": "Insufficient credits"}


def _fake_openrouter(*, status=200, error=None, stream=()):
    """An _ORClient over the real SDK, served by a handler that counts requests."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if error is not None:
            return httpx.Response(status, json={"error": error})
        events = "".join(f"data: {json.dumps(c)}\n\n" for c in stream) + "data: [DONE]\n\n"
        return httpx.Response(200, content=events.encode(),
                              headers={"content-type": "text/event-stream"})

    backend = openai.OpenAI(api_key="test-key", base_url="https://openrouter.ai/api/v1",
                            max_retries=0,
                            http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    return utilities._ORClient(backend), calls


@pytest.fixture
def _no_cache():
    llm_cache.set_cache_enabled(False)
    yield
    llm_cache.set_cache_enabled(None)


@pytest.mark.usefixtures("_no_cache")
@pytest.mark.parametrize("fake", [
    dict(status=403, error=MODERATION_403),
    dict(status=403, error=POLICY_403),
    dict(status=403, error=REFUSAL_403),
    # Headers already sent as 200, so the block arrives as the stream's last chunk.
    dict(stream=[_chunk('{"a": '),
                 _chunk("", "error", error=_error(403, "Output flagged",
                                                  error_type="content_policy_violation"))]),
    dict(stream=[_chunk('{"a": '), _chunk(None, "content_filter")]),
], ids=["moderation-403", "policy-403", "refusal-403", "policy-midstream", "finish-content-filter"])
def test_openrouter_content_filter_block_skips_the_item(fake):
    client, calls = _fake_openrouter(**fake)

    with pytest.raises(LLMContentFilteredError):
        utilities.llm_call(client, "prompt", model="m")
    assert len(calls) == 1  # not retried: the same prompt is blocked again


@pytest.mark.usefixtures("_no_cache")
@pytest.mark.parametrize(("fake", "raised"), [
    (dict(status=403, error=BUDGET_403), openai.PermissionDeniedError),
    (dict(status=402, error=CREDITS_402), openai.APIStatusError),
], ids=["budget-403", "credits-402"])
def test_openrouter_account_errors_still_stop_the_run(fake, raised):
    client, _ = _fake_openrouter(**fake)

    with pytest.raises(raised) as info:
        utilities.llm_call(client, "prompt", model="m")
    assert not isinstance(info.value, LLMContentFilteredError)


@pytest.mark.usefixtures("_no_cache")
def test_openrouter_reply_still_returns_text():
    client, _ = _fake_openrouter(stream=[_chunk("ok"), _chunk(None, "stop")])

    assert utilities.llm_call(client, "prompt", model="m") == "ok"
