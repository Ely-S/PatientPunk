# Scope — "model in config" (option 4, no Rumi)

Move the LLM **model choice** out of the `MODEL_FAST` / `MODEL_STRONG` env vars and into a
per-subsystem `brain.json`, **without** migrating the pipelines to Rumi. Same spirit as the
agents' `brain/brain.json` (the model lives in a file), but the batch pipelines keep
batching, the multi-provider abstraction, concurrency, caching, retries — **all behavior unchanged.**

## The core insight

Both LLM shims already hardcode a *provider → {fast, strong}* defaults table and read env
overrides **once at import**:
- `src/utilities/__init__.py` (~L89–105): the `_DEFAULT_FAST/_DEFAULT_STRONG` `if/elif/else` over `LLM_PROVIDER`.
- `variable_extraction/patientpunk/_utils.py` `resolve_llm_config()` (~L100–155).

The lift just **moves that table into a JSON file**, loaded at import. Behavior is identical
(same defaults, now in a file); **the env var still overrides** (config is the default); and the
**call sites don't change** — they keep referencing the resolved `MODEL_FAST`/`MODEL_STRONG`
constants.

**Resolution order after the lift:** `env MODEL_FAST/STRONG` → `brain.json[provider]` → (empty ⇒
the existing `openai`-must-set validation). Provider auto-detect (openrouter > anthropic > openai)
still selects the block.

## Config shape (unify across both subsystems)

```json
{
  "models": {
    "openrouter": { "fast": "anthropic/claude-haiku-4.5", "strong": "anthropic/claude-sonnet-4.6" },
    "anthropic":  { "fast": "claude-haiku-4-5-20251001",   "strong": "claude-sonnet-4-6" },
    "openai":     { "fast": "", "strong": "" }
  },
  "temperature": 0.0
}
```
`temperature` is only consumed by variable_extraction; `src/brain.json` omits it. (The two
surveys proposed slightly different nestings — pick **provider→tier** as above for both, since
it mirrors how each shim already indexes by `LLM_PROVIDER`.)

---

## Subsystem 1 — `src/` sentiment pipeline — **Small (~1–2 h), behavior-identical**

**Add** `src/brain.json` (the table above, no `temperature`).

**Edit** `src/utilities/__init__.py` only:
- Add `_BRAIN = _load_brain()` (reads `src/brain.json`; on missing/bad file → `{"models": {}}`).
- Replace the hardcoded `_DEFAULT_FAST/_DEFAULT_STRONG` `if/elif/else` (~L89–102) with
  `_pm = _BRAIN["models"].get(LLM_PROVIDER, {}); _DEFAULT_FAST = _pm.get("fast",""); _DEFAULT_STRONG = _pm.get("strong","")`.
- **Keep unchanged:** the env override (`MODEL_FAST = os.environ.get("MODEL_FAST", _DEFAULT_FAST)`)
  and the `openai`-must-set validation.

**Call sites — ZERO changes** (they import the constants): `extract.py`, `canonicalize.py`,
`classify.py` (prefilter + classify), `get_drug_aliases` (in utilities), `extract_demographics_conditions.py`,
`run_sentiment_pipeline.py` (still logs `{fast, strong}` to `extraction_runs.config`), `dev/eval/run_eval.py`.

**Verify:** 80-gate; `run_eval.py --selftest`; a `--limit 10` live smoke; an env-override smoke
(`MODEL_FAST=google/gemini-2.0-flash …` → log shows the override won).

---

## Subsystem 2 — `variable_extraction/patientpunk` — **Small–Medium, behavior-identical**

Its **own** config (decoupled — never reads `src/`): `variable_extraction/patientpunk/brain.json`
(provider→tier + `temperature`). **Not** added to `__init__` exports.

**Edit** `_utils.py resolve_llm_config()` only — add the brain.json step to the fallback chain
(env > brain.json > hardcoded). Module-level `MODEL_FAST/MODEL_STRONG/LLM_TEMPERATURE` stay
import-time constants.

**Untouched (frozen):** the per-phase model picks in `discover_fields.py` (HAIKU phase 1/4,
SONNET phase 2 — script-level, *stays*); the temperature-escalation retry (0→0.7→1.0); every call
site; `get_llm_client`/`call_model` signatures; the **7 frozen `_SCRIPT` filenames**; the
installable **public API**; batching / `split_retry_batch` / `RETRY_DELAYS` / `cache_control`.

**Verify:** `variable_extraction/tests` (a test that patches `resolve_llm_config`/`os.environ`
may need a one-line mock tweak); missing-brain.json fallback path.

---

## Frozen boundaries honored (both)
- **Env override stays** — README's custom/vLLM/OpenRouter workflow is unchanged (no doc edit needed).
- **Two shims stay decoupled** — a separate `brain.json` each, no cross-import.
- variable_extraction: **7 `_SCRIPT` names, public API, decoupling** untouched (lift is internal to `_utils`).
- 80-gate green; faithful eval unchanged; DB table/column + JSON-cache keys + CLI flags frozen.

## Risks (all low) + mitigations
- *Missing/malformed brain.json* → fallback to empty defaults ⇒ env required (no silent-wrong state). Keep a 2-line `try/except` loader.
- *Env vs config confusion* → config is the default, env always wins (already the documented path).
- *Eval stale model* → eval resolves at import; re-run after a config change (same as editing `.env` today).
- *varx test mocks* → if a test asserts a fixed model id, point its mock at the loader/brain.json.

## Effort + sequence
- **`src/` first** (Small, ~1–2 h — your active area).
- **variable_extraction second** (~2–4 h incl. a test-mock tweak).
- **Total ≈ half a day, one PR per subsystem.** *(The varx survey's "4–5 days" is inflated — the
  real change is one config file + one function's fallback chain, all call sites unchanged.)*

## Out of scope (separate follow-ups)
- **Per-phase / per-step model overrides** (e.g. a cheaper model for discover_fields phase 1) — needs a
  config-schema expansion + script option parsing.
- **Full Rumi migration of the pipelines** (options 2/3) — advised against: OpenRouter-lock, loses
  batching, breaks the frozen boundaries.

## Open choices for you
1. **Config shape** — unify on `provider→tier` (above) for both? (recommended)
2. **Lift `LLM_TEMPERATURE`** into the varx brain.json too? (recommended — it's a model knob)
3. **Naming** — `src/brain.json` + `variable_extraction/patientpunk/brain.json` (mirrors the agents'
   `brain.json`), or `models.json`?
