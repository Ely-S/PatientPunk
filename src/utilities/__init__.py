"""Shared utilities for the drug mention pipeline."""
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
# Load .env from project root. override=False so explicitly-exported
# env vars always win over .env file values. Root is the single source
# of truth; src/.env is a fallback only if root doesn't exist.
_root_env = Path(__file__).parent.parent.parent / ".env"
_src_env = Path(__file__).parent.parent / ".env"
if _root_env.exists():
    load_dotenv(_root_env, override=False)
elif _src_env.exists():
    load_dotenv(_src_env, override=False)

import anthropic

# ── Output file names ────────────────────────────────────────────────────────
TAGGED_MENTIONS = "tagged_mentions.json"
CANONICALIZED_MENTIONS = "canonicalized_mentions.json"


# ── Pipeline Config ──────────────────────────────────────────────────────────
@dataclass
class PipelineConfig:
    """Shared configuration for all pipeline steps."""
    # Either an anthropic.Anthropic (used directly or via OpenRouter base_url)
    # or a DispersedLLMClient — both expose `.messages.stream(...)` so the
    # downstream pipeline code is provider-agnostic.
    client: object
    output_dir: Path
    db_path: Path
    limit: int = 100
    reclassify: bool = False
    max_upstream_chars: int | None = None  # None = unlimited; truncate upstream comment text to N chars
    max_upstream_depth: int | None = None  # None = unlimited; max upstream hops for drug context
    workers: int = 3                       # ThreadPoolExecutor workers; 1 = sequential
    drug: str | None = None                # If set, extract + canonicalize + classify operate on this drug and its synonyms only
    drug_aliases: list[str] | None = None  # If set, use as the alias list directly and skip LLM alias lookup

    def __post_init__(self):
        if self.max_upstream_chars is not None and self.max_upstream_chars < 0:
            raise ValueError(f"max_upstream_chars must be non-negative, got {self.max_upstream_chars}")
        if self.max_upstream_depth is not None and self.max_upstream_depth < 0:
            raise ValueError(f"max_upstream_depth must be non-negative, got {self.max_upstream_depth}")

    def path(self, filename: str) -> Path:
        return self.output_dir / filename

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("pipeline")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)

# ── Models + Provider ────────────────────────────────────────────────────────
# Provider is auto-detected from which API key is set, unless overridden:
#   OPENROUTER_API_KEY set → openrouter (default models: anthropic/claude-*)
#   ANTHROPIC_API_KEY set  → anthropic  (default models: claude-*-20251001)
#   LLM_PROVIDER=...       → explicit override
#
# Override models in .env:
#   MODEL_FAST=google/gemini-2.0-flash
#   MODEL_STRONG=openai/gpt-4o
# Any model supported by your provider works.
_PLACEHOLDER_KEYS = {"", "your_openrouter_key_here", "your_anthropic_key_here", "XXX",
                     "your_dispersed_public_key_here", "your_dispersed_secret_key_here"}

_has_openrouter = os.environ.get("OPENROUTER_API_KEY", "") not in _PLACEHOLDER_KEYS
_has_anthropic = os.environ.get("ANTHROPIC_API_KEY", "") not in _PLACEHOLDER_KEYS
_has_dispersed = (
    os.environ.get("DISPERSED_PUBLIC_KEY", "") not in _PLACEHOLDER_KEYS
    and os.environ.get("DISPERSED_SECRET_KEY", "") not in _PLACEHOLDER_KEYS
)

# Auto-detect provider from available keys, or use explicit override.
# `dispersed` is opt-in (never auto-selected) since it depends on a Dispersed
# account + pre-existing job recipes; auto-selection here could surprise a
# user who set keys but hasn't yet created recipes.
_VALID_PROVIDERS = ("openrouter", "anthropic", "dispersed")
_explicit_provider = os.environ.get("LLM_PROVIDER", "").strip().lower() or None
if _explicit_provider and _explicit_provider not in _VALID_PROVIDERS:
    sys.exit(
        f"Unsupported LLM_PROVIDER={_explicit_provider!r} "
        f"(expected one of: {', '.join(_VALID_PROVIDERS)})"
    )
if _explicit_provider:
    LLM_PROVIDER = _explicit_provider
elif _has_openrouter:
    LLM_PROVIDER = "openrouter"
elif _has_anthropic:
    LLM_PROVIDER = "anthropic"
else:
    LLM_PROVIDER = "anthropic"  # default for backward compatibility

if LLM_PROVIDER == "openrouter":
    _DEFAULT_FAST = "anthropic/claude-haiku-4.5"
    _DEFAULT_STRONG = "anthropic/claude-sonnet-4.6"
    _API_BASE = "https://openrouter.ai/api"
elif LLM_PROVIDER == "dispersed":
    # vLLM model IDs as served by the Dispersed job recipes. The model name
    # passed to llm_call() must match what the vLLM server reports — this
    # is the same string used by `vllm serve <model>` to load the weights.
    _DEFAULT_FAST = "Qwen/Qwen3-8B"
    _DEFAULT_STRONG = "Qwen/Qwen3-32B"
    _API_BASE = None
else:
    _DEFAULT_FAST = "claude-haiku-4-5-20251001"
    _DEFAULT_STRONG = "claude-sonnet-4-6"
    _API_BASE = None

MODEL_FAST = os.environ.get("MODEL_FAST", _DEFAULT_FAST)
MODEL_STRONG = os.environ.get("MODEL_STRONG", _DEFAULT_STRONG)


# ── Git ──────────────────────────────────────────────────────────────────────
def get_git_commit() -> str:
    """Return current git commit hash, or 'unknown' (with a loud warning).

    If git metadata is unavailable we still return rather than raising — some
    environments (CI containers, standalone notebook runs, downstream
    consumers re-running the build with our DBs) legitimately won't have git
    installed. But we log loudly so 'unknown' provenance can never enter the
    audit trail silently."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
        )
        commit = result.stdout.strip()
        # Also flag dirty working tree so downstream consumers can see if the
        # build was made from a non-clean checkout.
        try:
            dirty = subprocess.run(
                ["git", "status", "--porcelain"], capture_output=True, text=True, check=True,
            ).stdout.strip()
            if dirty:
                log.warning(
                    "Git working tree is DIRTY at build time (commit %s + uncommitted "
                    "changes). Provenance manifest will include the commit hash but "
                    "the actual code may differ. Commit before treating outputs as "
                    "reproducible.", commit[:8],
                )
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass  # can't check dirty state, but we have the commit; proceed
        return commit
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log.warning(
            "Could not resolve git commit hash (got %s). Provenance manifest "
            "will record 'unknown' for git_commit; reproducibility chain broken. "
            "If this is a release build, install git and rerun from a clean "
            "checkout.", type(e).__name__,
        )
        return "unknown"


# ── Client ───────────────────────────────────────────────────────────────────
def _make_anthropic_client(provider: str) -> anthropic.Anthropic:
    """Build an Anthropic-SDK client (direct or via OpenRouter base_url)."""
    if provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        key_name = "OPENROUTER_API_KEY"
        api_base = "https://openrouter.ai/api"
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        key_name = "ANTHROPIC_API_KEY"
        api_base = None

    if not api_key or api_key in _PLACEHOLDER_KEYS:
        sys.exit(
            f"{key_name} not set (provider={provider}).\n"
            f"  Add {key_name}=... to .env"
        )
    kwargs: dict = {"api_key": api_key, "max_retries": 4, "timeout": 60.0}
    if api_base:
        kwargs["base_url"] = api_base
    return anthropic.Anthropic(**kwargs)


def get_client():
    """Return an LLM client matching the active provider.

    Returns:
      - anthropic.Anthropic when LLM_PROVIDER ∈ {anthropic, openrouter}
      - DispersedLLMClient   when LLM_PROVIDER == dispersed

    Both expose the same `client.messages.stream(...)` shape so llm_call()
    works against either without branching.

    Key selection is tied to the provider:
      openrouter → requires OPENROUTER_API_KEY
      anthropic  → requires ANTHROPIC_API_KEY
      dispersed  → requires DISPERSED_PUBLIC_KEY + DISPERSED_SECRET_KEY,
                   plus DISPERSED_RECIPE_FAST and DISPERSED_RECIPE_STRONG
                   recipe UUIDs (create them out-of-band via the Dispersed UI).
                   Optionally DISPERSED_FALLBACK=openrouter|anthropic for
                   graceful fallback when a job can't be brought up.
    """
    log.info(f"LLM provider: {LLM_PROVIDER} | fast: {MODEL_FAST} | strong: {MODEL_STRONG}")

    if LLM_PROVIDER == "dispersed":
        # Imported lazily so a stale Dispersed env doesn't break anthropic-only runs.
        from utilities.dispersed import DispersedAPIClient, DispersedLLMClient

        pub = os.environ.get("DISPERSED_PUBLIC_KEY", "")
        sec = os.environ.get("DISPERSED_SECRET_KEY", "")
        if pub in _PLACEHOLDER_KEYS or sec in _PLACEHOLDER_KEYS:
            sys.exit(
                "DISPERSED_PUBLIC_KEY / DISPERSED_SECRET_KEY not set "
                "(provider=dispersed).\n  Add both to .env."
            )

        recipe_fast = os.environ.get("DISPERSED_RECIPE_FAST", "").strip()
        recipe_strong = os.environ.get("DISPERSED_RECIPE_STRONG", "").strip()
        if not recipe_fast or not recipe_strong:
            sys.exit(
                "DISPERSED_RECIPE_FAST and DISPERSED_RECIPE_STRONG are required "
                "(provider=dispersed). Create the recipes in the Dispersed UI "
                "and add their UUIDs to .env."
            )

        recipe_map = {MODEL_FAST: recipe_fast, MODEL_STRONG: recipe_strong}

        fallback_name = os.environ.get("DISPERSED_FALLBACK", "").strip().lower() or None
        fallback_client = None
        if fallback_name:
            if fallback_name not in ("openrouter", "anthropic"):
                sys.exit(
                    f"Unsupported DISPERSED_FALLBACK={fallback_name!r} "
                    f"(expected 'openrouter' or 'anthropic')"
                )
            log.info(f"Dispersed fallback enabled: {fallback_name}")
            fallback_client = _make_anthropic_client(fallback_name)

        api_client = DispersedAPIClient(pub, sec)
        return DispersedLLMClient(
            recipe_map, api_client, fallback_client=fallback_client,
        )

    return _make_anthropic_client(LLM_PROVIDER)


# ── LLM response parsing ────────────────────────────────────────────────────
def _strip_markdown(raw: str) -> str:
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


class LLMParseError(ValueError):
    """LLM response could not be parsed as JSON."""


import re

_TRAILING_COMMA = re.compile(r",\s*([}\]])")

def parse_json_array(raw: str) -> list:
    raw = _strip_markdown(raw)
    start, end = raw.find("["), raw.rfind("]") + 1
    if start < 0 or end <= start:
        raise LLMParseError(f"No JSON array in response: {raw[:200]}")
    text = _TRAILING_COMMA.sub(r"\1", raw[start:end])
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMParseError(f"JSON decode failed: {e} — {raw[:200]}") from e


def parse_json_object(raw: str) -> dict:
    raw = _strip_markdown(raw)
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start < 0 or end <= start:
        raise LLMParseError(f"No JSON object in response: {raw[:200]}")
    text = _TRAILING_COMMA.sub(r"\1", raw[start:end])
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMParseError(f"JSON decode failed: {e} — {raw[:200]}") from e


# ── Drug aliases ─────────────────────────────────────────────────────────────
def resolve_aliases(config: "PipelineConfig") -> tuple[str, list[str]]:
    """Return (target, aliases) for config.drug.

    Uses config.drug_aliases if set (hand-curated list); otherwise falls back
    to get_drug_aliases (LLM lookup + disk cache). Target is always included.
    """
    target = config.drug.strip().lower()
    if config.drug_aliases is not None:
        aliases = [a.lower().strip() for a in config.drug_aliases if a.strip()]
        if target not in aliases:
            aliases.append(target)
        return target, aliases
    return target, get_drug_aliases(config.client, target, config.path(f"aliases_{target}.json"))


def get_drug_aliases(client, drug: str, cache_path: Path) -> list[str]:
    """Return [drug, ...aliases] for filtering in --drug mode.

    Asks the strong model once for common names, abbreviations, brand names,
    and plausible misspellings. Result is cached to disk and editable by hand.
    """
    from prompts.intervention_config import drug_aliases_prompt
    target = drug.strip().lower()
    if cache_path.exists():
        aliases = [a.lower().strip() for a in json.loads(cache_path.read_text(encoding="utf-8")) if a.strip()]
        log.info(f"Loaded {len(aliases)} cached aliases for {target!r} from {cache_path.name}.")
    else:
        raw = llm_call(client, drug_aliases_prompt(target), model=MODEL_STRONG, max_tokens=2000)
        aliases = [a.lower().strip() for a in parse_json_array(raw) if a.strip()]
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(aliases, indent=2))
        log.info(f"Fetched {len(aliases)} aliases for {target!r}; cached to {cache_path.name}.")
    if target not in aliases:
        aliases.append(target)
    log.info(f"Aliases for {target!r}: {', '.join(aliases)}")
    return aliases


# ── LLM Call Wrapper ─────────────────────────────────────────────────────────
def llm_call(
    client,
    prompt: str,
    model: str = MODEL_FAST,
    system: str | None = None,
    max_tokens: int = 100,
) -> str:
    """Send a single prompt and return the model's text reply.

    Accepts either an anthropic.Anthropic (incl. OpenRouter via base_url)
    or a DispersedLLMClient — both implement `.messages.stream(...)` with
    the Anthropic shape, so this function doesn't branch on provider.
    """
    kwargs = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if system:
        kwargs["system"] = system
    with client.messages.stream(**kwargs) as stream:
        return stream.get_final_message().content[0].text
