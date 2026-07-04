"""Runtime helpers for analysis Rumi agents and OpenRouter checks."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from rumi import World


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def load_analysis_env() -> None:
    """Load local env files without printing secrets."""
    load_dotenv(REPO_ROOT / ".env")
    load_dotenv(Path.home() / "dr" / ".env")
    load_dotenv()


def require_openrouter_key() -> str:
    """Return the OpenRouter key or raise a clear error."""
    load_analysis_env()
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to .env or the environment "
            "before running live A1 model calls."
        )
    return key


def analysis_world(*, data_dir: str | Path | None = None) -> World:
    """Create a Rumi world for analysis runs."""
    load_analysis_env()
    if data_dir is None and not os.environ.get("RUMI_DATA_DIR"):
        data_dir = tempfile.mkdtemp(prefix="patientpunk-a1-rumi-")
    return World(data_dir=data_dir)


def check_openrouter(model: str, *, timeout_seconds: float = 60.0) -> dict[str, Any]:
    """Make a tiny OpenRouter request to verify key and model reachability."""
    key = require_openrouter_key()
    from openai import OpenAI

    client = OpenAI(
        api_key=key,
        base_url=os.environ.get("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL),
        timeout=timeout_seconds,
    )
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with exactly: OK"}],
        temperature=0,
        max_tokens=8,
    )
    usage = getattr(response, "usage", None)
    content = response.choices[0].message.content if response.choices else ""
    return {
        "model": model,
        "content": content,
        "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
        "completion_tokens": getattr(usage, "completion_tokens", None) if usage else None,
        "total_tokens": getattr(usage, "total_tokens", None) if usage else None,
    }

