"""Version manifest for the A1 comment-coding instrument."""

from __future__ import annotations

from dev.analysis.agents.CommentCoderAgent.brain.prompts import PROMPT_VERSION
from dev.analysis.agents.CommentCoderAgent.schemas import SCHEMA_VERSION
from dev.analysis.agents._common.render_context import CONTEXT_RENDERER_VERSION


TASK_NAME = "comment_coding"
SCHEMA_NAME = "comment_coding"
PROMPT_NAME = "comment_coder"
DEFAULT_MODEL = "openai/gpt-oss-120b"
STRONG_COMPARATOR_MODEL = "anthropic/claude-sonnet-4"
CONTEXT_DEFAULTS = {
    "ancestor_depth": 2,
    "previous_sibling_limit": 2,
    "previous_thread_limit": 3,
    "max_body_chars": 1200,
    "max_total_chars": 16000,
}


def manifest() -> dict:
    """Return a serializable instrument manifest for run records."""
    return {
        "task_name": TASK_NAME,
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "prompt_name": PROMPT_NAME,
        "prompt_version": PROMPT_VERSION,
        "context_renderer_version": CONTEXT_RENDERER_VERSION,
        "default_model": DEFAULT_MODEL,
        "strong_comparator_model": STRONG_COMPARATOR_MODEL,
        "context_defaults": CONTEXT_DEFAULTS,
    }

