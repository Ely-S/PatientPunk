"""The debate model id, resolved once for all Trial agents.

``MODEL`` must be an OpenRouter model id for live runs. RUMI_MODEL wins;
otherwise fall back to the sentiment pipeline's strong model, then to a sane
OpenRouter default.
"""

from __future__ import annotations

import os

# Resolve the debate model once. RUMI_MODEL wins; otherwise fall back to the
# sentiment pipeline's strong model, then to a sane OpenRouter default.
MODEL = os.environ.get("RUMI_MODEL") or os.environ.get(
    "MODEL_STRONG", "~openai/gpt-latest"
)
