# The Trial — agents guide

**"The Trial"** puts a drug's *patient evidence* on the stand. You ask one question
("Should I try LDN for my long COVID fatigue?") and two LLM agents — a hype-man and a
skeptic — argue it out over PatientPunk's mined drug-sentiment database, then hand you a
grounded, patient-facing **real-world-evidence (RWE) briefing**.

It is built on the [`rumi`](https://github.com/cjleemesotes/Rumi) agent framework and lives
entirely on the **`src/` (SQLite) side** of the repo. It never imports `patientpunk` /
`variable_extraction` (the decoupling boundary in [CLAUDE.md](CLAUDE.md) holds).

> ⚕️ **Not medical advice.** Every output is anecdotal patient self-report, not a clinical
> finding. The agents scope evidence; they never tell you to start, stop, or dose anything.
> "Please discuss with your doctor" is baked into every briefing.

---

## TL;DR — run it

```bash
# Windows PowerShell uses `$env:NAME = "..."`; the values below are bash-style.
RUMI_MODEL=anthropic/claude-sonnet-4.6 PYTHONUTF8=1 PYTHONPATH=src \
  uv run python -m agents.TheTrialAgent.cli --db data/posts.db --prompt "Should I try LDN for my long COVID fatigue?"
```

You get a briefing like:

```
LDN — 100% positive · 0% negative · 0% mixed · 0% neutral (across 1 patient).
Confidence: thin — Thin evidence — treat as a rumor, not a finding.

In patients' own words:
  (+) "Once I started to have more energy due to ldn, it was like all of the delayed
       emotional and psychological processing started…"

Read the fine print:
  • SMALL N: only 1 distinct patient — below the n>=30 bar; treat every % as noisy.
  • SINGLE SOURCE: all reports come from r/covidlonghaulers (self-selected forum users).
  • SILENT DROP / SELF-SELECTION: a row exists ONLY when an author voiced personal
    experience — so a low NEGATIVE count is NOT proof of safety.
  • SELF-REPORT / ANECDOTAL: firsthand anecdotes, no controls, no dosing, no follow-up.

Bottom line: …with so few voices, treat this as very early, tentative evidence.
As always, discuss with your doctor.

[prov] run_id=2 · commit=807804b… · <timestamp>
```

Add `--json` to get the packet + full debate transcript + briefing as JSON. Add `--rounds 3`
for a longer argument.

---

## Prerequisites

1. **Deps + venv:** `uv sync` (this installs `rumi`, which compiles a small Rust core — needs a
   Rust toolchain on a fresh machine; already installed here).
2. **An LLM key in `.env`:** the agents talk to **OpenRouter**. `src/utilities/__init__.py`
   auto-loads `.env` (and `src/.env`) on import, so you only need:
   ```
   OPENROUTER_API_KEY=sk-or-...
   ```
   (`ANTHROPIC_API_KEY` also works for the rest of the pipeline, but the debate agents go
   through OpenRouter — see **`RUMI_MODEL`** below.)
3. **Data in the DB:** The Trial reads `data/posts.db` (the `treatment_reports` table). If it's
   empty or thin, briefings will say "no reports" or `n=1`. To populate it, run the sentiment
   pipeline from the main [README](README.md) (scrape → import → `run_sentiment_pipeline.py`).
   On the small demo DB, `ldn` and `fluvoxamine` are the only drugs with data.

---

## How to run it

### The CLI

```bash
RUMI_MODEL=anthropic/claude-sonnet-4.6 PYTHONPATH=src \
  uv run python -m agents.TheTrialAgent.cli --prompt "what do people say about LDN?" [--db PATH] [--rounds N] [--json]
```

| Flag | Default | Meaning |
|---|---|---|
| `--prompt` | *(required)* | Your free-text question. Any phrasing; a fast model extracts the drug. |
| `--db` | `data/posts.db` | The read-only SQLite posts DB. |
| `--rounds` | `2` | Debate rounds (each = one Hooper turn + one Dr. Vex turn). |
| `--json` | off | Emit `{packet, transcript, briefing}` as JSON instead of the prose briefing. |

**Drug not in the corpus?** (e.g. "horse dewormer") → the trial **short-circuits**: no debate,
just an honest "no patient reports for X" briefing. This is correct, not a failure.

### Environment variables

| Var | Required | Notes |
|---|---|---|
| `OPENROUTER_API_KEY` | **yes** | Auto-loaded from `.env`. The agents + judge run on OpenRouter. |
| `RUMI_MODEL` | **for live runs** | A valid **OpenRouter** model id, e.g. `anthropic/claude-sonnet-4.6`. Rumi is OpenRouter-only; without this the agents fall back to a default that may not route. |
| `PYTHONPATH=src` | **yes** | `pyproject` `pythonpath=["src"]` only applies under pytest; `python -m agents.TheTrialAgent.cli` needs it explicitly. |
| `PYTHONUTF8=1` | Windows | Avoids a cp1252 decode error (same as the test gate). |
| `RUMI_DATA_DIR` | no | Rumi persists agent history here. If unset, each run uses a fresh temp dir so debates never bleed across runs — leave it unset unless you want persistence. |

### The web UI (watch the trial unfold)

`src/agents/TheTrialAgent/api.py` serves a single-page courtroom UI (`src/agents/TheTrialAgent/trial.html`, styled after
Rumi's `poet_chat.html`) where you watch Hooper and Dr. Vex argue **live, turn by turn**, over the
frozen evidence — then read the verdict.

```bash
RUMI_MODEL=anthropic/claude-sonnet-4.6 PYTHONUTF8=1 PYTHONPATH=src \
  uv run python -m agents.TheTrialAgent.api --db data/posts.db --port 8770
# → open http://127.0.0.1:8770 and put a drug on the stand
```

| Flag / env | Default | Meaning |
|---|---|---|
| `--port` / `TRIAL_PORT` | `8770` | HTTP port (8765 is Rumi's Poet — kept distinct). |
| `--host` | `127.0.0.1` | Bind address (localhost-only by default). |
| `--db` | `data/posts.db` | The read-only posts DB. |

It's a **stdlib-only** server (no Flask/FastAPI) mirroring Rumi's `poet_server.py`: `POST /trial`
`{prompt}` starts a job; the browser polls `GET /poll?job_id=…`, which streams the **Case File**
(the frozen evidence packet) immediately, then each debate turn as it lands — each with a
`✓ grounded` / `⚠ flagged: G#` badge from the same G1–G6 gate — then the **Verdict**. One
`RUN_LOCK` serializes debates (the rumi driver isn't concurrency-safe), so it's a single-user
local tool, not a public server.

---

## How it works

```
user prompt
    │  fast model parses out the drug name (tolerant; falls back to raw text)
    ▼
build_packet(drug, db)            ← the deterministic RESOLVER (no LLM judgment)
    │  • resolve drug via aliases  • dedup reports by user_id (one sentiment/author)
    │  • % split, signal mix, side-effect tally, ≤3 verbatim quotes/pole, caveats, provenance
    │  • stamp every fact with a stable claim_id (S1, S2, …, Q-pos-1, C1…C4, PROV)
    ▼
EvidencePacket  ── the FROZEN, claim-id-stamped evidence. The ONLY thing the agents see.
    │
    ▼
run_debate(packet)                ← two rumi Dervishes argue for `rounds*2` turns
    │   Hooper (advocate) ⇄ Dr. Vex (skeptic), alternating; each may ONLY cite("S2")/quote("Q-pos-1")
    ▼
synthesize(packet, transcript)    ← the deterministic SYNTHESIZER
    │   headline %, quotes, side effects, caveats are CODE-TEMPLATED from the packet (never LLM)
    │   one tool-less LLM call writes the ≤2-sentence bottom line + the doctor coda + prov footer
    ▼
briefing  (printed by the CLI)
```

**Why it's funny *and* trustworthy.** The comedy lives entirely in the two personalities
reacting to each other and to the *shape* of the data ("n=7! single subreddit! self-graded
homework!"). But every number and quote must be a `cite()`/`quote()` reference into the frozen
packet, and the final briefing's figures are filled in by deterministic code — so the laughs
can never move a percentage or invent a side effect. The grounding is **structural, not
prompted-hope**, and a runtime gate (below) enforces it.

### The two agents

- **Hooper** (`src/agents/HooperAgent/main.py`, temp 0.7) — a loud, warm, exclamation-forward
  patient-advocate hype-man. Argues the optimistic case from the packet's positive claims, but
  must concede real negatives and caps its strongest line at *"might be worth asking your
  doctor about."*
- **Dr. Vex** (temp 0.4) — a dry, deadpan evidence-skeptic. Surfaces the real caveats and
  negatives, and **must** cite `C3` every trial (a low negative count is a *silent-drop sampling
  artifact*, not proof of safety). Roasts only flaws the data actually has.

Their system prompts are in `src/agents/HooperAgent/brain/prompts.py` and
`src/agents/DrVexAgent/brain/prompts.py` (the shared IRON RULES live in
`src/agents/_common/iron_rules.py`).

---

## Evaluating + prompt-engineering it

The Trial ships with a faithful eval harness (the methodology: a hard no-fabrication gate first,
graded quality axes only on gate-pass).

```bash
# Offline — stubs the debate with canned cite()-only turns; NO API, NO ScoreCard. Run this first.
PYTHONUTF8=1 PYTHONPATH=src uv run python eval/trial/harness.py --selftest

# Live — real debates over the 8-prompt bank -> gate -> LLM-judge axes -> ScoreCard (best-effort).
SCORECARD_API_KEY=ak_... SCORECARD_PROJECT=patientpunk-trial RUMI_MODEL=anthropic/claude-sonnet-4.6 \
  PYTHONUTF8=1 PYTHONPATH=src uv run python eval/trial/harness.py --live

# Unit tests (deterministic, stubbed heart, no network):
PYTHONUTF8=1 uv run pytest tests/trial_test.py -v
```

### The no-fabrication gate (`src/agents/_common/validate.py`) — the hard, run-failing bar

`check_turn(text, packet)` runs on every debate turn **and** the briefing. Any violation fails
the run, regardless of how good it reads:

| Gate | Catches |
|---|---|
| **G1** number-trace | a bare number/percent with no backing `cite()` |
| **G2** quote-trace | a long (≥8-word) quoted "patient testimonial" not in the packet (short rhetorical quotes are allowed) |
| **G3** caveat-real | a methodology roast that maps to a caveat the packet doesn't have; an `n=K` that ≠ the real denominator |
| **G4** no-Rx | a start / stop / take / dose directive |
| **G5** silent-drop | "no negatives → so it's safe" framing without citing `C3` |
| **G6** phantom-citation | `cite()`/`quote()` of a claim_id the packet **doesn't contain** (e.g. inventing `Q-neg-1` on a zero-negative drug) |

> The gate is the *measurement instrument* — keep it faithful. It was tuned by reading real
> debate rows: G2/G4 false-positives were relaxed and G6 was added after a live run where Dr.
> Vex fabricated a `quote("Q-neg-1")` (and Hooper *caught him* — the agents police each other).

### The query bank (`eval/trial/bank.py`)

8 kickoff prompts spanning the regimes that break naive systems: `ldn_long_covid` (richest),
`famotidine_alias` (brand↔generic), `nattokinase` (long-tail supplement), `ivabradine_low_n`
(low n — the skeptic's "n=N!" is literally true), `all_negative` (fluvoxamine — the advocate must
stay honest), `beta_blockers_category` (resolution edge), `horse_dewormer_not_in_corpus`
(short-circuit, no Rx), `lda_vs_ldn_confusable` (similar-abbreviation trap).

### ScoreCard

ScoreCard is the dashboard, **not** the gate (the local G1–G6 gate is the real quality bar). The
logger (`eval/trial/scorecard_logger.py`) is **no-op-safe**: it degrades silently if the SDK,
key, or network is missing, so local eval always runs.

- Install the SDK (eval-only — **not** a pipeline dep): `uv pip install "scorecard-ai[otel]>=3.7"`.
  The `[otel]` extra is mandatory; bare `scorecard-ai` disables tracing *silently*.
- Set `SCORECARD_API_KEY` and `SCORECARD_PROJECT` (e.g. `patientpunk-trial`). Optional:
  `SCORECARD_SYSTEM_VERSION_ID` (a run must bind a non-null system_version — the "graveyard" rule).
- A live run already exists at **project `patientpunk-trial` (1326)**.
- One known follow-up: a `scorecard_setup.py` that pre-creates the system/version and caches the
  id would let `--live` log fully on its own (mirror dr-hiro's `scorecard_setup_systems.py`).

---

## File map

| Path | What |
|---|---|
| `src/agents/__init__.py` | Lazy PEP-562 re-export (`run_trial`, `build_packet`, `EvidencePacket`). |
| `src/agents/_common/packet.py` | `EvidencePacket` + `build_packet` — the deterministic Resolver + claim_id scheme + `as_prompt_block()`. |
| `src/agents/_common/validate.py` | The G1–G6 no-fabrication gate (`check_turn`, `render_citations`). |
| `src/agents/_common/tools/` | 5 read-only DB tools (sentiment breakdown, example reports, side effects, list drugs, caveats) + `_resolve_drug`/`SIG_RANK` in `deps.py`. |
| `src/agents/_common/iron_rules.py` | The shared IRON RULES + citation HOW-TO embedded in both system prompts. |
| `src/agents/_common/model.py` | The debate `MODEL` id resolution (RUMI_MODEL → MODEL_STRONG → default). |
| `src/agents/HooperAgent/` | The `Hooper` rumi `Dervish` (`main.py`) + its system prompt (`brain/prompts.py`) + `manifest.py`. |
| `src/agents/DrVexAgent/` | The `DrVex` rumi `Dervish` (`main.py`) + its system prompt (`brain/prompts.py`) + `manifest.py`. |
| `src/agents/TheTrialAgent/main.py` | `run_trial` (end-to-end) + `run_debate` (the rumi back-and-forth driver loop). |
| `src/agents/TheTrialAgent/synthesize.py` | The deterministic briefing builder (+ the one bottom-line LLM call). |
| `src/agents/TheTrialAgent/cli.py` | CLI entrypoint (`python -m agents.TheTrialAgent.cli`). |
| `src/agents/TheTrialAgent/api.py` | The stdlib web server (`python -m agents.TheTrialAgent.api`), serves sibling `trial.html`. |
| `src/agents/TheTrialAgent/brain/prompts.py` | The kickoff-parse + bottom-line user prompts. |
| `tests/trial_test.py` | Unit tests (run explicitly; not in CI's default collection). |
| `eval/trial/` | `harness.py` (gate + axes), `bank.py` (8 prompts), `rubric.py` (graded axes), `scorecard_logger.py`. |

---

## Gotchas & config

- **`RUMI_MODEL` must be an OpenRouter model id** (`anthropic/claude-sonnet-4.6`, etc.). Rumi is
  OpenRouter-only and has no env auto-select.
- **`PYTHONPATH=src`** for any ad-hoc `python …` invocation (the `pyproject` `pythonpath` is
  pytest-only). `pytest` and the CLI-via-module both need it; pytest sets it itself.
- **Thin demo data.** On the 7-report demo DB nearly everything resolves to `n=1` or `n=0` — which
  is *why* the skeptic is so withering. Populate the DB (main README) for richer briefings.
- **History is ephemeral by default** (`RUMI_DATA_DIR` → fresh temp dir per run; fresh `agent_id`)
  so debates never contaminate each other. Pin `RUMI_DATA_DIR` only if you want persistence.
- **Cost.** A debate is ~6 LLM calls (parse + `rounds*2` turns + bottom line) — cents on the
  default models. `--live` over the bank adds the LLM-judge axes (a few dollars).
- **`scorecard-ai[otel]` is venv-only** — intentionally *not* in `pyproject` (keeps it out of the
  pipeline deps, consistent with the two-decoupled-systems doctrine).
- **Behavior-preserving:** the gate stays green — `PYTHONUTF8=1 uv run pytest tests/ variable_extraction/tests/ -v`
  → 80 passed (63 pipeline + 17 trial). The Trial adds files only; it changes no pipeline behavior.

## Extending it

- **A new evidence dimension?** Add a tool under `src/agents/_common/tools/`, surface it in
  `build_packet` with a new `claim_id` family, list it in `as_prompt_block()`, and (if it's a
  number/quote) make sure the gate's G1/G2/G6 can trace it. The agents pick it up for free — they
  only cite claim_ids.
- **Tune a persona?** Edit `src/agents/HooperAgent/brain/prompts.py` or
  `src/agents/DrVexAgent/brain/prompts.py`, then re-prove the gate: run the bank
  through `harness.py --selftest` (logic) and a couple of `--live` debates, and confirm the G1–G6
  gate stays clean. Ground every prompt change in a real failing turn (read `--json` transcripts).
- **The whole thing is read-only on `data/posts.db`** — it never writes the DB and never imports
  the `patientpunk` package. Keep it that way.
