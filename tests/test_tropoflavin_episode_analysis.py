from pathlib import Path

import pytest
from pydantic import ValidationError

from studies.tropoflavin_nootropics.analyze_78dhf_episodes import (
    Episode,
    fit_trend_model,
    load_episode_records,
)
from studies.tropoflavin_nootropics.extract_78dhf_episodes import (
    DoseValue,
    EpisodeExtractionManifest,
    EpisodeItemResult,
    EpisodeRecord,
    SourceDatabase,
    UsageSummary,
    _parse_response,
    _resume_results,
)


def test_dose_value_converts_to_milligrams() -> None:
    assert DoseValue(low=500, high=1_500, unit="mcg").midpoint_mg == 1.0
    assert DoseValue(low=0.01, high=0.02, unit="g").midpoint_mg == 15.0


def test_episode_item_requires_status_counts_to_match() -> None:
    with pytest.raises(ValidationError, match="Dose status"):
        EpisodeItemResult(
            item_id=0,
            explicit_personal_use=True,
            dose_status="single",
            doses=(),
            route_status="not_reported",
            routes=(),
            reasons=(),
        )

    with pytest.raises(ValidationError, match="Non-personal"):
        EpisodeItemResult(
            item_id=0,
            explicit_personal_use=False,
            dose_status="not_reported",
            doses=(),
            route_status="single",
            routes=("swallowed oral",),
            reasons=(),
        )


def test_parse_episode_response_requires_ordered_ids() -> None:
    valid = (
        '{"items":[{"item_id":2,"explicit_personal_use":true,'
        '"dose_status":"single","doses":[{"low":20,"high":20,'
        '"unit":"mg"}],"route_status":"single",'
        '"routes":["oral mucosal"],"reasons":["focus or attention"]}]}'
    )
    parsed = _parse_response(valid, (2,))
    assert parsed.items[0].doses[0].midpoint_mg == 20.0

    with pytest.raises(ValueError, match="item IDs"):
        _parse_response(valid, (3,))


def test_episode_response_deduplicates_identical_doses() -> None:
    duplicated = (
        '{"items":[{"item_id":0,"explicit_personal_use":true,'
        '"dose_status":"multiple","doses":['
        '{"low":20,"high":20,"unit":"mg"},'
        '{"low":20,"high":20,"unit":"mg"}],'
        '"route_status":"not_reported","routes":[],"reasons":[]}]}'
    )

    parsed = _parse_response(duplicated, (0,))

    assert parsed.items[0].dose_status == "single"
    assert len(parsed.items[0].doses) == 1


def test_load_episode_records_rejects_duplicate_source_episode(tmp_path: Path) -> None:
    record = EpisodeRecord(
        subreddit="Nootropics",
        author_hash="1" * 32,
        post_id="post-1",
        report_id=1,
        explicit_personal_use=True,
        dose_status="single",
        doses=(DoseValue(low=20, high=20, unit="mg"),),
        route_status="not_reported",
        routes=(),
        reasons=(),
    )
    path = tmp_path / "episodes.jsonl"
    path.write_text(
        record.model_dump_json() + "\n" + record.model_dump_json() + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate episode"):
        load_episode_records(path)


def test_clustered_trend_model_uses_dose_complete_episodes() -> None:
    episodes = []
    for author in range(30):
        for visit, dose in enumerate((5.0, 40.0)):
            high_dose = dose > 10
            episodes.append(
                Episode(
                    subreddit="Nootropics" if author < 15 else "NootropicsDepot",
                    author_hash=f"{author + 1:032x}",
                    post_id=f"post-{author}-{visit}",
                    report_id=author * 2 + visit + 1,
                    sentiment="positive" if high_dose else "negative",
                    side_effects=frozenset({"headache"} if high_dose else set()),
                    explicit_personal_use=True,
                    dose_status="single",
                    dose_midpoints_mg=(dose,),
                    route_status="not_reported",
                    routes=(),
                    reasons=(),
                )
            )

    estimate = fit_trend_model(
        episodes,
        "side-effect reporting",
        minimum_episodes=30,
        minimum_authors=20,
        minimum_community_episodes=5,
    )

    assert estimate.episodes == 60
    assert estimate.authors == 30
    assert estimate.status in {"estimated", "did not converge"}
    assert estimate.odds_ratio is not None
    assert estimate.odds_ratio > 1


def test_episode_resume_loads_only_completed_source_records(tmp_path: Path) -> None:
    record = EpisodeRecord(
        subreddit="Nootropics",
        author_hash="1" * 32,
        post_id="post-1",
        report_id=1,
        explicit_personal_use=False,
        dose_status="not_reported",
        doses=(),
        route_status="not_reported",
        routes=(),
        reasons=(),
    )
    records_path = tmp_path / "episode_records.jsonl"
    records_path.write_text(record.model_dump_json() + "\n", encoding="utf-8")
    from studies.tropoflavin_nootropics.comparator_support import sha256_file
    from studies.tropoflavin_nootropics.extract_78dhf_episodes import EpisodeContext

    manifest = EpisodeExtractionManifest(
        provider="openrouter",
        model="test",
        code_commit="abc",
        prompt_file="prompt.txt",
        prompt_sha256="a" * 64,
        max_text_chars=6_000,
        max_output_tokens=4_096,
        batch_size=8,
        source_databases=(
            SourceDatabase(subreddit="Nootropics", database="one.db", sha256="b" * 64),
        ),
        source_episodes=2,
        completed_episodes=1,
        personal_use_episodes=0,
        single_dose_episodes=0,
        single_route_episodes=0,
        missing_episodes=1,
        records_file=records_path.name,
        records_sha256=sha256_file(records_path),
        usage=UsageSummary(
            requests=1, prompt_tokens=10, completion_tokens=5, total_tokens=15
        ),
        completed_at="2026-09-02T00:00:00+00:00",
    )
    contexts = (
        EpisodeContext("Nootropics", "1" * 32, "post-1", 1, "first"),
        EpisodeContext("Nootropics", "2" * 32, "post-2", 2, "second"),
    )

    resumed = _resume_results(records_path, manifest, contexts)

    assert tuple(resumed) == (0,)
    assert resumed[0].explicit_personal_use is False
