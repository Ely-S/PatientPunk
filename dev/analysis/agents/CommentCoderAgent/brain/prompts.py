"""Prompt loading for CommentCoderAgent."""

from __future__ import annotations

from pathlib import Path

from dev.analysis.agents._common.render_context import CONTEXT_RENDERER_VERSION


PROMPT_VERSION = "comment_coder_v0.1"
PROMPT_FILE = "comment_coder_v0.1.md"
PROMPT_PATH = Path(__file__).resolve().parents[3] / "a1_coding_research" / "prompts" / PROMPT_FILE


def load_instructions() -> str:
    """Load the versioned system prompt text."""
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


INSTRUCTIONS = load_instructions()


def build_message(rendered_context: str) -> str:
    """Build the user message for one rendered context."""
    return (
        f"Prompt version: {PROMPT_VERSION}\n"
        f"Context renderer version: {CONTEXT_RENDERER_VERSION}\n\n"
        "Code the TARGET_COMMENT below using the response schema.\n\n"
        f"{rendered_context}"
    )

