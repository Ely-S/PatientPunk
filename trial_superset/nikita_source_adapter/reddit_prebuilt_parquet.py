"""RedditPrebuiltParquet — feed a pre-built content_type=/bucket= parquet corpus into NATURAL's
reddit pipeline, skipping the .zst download+parse.

Drop-in replacement for RedditDumpProcessor. Three things it handles:

1. **Bucket re-partitioning.** NATURAL partitions by a HASH bucket (`bucket=081`, BUCKET_COUNT=160)
   and its scan filter is `bucket.isin(hash(subreddits)) AND subreddit.isin(names)`. Our corpus was
   written with `bucket=<subreddit-name>`, so those filters matched no fragments and curation
   silently produced zero records. We restage into the hash layout (source corpus left untouched).
2. **Reuse.** The contextualized dataset is corpus-level, not per-trial, so re-curating another NCT
   reuses it instead of rebuilding (restage+contextualize is minutes; curate is seconds).
3. **available_subreddits**, which condition_filter would normally set — needed by curate when that
   stage is skipped.
"""

import logging
import os
import shutil
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from naturalv2.sources.core import SourceStage
from naturalv2.sources.reddit.processing import build_contextualized_dataset
from naturalv2.sources.reddit.processing._utils import bucket_from_subreddit

if TYPE_CHECKING:
    from naturalv2.sources.core import CurationContext, StageState

logger = logging.getLogger(__name__)


def _subreddits(parquet_dir: str) -> list[str]:
    out = set()
    for _, dirs, _ in os.walk(parquet_dir):
        for d in dirs:
            if d.startswith("bucket="):
                out.add(d.split("=", 1)[1])
    return sorted(out)


def _has_parquet(path: str) -> bool:
    for _, _, files in os.walk(path):
        if any(f.endswith(".parquet") for f in files):
            return True
    return False


def _restage_to_hash_buckets(src: str, dst: str) -> None:
    """Rewrite <src>/content_type=X/bucket=<name>/ into <dst>/content_type=X/bucket=<hash>/."""
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    for content_type in sorted(
        d.split("=", 1)[1] for d in os.listdir(src) if d.startswith("content_type=")
    ):
        ct_dir = os.path.join(src, f"content_type={content_type}")
        for bucket_dir in sorted(d for d in os.listdir(ct_dir) if d.startswith("bucket=")):
            subreddit = bucket_dir.split("=", 1)[1]
            bucket = bucket_from_subreddit(pa.array([subreddit]))[0].as_py()
            table = ds.dataset(os.path.join(ct_dir, bucket_dir), format="parquet").to_table()
            out_dir = os.path.join(dst, f"content_type={content_type}", f"bucket={bucket}")
            os.makedirs(out_dir, exist_ok=True)
            pq.write_table(table, os.path.join(out_dir, "part-0.parquet"), compression="zstd")
            logger.info("  restaged %s/%s -> bucket=%s (%d rows)",
                        content_type, subreddit, bucket, table.num_rows)


class RedditPrebuiltParquet(SourceStage):
    """Contextualize a pre-built partitioned parquet corpus (no .zst parse)."""

    def __init__(
        self, parquet_dir: str, *, reuse_existing: bool = True, name: str | None = None
    ) -> None:
        super().__init__(name=name)
        self.parquet_dir = parquet_dir
        self.reuse_existing = reuse_existing

    async def run(self, context: "CurationContext", state: "StageState") -> "StageState":
        source_dir = self.source_dir(context)
        staging_dir = os.path.join(source_dir, "reddit_dump", "staging")
        final_dir = os.path.join(source_dir, "reddit_dump", "final")

        if self.reuse_existing and _has_parquet(final_dir):
            logger.info("%s: reusing contextualized dataset at %s", self.stage_name, final_dir)
        else:
            logger.info("%s: restaging %s into hash buckets", self.stage_name, self.parquet_dir)
            _restage_to_hash_buckets(self.parquet_dir, staging_dir)

            logger.info("%s: contextualizing -> %s", self.stage_name, final_dir)
            _ = build_contextualized_dataset(
                source_dir=staging_dir,
                dest_dir=final_dir,
                run_tag=context.experiment_name,
                cleanup_source=True,  # only removes OUR restaged copy, not the source corpus
            )

        state.payload = final_dir
        state.update(
            data_root=final_dir,
            source_dir=source_dir,
            available_subreddits=_subreddits(self.parquet_dir),
        )
        self.persist_dataset(
            context,
            namespace_paths={f"{context.source_name}_cleaned": final_dir},
        )
        return state
