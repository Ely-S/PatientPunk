"""Build and verify the local r/covidlonghaulers comments dataset.

The source export is a large JSONL file with one Reddit comment object per
line. This module keeps the split dataset deliberately raw: every valid source
record is preserved as JSONL, while CSV indexes and metadata make it easier to
browse, validate, and build later derived analysis layers.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, TextIO


REPO_ROOT = Path(__file__).resolve().parents[3]
DATASET_ROOT = REPO_ROOT / "dataset"
DEFAULT_SOURCE = Path.home() / "Downloads" / "r_covidlonghaulers_comments_all.jsonl"
DEFAULT_OUTPUT = DATASET_ROOT / "covidlonghaulers_comments"

INDEX_FIELDS = [
    "source_line",
    "id",
    "name",
    "date_utc",
    "created_utc",
    "author",
    "score",
    "link_id",
    "parent_id",
    "is_submitter",
    "stickied",
    "body_preview",
    "permalink",
    "chunk_file",
]

CHUNK_FIELDS = [
    "relative_path",
    "partition",
    "partition_label",
    "part",
    "rows",
    "bytes",
    "sha256",
    "min_created_utc",
    "max_created_utc",
    "min_date_utc",
    "max_date_utc",
]

INDEX_FILE_FIELDS = ["relative_path", "rows", "bytes"]


@dataclass(frozen=True)
class DatasetConfig:
    source: Path = DEFAULT_SOURCE
    output: Path = DEFAULT_OUTPUT
    max_rows_per_jsonl: int = 10_000
    max_rows_per_index: int = 50_000
    preview_chars: int = 500
    progress_every: int = 100_000
    replace: bool = False


@dataclass
class JsonlChunkState:
    partition: str
    partition_label: str
    part: int
    path: Path
    handle: BinaryIO
    sha256: Any
    rows: int = 0
    bytes_written: int = 0
    min_created_utc: int | None = None
    max_created_utc: int | None = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def iso_from_timestamp(timestamp: int | None) -> str:
    if timestamp is None:
        return ""
    return datetime.fromtimestamp(timestamp, timezone.utc).replace(microsecond=0).isoformat()


def csv_value(value: int | None) -> int | str:
    return value if value is not None else ""


def parse_created_utc(value: Any) -> tuple[int | None, str, str, str]:
    """Return timestamp, ISO date, partition path, and partition label."""
    if value is None or value == "":
        return None, "", "unknown_date", "unknown"

    try:
        timestamp = int(float(value))
        created = datetime.fromtimestamp(timestamp, timezone.utc)
    except (OverflowError, OSError, TypeError, ValueError):
        return None, "", "unknown_date", "unknown"

    return (
        timestamp,
        created.replace(microsecond=0).isoformat(),
        f"year={created:%Y}/month={created:%m}",
        f"{created:%Y-%m}",
    )


def compact_preview(value: Any, limit: int) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).replace("\r", " ").replace("\n", " ").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def simple_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def reddit_permalink(value: Any) -> str:
    permalink = value or ""
    if permalink and isinstance(permalink, str) and permalink.startswith("/"):
        return "https://www.reddit.com" + permalink
    return str(permalink)


def ensure_positive_config(config: DatasetConfig) -> None:
    if config.max_rows_per_jsonl <= 0:
        raise SystemExit("ERROR: --max-rows-per-jsonl must be positive.")
    if config.max_rows_per_index <= 0:
        raise SystemExit("ERROR: --max-rows-per-index must be positive.")
    if config.preview_chars < 0:
        raise SystemExit("ERROR: --preview-chars cannot be negative.")


def safe_remove_dataset_path(path: Path) -> None:
    resolved = path.resolve()
    dataset_root = DATASET_ROOT.resolve()
    if resolved != dataset_root and dataset_root not in resolved.parents:
        raise RuntimeError(f"Refusing to remove path outside dataset/: {resolved}")
    if path.exists():
        shutil.rmtree(path)


class JsonlChunkWriter:
    """Write valid JSONL records to partitioned, row-limited chunk files."""

    def __init__(self, output_root: Path, max_rows_per_file: int) -> None:
        self.output_root = output_root
        self.max_rows_per_file = max_rows_per_file
        self.states: dict[str, JsonlChunkState] = {}
        self.next_part: defaultdict[str, int] = defaultdict(lambda: 1)
        self.metadata: list[dict[str, Any]] = []

    def write(
        self,
        partition: str,
        partition_label: str,
        raw_line: bytes,
        created_utc: int | None,
    ) -> str:
        state = self.states.get(partition)
        if state is None:
            state = self._open_state(partition, partition_label)
            self.states[partition] = state

        data = raw_line if raw_line.endswith(b"\n") else raw_line + b"\n"
        state.handle.write(data)
        state.sha256.update(data)
        state.rows += 1
        state.bytes_written += len(data)
        self._track_timestamp(state, created_utc)

        relative_path = state.path.relative_to(self.output_root).as_posix()
        if state.rows >= self.max_rows_per_file:
            self._close_state(partition)
        return relative_path

    def close_all(self) -> None:
        for partition in list(self.states):
            self._close_state(partition)

    def _open_state(self, partition: str, partition_label: str) -> JsonlChunkState:
        part = self.next_part[partition]
        self.next_part[partition] += 1

        filename_label = partition_label.replace("/", "-")
        directory = self.output_root / "comments_jsonl" / Path(partition)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"comments_{filename_label}_part-{part:04d}.jsonl"

        return JsonlChunkState(
            partition=partition,
            partition_label=partition_label,
            part=part,
            path=path,
            handle=path.open("wb"),
            sha256=hashlib.sha256(),
        )

    def _close_state(self, partition: str) -> None:
        state = self.states.pop(partition)
        state.handle.close()
        self.metadata.append(
            {
                "relative_path": state.path.relative_to(self.output_root).as_posix(),
                "partition": state.partition,
                "partition_label": state.partition_label,
                "part": state.part,
                "rows": state.rows,
                "bytes": state.bytes_written,
                "sha256": state.sha256.hexdigest(),
                "min_created_utc": csv_value(state.min_created_utc),
                "max_created_utc": csv_value(state.max_created_utc),
                "min_date_utc": iso_from_timestamp(state.min_created_utc),
                "max_date_utc": iso_from_timestamp(state.max_created_utc),
            }
        )

    @staticmethod
    def _track_timestamp(state: JsonlChunkState, created_utc: int | None) -> None:
        if created_utc is None:
            return
        if state.min_created_utc is None or created_utc < state.min_created_utc:
            state.min_created_utc = created_utc
        if state.max_created_utc is None or created_utc > state.max_created_utc:
            state.max_created_utc = created_utc


class CsvPartWriter:
    """Write row-limited CSV files with a shared header."""

    def __init__(
        self,
        output_root: Path,
        directory_name: str,
        filename_prefix: str,
        fieldnames: list[str],
        max_rows_per_file: int,
    ) -> None:
        self.output_root = output_root
        self.directory = output_root / directory_name
        self.filename_prefix = filename_prefix
        self.fieldnames = fieldnames
        self.max_rows_per_file = max_rows_per_file
        self.part = 0
        self.rows_in_part = 0
        self.path: Path | None = None
        self.handle: TextIO | None = None
        self.writer: csv.DictWriter | None = None
        self.metadata: list[dict[str, Any]] = []

    def write(self, row: dict[str, Any]) -> None:
        if self.writer is None or self.rows_in_part >= self.max_rows_per_file:
            self._rotate()
        assert self.writer is not None
        self.writer.writerow(row)
        self.rows_in_part += 1

    def close(self) -> None:
        if self.handle is None or self.path is None:
            return
        path = self.path
        rows = self.rows_in_part
        self.handle.close()
        self.metadata.append(
            {
                "relative_path": path.relative_to(self.output_root).as_posix(),
                "rows": rows,
                "bytes": path.stat().st_size,
            }
        )
        self.path = None
        self.handle = None
        self.writer = None
        self.rows_in_part = 0

    def _rotate(self) -> None:
        self.close()
        self.part += 1
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / f"{self.filename_prefix}_part-{self.part:04d}.csv"
        self.handle = self.path.open("w", encoding="utf-8-sig", newline="")
        self.writer = csv.DictWriter(self.handle, fieldnames=self.fieldnames)
        self.writer.writeheader()
        self.rows_in_part = 0


def prepare_output(output: Path, replace: bool) -> Path:
    final_output = output.resolve()
    tmp_output = final_output.with_name(final_output.name + ".tmp")

    if final_output.exists():
        if not replace:
            raise SystemExit(f"ERROR: output already exists, use --replace to rebuild: {final_output}")
        safe_remove_dataset_path(final_output)

    if tmp_output.exists():
        if not replace:
            raise SystemExit(f"ERROR: temp output already exists, use --replace to rebuild: {tmp_output}")
        safe_remove_dataset_path(tmp_output)

    tmp_output.mkdir(parents=True, exist_ok=False)
    return tmp_output


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_dataset_readme(output_root: Path, manifest: dict[str, Any]) -> None:
    readme = f"""# r/covidlonghaulers Comments Dataset

Generated at: `{manifest["generated_at_utc"]}`

Source file: `{manifest["source_path"]}`

## Layout

- `comments_jsonl/year=YYYY/month=MM/*.jsonl`: full original Reddit comment JSON objects, one per line.
- `index/comments_index_part-*.csv`: browseable indexes with IDs, dates, authors, scores, body previews, Reddit permalinks, and source chunks.
- `metadata/manifest.json`: source hash, totals, settings, and date span.
- `metadata/chunks.csv`: row count and SHA-256 checksum for every JSONL chunk.
- `metadata/index_files.csv`: row count for every CSV index part.
- `metadata/summary_by_month.csv`: valid comment counts by month.
- `metadata/field_counts.csv`: observed source JSON fields and value types.
- `metadata/malformed_lines.jsonl`: malformed source lines, if any.

## Quick Checks

Verify the dataset:

```powershell
python dev/analysis/a0_extraction/build_comment_dataset.py --verify-only
```

Open the first index file:

```powershell
Invoke-Item "dataset\\covidlonghaulers_comments\\index\\comments_index_part-0001.csv"
```

Inspect a JSONL chunk:

```powershell
Get-Content "dataset\\covidlonghaulers_comments\\comments_jsonl\\year=2020\\month=07\\comments_2020-07_part-0001.jsonl" -TotalCount 3
```

## Totals

- Source lines: `{manifest["total_source_lines"]}`
- Valid records: `{manifest["valid_records"]}`
- Blank lines: `{manifest["blank_lines"]}`
- Malformed lines: `{manifest["malformed_lines"]}`
- JSONL chunk files: `{manifest["jsonl_chunk_files"]}`
- CSV index files: `{manifest["index_files"]}`
- Date span UTC: `{manifest["min_date_utc"]}` to `{manifest["max_date_utc"]}`
"""
    (output_root / "README.md").write_text(readme, encoding="utf-8")


def write_malformed_line(errors: TextIO, source_line: int, error: str, raw_line: bytes) -> None:
    errors.write(
        json.dumps(
            {
                "source_line": source_line,
                "error": error,
                "preview": raw_line[:500].decode("utf-8", errors="replace"),
            },
            ensure_ascii=False,
        )
        + "\n"
    )


def update_field_stats(
    record: dict[str, Any],
    field_presence: Counter[str],
    field_type_counts: defaultdict[str, Counter[str]],
) -> None:
    for field, value in record.items():
        field_presence[field] += 1
        field_type_counts[field][simple_type_name(value)] += 1


def build_index_row(
    record: dict[str, Any],
    source_line: int,
    date_utc: str,
    created_utc: int | None,
    chunk_file: str,
    preview_chars: int,
) -> dict[str, Any]:
    return {
        "source_line": source_line,
        "id": record.get("id", ""),
        "name": record.get("name", ""),
        "date_utc": date_utc,
        "created_utc": csv_value(created_utc),
        "author": record.get("author", ""),
        "score": record.get("score", ""),
        "link_id": record.get("link_id", ""),
        "parent_id": record.get("parent_id", ""),
        "is_submitter": record.get("is_submitter", ""),
        "stickied": record.get("stickied", ""),
        "body_preview": compact_preview(record.get("body", ""), preview_chars),
        "permalink": reddit_permalink(record.get("permalink")),
        "chunk_file": chunk_file,
    }


def build_field_count_rows(
    field_presence: Counter[str],
    field_type_counts: defaultdict[str, Counter[str]],
    valid_records: int,
) -> list[dict[str, Any]]:
    rows = []
    for field in sorted(field_presence):
        type_counts = dict(sorted(field_type_counts[field].items()))
        rows.append(
            {
                "field": field,
                "present_count": field_presence[field],
                "missing_count": valid_records - field_presence[field],
                "type_counts_json": json.dumps(type_counts, sort_keys=True),
            }
        )
    return rows


def build_dataset(config: DatasetConfig) -> Path:
    ensure_positive_config(config)

    source = config.source.expanduser().resolve()
    output = config.output.resolve()
    if not source.exists():
        raise SystemExit(f"ERROR: source not found: {source}")

    tmp_output = prepare_output(output, config.replace)
    metadata_dir = tmp_output / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    chunk_writer = JsonlChunkWriter(tmp_output, config.max_rows_per_jsonl)
    index_writer = CsvPartWriter(
        tmp_output,
        "index",
        "comments_index",
        INDEX_FIELDS,
        config.max_rows_per_index,
    )

    source_sha256 = hashlib.sha256()
    month_counts: Counter[str] = Counter()
    field_presence: Counter[str] = Counter()
    field_type_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)

    total_lines = 0
    blank_lines = 0
    valid_records = 0
    malformed_lines = 0
    min_created_utc: int | None = None
    max_created_utc: int | None = None

    errors_path = metadata_dir / "malformed_lines.jsonl"
    with source.open("rb") as source_handle, errors_path.open("w", encoding="utf-8", newline="\n") as errors:
        for raw_line in source_handle:
            total_lines += 1
            source_sha256.update(raw_line)

            if config.progress_every and total_lines % config.progress_every == 0:
                print(
                    f"processed={total_lines:,} valid={valid_records:,} "
                    f"malformed={malformed_lines:,}",
                    flush=True,
                )

            if not raw_line.strip():
                blank_lines += 1
                continue

            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                malformed_lines += 1
                write_malformed_line(errors, total_lines, str(exc), raw_line)
                continue

            if not isinstance(record, dict):
                malformed_lines += 1
                write_malformed_line(errors, total_lines, f"expected object, got {type(record).__name__}", raw_line)
                continue

            valid_records += 1
            update_field_stats(record, field_presence, field_type_counts)

            created_utc, date_utc, partition, partition_label = parse_created_utc(record.get("created_utc"))
            if created_utc is not None:
                min_created_utc = created_utc if min_created_utc is None else min(min_created_utc, created_utc)
                max_created_utc = created_utc if max_created_utc is None else max(max_created_utc, created_utc)

            chunk_file = chunk_writer.write(partition, partition_label, raw_line, created_utc)
            month_counts[partition_label] += 1
            index_writer.write(
                build_index_row(
                    record,
                    total_lines,
                    date_utc,
                    created_utc,
                    chunk_file,
                    config.preview_chars,
                )
            )

    chunk_writer.close_all()
    index_writer.close()

    chunk_rows = sorted(chunk_writer.metadata, key=lambda row: (row["partition"], int(row["part"])))
    write_csv(metadata_dir / "chunks.csv", CHUNK_FIELDS, chunk_rows)
    write_csv(metadata_dir / "index_files.csv", INDEX_FILE_FIELDS, index_writer.metadata)

    summary_rows = [
        {"month": month, "rows": rows}
        for month, rows in sorted(month_counts.items(), key=lambda item: (item[0] == "unknown", item[0]))
    ]
    write_csv(metadata_dir / "summary_by_month.csv", ["month", "rows"], summary_rows)
    write_csv(
        metadata_dir / "field_counts.csv",
        ["field", "present_count", "missing_count", "type_counts_json"],
        build_field_count_rows(field_presence, field_type_counts, valid_records),
    )

    manifest = {
        "dataset_name": "covidlonghaulers_comments",
        "generated_at_utc": utc_now_iso(),
        "source_path": str(source),
        "source_size_bytes": source.stat().st_size,
        "source_sha256": source_sha256.hexdigest(),
        "output_path": str(output),
        "max_rows_per_jsonl": config.max_rows_per_jsonl,
        "max_rows_per_index": config.max_rows_per_index,
        "preview_chars": config.preview_chars,
        "total_source_lines": total_lines,
        "blank_lines": blank_lines,
        "valid_records": valid_records,
        "malformed_lines": malformed_lines,
        "jsonl_chunk_files": len(chunk_rows),
        "index_files": len(index_writer.metadata),
        "min_created_utc": csv_value(min_created_utc),
        "max_created_utc": csv_value(max_created_utc),
        "min_date_utc": iso_from_timestamp(min_created_utc),
        "max_date_utc": iso_from_timestamp(max_created_utc),
    }

    (metadata_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_dataset_readme(tmp_output, manifest)

    tmp_output.rename(output)
    print(f"built dataset: {output}", flush=True)
    print(f"valid records: {valid_records:,}", flush=True)
    print(f"jsonl chunks: {len(chunk_rows):,}", flush=True)
    print(f"index files: {len(index_writer.metadata):,}", flush=True)
    return output


def count_csv_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            next(reader)
        except StopIteration:
            return 0
        return sum(1 for _ in reader)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def count_nonblank_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def verify_chunk(output: Path, row: dict[str, str]) -> tuple[int, list[str]]:
    path = output / row["relative_path"]
    expected_rows = int(row["rows"])
    expected_sha256 = row["sha256"]
    expected_partition = row["partition"]
    problems = []

    if not path.exists():
        return 0, [f"missing chunk file: {path}"]

    actual_rows = 0
    actual_sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        for raw_line in handle:
            actual_sha256.update(raw_line)
            actual_rows += 1
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                problems.append(f"invalid JSON in {path} line {actual_rows}: {exc}")
                continue

            _, _, actual_partition, _ = parse_created_utc(record.get("created_utc"))
            if actual_partition != expected_partition:
                problems.append(
                    f"partition mismatch in {path} line {actual_rows}: "
                    f"expected {expected_partition}, got {actual_partition}"
                )

    if actual_rows != expected_rows:
        problems.append(f"row mismatch for {path}: expected {expected_rows}, got {actual_rows}")
    if actual_sha256.hexdigest() != expected_sha256:
        problems.append(f"sha256 mismatch for {path}")

    return actual_rows, problems


def verify_dataset(output: Path = DEFAULT_OUTPUT) -> bool:
    output = output.resolve()
    metadata_dir = output / "metadata"
    manifest_path = metadata_dir / "manifest.json"
    chunks_path = metadata_dir / "chunks.csv"
    index_files_path = metadata_dir / "index_files.csv"
    errors_path = metadata_dir / "malformed_lines.jsonl"

    if not manifest_path.exists():
        raise SystemExit(f"ERROR: manifest not found: {manifest_path}")
    if not chunks_path.exists():
        raise SystemExit(f"ERROR: chunks metadata not found: {chunks_path}")
    if not index_files_path.exists():
        raise SystemExit(f"ERROR: index file metadata not found: {index_files_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    chunk_rows = read_csv_rows(chunks_path)
    index_file_rows = read_csv_rows(index_files_path)
    problems: list[str] = []

    total_jsonl_rows = 0
    for i, row in enumerate(chunk_rows, start=1):
        actual_rows, chunk_problems = verify_chunk(output, row)
        total_jsonl_rows += actual_rows
        problems.extend(chunk_problems)

        if i % 100 == 0:
            print(f"verified chunks={i:,} rows={total_jsonl_rows:,}", flush=True)

    total_index_rows = 0
    for row in index_file_rows:
        path = output / row["relative_path"]
        expected_rows = int(row["rows"])
        if not path.exists():
            problems.append(f"missing index file: {path}")
            continue
        actual_rows = count_csv_rows(path)
        if actual_rows != expected_rows:
            problems.append(f"index row mismatch for {path}: expected {expected_rows}, got {actual_rows}")
        total_index_rows += actual_rows

    malformed_count = count_nonblank_lines(errors_path)
    expected_valid = int(manifest["valid_records"])
    expected_malformed = int(manifest["malformed_lines"])

    if total_jsonl_rows != expected_valid:
        problems.append(f"valid record mismatch: manifest={expected_valid}, jsonl_rows={total_jsonl_rows}")
    if total_index_rows != expected_valid:
        problems.append(f"index row mismatch: manifest={expected_valid}, index_rows={total_index_rows}")
    if malformed_count != expected_malformed:
        problems.append(f"malformed count mismatch: manifest={expected_malformed}, errors={malformed_count}")
    if len(chunk_rows) != int(manifest["jsonl_chunk_files"]):
        problems.append(f"chunk count mismatch: manifest={manifest['jsonl_chunk_files']}, chunks_csv={len(chunk_rows)}")
    if len(index_file_rows) != int(manifest["index_files"]):
        problems.append(
            f"index file count mismatch: manifest={manifest['index_files']}, "
            f"index_files_csv={len(index_file_rows)}"
        )

    print(f"jsonl rows verified: {total_jsonl_rows:,}", flush=True)
    print(f"index rows verified: {total_index_rows:,}", flush=True)
    print(f"malformed lines: {malformed_count:,}", flush=True)

    if problems:
        print("verification failed:", flush=True)
        for problem in problems[:50]:
            print(f"- {problem}", flush=True)
        if len(problems) > 50:
            print(f"- ... {len(problems) - 50} more problems", flush=True)
        return False

    print("verification passed", flush=True)
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Split a large Reddit comments JSONL export into smaller structured files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-rows-per-jsonl", type=int, default=10_000)
    parser.add_argument("--max-rows-per-index", type=int, default=50_000)
    parser.add_argument("--preview-chars", type=int, default=500)
    parser.add_argument("--progress-every", type=int, default=100_000)
    parser.add_argument("--replace", action="store_true", help="Replace an existing output directory.")
    parser.add_argument("--verify-only", action="store_true", help="Only verify an already-built dataset.")
    return parser


def config_from_args(args: argparse.Namespace) -> DatasetConfig:
    return DatasetConfig(
        source=args.source,
        output=args.output,
        max_rows_per_jsonl=args.max_rows_per_jsonl,
        max_rows_per_index=args.max_rows_per_index,
        preview_chars=args.preview_chars,
        progress_every=args.progress_every,
        replace=args.replace,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = config_from_args(args)

    if args.verify_only:
        return 0 if verify_dataset(config.output) else 1

    output = build_dataset(config)
    return 0 if verify_dataset(output) else 1
