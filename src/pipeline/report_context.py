"""
report_context.py — Shared pieces for the per-report extraction steps (doses, effects).

The report context query (latest treatment report per post for one drug, with the parent
post and the thread's root title as context), batching, the thread-pool loop, and the
split-on-malformed-reply retry. pipeline/doses.py still carries its own copies of the
first three; pointing it here is a one-line follow-up once that step is frozen.
"""
from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from utilities import LLMParseError, llm_call, log
from utilities.db import post_text

_WS = re.compile(r"\s+")

# Title of the post that started the thread, walking parent_id up from a post.
_THREAD_TITLE_SQL = """
WITH RECURSIVE chain(post_id, parent_id, title, depth) AS (
    SELECT post_id, parent_id, title, 0 FROM posts WHERE post_id = ?
    UNION ALL
    SELECT p.post_id, p.parent_id, p.title, chain.depth + 1
    FROM posts p JOIN chain ON p.post_id = chain.parent_id
    WHERE chain.depth < 64
)
SELECT title FROM chain WHERE parent_id IS NULL LIMIT 1
"""


@dataclass(frozen=True)
class ReportContext:
    report_id: int
    post_id: str
    user_id: str | None
    drug_id: int
    text: str
    replying_to: str
    thread_title: str = ""


def load_report_contexts(
    conn: sqlite3.Connection,
    drug: str,
    *,
    parent_chars: int | None = 1500,
    thread_chars: int | None = 200,
    limit: int | None = None,
    max_text_chars: int = 8000,
) -> list[ReportContext]:
    """Latest treatment report per post for ``drug``, with the parent post and thread title as context.

    ``thread_title`` is set only for replies; a top-level post already starts with its title.
    """
    rows = conn.execute(
        """
        SELECT tr.report_id, tr.post_id, tr.user_id, tr.drug_id,
               p.title, p.body_text, p.parent_id,
               pp.title AS parent_title, pp.body_text AS parent_body, pp.parent_id AS parent_parent
        FROM treatment_reports tr
        JOIN treatment t ON t.id = tr.drug_id
        JOIN posts p ON p.post_id = tr.post_id
        LEFT JOIN posts pp ON pp.post_id = p.parent_id
        WHERE lower(t.canonical_name) = lower(?)
          AND tr.report_id = (
              SELECT MAX(tr2.report_id) FROM treatment_reports tr2
              WHERE tr2.post_id = tr.post_id AND tr2.drug_id = tr.drug_id
          )
        ORDER BY tr.report_id
        """,
        (drug,),
    ).fetchall()
    contexts: list[ReportContext] = []
    for report_id, post_id, user_id, drug_id, title, body, parent_id, ptitle, pbody, pparent in rows:
        text = _WS.sub(" ", post_text(title, body, parent_id)).strip()[:max_text_chars]
        if not text:
            continue
        parent = ""
        if parent_chars and parent_id is not None and (ptitle or pbody):
            parent = _WS.sub(" ", post_text(ptitle, pbody, pparent)).strip()[:parent_chars]
        thread = ""
        if thread_chars and parent_id is not None:
            root = conn.execute(_THREAD_TITLE_SQL, (parent_id,)).fetchone()
            if root and root[0]:
                thread = _WS.sub(" ", root[0]).strip()[:thread_chars]
        contexts.append(ReportContext(report_id, post_id, user_id, drug_id, text, parent, thread))
        if limit and len(contexts) >= limit:
            break
    return contexts


def make_batches(contexts: list, batch_size: int, solo_above_chars: int | None) -> list[list]:
    """Group short reports ``batch_size`` per call; long reports go one per call."""
    short = [c for c in contexts if solo_above_chars is None or len(c.text) <= solo_above_chars]
    long_ = [c for c in contexts if solo_above_chars is not None and len(c.text) > solo_above_chars]
    batches = [short[i:i + batch_size] for i in range(0, len(short), batch_size)]
    batches.extend([c] for c in long_)
    return batches


def run_batches(batches: list, fn: Callable, workers: int) -> Iterator[tuple[Any, Any, Exception | None]]:
    """Run ``fn(batch)`` over ``batches`` on a thread pool; yield ``(batch, result, error)`` as each completes."""
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(fn, batch): batch for batch in batches}
        for future in as_completed(futures):
            batch = futures[future]
            try:
                yield batch, future.result(), None
            except Exception as e:  # noqa: BLE001 — transport failures after retries, truncation at the largest budget
                yield batch, None, e


def extract_with_split(
    client,
    batch: list,
    system: str,
    model: str,
    payload_fn: Callable[[list], str],
    parse_fn: Callable[[str, list[int]], tuple[dict[int, Any], int]],
    tokens_per_item: int,
    call: Callable = llm_call,
) -> tuple[dict[int, Any], int]:
    """Extract one batch; on a malformed reply, split the batch and retry down to single items.

    ``parse_fn(raw, expected_item_ids)`` returns ``(per_item_id, dropped)``; the result is keyed by
    report_id. ``dropped`` counts objects the model returned that did not validate.
    """
    try:
        raw = call(client, payload_fn(batch), model=model, system=system, max_tokens=tokens_per_item * len(batch))
        per_item, dropped = parse_fn(raw, list(range(len(batch))))
        return {batch[i].report_id: value for i, value in per_item.items()}, dropped
    except LLMParseError as e:
        if len(batch) == 1:
            log.warning(f"Skipping report {batch[0].report_id}: {e}")
            return {}, 0
        log.warning(f"Malformed reply for a batch of {len(batch)}; splitting. {e}")
        mid = len(batch) // 2
        left, dropped_left = extract_with_split(client, batch[:mid], system, model, payload_fn, parse_fn, tokens_per_item, call)
        right, dropped_right = extract_with_split(client, batch[mid:], system, model, payload_fn, parse_fn, tokens_per_item, call)
        return {**left, **right}, dropped_left + dropped_right
