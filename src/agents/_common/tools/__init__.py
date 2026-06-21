"""Read-only evidence tools over the sentiment SQLite DB (`data/posts.db`).

Re-exports the five JSON-able tool functions the EvidencePacket builder calls,
plus the shared `_resolve_drug` resolver and `SIG_RANK` ordering, so callers can
do `from agents._common.tools import get_sentiment_breakdown, _resolve_drug,
SIG_RANK`. Each tool is read-only, never writes, and degrades gracefully on an
unknown drug (`found: False`) — it NEVER fabricates a row.

Part of the `src/` (sentiment) system. Imports ONLY from `utilities` — never
`patientpunk` / `variable_extraction` (frozen decoupling boundary).
"""
from __future__ import annotations

from agents._common.tools.deps import SENTIMENTS, SIG_RANK, _resolve_drug
from agents._common.tools.tool_get_caveats import get_caveats
from agents._common.tools.tool_get_example_reports import get_example_reports
from agents._common.tools.tool_get_sentiment_breakdown import get_sentiment_breakdown
from agents._common.tools.tool_get_side_effects import get_side_effects
from agents._common.tools.tool_list_drugs import list_drugs

__all__ = [
    "SENTIMENTS",
    "SIG_RANK",
    "_resolve_drug",
    "get_caveats",
    "get_example_reports",
    "get_sentiment_breakdown",
    "get_side_effects",
    "list_drugs",
]
