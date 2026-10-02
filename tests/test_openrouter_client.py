from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import openai

import utilities


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
