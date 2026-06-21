"""Unit tests for "The Trial" — the two-agent debate over a frozen packet.

Covers the deterministic spine (no network):
  - _resolve_drug: canonical + alias resolution, unknown -> passthrough.
  - build_packet: on a fixture DB AND on the live data/posts.db ldn row.
  - dedup: one user's many reports collapse to one verdict (strongest signal).
  - n=0 short-circuit: an unknown drug yields found=False with no debate claims.
  - the GATE trips on a fabricated turn and passes a clean cite-only turn.
  - synthesize numbers == packet numbers (code-templated, never drifting).

The Rumi heart is STUBBED (Hooper/DrVex.whirl monkeypatched) and RUMI_DATA_DIR
points at a tmp dir, so no agent ever makes a real LLM call. The synthesize
bottom-line LLM call is stubbed too.

pyproject sets pythonpath=["src"], so `agents.*` / `utilities.*` import bare.
This file lives in tests/ (collected only when pytest is given the tests/ path
explicitly — see CLAUDE.md gate notes).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from agents._common.packet import build_packet, _dedup_by_user, EvidencePacket
from agents._common.tools import _resolve_drug
from agents._common.validate import check_turn, render_citations
from agents.TheTrialAgent.synthesize import synthesize

SCHEMA = Path(__file__).parent.parent / "schema.sql"
LIVE_DB = Path(__file__).parent.parent / "data" / "posts.db"


# ── Fixture DB ───────────────────────────────────────────────────────────────
@pytest.fixture()
def trial_db(tmp_path: Path) -> Path:
    """A tiny DB built from schema.sql with a known LDN sentiment story.

    Two users report on LDN: user 'u_a' twice (weak positive, then strong
    positive — strongest wins), user 'u_b' once (strong negative). That makes
    n_reports=3, n_users=2, with 1 positive + 1 negative after dedup.
    A second drug 'zzz' has NO reports (the n=0 short-circuit case).
    """
    db = tmp_path / "trial.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))

    now = 1_700_000_000
    conn.execute(
        "INSERT INTO users (user_id, source_subreddit, scraped_at) VALUES (?,?,?)",
        ("u_a", "covidlonghaulers", now),
    )
    conn.execute(
        "INSERT INTO users (user_id, source_subreddit, scraped_at) VALUES (?,?,?)",
        ("u_b", "covidlonghaulers", now),
    )
    # Posts the reports point at (post_text reconstructs from title/body/parent).
    conn.executemany(
        "INSERT INTO posts (post_id, title, parent_id, user_id, body_text, post_date, scraped_at) "
        "VALUES (?,?,?,?,?,?,?)",
        [
            ("p_a1", "LDN thread", None, "u_a", "LDN gave me my mornings back, slowly.", now, now),
            ("p_a2", None, "p_a1", "u_a", "Update: it really helped after week six.", now + 10, now),
            ("p_b1", None, "p_a1", "u_b", "LDN wrecked my sleep, I had to stop.", now + 20, now),
        ],
    )
    conn.execute(
        "INSERT INTO treatment (canonical_name, aliases) VALUES (?,?)",
        ("ldn", json.dumps(["low dose naltrexone", "naltrexone (low dose)"])),
    )
    conn.execute("INSERT INTO treatment (canonical_name, aliases) VALUES (?,?)", ("zzz", None))
    ldn_id = conn.execute("SELECT id FROM treatment WHERE canonical_name='ldn'").fetchone()[0]
    conn.execute(
        "INSERT INTO extraction_runs (run_at, commit_hash, extraction_type, config) VALUES (?,?,?,?)",
        (now, "deadbeefcafebabe", "treatment_sentiment", "{}"),
    )
    run_id = conn.execute("SELECT run_id FROM extraction_runs LIMIT 1").fetchone()[0]
    conn.executemany(
        "INSERT INTO treatment_reports "
        "(run_id, post_id, user_id, drug_id, sentiment, signal_strength, side_effects) "
        "VALUES (?,?,?,?,?,?,?)",
        [
            (run_id, "p_a1", "u_a", ldn_id, "positive", "weak", json.dumps(["nausea"])),
            (run_id, "p_a2", "u_a", ldn_id, "positive", "strong", json.dumps(["worse sleep"])),
            (run_id, "p_b1", "u_b", ldn_id, "negative", "strong", json.dumps(["worse sleep", "insomnia"])),
        ],
    )
    conn.commit()
    conn.close()
    return db


# ── _resolve_drug ────────────────────────────────────────────────────────────
def test_resolve_drug_canonical(trial_db: Path):
    assert _resolve_drug("ldn", trial_db) == "ldn"
    assert _resolve_drug("LDN", trial_db) == "ldn"
    assert _resolve_drug("  Ldn ", trial_db) == "ldn"


def test_resolve_drug_alias(trial_db: Path):
    assert _resolve_drug("low dose naltrexone", trial_db) == "ldn"
    assert _resolve_drug("naltrexone (low dose)", trial_db) == "ldn"


def test_resolve_drug_unknown_passthrough(trial_db: Path):
    # Unknown -> lowercased passthrough (downstream queries simply return empty).
    assert _resolve_drug("Horse Dewormer", trial_db) == "horse dewormer"


# ── build_packet on the fixture ──────────────────────────────────────────────
def test_build_packet_fixture_counts_and_dedup(trial_db: Path):
    pkt = build_packet("ldn", trial_db)
    assert isinstance(pkt, EvidencePacket)
    assert pkt.found is True
    assert pkt.drug == "ldn"
    # 3 raw reports, 2 distinct users after dedup.
    assert pkt.n_reports == 3
    assert pkt.n_users == 2
    # User u_a's two positives collapse to one positive; u_b is one negative.
    assert pkt.counts["positive"] == 1
    assert pkt.counts["negative"] == 1
    assert pkt.pct["positive"] == 50
    assert pkt.pct["negative"] == 50
    # Quotes: at least one per pole, all verbatim from posts.
    poles = {q["pole"] for q in pkt.quotes}
    assert "pos" in poles and "neg" in poles
    # Required claim_ids exist.
    for cid in ("S1", "S2", "S3", "S4", "C3", "PROV"):
        assert cid in pkt.claims, f"missing claim {cid}"


def test_build_packet_alias_resolves(trial_db: Path):
    pkt = build_packet("low dose naltrexone", trial_db)
    assert pkt.found is True
    assert pkt.drug == "ldn"


def test_dedup_by_user_strongest_signal_wins(trial_db: Path):
    deduped = _dedup_by_user(trial_db, "ldn")
    by_user = {r["user_id"]: r for r in deduped}
    assert set(by_user) == {"u_a", "u_b"}
    # u_a had weak+strong positive -> strongest (strong) survives.
    assert by_user["u_a"]["signal"] == "strong"
    assert by_user["u_a"]["sentiment"] == "positive"
    assert by_user["u_b"]["sentiment"] == "negative"


def test_n0_short_circuit(trial_db: Path):
    """A treatment with zero reports -> found=False, no debate claims."""
    pkt = build_packet("zzz", trial_db)
    assert pkt.found is False
    assert pkt.n_reports == 0
    assert pkt.n_users == 0
    # Only provenance survives; there is nothing to put on trial.
    assert set(pkt.claims) <= {"PROV"}


def test_unknown_drug_short_circuit(trial_db: Path):
    pkt = build_packet("totally-not-a-real-drug", trial_db)
    assert pkt.found is False
    assert pkt.n_reports == 0


# ── The GATE ─────────────────────────────────────────────────────────────────
def test_gate_trips_on_fabricated_turn(trial_db: Path):
    pkt = build_packet("ldn", trial_db)
    # A fabricated turn: an orphan percentage with no backing citation (G1), a
    # long invented patient testimonial (>=8 words, G2), and a phantom claim_id
    # the packet does not list (G6 — the most important fabrication to catch).
    bad = (
        'Amazing news — 97% of people are cured! One patient even said '
        '"this fixed everything in a single day and gave me my life back". '
        'And do not forget quote("Q-neg-99").'
    )
    rules = {v.rule for v in check_turn(bad, pkt)}
    assert "G1" in rules, f"expected G1 (orphan number) in {rules}"
    assert "G2" in rules, f"expected G2 (long fabricated quote) in {rules}"
    assert "G6" in rules, f"expected G6 (phantom claim_id) in {rules}"


def test_gate_allows_rhetorical_short_quote(trial_db: Path):
    # A short rhetorical/illustrative quote is normal prose, NOT fabricated
    # evidence — it must not trip the gate (regression: the G2 false positive
    # that flagged Hooper's 'not someone saying "I feel a little better"').
    pkt = build_packet("ldn", trial_db)
    ok = 'That is not someone saying "I feel a little better"; cite("S4") is strong.'
    assert check_turn(ok, pkt) == []


def test_gate_trips_on_prescription_directive(trial_db: Path):
    pkt = build_packet("ldn", trial_db)
    bad = 'You should definitely start taking it right away.'
    rules = {v.rule for v in check_turn(bad, pkt)}
    assert "G4" in rules, f"expected G4 (prescription) in {rules}"


def test_gate_passes_clean_cite_only_turn(trial_db: Path):
    pkt = build_packet("ldn", trial_db)
    good = (
        'The hopeful read is cite("S2"), and the honest counterweight is '
        'cite("S3"). Remember cite("C3"): a low negative count is a sampling '
        'artifact, not proof of safety. This might be worth asking your doctor about.'
    )
    assert check_turn(good, pkt) == []


def test_render_citations_expands_and_marks_missing(trial_db: Path):
    pkt = build_packet("ldn", trial_db)
    rendered = render_citations('See cite("S1") and cite("NOPE").', pkt)
    assert "distinct" in rendered.lower()  # S1 render mentions distinct patients
    assert "[unknown claim NOPE]" in rendered or "[missing:NOPE]" in rendered


# ── synthesize numbers == packet numbers ─────────────────────────────────────
def _stub_synth_bottom_line(monkeypatch):
    import agents.TheTrialAgent.synthesize as syn
    monkeypatch.setattr(
        syn, "llm_call",
        lambda *a, **k: "Patients reported a mix of experiences; discuss with your doctor.",
    )
    monkeypatch.setattr(syn, "get_client", lambda: object())


def test_synthesize_numbers_match_packet(trial_db: Path, monkeypatch):
    _stub_synth_bottom_line(monkeypatch)
    pkt = build_packet("ldn", trial_db)
    briefing = synthesize(pkt, transcript=[])
    # The synthesized headline must use the packet's exact percentages.
    assert f"{pkt.pct['positive']}% positive" in briefing["text"]
    assert f"{pkt.pct['negative']}% negative" in briefing["text"]
    # n_users appears verbatim in the headline.
    assert f"across {pkt.n_users} patient" in briefing["text"]
    # The reported tier matches the packet's.
    assert briefing["tier"] == pkt.confidence_tier
    # The verbatim quotes used are the packet's quotes (no LLM rewriting).
    packet_quote_texts = {q["text"] for q in pkt.quotes}
    for q in briefing["pos_quotes"] + briefing["neg_quotes"]:
        assert q in packet_quote_texts
    # Safety coda is always present; no prescription directive in the briefing.
    assert "discuss with your doctor" in briefing["text"].lower()


def test_synthesize_briefing_passes_safety_gate(trial_db: Path, monkeypatch):
    """The code-templated briefing must carry no Rx directive (G4)."""
    _stub_synth_bottom_line(monkeypatch)
    pkt = build_packet("ldn", trial_db)
    briefing = synthesize(pkt, transcript=[])
    rules = {v.rule for v in check_turn(briefing["text"], pkt)}
    assert "G4" not in rules


# ── Stubbed Rumi debate (no LLM) ─────────────────────────────────────────────
def test_run_debate_with_stubbed_heart(trial_db: Path, tmp_path: Path, monkeypatch):
    """run_debate drives the alternating loop over STUBBED agent turns.

    We monkeypatch Hooper/DrVex.whirl so no Rumi LLM call happens, and point
    RUMI_DATA_DIR at a tmp dir so no disk history bleeds across runs.
    """
    monkeypatch.setenv("RUMI_DATA_DIR", str(tmp_path / "rumi"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-offline")

    import agents.HooperAgent.main as hooper_mod
    import agents.DrVexAgent.main as drvex_mod
    from agents.TheTrialAgent.main import run_debate

    class _Idea:
        def __init__(self, content):
            self.content = content

    monkeypatch.setattr(
        hooper_mod.Hooper, "whirl",
        lambda self, message, **kw: _Idea('Hopeful: cite("S2"). Ask your doctor.'),
        raising=False,
    )
    monkeypatch.setattr(
        drvex_mod.DrVex, "whirl",
        lambda self, message, **kw: _Idea('Skeptical: cite("S3") and cite("C3").'),
        raising=False,
    )

    pkt = build_packet("ldn", trial_db)
    transcript = run_debate(pkt, rounds=2)
    # rounds*2 = 4 alternating turns, Hooper first.
    assert len(transcript) == 4
    assert transcript[0]["agent"] == "hooper"
    assert transcript[1]["agent"] == "drvex"
    # Every stubbed turn passes the gate (cite-only).
    for turn in transcript:
        assert check_turn(turn["text"], pkt) == []


# ── Live DB smoke (only if data/posts.db exists) ─────────────────────────────
@pytest.mark.skipif(not LIVE_DB.exists(), reason="no live data/posts.db")
def test_build_packet_live_ldn():
    """build_packet on the live ldn row resolves and is internally consistent."""
    pkt = build_packet("ldn", LIVE_DB)
    if not pkt.found:
        pytest.skip("live DB has no ldn reports")
    assert pkt.drug == "ldn"
    assert pkt.n_reports >= 1
    assert pkt.n_users >= 1
    assert pkt.n_users <= pkt.n_reports
    # pct sums to ~100 over the four sentiment buckets (rounding tolerant).
    assert abs(sum(pkt.pct.values()) - 100) <= 2
    # C3 (silent-drop) is always present for a found packet.
    assert "C3" in pkt.claims
    assert "PROV" in pkt.claims
