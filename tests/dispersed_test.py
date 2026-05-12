"""Tests for the Dispersed compute integration (src/utilities/dispersed/).

We exercise three things:
  1. HMAC-SHA256 signing (auth.make_headers) — deterministic, no network.
  2. DispersedLLMClient end-to-end with a stub DispersedAPIClient + stub OpenAI
     client — proves llm_call() routes correctly without touching real Dispersed.
  3. Fallback path — when no recipe is configured, the wrapper delegates to a
     fallback Anthropic-shaped client.
"""
from __future__ import annotations

import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from utilities.dispersed.api_client import DispersedAPIClient, DispersedAPIError
from utilities.dispersed.auth import EMPTY_BODY_SHA256, make_headers
from utilities.dispersed.llm_client import DispersedLLMClient


# ─────────────────────────────────────────────────────────────────────────────
# 1. Auth: deterministic HMAC signing
# ─────────────────────────────────────────────────────────────────────────────
class TestAuth:
    def test_headers_contain_all_four_required_fields(self):
        h = make_headers(
            public_key="pk_test", secret_key="sk_test",
            method="GET", path="/v1/jobs",
            _timestamp_ms=1_700_000_000_000, _nonce="a" * 32,
        )
        assert set(h) == {"X-API-Key", "X-Time", "X-Nonce", "X-Signature"}
        assert h["X-API-Key"] == "pk_test"
        assert h["X-Time"] == "1700000000000"
        assert h["X-Nonce"] == "a" * 32

    def test_signature_matches_canonical_string(self):
        """End-to-end: hand-compute the expected HMAC and compare."""
        ts, nonce = 1_700_000_000_000, "a" * 32
        h = make_headers(
            public_key="pk_x", secret_key="sk_x",
            method="GET", path="/v1/jobs",
            query={"limit": "10"}, body=b"",
            _timestamp_ms=ts, _nonce=nonce,
        )
        canonical = f"pk_x|{ts}|{nonce}|GET|/v1/jobs|limit=10|{EMPTY_BODY_SHA256}"
        expected = hmac.new(b"sk_x", canonical.encode(), hashlib.sha256).hexdigest()
        assert h["X-Signature"] == expected

    def test_query_params_sorted_alphabetically(self):
        """Signing must be order-independent on query params."""
        ts, nonce = 1_700_000_000_000, "b" * 32
        h1 = make_headers(
            "pk", "sk", "GET", "/v1/jobs",
            query={"z": "1", "a": "2"}, body=b"",
            _timestamp_ms=ts, _nonce=nonce,
        )
        h2 = make_headers(
            "pk", "sk", "GET", "/v1/jobs",
            query={"a": "2", "z": "1"}, body=b"",
            _timestamp_ms=ts, _nonce=nonce,
        )
        assert h1["X-Signature"] == h2["X-Signature"]

    def test_body_sha256_in_canonical(self):
        """Non-empty body is hashed and folded into the canonical string."""
        ts, nonce = 1_700_000_000_000, "c" * 32
        body = b'{"recipe_uuid":"abc"}'
        h = make_headers(
            "pk", "sk", "POST", "/v1/jobs", body=body,
            _timestamp_ms=ts, _nonce=nonce,
        )
        body_sha = hashlib.sha256(body).hexdigest()
        canonical = f"pk|{ts}|{nonce}|POST|/v1/jobs||{body_sha}"
        expected = hmac.new(b"sk", canonical.encode(), hashlib.sha256).hexdigest()
        assert h["X-Signature"] == expected

    def test_empty_keys_rejected(self):
        with pytest.raises(ValueError):
            make_headers("", "sk", "GET", "/v1/jobs")
        with pytest.raises(ValueError):
            make_headers("pk", "", "GET", "/v1/jobs")


# ─────────────────────────────────────────────────────────────────────────────
# 2. API client: extract_endpoint() handles the various job-response shapes
# ─────────────────────────────────────────────────────────────────────────────
class TestAPIClientHelpers:
    def test_extract_endpoint_top_level_url(self):
        assert DispersedAPIClient.extract_endpoint(
            {"endpoint_url": "https://job-123.dispersed.com"}
        ) == "https://job-123.dispersed.com"

    def test_extract_endpoint_nested_container(self):
        assert DispersedAPIClient.extract_endpoint(
            {"container": {"public_url": "https://x.example"}}
        ) == "https://x.example"

    def test_extract_endpoint_host_port_fallback(self):
        assert DispersedAPIClient.extract_endpoint(
            {"network": {"host": "10.0.0.5", "port": 8000}}
        ) == "http://10.0.0.5:8000"

    def test_extract_endpoint_missing(self):
        assert DispersedAPIClient.extract_endpoint({"status": "PENDING"}) is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. DispersedLLMClient: full path with stubbed API + stubbed OpenAI
# ─────────────────────────────────────────────────────────────────────────────
def _stub_api_client(running_jobs=None, created_job=None, wait_result=None):
    """Build a MagicMock that quacks like a DispersedAPIClient."""
    api = MagicMock(spec=DispersedAPIClient)
    api.list_jobs.return_value = running_jobs or []
    api.create_job.return_value = created_job or {"uuid": "new-job-uuid"}
    api.wait_for_running.return_value = wait_result or {
        "uuid": "new-job-uuid",
        "status": "RUNNING",
        "endpoint_url": "http://10.0.0.7:8000",
    }
    # The static method needs the real implementation
    api.extract_endpoint = DispersedAPIClient.extract_endpoint
    return api


def _install_fake_openai(monkeypatch, captured_calls: list, reply_text: str = "hi"):
    """Replace OpenAI() in llm_client with a stub that records calls."""
    class _FakeChat:
        def __init__(self):
            self.completions = self

        def create(self, **kwargs):
            captured_calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=reply_text))]
            )

    class _FakeOpenAI:
        def __init__(self, *_, **__):
            self.chat = _FakeChat()

        def with_options(self, **_):
            return self  # ignore base_url override for the test

    import utilities.dispersed.llm_client as mod
    monkeypatch.setattr(mod, "OpenAI", _FakeOpenAI)


class TestDispersedLLMClient:
    def test_reuses_existing_running_job(self, monkeypatch):
        """If a RUNNING job already exists for the recipe, no new job is started."""
        api = _stub_api_client(running_jobs=[{
            "uuid": "existing-job",
            "status": "RUNNING",
            "endpoint_url": "http://10.0.0.9:8000",
        }])
        calls: list = []
        _install_fake_openai(monkeypatch, calls, reply_text="hello from vllm")

        client = DispersedLLMClient(
            recipe_map={"Qwen/Qwen3-8B": "recipe-fast-uuid"},
            api_client=api,
        )

        with client.messages.stream(
            model="Qwen/Qwen3-8B", max_tokens=50,
            messages=[{"role": "user", "content": "hi"}],
        ) as s:
            text = s.get_final_message().content[0].text

        assert text == "hello from vllm"
        api.list_jobs.assert_called_once()
        api.create_job.assert_not_called()
        api.wait_for_running.assert_not_called()
        # OpenAI was called with the right model + messages
        assert calls[0]["model"] == "Qwen/Qwen3-8B"
        assert calls[0]["messages"] == [{"role": "user", "content": "hi"}]
        assert calls[0]["max_tokens"] == 50

    def test_starts_new_job_when_none_running(self, monkeypatch):
        """No running job → create one, wait for RUNNING, then call it."""
        api = _stub_api_client(
            running_jobs=[],
            created_job={"uuid": "new-job", "status": "PENDING"},
            wait_result={
                "uuid": "new-job", "status": "RUNNING",
                "endpoint_url": "http://10.0.0.10:8000",
            },
        )
        calls: list = []
        _install_fake_openai(monkeypatch, calls)

        client = DispersedLLMClient(
            recipe_map={"Qwen/Qwen3-8B": "recipe-fast-uuid"},
            api_client=api,
        )
        with client.messages.stream(
            model="Qwen/Qwen3-8B", max_tokens=10,
            messages=[{"role": "user", "content": "x"}],
        ) as s:
            s.get_final_message().content[0].text

        api.list_jobs.assert_called_once()
        api.create_job.assert_called_once_with(
            "recipe-fast-uuid", task_type="PERSISTENT",
        )
        api.wait_for_running.assert_called_once()

    def test_caches_endpoint_across_calls(self, monkeypatch):
        """Second llm_call for same model should NOT hit the Dispersed API again."""
        api = _stub_api_client(running_jobs=[{
            "uuid": "j", "status": "RUNNING",
            "endpoint_url": "http://10.0.0.1:8000",
        }])
        calls: list = []
        _install_fake_openai(monkeypatch, calls)

        client = DispersedLLMClient(
            recipe_map={"Qwen/Qwen3-8B": "uuid-fast"},
            api_client=api,
        )
        for _ in range(3):
            with client.messages.stream(
                model="Qwen/Qwen3-8B", max_tokens=10,
                messages=[{"role": "user", "content": "x"}],
            ) as s:
                s.get_final_message().content[0].text

        assert api.list_jobs.call_count == 1   # endpoint cached
        assert len(calls) == 3                  # but 3 OpenAI calls fired

    def test_routes_fast_vs_strong_to_different_recipes(self, monkeypatch):
        """Two different models should resolve to two different jobs."""
        def list_jobs_side_effect(*, recipe_uuid, **_):
            uuid = "fast-job" if recipe_uuid == "uuid-fast" else "strong-job"
            host = "10.0.0.1" if uuid == "fast-job" else "10.0.0.2"
            return [{"uuid": uuid, "status": "RUNNING",
                     "endpoint_url": f"http://{host}:8000"}]

        api = _stub_api_client()
        api.list_jobs.side_effect = list_jobs_side_effect
        calls: list = []
        _install_fake_openai(monkeypatch, calls)

        client = DispersedLLMClient(
            recipe_map={
                "Qwen/Qwen3-8B": "uuid-fast",
                "Qwen/Qwen3-32B": "uuid-strong",
            },
            api_client=api,
        )
        with client.messages.stream(model="Qwen/Qwen3-8B", max_tokens=10,
                                     messages=[{"role": "user", "content": "x"}]) as s:
            s.get_final_message().content[0].text
        with client.messages.stream(model="Qwen/Qwen3-32B", max_tokens=10,
                                     messages=[{"role": "user", "content": "y"}]) as s:
            s.get_final_message().content[0].text

        assert api.list_jobs.call_count == 2
        # Each model triggered exactly one list_jobs lookup with its own recipe_uuid
        recipe_args = {c.kwargs["recipe_uuid"] for c in api.list_jobs.call_args_list}
        assert recipe_args == {"uuid-fast", "uuid-strong"}

    def test_system_prompt_converted_to_openai_format(self, monkeypatch):
        """Anthropic top-level `system` → OpenAI 'system' message at index 0."""
        api = _stub_api_client(running_jobs=[{
            "uuid": "j", "status": "RUNNING",
            "endpoint_url": "http://10.0.0.1:8000",
        }])
        calls: list = []
        _install_fake_openai(monkeypatch, calls)

        client = DispersedLLMClient(
            recipe_map={"Qwen/Qwen3-8B": "uuid"},
            api_client=api,
        )
        with client.messages.stream(
            model="Qwen/Qwen3-8B", max_tokens=10,
            messages=[{"role": "user", "content": "hello"}],
            system="you are terse",
        ) as s:
            s.get_final_message().content[0].text

        assert calls[0]["messages"] == [
            {"role": "system", "content": "you are terse"},
            {"role": "user", "content": "hello"},
        ]


# ─────────────────────────────────────────────────────────────────────────────
# 4. Fallback path
# ─────────────────────────────────────────────────────────────────────────────
class TestFallback:
    def test_no_recipe_for_model_falls_back(self, monkeypatch):
        """Asking for a model not in recipe_map → uses fallback if set."""
        api = _stub_api_client()
        # Build a fallback that returns "fallback-text"
        fallback = MagicMock()
        fallback.messages.stream.return_value.__enter__.return_value.get_final_message.return_value = \
            SimpleNamespace(content=[SimpleNamespace(text="fallback-text")])
        fallback.messages.stream.return_value.__exit__.return_value = None

        client = DispersedLLMClient(
            recipe_map={"Qwen/Qwen3-8B": "uuid"},  # only fast configured
            api_client=api,
            fallback_client=fallback,
        )
        with client.messages.stream(
            model="some-other-model",  # not in recipe_map
            max_tokens=10,
            messages=[{"role": "user", "content": "x"}],
        ) as s:
            text = s.get_final_message().content[0].text

        assert text == "fallback-text"
        fallback.messages.stream.assert_called_once()
        api.create_job.assert_not_called()

    def test_no_fallback_raises(self):
        api = _stub_api_client()
        client = DispersedLLMClient(
            recipe_map={"Qwen/Qwen3-8B": "uuid"},
            api_client=api,
            fallback_client=None,
        )
        with pytest.raises(DispersedAPIError):
            with client.messages.stream(
                model="unknown-model", max_tokens=10,
                messages=[{"role": "user", "content": "x"}],
            ) as s:
                s.get_final_message().content[0].text
