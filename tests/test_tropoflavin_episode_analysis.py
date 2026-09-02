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
    EpisodeItemResult,
    EpisodeRecord,
    _parse_response,
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
