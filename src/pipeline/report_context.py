"""
report_context.py — Shared mechanics for the per-report extraction steps (doses, effects).

Moved out of pipeline/doses.py unchanged: the report context query (latest treatment
report per post for one drug, with the parent post as context), batching, the thread-pool
loop, and the split-on-malformed-reply retry, plus the alias lookup. The one addition is
an optional thread-root title on ReportContext, fetched only when ``thread_chars`` is set;
the dose step leaves it off, so its rows and payloads are byte-identical to before.

A step built on this module supplies three things: a payload function (what one batch
looks like to the model), a parse function (what comes back, keyed by item id), and a
writer method on utilities.db.ReportWriter for its table.
"""
from __future__ import annotations

import json
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
    WHERE chain.depth < 256  -- terminates on cyclic parent links; deeper posts get no title (real chains reach ~70)
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
    thread_title: str = ""  # only when load_report_contexts(thread_chars=...) asks for it


def load_report_contexts(
    conn: sqlite3.Connection,
    drug: str,
    *,
    parent_chars: int | None = 1500,
    thread_chars: int | None = None,
    limit: int | None = None,
    max_text_chars: int = 8000,
) -> list[ReportContext]:
    """Latest treatment report per post for ``drug``, with the parent post as context.

    With ``thread_chars`` set, replies also carry the title of the post that started the
    thread (a top-level post already starts with its own title).
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


def make_batches(
    contexts: list[ReportContext], batch_size: int, solo_above_chars: int | None
) -> list[list[ReportContext]]:
    """Group short reports ``batch_size`` per call; long reports go one per call."""
    short = [c for c in contexts if solo_above_chars is None or len(c.text) <= solo_above_chars]
    long_ = [c for c in contexts if solo_above_chars is not None and len(c.text) > solo_above_chars]
    batches = [short[i:i + batch_size] for i in range(0, len(short), batch_size)]
    batches.extend([c] for c in long_)
    return batches


def extract_with_split(
    client,
    batch: list[ReportContext],
    system: str,
    model: str,
    payload_fn: Callable[[list[ReportContext]], str],
    parse_fn: Callable[[str, list[int]], tuple[dict[int, Any], int]],
    tokens_per_item: int,
    call: Callable | None = None,
) -> tuple[dict[int, Any], int]:
    """Extract one batch; on a malformed reply, split the batch and retry down to single items.

    ``parse_fn(raw, expected_item_ids)`` returns ``(per_item_id, dropped)``; the result is
    re-keyed by report_id. ``call`` defaults to utilities.llm_call, looked up at call time, so
    a direct caller can stub ``report_context.llm_call``. Step modules pass ``call=llm_call``
    from their own globals, so to stub a step, patch that step's module (``pipeline.doses.llm_call``).
    """
    fn = call or llm_call
    try:
        raw = fn(client, payload_fn(batch), model=model, system=system, max_tokens=tokens_per_item * len(batch))
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


def aliases_from_db(conn: sqlite3.Connection, drug: str) -> list[str]:
    """Spellings the sentiment run stored for ``drug`` in the treatment table; [] when none."""
    row = conn.execute(
        "SELECT aliases FROM treatment WHERE lower(canonical_name) = lower(?)", (drug,)
    ).fetchone()
    if not row or not row[0]:
        return []
    try:
        return [str(a) for a in json.loads(row[0]) if str(a).strip()]
    except (TypeError, ValueError):
        return []


def run_batches(batches: list, fn: Callable, workers: int) -> Iterator[tuple[Any, Any, Exception | None]]:
    """Run ``fn(batch)`` over ``batches`` on a thread pool; yield ``(batch, result, error)`` as each completes.

    Mirrors the pool loop in classify.run_classification (candidate for a shared helper).
    """
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(fn, batch): batch for batch in batches}
        for future in as_completed(futures):
            batch = futures[future]
            try:
                yield batch, future.result(), None
            except Exception as e:  # noqa: BLE001 — transport failures after retries, truncation at the largest budget
                yield batch, None, e
