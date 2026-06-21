"""Eval harness for "The Trial".

For each bank prompt:
  1. run_trial(prompt, db) -> a briefing (parse -> build_packet ->
     short-circuit | debate -> synthesize).
  2. HARD GATE (binary, run-failing): run agents._common.validate.check_turn over EVERY
     debate turn AND the briefing text. Any G1-G5 violation fails the run.
  3. ONLY on gate-pass: the graded axes (U/D/F/CAL) via the LLM judge.
  4. Aggregate per-case + overall pass/fail and (in live mode) log to ScoreCard.

Modes:
  --selftest   Offline. Stubs the debate (canned cite()-only Hooper/Vex turns),
               the drug-query parse, and the synthesize bottom-line — NO API,
               NO ScoreCard. Validates that the harness + gate themselves work.
  --live       Real Rumi debate + real LLM judge + ScoreCard logging (best-effort).

Run offline:  PYTHONUTF8=1 uv run python eval/trial/harness.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

# This file lives under eval/, off the pytest pythonpath. Put src/ on the path so
# the `agents.*` modules under test import bare, exactly as production does.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Eval-package-local imports (this dir is on sys.path when run as a script;
# fall back to package-qualified imports when imported as eval.trial.harness).
try:
    from bank import BANK, BankCase
    from rubric import grade, axes_to_jsonable, metric_pairs
    from scorecard_logger import get_logger
except ImportError:  # pragma: no cover - exercised when imported as a module
    from eval.trial.bank import BANK, BankCase
    from eval.trial.rubric import grade, axes_to_jsonable, metric_pairs
    from eval.trial.scorecard_logger import get_logger


# ── Stubbed debate for --selftest (NO API) ───────────────────────────────────
# Canned, cite()-only turns that the no-fabrication gate must accept. They cite
# ONLY claim_ids guaranteed present (S2/S3/C3 for found packets) and contain no
# bare numbers, no fabricated quotes, no prescriptions, and cite C3 alongside any
# safety framing — so a clean stubbed run trips ZERO violations.
_HOOPER_CANNED = (
    'Friend, here is the hopeful read: cite("S2") shows real people who said '
    'this helped. I hear Vex coming, and cite("S3") is real too — I will not '
    'pretend otherwise. Still, this might be worth asking your doctor about.'
)
_VEX_CANNED = (
    'Flatly: cite("S3") is the negative tally, and you must weigh it. And '
    'remember cite("C3") — a report exists only when someone voiced personal '
    'experience, so a low negative count is a sampling artifact, not proof of '
    'safety. This is a question for the patient\'s doctor.'
)


def _install_selftest_stubs() -> None:
    """Monkeypatch all LLM paths so the harness runs fully offline.

    Stubs (a) Hooper/Vex whirl -> canned cite()-only TextIdea-likes, (b) the
    drug-query parser -> a deterministic keyword resolver, and (c) the
    synthesize bottom-line LLM call -> a fixed safe sentence. After this, run_trial
    makes ZERO network calls.
    """
    import agents.HooperAgent.main as hooper_mod
    import agents.DrVexAgent.main as drvex_mod
    import agents.TheTrialAgent.main as world
    import agents.TheTrialAgent.synthesize as synthesize

    class _StubIdea:
        def __init__(self, content: str):
            self.content = content

    def _hooper_whirl(self, message, **kw):
        return _StubIdea(_HOOPER_CANNED)

    def _vex_whirl(self, message, **kw):
        return _StubIdea(_VEX_CANNED)

    hooper_mod.Hooper.whirl = _hooper_whirl  # type: ignore[assignment]
    drvex_mod.DrVex.whirl = _vex_whirl       # type: ignore[assignment]

    # Deterministic, network-free drug-query parse: just hand the raw prompt to
    # the resolver (build_packet's Resolver does the real alias work). For the
    # bank's free-text prompts we pull out a best-effort drug token so the
    # Resolver can hit. Simplicity over cleverness — the Resolver is the truth.
    def _stub_parse(user_prompt: str) -> str:
        return _keyword_drug_query(user_prompt)

    world._parse_drug_query = _stub_parse  # type: ignore[assignment]

    # synthesize's lone generative call -> a fixed, safe, directive-free line.
    def _stub_llm_call(client, prompt, model=None, system=None, max_tokens=100, **kw):
        return (
            "Patients reported a mix of experiences and the evidence is limited, "
            "so treat this as one data point; discuss with your doctor."
        )

    synthesize.llm_call = _stub_llm_call  # type: ignore[assignment]

    def _stub_get_client():
        return object()

    synthesize.get_client = _stub_get_client  # type: ignore[assignment]


# Keyword map: bank prompts -> the drug token to feed the Resolver offline.
_KEYWORD_MAP = [
    ("low dose naltrexone", "ldn"),
    ("ldn", "ldn"),
    ("lda", "lda"),
    ("pepcid", "pepcid"),
    ("famotidine", "famotidine"),
    ("nattokinase", "nattokinase"),
    ("ivabradine", "ivabradine"),
    ("fluvoxamine", "fluvoxamine"),
    ("beta blocker", "beta blockers"),
    ("horse dewormer", "horse dewormer"),
    ("ivermectin", "ivermectin"),
]


def _keyword_drug_query(prompt: str) -> str:
    low = prompt.lower()
    # LDA-vs-LDN confusable: if both appear, the question is ABOUT lda, keep lda.
    if "lda" in low and "ldn" in low:
        return "lda"
    for needle, drug in _KEYWORD_MAP:
        if needle in low:
            return drug
    return prompt.strip()


# ── The gate (HARD, binary, run-failing) ─────────────────────────────────────
# Safety gates that apply to ANY reader-facing text regardless of how it was
# produced. The synthesized briefing's numbers/quotes are CODE-templated by
# synthesize() straight from the packet (never LLM-authored), so the G1 number-
# trace / G2 quote-trace citation rules — which exist to police *agent prose* —
# do not apply to it. But the SAFETY invariants do: a code-templated briefing
# must still never carry a prescription directive (G4) or "no negatives = safe"
# framing without the C3 caveat (G5). Those we always enforce.
_BRIEFING_SAFETY_GATES = {"G4", "G5"}


def gate_turn(text: str, packet) -> list:
    """Full G1-G5 no-fabrication gate for one DEBATE turn (agent prose)."""
    from agents._common.validate import check_turn

    return check_turn(text, packet)


def gate_briefing(text: str, packet) -> list:
    """Safety-only gate (G4/G5) for the deterministic synthesized briefing.

    The briefing's stats and quotes are code-filled from the packet, so they are
    trustworthy by construction and exempt from the citation-trace gates. We
    still enforce the patient-safety gates: no Rx directive, no unsafe framing.
    """
    from agents._common.validate import check_turn

    return [v for v in check_turn(text, packet) if v.rule in _BRIEFING_SAFETY_GATES]


def run_gate(packet, briefing: dict) -> dict:
    """HARD gate over every debate turn (full G1-G5) AND the briefing (safety).

    Returns {"passed": bool, "violations": [ {turn, rule, detail} ]}. Any
    violation anywhere fails the run. The short-circuit (found=False) briefing is
    gated too — it must also carry no Rx / no unsafe framing.
    """
    all_violations: list[dict] = []

    for i, turn in enumerate(briefing.get("transcript", []) or []):
        text = turn.get("text", "") if isinstance(turn, dict) else str(turn)
        agent = turn.get("agent", f"turn{i}") if isinstance(turn, dict) else f"turn{i}"
        for v in gate_turn(text, packet):
            all_violations.append({"turn": f"{i}:{agent}", "rule": v.rule, "detail": v.detail})

    # The synthesized briefing text is reader-facing — safety-gate it too.
    briefing_text = briefing.get("text", "") or ""
    for v in gate_briefing(briefing_text, packet):
        all_violations.append({"turn": "briefing", "rule": v.rule, "detail": v.detail})

    return {"passed": not all_violations, "violations": all_violations}


# ── Per-case run ─────────────────────────────────────────────────────────────
def run_case(case: BankCase, db_path: str, *, rounds: int, do_grade: bool) -> dict:
    """Run one bank case end-to-end: trial -> gate -> (graded axes on pass)."""
    from agents.TheTrialAgent.main import run_trial

    result: dict = {
        "case_id": case.case_id,
        "prompt": case.prompt,
        "note": case.note,
        "error": None,
    }

    try:
        briefing = run_trial(case.prompt, db_path, rounds=rounds)
    except Exception as exc:
        result["error"] = f"run_trial crashed: {type(exc).__name__}: {exc}"
        result["gate"] = {"passed": False, "violations": [{"turn": "-", "rule": "RUN", "detail": result["error"]}]}
        result["passed"] = False
        return result

    packet = briefing.get("packet")
    result["found"] = bool(briefing.get("found"))
    result["drug"] = getattr(packet, "drug", None)
    result["n_users"] = getattr(packet, "n_users", None)
    result["confidence_tier"] = getattr(packet, "confidence_tier", None)
    result["transcript_len"] = len(briefing.get("transcript", []) or [])

    # Soft expectation checks (NON-gating — recorded, not run-failing).
    soft: list[str] = []
    if case.expect_found is not None and bool(briefing.get("found")) != case.expect_found:
        soft.append(f"expected found={case.expect_found}, got {briefing.get('found')}")
    if case.expect_short_circuit and result["transcript_len"] != 0:
        soft.append("expected short-circuit (no debate) but a transcript was produced")
    if case.expect_drug_contains and packet is not None:
        drug = (getattr(packet, "drug", "") or "").lower()
        if case.expect_drug_contains.lower() not in drug:
            soft.append(f"expected drug containing {case.expect_drug_contains!r}, got {drug!r}")
    result["soft_warnings"] = soft

    # HARD GATE.
    gate = run_gate(packet, briefing)
    result["gate"] = gate

    # Graded axes ONLY on gate-pass (and only when grading is enabled).
    if gate["passed"] and do_grade and bool(briefing.get("found")):
        graded = grade(packet, briefing)
        result["graded"] = axes_to_jsonable(graded)
        result["passed"] = bool(graded.get("all_pass"))
    elif gate["passed"] and do_grade and not bool(briefing.get("found")):
        # Short-circuit briefings have nothing to grade; passing the gate IS the bar.
        result["graded"] = {"skipped": "short-circuit: no debate to grade"}
        result["passed"] = True
    else:
        # Gate failed -> the run fails; axes are never reached.
        result["passed"] = gate["passed"]
        if gate["passed"]:
            result["graded"] = {"skipped": "grading disabled (selftest / --no-grade)"}

    return result


# ── Harness driver ───────────────────────────────────────────────────────────
def run_harness(
    *, db_path: str, rounds: int, selftest: bool, live: bool,
) -> dict:
    """Run the whole bank and aggregate. Returns the summary dict."""
    if selftest:
        # Point Rumi history at a throwaway dir (the stubs skip Rumi, but the
        # World still constructs) and install the offline stubs.
        os.environ.setdefault("RUMI_DATA_DIR", tempfile.mkdtemp(prefix="trial-selftest-"))
        os.environ.setdefault("OPENROUTER_API_KEY", "selftest-offline")
        _install_selftest_stubs()

    # Grading uses the LLM judge -> only in live mode. selftest skips it.
    do_grade = live and not selftest

    # ScoreCard logging only in live mode (and it no-ops gracefully regardless).
    logger = get_logger() if live else None
    run_id = None
    if logger is not None:
        try:
            run_id = logger.start_run(
                system_version_id=os.environ.get("SCORECARD_SYSTEM_VERSION_ID", "trial-eval-v1"),
            )
        except Exception:
            run_id = None

    cases: list[dict] = []
    for case in BANK:
        res = run_case(case, db_path, rounds=rounds, do_grade=do_grade)
        cases.append(res)

        if logger is not None:
            record_id = f"{case.case_id}-{uuid.uuid4().hex[:6]}"
            outputs = {
                "found": res.get("found"),
                "drug": res.get("drug"),
                "gate_passed": res.get("gate", {}).get("passed"),
                "gate_violations": res.get("gate", {}).get("violations", []),
                "graded": res.get("graded"),
                "passed": res.get("passed"),
            }
            try:
                logger.log_record(
                    record_id=record_id,
                    inputs={"prompt": case.prompt, "case_id": case.case_id},
                    outputs=outputs,
                    expected={"expect_found": case.expect_found,
                              "expect_short_circuit": case.expect_short_circuit},
                )
                for metric_key, _axis in metric_pairs():
                    logger.score(metric_key, record_id=record_id, score=bool(res.get("passed")))
            except Exception:
                pass

    gate_passes = sum(1 for c in cases if c.get("gate", {}).get("passed"))
    overall_passes = sum(1 for c in cases if c.get("passed"))
    summary = {
        "mode": "selftest" if selftest else ("live" if live else "dry"),
        "db_path": db_path,
        "rounds": rounds,
        "n_cases": len(cases),
        "gate_passes": gate_passes,
        "gate_fails": len(cases) - gate_passes,
        "overall_passes": overall_passes,
        "all_gate_passed": gate_passes == len(cases),
        "scorecard": {
            "enabled": logger is not None,
            "live": bool(getattr(logger, "is_live", False)) if logger else False,
            "reason": getattr(logger, "reason", None) if logger else "logging off (not --live)",
            "url": logger.url() if logger else None,
            "run_id": run_id,
        },
        "cases": cases,
    }
    return summary


def _print_summary(summary: dict) -> None:
    print("=" * 70)
    print(f"THE TRIAL — eval harness [{summary['mode']}]  db={summary['db_path']}")
    print("=" * 70)
    for c in summary["cases"]:
        gate = c.get("gate", {})
        mark = "PASS" if c.get("passed") else "FAIL"
        gmark = "gate:ok" if gate.get("passed") else f"gate:FAIL({len(gate.get('violations', []))})"
        extra = ""
        if c.get("found") is not None:
            extra = f" found={c.get('found')} drug={c.get('drug')!r} n_users={c.get('n_users')}"
        print(f"  [{mark}] {c['case_id']:30} {gmark}{extra}")
        for v in gate.get("violations", []):
            print(f"          ! {v['rule']} @ {v['turn']}: {v['detail'][:90]}")
        for w in c.get("soft_warnings", []) or []:
            print(f"          ~ soft: {w}")
        if c.get("error"):
            print(f"          x error: {c['error']}")
    print("-" * 70)
    sc = summary["scorecard"]
    print(
        f"gate: {summary['gate_passes']}/{summary['n_cases']} passed  |  "
        f"overall: {summary['overall_passes']}/{summary['n_cases']}  |  "
        f"scorecard: {'LIVE' if sc['live'] else 'noop'} ({sc['reason']})"
    )
    if sc.get("url"):
        print(f"scorecard run: {sc['url']}")
    print("=" * 70)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="trial-harness",
        description="Eval harness for The Trial: HARD G1-G5 gate + graded axes.",
    )
    p.add_argument("--db", default="data/posts.db", help="Read-only posts DB (default: data/posts.db).")
    p.add_argument("--rounds", type=int, default=2, help="Debate rounds (default: 2).")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--selftest", action="store_true",
                      help="Offline: stubbed debate, no API, no ScoreCard. Validates harness+gate.")
    mode.add_argument("--live", action="store_true",
                      help="Real debate + LLM judge + ScoreCard logging.")
    p.add_argument("--json", action="store_true", help="Emit the full summary as JSON.")
    args = p.parse_args(argv)

    summary = run_harness(
        db_path=args.db, rounds=args.rounds, selftest=args.selftest, live=args.live,
    )

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    else:
        _print_summary(summary)

    # In selftest the bar is: every case clears the HARD gate. In live, same
    # hard requirement (graded axes are reported but gate-pass is the gate).
    ok = summary["all_gate_passed"]
    if args.selftest and not ok:
        print("SELFTEST FAILED: at least one case did not clear the gate.", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
