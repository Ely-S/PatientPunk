"""Eval harness for "The Trial" two-agent debate.

Pieces:
  - bank.py             — 8 kickoff prompts covering every code path.
  - rubric.py           — 4 graded axes (U/D/F/CAL), LLM-judged at temp 0.
  - scorecard_logger.py — LIVE ScoreCard logger that no-ops gracefully.
  - harness.py          — runs each bank prompt: the HARD G1-G5 gate (binary,
                          run-failing) over every turn + the briefing, then the
                          graded axes only on gate-pass. `--selftest` runs fully
                          offline with a stubbed debate; `--live` runs for real.

This package lives under eval/, not on the pytest pythonpath; the harness adds
`src/` to sys.path so it can import the `agents.*` modules under test.
"""
