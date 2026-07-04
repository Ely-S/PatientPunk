"""Public API for coding one rendered comment context."""

from __future__ import annotations

import time
import uuid
import warnings
from dataclasses import dataclass
from typing import Any

from rumi import World

from dev.analysis.agents.CommentCoderAgent.brain.prompts import PROMPT_VERSION, build_message
from dev.analysis.agents.CommentCoderAgent.main import CommentCoderAgent, configure_model
from dev.analysis.agents.CommentCoderAgent.schemas import CommentCodingResult
from dev.analysis.agents._common.runtime import analysis_world


@dataclass(frozen=True)
class CodingResponse:
    """A parsed coding result plus run metadata from Rumi/OpenRouter."""

    result: CommentCodingResult
    metadata: dict[str, Any]
    latency_seconds: float
    model: str
    agent_id: str


def code_comment(
    rendered_context: str,
    *,
    target_comment_id: str,
    source_line: int,
    model: str | None = None,
    world: World | None = None,
    agent_id: str | None = None,
) -> CommentCodingResult:
    """Code one rendered comment context and return only the parsed result."""
    return code_comment_with_metadata(
        rendered_context,
        target_comment_id=target_comment_id,
        source_line=source_line,
        model=model,
        world=world,
        agent_id=agent_id,
    ).result


def code_comment_with_metadata(
    rendered_context: str,
    *,
    target_comment_id: str,
    source_line: int,
    model: str | None = None,
    world: World | None = None,
    agent_id: str | None = None,
) -> CodingResponse:
    """Code one rendered comment context with Rumi structured output."""
    model_name = configure_model(model)
    run_world = world or analysis_world()
    stable_agent_id = agent_id or f"comment-coder-{uuid.uuid4().hex[:12]}"
    agent = CommentCoderAgent(world=run_world, agent_id=stable_agent_id)

    started = time.perf_counter()
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Pydantic serializer warnings:*",
            category=UserWarning,
        )
        idea = agent.whirl(
            build_message(rendered_context),
            response_model=CommentCodingResult,
        )
    latency = time.perf_counter() - started

    result = idea.content
    if isinstance(result, str):
        raise ValueError(
            "Rumi returned text instead of a structured CommentCodingResult; "
            f"text length={len(result)}"
        )
    if not isinstance(result, CommentCodingResult):
        result = CommentCodingResult.model_validate(result)

    if result.comment_id != target_comment_id:
        raise ValueError(
            f"Model returned comment_id={result.comment_id!r}, "
            f"expected {target_comment_id!r}"
        )
    if result.source_line != source_line:
        raise ValueError(
            f"Model returned source_line={result.source_line!r}, "
            f"expected {source_line!r}"
        )
    if result.prompt_version != PROMPT_VERSION:
        raise ValueError(
            f"Model returned prompt_version={result.prompt_version!r}, "
            f"expected {PROMPT_VERSION!r}"
        )

    return CodingResponse(
        result=result,
        metadata=dict(idea.metadata or {}),
        latency_seconds=latency,
        model=model_name,
        agent_id=stable_agent_id,
    )
