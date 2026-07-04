"""Prompt-context rendering for comment coding experiments."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

from dev.analysis.a0_extraction.comment_context import Comment, CommentContext


CONTEXT_RENDERER_VERSION = "comment_context_prompt_v0.1"
DEFAULT_ANCESTOR_DEPTH = 2
DEFAULT_PREVIOUS_SIBLING_LIMIT = 2
DEFAULT_PREVIOUS_THREAD_LIMIT = 3
DEFAULT_MAX_BODY_CHARS = 1200
DEFAULT_MAX_TOTAL_CHARS = 16000


@dataclass(frozen=True)
class ContextRenderConfig:
    """Deterministic context-rendering settings for A1."""

    ancestor_depth: int = DEFAULT_ANCESTOR_DEPTH
    previous_sibling_limit: int = DEFAULT_PREVIOUS_SIBLING_LIMIT
    previous_thread_limit: int = DEFAULT_PREVIOUS_THREAD_LIMIT
    max_body_chars: int = DEFAULT_MAX_BODY_CHARS
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"renderer_version": CONTEXT_RENDERER_VERSION}


def stable_text_hash(text: str) -> str:
    """Return a stable SHA-256 digest for rendered prompt text."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def short_hash(text: str, length: int = 10) -> str:
    """Return a short stable hash for non-semantic identifiers."""
    return stable_text_hash(text)[:length]


def context_comment_ids(context: CommentContext) -> list[str]:
    """IDs present as context, excluding the target comment."""
    seen = {context.target.id}
    ids: list[str] = []
    for comment in [
        *context.ancestors,
        *context.previous_siblings,
        *context.previous_thread_comments,
    ]:
        if comment.id not in seen:
            ids.append(comment.id)
            seen.add(comment.id)
    return ids


def render_context_for_prompt(
    context: CommentContext,
    config: ContextRenderConfig | None = None,
) -> str:
    """Render a comment and its available reply context for the coding prompt."""
    config = config or ContextRenderConfig()
    parts = [
        f"CONTEXT_RENDERER_VERSION: {CONTEXT_RENDERER_VERSION}",
        f"THREAD_ID: {context.target.link_id}",
        (
            "TARGET_COMMENT: "
            f"id={context.target.id} source_line={context.target.source_line} "
            f"date_utc={context.target.date_utc} parent_kind={context.target.parent_kind}"
        ),
        "",
        "Use context only to resolve references in TARGET_COMMENT.",
        "Extract claims only when TARGET_COMMENT itself states or adopts them.",
        "",
    ]

    if context.ancestors:
        parts.append("ANCESTORS_OLDEST_TO_NEWEST:")
        for depth, ancestor in reversed(list(enumerate(context.ancestors, start=1))):
            label = "PARENT_COMMENT" if depth == 1 else f"ANCESTOR_COMMENT_{depth}"
            parts.append(render_comment_block(label, ancestor, config.max_body_chars))
            parts.append("")

    if context.previous_siblings:
        parts.append("PREVIOUS_SIBLINGS_SAME_PARENT:")
        for index, sibling in enumerate(context.previous_siblings, start=1):
            parts.append(render_comment_block(f"PREVIOUS_SIBLING_{index}", sibling, config.max_body_chars))
            parts.append("")

    if context.previous_thread_comments:
        parts.append("PREVIOUS_THREAD_COMMENTS_BEFORE_TARGET:")
        for index, prior in enumerate(context.previous_thread_comments, start=1):
            parts.append(render_comment_block(f"PREVIOUS_THREAD_{index}", prior, config.max_body_chars))
            parts.append("")

    parts.append("TARGET_COMMENT_TO_CODE:")
    parts.append(render_comment_block("TARGET_COMMENT", context.target, config.max_body_chars))

    if context.missing:
        parts.append("")
        parts.append("MISSING_CONTEXT:")
        for key, value in sorted(context.missing.items()):
            parts.append(f"- {key}: {value}")

    rendered = "\n".join(parts)
    return truncate_total(rendered, config.max_total_chars)


def render_comment_block(label: str, comment: Comment, max_body_chars: int) -> str:
    """Render one comment with stable metadata and bounded body text."""
    author_hash = short_hash(comment.author or "unknown")
    header = (
        f"[{label} id={comment.id} source_line={comment.source_line} "
        f"date_utc={comment.date_utc} score={comment.score} "
        f"author_hash={author_hash}]"
    )
    return f"{header}\n{truncate_body(comment.body, max_body_chars)}"


def truncate_body(text: str, max_chars: int) -> str:
    """Normalize and truncate a comment body for prompt rendering."""
    cleaned = (text or "").replace("\r", " ").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max(0, max_chars - 15)].rstrip() + "\n[TRUNCATED]"


def truncate_total(text: str, max_chars: int) -> str:
    """Keep a rendered prompt context under a total character cap."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 31)].rstrip() + "\n[CONTEXT_TRUNCATED_FOR_PROMPT]"

