"""Contracts for the garlic beliefs-and-use probe."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from probes.garlic_pharmacology import claim as garlic
from probes.garlic_pharmacology.evidence import (
    TARGETS,
    author_hash,
    collect_windows,
    matching_author_hashes,
    mention_windows,
)
from probes.models import CohortMember, SourceWindow, Unit
from probes.psychedelic_pharmacology.evidence import BOT_AUTHORS

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_garlic_cohort_db", SCRIPTS / "build_garlic_cohort_db.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = _load_builder()


def _unit(text: str = "I crush raw garlic and let it sit for allicin.") -> Unit:
    window = SourceWindow(
        source_window_id="w1",
        source_type="comment",
        source_id="c1",
        text=text,
    )
    return Unit(
        unit_key="u1",
        author_hash="abc",
        target="garlic",
        windows=[window],
        character_count=len(text),
    )


def _event(**overrides) -> dict:
    base = {
        "source_window_id": "w1",
        "source_id": "c1",
        "source_type": "comment",
        "speech_act": "food_list",
        "speech_act_quote": "garlic is on the high histamine list",
        "subject": "self",
        "subject_quote": "I cannot eat garlic",
        "exposure_status": "unclear",
        "exposure_status_quote": "garlic is on the high histamine list",
        "adverse_event_status": "not_stated",
        "polarity": "anti_use",
        "mechanisms": ["histamine_or_mcas_trigger"],
    }
    base.update(overrides)
    return base


def _envelope(*events) -> dict:
    return {"target_drug": "garlic", "events": list(events)}


# ── Retrieval / hasher ─────────────────────────────────────────────────────


def test_hasher_matches_db_to_corpus():
    source = (REPO / "scripts/db_to_corpus.py").read_text()
    assert "hashlib.sha256(username.encode()).hexdigest()" in source
    assert author_hash("Alice") == hashlib.sha256(b"Alice").hexdigest()
    assert author_hash("Alice") != author_hash("alice")


def test_targets_are_single_garlic_fts_query():
    assert list(TARGETS) == ["garlic"]
    fts, term = TARGETS["garlic"]
    assert fts == "garlic OR allicin OR kyolic"
    assert term.search("allium sativum extract")
    assert term.search("Kyolic aged garlic")
    assert term.search("allicin 450mg")
    assert not term.search("allium cepa only")
    assert not term.search("🧄")


def test_cohort_sql_is_one_select_of_hash_and_target():
    sql = (REPO / "probes/garlic_pharmacology/cohort.sql").read_text()
    statement = sql.strip().rstrip(";")
    assert ";" not in statement
    assert statement.upper().startswith("SELECT")
    assert "author_hash" in statement
    assert "target" in statement
    assert "treatment_reports" not in statement


def test_mention_windows_keep_neighboring_paragraphs():
    text = "Before.\n\nI take allicin for biofilm.\n\nAfter.\n\nOther."
    windows = mention_windows(text, TARGETS["garlic"][1])
    assert windows == ["Before.\n\nI take allicin for biofilm.\n\nAfter."]


def _source_db(tmp_path: Path) -> Path:
    path = tmp_path / "reddit.db"
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE posts (id TEXT, subreddit TEXT, created_utc INT, score INT, "
        "num_comments INT, title TEXT, selftext TEXT, author TEXT, permalink TEXT)"
    )
    db.execute(
        "CREATE TABLE comments (id TEXT, subreddit TEXT, created_utc INT, score INT, "
        "body TEXT, author TEXT, link_id TEXT, parent_id TEXT)"
    )
    db.execute(
        "CREATE VIRTUAL TABLE posts_fts USING fts5(title, selftext, content='posts', "
        "content_rowid='rowid')"
    )
    db.execute(
        "CREATE VIRTUAL TABLE comments_fts USING fts5(body, content='comments', "
        "content_rowid='rowid')"
    )
    db.execute(
        "INSERT INTO posts (id, created_utc, title, selftext, author) "
        "VALUES ('p1', 1, 'allicin', 'I take allicin for biofilm', 'alice')"
    )
    db.execute(
        "INSERT INTO posts_fts(rowid, title, selftext) "
        "SELECT rowid, title, selftext FROM posts"
    )
    db.execute(
        "INSERT INTO comments (id, created_utc, body, author) "
        "VALUES ('c1', 1, 'high histamine: tomato, garlic, spinach', 'bob')"
    )
    db.execute(
        "INSERT INTO comments (id, created_utc, body, author) "
        "VALUES ('c2', 1, 'garlic protocol', 'AutoModerator')"
    )
    db.execute(
        "INSERT INTO comments (id, created_utc, body, author) "
        "VALUES ('c3', 1, 'no allium words here', 'carol')"
    )
    db.execute("INSERT INTO comments_fts(rowid, body) SELECT rowid, body FROM comments")
    db.commit()
    db.close()
    return path


def test_matching_author_hashes_drops_bots_and_uses_targets(tmp_path):
    path = _source_db(tmp_path)
    hashes = matching_author_hashes(path)
    assert author_hash("alice") in hashes
    assert author_hash("bob") in hashes
    assert author_hash("AutoModerator") not in hashes
    assert author_hash("carol") not in hashes
    assert "AutoModerator" in BOT_AUTHORS


def test_collect_windows_filters_to_cohort_members(tmp_path):
    path = _source_db(tmp_path)
    members = [CohortMember(author_hash=author_hash("alice"), target="garlic")]
    windows = collect_windows(path, members)
    key = (author_hash("alice"), "garlic")
    assert key in windows
    assert all("allicin" in w.text.lower() for w in windows[key])
    assert (author_hash("bob"), "garlic") not in windows


def _insert_comment(path: Path, source_id: str, created_utc: int, body: str, author: str) -> None:
    db = sqlite3.connect(path)
    db.execute(
        "INSERT INTO comments (id, created_utc, body, author) VALUES (?, ?, ?, ?)",
        (source_id, created_utc, body, author),
    )
    db.execute(
        "INSERT INTO comments_fts(rowid, body) SELECT rowid, body FROM comments WHERE id = ?",
        (source_id,),
    )
    db.commit()
    db.close()


def test_collect_windows_dedups_identical_text_across_source_ids(tmp_path):
    path = _source_db(tmp_path)
    body = "high histamine: tomato, garlic, spinach"
    _insert_comment(path, "c4", 2, body, "bob")
    members = [CohortMember(author_hash=author_hash("bob"), target="garlic")]
    windows = collect_windows(path, members)[(author_hash("bob"), "garlic")]
    assert len(windows) == 1
    assert windows[0].source_id == "c1"


def test_collect_windows_keeps_identical_text_from_different_authors(tmp_path):
    path = _source_db(tmp_path)
    body = "high histamine: tomato, garlic, spinach"
    _insert_comment(path, "c4", 2, body, "alice")
    members = [
        CohortMember(author_hash=author_hash("alice"), target="garlic"),
        CohortMember(author_hash=author_hash("bob"), target="garlic"),
    ]
    windows = collect_windows(path, members)
    alice = windows[(author_hash("alice"), "garlic")]
    bob = windows[(author_hash("bob"), "garlic")]
    assert any(w.text == body or body in w.text for w in alice)
    assert any(w.text == body or body in w.text for w in bob)


# ── Claim schema ───────────────────────────────────────────────────────────


def test_food_list_is_included_but_cannot_carry_use_payload():
    text = "I cannot eat garlic. garlic is on the high histamine list with tomato."
    payload = _envelope(_event())
    envelope = garlic.validate_extraction(payload, _unit(text))
    event = envelope.events[0]
    assert event.included is True
    assert event.use_payload_allowed is False

    claims = garlic.parse_claims(payload, _unit(text))
    assert claims[0].included is True
    assert claims[0].values.get("doses") == []

    bad_ae = _event(
        adverse_event_status="reported",
        adverse_events=[
            {
                "category": "histamine_flare",
                "raw_event": "histamine",
                "quote": "high histamine list",
                "confidence": "high",
            }
        ],
    )
    with pytest.raises(ValueError, match="use_payload_allowed|subject=self"):
        garlic.validate_extraction(_envelope(bad_ae), _unit(text))

    bad_dose = _event(
        doses=[{"raw_text": "1 clove", "quote": "garlic", "unit": "clove"}]
    )
    with pytest.raises(ValueError, match="use_payload_allowed|subject=self"):
        garlic.validate_extraction(_envelope(bad_dose), _unit(text))


def test_actual_use_carries_both_payloads_and_is_included():
    text = (
        "I crush raw garlic and let it sit to get the allicin, trying to break up biofilm."
    )
    payload = _envelope(
        _event(
            speech_act="actual_use",
            speech_act_quote="I crush raw garlic and let it sit",
            subject="self",
            subject_quote="I crush raw garlic",
            exposure_status="actual_use",
            exposure_status_quote="I crush raw garlic and let it sit",
            preparation="crushed_wait_allicin",
            polarity="pro_use",
            mechanisms=["gut_or_biofilm"],
            adverse_event_status="not_stated",
        )
    )
    envelope = garlic.validate_extraction(payload, _unit(text))
    event = envelope.events[0]
    assert event.use_payload_allowed is True
    assert event.included is True
    assert event.preparation == garlic.Preparation.CRUSHED_WAIT_ALLICIN
    assert garlic.Mechanism.GUT_OR_BIOFILM in event.mechanisms
    claims = garlic.parse_claims(payload, _unit(text))
    assert claims[0].included is True
    assert claims[0].values["polarity"] == "pro_use"
    assert claims[0].values["preparation"] == "crushed_wait_allicin"


def test_culinary_is_not_included():
    text = "Dinner was pasta with garlic bread on the side."
    payload = _envelope(
        _event(
            speech_act="culinary",
            speech_act_quote="garlic bread on the side",
            subject="self",
            subject_quote="Dinner was pasta",
            exposure_status="unclear",
            exposure_status_quote="garlic bread on the side",
            polarity=None,
            mechanisms=[],
        )
    )
    event = garlic.validate_extraction(payload, _unit(text)).events[0]
    assert event.included is False
    assert event.use_payload_allowed is False
    assert garlic.parse_claims(payload, _unit(text))[0].included is False


def test_other_person_actual_use_is_not_included_and_has_no_use_payload():
    text = "Garlic helped my friend with biofilm."
    payload = _envelope(
        _event(
            speech_act="actual_use",
            speech_act_quote="Garlic helped my friend",
            subject="other",
            subject_quote="my friend",
            exposure_status="actual_use",
            exposure_status_quote="Garlic helped my friend",
            polarity="pro_use",
            mechanisms=["gut_or_biofilm"],
        )
    )
    event = garlic.validate_extraction(payload, _unit(text)).events[0]
    assert event.included is False
    assert event.use_payload_allowed is False


def test_preparation_required_only_when_use_payload_allowed():
    text = "I crush raw garlic and let it sit to get the allicin."
    missing = _event(
        speech_act="actual_use",
        speech_act_quote="I crush raw garlic",
        subject="self",
        subject_quote="I crush raw garlic",
        exposure_status="actual_use",
        exposure_status_quote="I crush raw garlic",
        preparation=None,
    )
    with pytest.raises(ValueError, match="preparation"):
        garlic.validate_extraction(_envelope(missing), _unit(text))

    food = _event(preparation="raw_clove")
    with pytest.raises(ValueError, match="preparation"):
        garlic.validate_extraction(
            _envelope(food),
            _unit("I cannot eat garlic. garlic is on the high histamine list"),
        )


def test_placeholder_ban_on_free_text_but_not_form_enum():
    text = "I take garlic 500 mg."
    payload = _envelope(
        _event(
            speech_act="actual_use",
            speech_act_quote="I take garlic 500 mg",
            subject="self",
            subject_quote="I take garlic",
            exposure_status="actual_use",
            exposure_status_quote="I take garlic 500 mg",
            preparation="unspecified_form",
            doses=[{"raw_text": "unknown", "quote": "500 mg", "unit": "mg"}],
            adverse_event_status="not_stated",
            polarity="pro_use",
            mechanisms=[],
        )
    )
    with pytest.raises(ValueError, match="placeholder"):
        garlic.validate_extraction(payload, _unit(text))

    payload["events"][0]["doses"] = [
        {"raw_text": "500 mg", "quote": "500 mg", "unit": "mg"}
    ]
    envelope = garlic.validate_extraction(payload, _unit(text))
    assert envelope.events[0].preparation == garlic.Preparation.UNSPECIFIED_FORM
    values = garlic.parse_claims(payload, _unit(text))[0].values
    assert values["preparation"] == "unspecified_form"


def test_quote_grounding_floor_and_empty_quotes():
    assert garlic.QUOTE_GROUNDING_MIN_OVERLAP == 0.5
    text = "I take raw garlic cloves every morning."
    payload = _envelope(
        _event(
            speech_act="actual_use",
            speech_act_quote="I take raw garlic cloves every morning",
            subject="self",
            subject_quote="I take raw garlic",
            exposure_status="actual_use",
            exposure_status_quote="I take raw garlic cloves",
            preparation="raw_clove",
            adverse_event_status="not_stated",
        )
    )
    garlic.validate_extraction(payload, _unit(text))
    # 2/4 tokens in-window is exactly the floor and must pass (paraphrase with
    # some invented filler is allowed at the floor).
    payload["events"][0]["speech_act_quote"] = "take garlic zzzyy wwxx"
    assert garlic._grounding("take garlic zzzyy wwxx", text) == 0.5
    garlic.validate_extraction(payload, _unit(text))
    # 2/5 tokens is below the floor and must fail.
    payload["events"][0]["speech_act_quote"] = "take garlic zzzyy wwxx vvuu"
    with pytest.raises(ValueError, match="not grounded"):
        garlic.validate_extraction(payload, _unit(text))
    payload["events"][0]["speech_act_quote"] = "   "
    with pytest.raises(ValueError, match="non-empty"):
        garlic.validate_extraction(payload, _unit(text))


def test_paraphrased_quotes_pass_if_grounded():
    text = "I take raw garlic cloves every morning. Later I also tried Kyolic."
    payload = _envelope(
        _event(
            speech_act="actual_use",
            speech_act_quote="daily raw garlic, later Kyolic",
            subject="self",
            subject_quote="I take garlic",
            exposure_status="actual_use",
            exposure_status_quote="raw garlic then Kyolic",
            preparation="raw_clove",
            adverse_event_status="not_stated",
        )
    )
    garlic.validate_extraction(payload, _unit(text))
    # Compressed non-contiguous restatement is a paraphrase, not a failure.
    payload["events"][0]["speech_act_quote"] = "I take Kyolic"
    garlic.validate_extraction(payload, _unit(text))


def test_adverse_event_status_rules():
    text = "I take garlic. No side effects from the garlic."
    use = dict(
        speech_act="actual_use",
        speech_act_quote="I take garlic",
        subject="self",
        subject_quote="I take garlic",
        exposure_status="actual_use",
        exposure_status_quote="I take garlic",
        preparation="unspecified_form",
        polarity="pro_use",
        mechanisms=[],
    )
    with pytest.raises(ValueError, match="explicit_none requires"):
        garlic.validate_extraction(
            _envelope(_event(**use, adverse_event_status="explicit_none")),
            _unit(text),
        )
    with pytest.raises(ValueError, match="not_stated cannot"):
        garlic.validate_extraction(
            _envelope(
                _event(
                    **use,
                    adverse_event_status="not_stated",
                    adverse_event_status_quote="No side effects from the garlic",
                )
            ),
            _unit(text),
        )
    with pytest.raises(ValueError, match="reported requires"):
        garlic.validate_extraction(
            _envelope(_event(**use, adverse_event_status="reported")),
            _unit(text),
        )
    with pytest.raises(ValueError, match="adverse events require status=reported"):
        garlic.validate_extraction(
            _envelope(
                _event(
                    **use,
                    adverse_event_status="not_stated",
                    adverse_events=[
                        {
                            "category": "gi",
                            "raw_event": "nausea",
                            "quote": "I take garlic",
                            "confidence": "low",
                        }
                    ],
                )
            ),
            _unit(text),
        )
    ok = _event(
        **use,
        adverse_event_status="explicit_none",
        adverse_event_status_quote="No side effects from the garlic",
    )
    assert garlic.validate_extraction(_envelope(ok), _unit(text)).events[0].included


def test_duplicate_events_in_one_unit_rejected():
    text = "garlic is on the high histamine list. I cannot eat garlic."
    event = _event()
    with pytest.raises(ValueError, match="duplicate event"):
        garlic.validate_extraction(_envelope(event, dict(event)), _unit(text))


def test_source_must_belong_to_unit():
    text = "garlic is on the high histamine list. I cannot eat garlic."
    payload = _envelope(_event(source_window_id="nope"))
    with pytest.raises(ValueError, match="does not belong"):
        garlic.validate_extraction(payload, _unit(text))


def test_cited_authority_requires_a_garlic_quote():
    text = "Dr Smith told me to try Kyolic garlic extract."
    payload = _envelope(
        _event(
            speech_act="recommendation",
            speech_act_quote="try Kyolic garlic extract",
            subject="other",
            subject_quote="Dr Smith told me",
            exposure_status="unclear",
            exposure_status_quote="try Kyolic garlic extract",
            cited_authority="clinician",
            polarity="pro_use",
            mechanisms=[],
        )
    )
    with pytest.raises(ValueError, match="cited_authority"):
        garlic.validate_extraction(payload, _unit(text))
    payload["events"][0]["cited_authority_quote"] = "Dr Smith told me to try Kyolic garlic"
    garlic.validate_extraction(payload, _unit(text))


def test_use_payload_allowed_is_two_conjuncts():
    """DESIGN §7: actual_use + self allows the use payload even if exposure_status is unclear."""

    text = "I take raw garlic cloves every morning."
    payload = _envelope(
        _event(
            speech_act="actual_use",
            speech_act_quote="I take raw garlic cloves every morning",
            subject="self",
            subject_quote="I take raw garlic",
            exposure_status="unclear",
            exposure_status_quote="I take raw garlic cloves",
            preparation="raw_clove",
            adverse_event_status="not_stated",
            polarity="pro_use",
            mechanisms=[],
        )
    )
    event = garlic.validate_extraction(payload, _unit(text)).events[0]
    assert event.use_payload_allowed is True
    assert event.included is True
    assert event.preparation == garlic.Preparation.RAW_CLOVE


def test_prompt_states_load_bearing_distinctions():
    system, prompt = garlic.build_prompt(_unit(), variant=0, feedback=None)
    assert "food_list" in system
    assert "Garlic bread" in system
    assert "never a negative" in system
    assert "worsened my long COVID" in system
    assert "SHORT PARAPHRASE" in system
    assert "verbatim excerpt" in system
    assert "contiguous span" not in system
    assert "Do not splice" not in system
    assert "AND exposure_status=actual_use" not in system
    assert "TARGET DRUG: garlic" in prompt
    bare = _unit().model_copy(update={"target": None})
    with pytest.raises(ValueError, match="require a target"):
        garlic.build_prompt(bare)


def test_included_does_not_gate_belief_on_actual_use():
    """Regression: included must not be reused as the use-payload gate."""

    text = "I crush raw garlic and let it sit to get the allicin, trying to break up biofilm."
    payload = _envelope(
        _event(
            speech_act="actual_use",
            speech_act_quote="I crush raw garlic and let it sit",
            subject="self",
            subject_quote="I crush raw garlic",
            exposure_status="actual_use",
            exposure_status_quote="I crush raw garlic",
            preparation="crushed_wait_allicin",
            polarity="pro_use",
            mechanisms=["gut_or_biofilm"],
            adverse_event_status="not_stated",
        )
    )
    event = garlic.validate_extraction(payload, _unit(text)).events[0]
    assert event.included and event.use_payload_allowed
    assert event.mechanisms == [garlic.Mechanism.GUT_OR_BIOFILM]


# ── Cohort builder ─────────────────────────────────────────────────────────


def test_builder_imports_evidence_targets_and_hasher():
    assert builder.TARGETS is TARGETS
    assert builder.author_hash is author_hash
    assert builder.TARGET == "garlic"


def test_json_garlic_re_uses_word_boundaries():
    assert builder.JSON_GARLIC_RE.search("raw garlic: helped")
    assert not builder.JSON_GARLIC_RE.search("ungarlicked potatoes")


def test_write_cohort_one_row_per_author(tmp_path):
    out = tmp_path / "garlic_cohort.db"
    hashes = {author_hash("alice"), author_hash("bob")}
    builder.write_cohort(out, hashes)
    rows = sqlite3.connect(out).execute(
        "SELECT author_hash, target FROM garlic_cohort ORDER BY author_hash"
    ).fetchall()
    assert len(rows) == 2
    assert {row[1] for row in rows} == {"garlic"}
    sql = (REPO / "probes/garlic_pharmacology/cohort.sql").read_text()
    resolved = sqlite3.connect(out).execute(sql).fetchall()
    assert len(resolved) == 2


def test_json_garlic_hashes_and_gate1_hallucination_pass(tmp_path):
    records = [
        {
            "record_meta": {"author_hash": author_hash("alice")},
            "fields": {
                "medications": {"values": ["allicin"]},
                "treatment_outcome": {"values": None},
            },
        },
        {
            "record_meta": {"author_hash": "jsononlyhash"},
            "fields": {
                "treatment_outcome": {"values": ["raw garlic: helped: constipation"]},
            },
        },
    ]
    json_path = tmp_path / "records.json"
    json_path.write_text(json.dumps(records))
    json_all, json_any, json_health = builder.json_garlic_hashes(json_path)
    assert author_hash("alice") in json_any
    assert "jsononlyhash" in json_any
    assert author_hash("alice") in json_health

    stats = {"jsononlyhash": (10, 0), "jsononly2": (11, 0)}
    fts = {f"f{i:04d}" for i in range(1928)}
    json_any = {f"f{i:04d}" for i in range(500)} | {"jsononlyhash", "jsononly2"}
    json_all = set(json_any) | {f"f{i:04d}" for i in range(1815)}
    json_health = set(json_any)
    assert builder._gate1(fts, json_all, json_any, json_health, stats) == 0


def _gate1_args(*, overlap: int = 500, json_only: tuple[str, ...] = ("jsononlyhash",)):
    """Realistically sized GATE 1 inputs, so each test trips only its own branch."""

    fts = {f"f{i:04d}" for i in range(1928)}
    json_any = {f"f{i:04d}" for i in range(overlap)} | set(json_only)
    json_all = json_any | {f"f{i:04d}" for i in range(1815)}
    return fts, json_all, json_any, set(json_any)


def test_gate1_fails_when_json_only_row_has_source_tokens():
    fts, json_all, json_any, json_health = _gate1_args(overlap=501)
    stats = {"jsononlyhash": (3, 1)}
    assert builder._gate1(fts, json_all, json_any, json_health, stats) == 1


def test_gate1_fails_on_empty_overlap():
    fts, json_all, json_any, json_health = _gate1_args(overlap=0, json_only=())
    json_any = {f"x{i:04d}" for i in range(502)}
    json_all = json_any | fts
    assert builder._gate1(fts, json_all, json_any, set(json_any), {}) == 1


def test_gate1_fails_when_json_side_collapses():
    """A record-shape drift must fail the gate, not pass it with 0 / 0."""

    fts, json_all, _json_any, _json_health = _gate1_args()
    assert builder._gate1(fts, json_all, set(), set(), {}) == 1


def test_gate1_fails_when_json_only_row_has_no_source_items():
    """Zero items is 'cannot confirm', not 'hallucination confirmed'."""

    fts, json_all, json_any, json_health = _gate1_args(overlap=501)
    stats = {"jsononlyhash": (0, 0)}
    assert builder._gate1(fts, json_all, json_any, json_health, stats) == 1


def test_failed_gate1_writes_no_cohort_db(tmp_path, monkeypatch):
    """Stage 2 names the cohort DB by path; a failed gate must not leave one."""

    out = tmp_path / "garlic_cohort.db"
    records = [{"record_meta": {"author_hash": "x"}, "fields": {}}]
    json_path = tmp_path / "records.json"
    json_path.write_text(json.dumps(records))
    monkeypatch.setattr(
        builder, "matching_author_hashes", lambda _db: {f"f{i:04d}" for i in range(1928)}
    )
    monkeypatch.setattr(builder, "source_item_stats", lambda _db, _hashes: {})
    status = builder.main(
        [
            "--source-db", str(tmp_path / "reddit.db"),
            "--records-json", str(json_path),
            "--out", str(out),
        ]
    )
    assert status == 1
    assert not out.exists()
