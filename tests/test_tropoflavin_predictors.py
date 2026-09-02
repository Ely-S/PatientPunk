from pathlib import Path

import pytest
from pydantic import ValidationError

from studies.tropoflavin_nootropics.analyze_78dhf_predictors import (
    CrossCompoundBaseline,
    CohortDataset,
    ReasonRecord,
    TargetAuthor,
    Vote,
    cross_compound_baseline,
    load_reason_records,
    merge_datasets,
    summarize_predictor,
)
from studies.tropoflavin_nootropics.comparator_support import (
    DEFAULT_COHORT_CONFIG,
    load_comparator_cohort,
)
from studies.tropoflavin_nootropics.extract_78dhf_reasons import (
    AuthorContext,
    BatchItem,
    CachedReasonBatch,
    ReasonItemResult,
    _cache_path,
    _extract_with_split,
    _parse_response,
    _request_payload,
    _request_sha256,
    _write_cache,
)


def _vote(
    author_number: int,
    slug: str,
    sentiment: str,
    subreddit: str = "Nootropics",
    post_date: int = 1,
) -> Vote:
    return Vote(
        author_hash=f"{author_number:032x}",
        subreddit=subreddit,
        compound_slug=slug,
        report_id=author_number,
        post_id=f"post-{author_number}",
        sentiment=sentiment,  # type: ignore[arg-type]
        signal="strong",
        post_date=post_date,
        run_id=1,
    )


def _target(
    author_number: int,
    sentiment: str,
    reason: str,
    subreddit: str = "Nootropics",
    post_date: int = 1,
) -> TargetAuthor:
    vote = _vote(author_number, "78dhf", sentiment, subreddit, post_date)
    return TargetAuthor(
        author_hash=vote.author_hash,
        subreddit=subreddit,
        vote=vote,
        side_effects=frozenset(
            {"insomnia or sleep disruption"} if author_number % 2 else set()
        ),
        dose_bands=frozenset({"10 to <25 mg"}),
        route_buckets=frozenset({"oral mucosal"}),
        reasons=frozenset({reason}),
    )


def test_cross_compound_baseline_gives_each_compound_equal_weight() -> None:
    cohort = load_comparator_cohort(DEFAULT_COHORT_CONFIG)
    votes = {
        "78dhf": {vote.author_hash: vote for vote in [_vote(1, "78dhf", "positive")]},
        "semax": {
            vote.author_hash: vote
            for vote in [_vote(index, "semax", "positive") for index in range(10, 20)]
        },
        "selank": {
            vote.author_hash: vote
            for vote in [_vote(index, "selank", "negative") for index in range(100, 200)]
        },
        "cerebrolysin": {
            vote.author_hash: vote
            for vote in [
                _vote(index, "cerebrolysin", "positive") for index in range(300, 309)
            ]
        },
    }

    baseline = cross_compound_baseline(votes, cohort, minimum_authors=10)

    assert baseline.eligible_compounds == 2
    assert baseline.mean_positive_rate == pytest.approx(0.5)
    assert baseline.mean_score == pytest.approx(0.0)


def test_merge_datasets_deduplicates_author_and_unions_predictors() -> None:
    cohort = load_comparator_cohort(DEFAULT_COHORT_CONFIG)
    older = _target(1, "negative", "anxiety or stress", post_date=1)
    newer = _target(
        1,
        "positive",
        "focus or attention",
        subreddit="StackAdvice",
        post_date=2,
    )
    newer = TargetAuthor(
        **{
            **newer.__dict__,
            "dose_bands": frozenset({"25 to <50 mg"}),
            "route_buckets": frozenset({"swallowed oral"}),
        }
    )
    datasets = (
        CohortDataset(
            subreddit="Nootropics",
            database=Path("one.db"),
            votes={"78dhf": {older.author_hash: older.vote}},
            target_authors={older.author_hash: older},
        ),
        CohortDataset(
            subreddit="StackAdvice",
            database=Path("two.db"),
            votes={"78dhf": {newer.author_hash: newer.vote}},
            target_authors={newer.author_hash: newer},
        ),
    )

    merged = merge_datasets(datasets, cohort)
    author = merged.target_authors[older.author_hash]

    assert len(merged.target_authors) == 1
    assert author.vote.sentiment == "positive"
    assert author.subreddit == "StackAdvice"
    assert author.dose_bands == frozenset({"10 to <25 mg", "25 to <50 mg"})
    assert author.route_buckets == frozenset({"oral mucosal", "swallowed oral"})
    assert author.reasons == frozenset(
        {"anxiety or stress", "focus or attention"}
    )


def test_reason_record_requires_explicit_flag_to_match_categories() -> None:
    with pytest.raises(ValidationError):
        ReasonRecord(
            subreddit="Nootropics",
            author_hash="1" * 32,
            explicit_reason_found=False,
            reasons=("anxiety or stress",),
            source_report_count=1,
        )


def test_load_reason_records_rejects_duplicate_author_cohort(tmp_path: Path) -> None:
    record = ReasonRecord(
        subreddit="Nootropics",
        author_hash="1" * 32,
        explicit_reason_found=True,
        reasons=("anxiety or stress",),
        source_report_count=1,
    )
    path = tmp_path / "records.jsonl"
    path.write_text(
        record.model_dump_json() + "\n" + record.model_dump_json() + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate reason record"):
        load_reason_records(path)


def test_reason_summary_uses_authors_with_an_explicit_reason_as_comparison() -> None:
    authors = tuple(
        _target(
            index,
            "positive" if index < 8 else "negative",
            "anxiety or stress" if index < 10 else "focus or attention",
        )
        for index in range(20)
    )
    baseline = CrossCompoundBaseline(
        metrics=(),
        mean_positive_rate=0.5,
        mean_score=0.0,
        score_sd=0.5,
    )

    summaries = summarize_predictor(
        authors,
        "reason",
        baseline,
        minimum_inference_authors=10,
    )
    anxiety = next(row for row in summaries if row.category == "anxiety or stress")

    assert anxiety.authors == 10
    assert anxiety.comparison_authors == 10
    assert anxiety.positive_rate == pytest.approx(0.8)
    assert anxiety.normalized_positive_points == pytest.approx(30.0)
    assert anxiety.status == "estimable association; not causal"


def test_parse_reason_response_requires_all_ids_in_order() -> None:
    valid = (
        '{"items":[{"item_id":2,"explicit_reason_found":true,'
        '"reasons":["mood or depression"]}]}'
    )
    parsed = _parse_response(valid, (2,))
    assert parsed.items[0].reasons == ("mood or depression",)

    with pytest.raises(ValueError, match="item IDs"):
        _parse_response(valid, (3,))


def test_reason_extraction_reassembles_split_cache_without_provider_call(
    tmp_path: Path,
) -> None:
    items = tuple(
        BatchItem(
            item_id=index,
            context=AuthorContext(
                subreddit="Nootropics",
                author_hash=f"{index + 1:032x}",
                reports=(f"report {index}",),
            ),
        )
        for index in range(4)
    )
    prompt_sha256 = "a" * 64
    provider = "openrouter"
    model = "test-model"
    for subset in (items[:2], items[2:]):
        payload = _request_payload(subset)
        request_sha256 = _request_sha256(prompt_sha256, model, payload)
        results = tuple(
            ReasonItemResult(
                item_id=item.item_id,
                explicit_reason_found=False,
                reasons=(),
            )
            for item in subset
        )
        _write_cache(
            _cache_path(tmp_path, request_sha256),
            CachedReasonBatch(
                request_sha256=request_sha256,
                prompt_sha256=prompt_sha256,
                provider=provider,
                model=model,
                items=results,
            ),
        )

    class FailingClient:
        class Messages:
            @staticmethod
            def create(**_: object) -> object:
                raise AssertionError("Provider should not be called")

        messages = Messages()

    combined = _extract_with_split(
        FailingClient(),
        items,
        "prompt",
        prompt_sha256,
        provider,
        model,
        512,
        tmp_path,
    )

    assert tuple(result.item_id for result in combined) == (0, 1, 2, 3)
    parent_sha = _request_sha256(prompt_sha256, model, _request_payload(items))
    assert _cache_path(tmp_path, parent_sha).is_file()
