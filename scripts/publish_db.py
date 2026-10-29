#!/usr/bin/env python3
"""Finalize, publish and audit PatientPunk databases (see docs/database-provenance.md).

Usage:
    # Checkpoint the WAL, check integrity, hash, and write the output fields into
    # <stem>_provenance.yaml beside the database.
    uv run python scripts/publish_db.py finalize path/to/example.db

    # Check the YAML, upload the database to a new S3 key, verify it by download,
    # add its row to s3://patientpunk/INDEX.md with a conditional write, then
    # upload the finished YAML beside it.
    uv run python scripts/publish_db.py publish path/to/example.db \
        --s3-uri s3://patientpunk/<prefix>/example.db --label multi-treatment

    # List S3 databases with no provenance YAML beside them or no INDEX.md row.
    uv run python scripts/publish_db.py audit [--prefix scientific_validation/] [--strict]

S3 calls use boto3 with the AWS CLI's credentials (~/.aws or AWS_* environment variables).
"""
import argparse
import hashlib
import re
import sqlite3
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml
from botocore.exceptions import ClientError

BUCKET = "patientpunk"
INDEX_KEY = "INDEX.md"
CATALOG_PREFIX = "database_catalog/"  # browsing copies of databases listed elsewhere; audit skips them
TOTALS_PREFIX = "Listed databases:"
# Machine-local absolute paths: drive letters and home directories.
LOCAL_PATH = re.compile(r"(?i)(?<![\w:/])[a-z]:[\\/]|(?<![\w.])/(?:Users|home)/")
SECRET = re.compile(r"sk-or-v1-|sk-ant-|sk-proj-|\bAKIA[0-9A-Z]{16}\b|X-Amz-Signature=")


class PublishError(Exception):
    """A check failed; the message says what to fix."""


# ── Local database ────────────────────────────────────────────────────────────

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def provenance_path(db: Path) -> Path:
    return db.with_name(f"{db.stem}_provenance.yaml")


def load_record(path: Path) -> dict:
    if not path.exists():
        raise PublishError(f"{path.name} not found beside the database; create it before the run "
                           "(docs/database-provenance.md)")
    try:
        record = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise PublishError(f"{path.name} is not valid YAML (quote values such as 'repo:'): {e}") from e
    if not isinstance(record, dict):
        raise PublishError(f"{path.name} is not a YAML mapping")
    return record


def save_record(path: Path, record: dict) -> None:
    path.write_text(yaml.safe_dump(record, sort_keys=False, allow_unicode=True, width=100),
                    encoding="utf-8", newline="\n")


def require_database(db: Path) -> None:
    if not db.is_file():  # sqlite3.connect would quietly create an empty one
        raise PublishError(f"{db} does not exist")


def leftover_journals(db: Path) -> list[str]:
    """Non-empty -wal or -journal files, which hold writes the .db alone does not."""
    return [p.name for p in (db.with_name(db.name + "-wal"), db.with_name(db.name + "-journal"))
            if p.exists() and p.stat().st_size > 0]


def finalize_database(db: Path) -> dict:
    """Checkpoint, integrity-check and hash a closed database; return the output fields."""
    conn = sqlite3.connect(db)
    try:
        busy, _, _ = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    finally:
        conn.close()
    if busy:
        raise PublishError(f"{db.name} is still open in another process; close every writer and retry")
    if leftover := leftover_journals(db):
        raise PublishError(f"{', '.join(leftover)} still holds data after the checkpoint; "
                           "close every connection and retry")
    conn = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
    try:
        integrity = [row[0] for row in conn.execute("PRAGMA integrity_check")]
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        counts = {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
        run_ids = ([r[0] for r in conn.execute("SELECT run_id FROM extraction_runs ORDER BY run_id")]
                   if "extraction_runs" in tables else [])
    finally:
        conn.close()
    if integrity != ["ok"]:
        raise PublishError(f"PRAGMA integrity_check failed for {db.name}: {integrity[:5]}")
    return {"sha256": sha256_file(db), "bytes": db.stat().st_size, "wal_checkpointed": True,
            "sqlite_integrity_check": "ok", "table_row_counts": counts, "extraction_run_ids": run_ids}


def walk_strings(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk_strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_strings(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def check_record(record: dict, db: Path) -> list[str]:
    """Problems that stop publication; an empty list means the record is ready."""
    problems = []
    get = lambda section: record.get(section) if isinstance(record.get(section), dict) else {}
    database, code, output, publication = get("database"), get("code"), get("output"), get("publication")
    if record.get("record_kind") != "database_provenance":
        problems.append("record_kind must be database_provenance")
    if database.get("filename") != db.name:
        problems.append(f"database.filename is {database.get('filename')!r}, expected {db.name!r}")
    if database.get("status") != "completed":
        problems.append(f"database.status is {database.get('status')!r}; publish only a completed run")
    if not database.get("completed_utc"):
        problems.append("database.completed_utc is missing")
    if not re.fullmatch(r"[0-9a-f]{40}", str(code.get("commit_sha", ""))):
        problems.append("code.commit_sha must be the full 40-character SHA")
    if code.get("working_tree") not in ("clean", "dirty"):
        problems.append("code.working_tree must be clean or dirty")
    if not isinstance(record.get("inputs"), list):
        problems.append("inputs must be a list")
    commands = record.get("commands")
    if not isinstance(commands, list) or not commands:
        problems.append("commands must list the commands that built the database")
    else:
        for i, cmd in enumerate(commands):
            missing = [f for f in ("command", "cwd", "exit_code") if not isinstance(cmd, dict) or f not in cmd]
            if missing:
                problems.append(f"commands[{i}] is missing {', '.join(missing)}")
    if publication.get("status") != "local":
        problems.append(f"publication.status is {publication.get('status')!r}; a published record is frozen")
    if output.get("sqlite_integrity_check") != "ok" or output.get("wal_checkpointed") is not True:
        problems.append("output is not finalized; run `scripts/publish_db.py finalize` first")
    elif leftover := leftover_journals(db):
        problems.append(f"{', '.join(leftover)} appeared after finalizing; the database changed")
    elif output.get("sha256") != sha256_file(db) or output.get("bytes") != db.stat().st_size:
        problems.append("the database changed after finalizing; finalize it again")
    for where, text in walk_strings(record):
        if LOCAL_PATH.search(text):
            problems.append(f"{where} has a machine-local absolute path; use a repo: or data: root")
        if SECRET.search(text):
            problems.append(f"{where} looks like it contains a secret")
    return problems


# ── S3 ────────────────────────────────────────────────────────────────────────

class S3:
    """The few S3 operations publishing needs, through boto3 (same credentials as the AWS CLI)."""

    def __init__(self):
        import boto3  # imported here so finalize and the tests never create an AWS client
        self.client = boto3.client("s3")

    @staticmethod
    def _code(e: ClientError) -> str:
        return str(e.response.get("Error", {}).get("Code", ""))

    def head(self, bucket: str, key: str) -> dict | None:
        try:
            return self.client.head_object(Bucket=bucket, Key=key)
        except ClientError as e:
            if self._code(e) in ("404", "NoSuchKey", "NotFound"):
                return None
            raise

    def upload(self, path: Path, bucket: str, key: str, sha256: str) -> None:
        self.client.upload_file(str(path), bucket, key, ExtraArgs={"Metadata": {"sha256": sha256}})

    def download(self, bucket: str, key: str, path: Path) -> None:
        self.client.download_file(bucket, key, str(path))

    def get_text(self, bucket: str, key: str) -> tuple[str, str] | None:
        """(text, ETag), or None if the object does not exist."""
        try:
            obj = self.client.get_object(Bucket=bucket, Key=key)
        except ClientError as e:
            if self._code(e) in ("404", "NoSuchKey"):
                return None
            raise
        return obj["Body"].read().decode("utf-8"), obj["ETag"]

    def put_text(self, bucket: str, key: str, text: str, *, content_type: str,
                 if_match: str | None = None, if_none_match: bool = False) -> bool:
        """Write a small text object; False if the condition failed (someone else wrote first)."""
        data = text.encode("utf-8")
        kwargs = {"Bucket": bucket, "Key": key, "Body": data, "ContentType": content_type,
                  "Metadata": {"sha256": hashlib.sha256(data).hexdigest()}}
        if if_match:
            kwargs["IfMatch"] = if_match
        if if_none_match:
            kwargs["IfNoneMatch"] = "*"
        try:
            self.client.put_object(**kwargs)
        except ClientError as e:
            if self._code(e) in ("PreconditionFailed", "ConditionalRequestConflict", "412", "409"):
                return False
            raise
        return True

    def list_keys(self, bucket: str, prefix: str = "") -> list[dict]:
        pages = self.client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
        return [obj for page in pages for obj in page.get("Contents", [])]


def parse_s3_uri(uri: str) -> tuple[str, str]:
    m = re.fullmatch(r"s3://([^/]+)/(.+)", uri)
    if not m:
        raise PublishError(f"{uri!r} is not an s3://bucket/key URI")
    return m.group(1), m.group(2)


# ── INDEX.md ──────────────────────────────────────────────────────────────────

def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def table_bounds(lines: list[str]) -> tuple[int, int]:
    """(header line, one past the last row) of the catalog table."""
    for i, line in enumerate(lines):
        if line.startswith("| Original S3 object"):
            end = i + 2
            while end < len(lines) and lines[end].startswith("|"):
                end += 1
            return i, end
    raise PublishError("INDEX.md has no table starting with '| Original S3 object'")


def index_rows(text: str) -> list[dict]:
    lines = text.splitlines()
    start, end = table_bounds(lines)
    header = _cells(lines[start])
    return [dict(zip(header, _cells(line))) for line in lines[start + 2:end]]


def add_index_row(text: str, row: dict) -> str:
    """Insert one row in URI order and refresh the totals line."""
    lines = text.splitlines()
    start, end = table_bounds(lines)
    header = _cells(lines[start])
    rows = [dict(zip(header, _cells(line))) for line in lines[start + 2:end]]
    if any(r.get("Original S3 object") == row["Original S3 object"] for r in rows):
        raise PublishError(f"INDEX.md already lists {row['Original S3 object']}")
    header += [c for c in row if c not in header]  # older rows leave a new column blank
    rows.append(row)
    rows.sort(key=lambda r: r["Original S3 object"].strip("`"))
    align = ["---:" if c == "Bytes" else "---" for c in header]
    table = [_row(header), _row(align)] + [_row([r.get(c, "") for c in header]) for r in rows]
    total_bytes = sum(int(r["Bytes"]) for r in rows if r.get("Bytes", "").isdigit())
    totals = (f"{TOTALS_PREFIX} {len(rows)} objects, {total_bytes:,} bytes. "
              f"Updated {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} by `scripts/publish_db.py`.")
    head = [line for line in lines[:start] if not line.startswith(TOTALS_PREFIX)]
    while head and head[-1] == "":
        head.pop()
    return "\n".join(head + ["", totals, ""] + table + lines[end:]) + "\n"


def update_index(s3: S3, bucket: str, row: dict, attempts: int = 5) -> None:
    """Add a row with a conditional write, retrying when another writer got there first."""
    for _ in range(attempts):
        current = s3.get_text(bucket, INDEX_KEY)
        if current is None:
            raise PublishError(f"s3://{bucket}/{INDEX_KEY} does not exist; build it from an inventory first "
                               "(docs/database-provenance.md)")
        text, etag = current
        if s3.put_text(bucket, INDEX_KEY, add_index_row(text, row),
                       content_type="text/markdown; charset=utf-8", if_match=etag):
            break
        time.sleep(1)
    else:
        raise PublishError(f"INDEX.md kept changing under us; tried {attempts} times")


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_finalize(args) -> None:
    db = args.db
    require_database(db)
    yaml_path = provenance_path(db)
    record = load_record(yaml_path)
    if (record.get("publication") or {}).get("status") == "published":
        raise PublishError(f"{yaml_path.name} is published and frozen; a change is a new snapshot")
    output = finalize_database(db)
    record["output"] = {**(record.get("output") or {}), **output}
    save_record(yaml_path, record)
    print(f"finalized {db.name}: sha256 {output['sha256']}, {output['bytes']:,} bytes, "
          f"{len(output['table_row_counts'])} tables, {len(output['extraction_run_ids'])} extraction runs")
    print(f"wrote the output fields to {yaml_path.name}; set database.status and completed_utc yourself")


def cmd_publish(args, s3: S3 | None = None) -> None:
    s3 = s3 or S3()
    db = args.db
    require_database(db)
    yaml_path = provenance_path(db)
    record = load_record(yaml_path)
    if problems := check_record(record, db):
        raise PublishError("not ready to publish:\n  - " + "\n  - ".join(problems))
    bucket, key = parse_s3_uri(args.s3_uri)
    if Path(key).name != db.name:
        raise PublishError(f"the S3 key must end with {db.name}")
    yaml_key = key[: -len(db.name)] + yaml_path.name
    for k in (key, yaml_key):
        if s3.head(bucket, k) is not None:
            raise PublishError(f"s3://{bucket}/{k} already exists; published snapshots are never overwritten")

    sha = record["output"]["sha256"]
    s3.upload(db, bucket, key, sha)
    uploaded = datetime.now(UTC)  # before the verification download, which can take as long
    try:
        publish_uploaded(s3, args, db, yaml_path, record, bucket, key, yaml_key, sha, uploaded)
    except Exception as e:
        raise PublishError(f"{e}\ns3://{bucket}/{key} is uploaded but publishing is incomplete; finish the "
                           "remaining steps by hand (docs/database-provenance.md) and record them") from e


def publish_uploaded(s3: S3, args, db: Path, yaml_path: Path, record: dict,
                     bucket: str, key: str, yaml_key: str, sha: str, uploaded: datetime) -> None:
    """Everything after the database upload: verify, add the INDEX.md row, then upload the YAML."""
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / db.name
        s3.download(bucket, key, copy)
        if sha256_file(copy) != sha:
            raise PublishError(f"s3://{bucket}/{key} does not match the local SHA-256; do not use it")
    head = s3.head(bucket, key) or {}

    update_index(s3, bucket, {
        "Original S3 object": f"`s3://{bucket}/{key}`",
        "Catalog copy": "none",
        "Label": args.label,
        "Original upload date": f"{uploaded:%Y-%m-%d}",
        "Bytes": str(db.stat().st_size),
        "Run date": str(record["database"]["completed_utc"])[:10],
        "SHA-256": f"`{sha}`",
        "Provenance": f"`s3://{bucket}/{yaml_key}`",
    })
    record["publication"] = {
        **record["publication"], "status": "published", "s3_uri": f"s3://{bucket}/{key}",
        "s3_version_id": head.get("VersionId"), "uploaded_utc": uploaded.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "downloaded_sha256_matches": True, "catalog_copy_uri": None,
        "catalog_verified_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    save_record(yaml_path, record)
    text = yaml_path.read_text(encoding="utf-8")
    if not s3.put_text(bucket, yaml_key, text, content_type="application/yaml", if_none_match=True):
        raise PublishError(f"s3://{bucket}/{yaml_key} appeared during publishing; it was not overwritten")
    print(f"published s3://{bucket}/{key}")
    print(f"provenance s3://{bucket}/{yaml_key}")
    print(f"INDEX.md row added in s3://{bucket}/{INDEX_KEY}")


def audit(s3: S3, bucket: str, prefix: str) -> list[dict]:
    keys = {o["Key"]: o for o in s3.list_keys(bucket, prefix)}
    index = s3.get_text(bucket, INDEX_KEY)
    listed = {r.get("Original S3 object", "").strip("`") for r in index_rows(index[0])} if index else set()
    report = []
    for key, obj in sorted(keys.items()):
        if not key.endswith(".db") or key.startswith(CATALOG_PREFIX):
            continue
        yaml_key = key[: -len(".db")] + "_provenance.yaml"
        report.append({"s3_uri": f"s3://{bucket}/{key}", "bytes": obj.get("Size"),
                       "provenance": yaml_key in keys, "in_index": f"s3://{bucket}/{key}" in listed})
    return report


def cmd_audit(args, s3: S3 | None = None) -> int:
    report = audit(s3 or S3(), BUCKET, args.prefix)
    for r in report:
        gaps = [g for g, ok in (("no provenance YAML", r["provenance"]), ("not in INDEX.md", r["in_index"]))
                if not ok]
        print(f"{'ok  ' if not gaps else 'GAP '} {r['s3_uri']}" + (f"  ({'; '.join(gaps)})" if gaps else ""))
    print(f"{len(report)} databases: {sum(r['provenance'] for r in report)} with provenance YAML, "
          f"{sum(r['in_index'] for r in report)} in INDEX.md")
    complete = all(r["provenance"] and r["in_index"] for r in report)
    return 0 if complete or not args.strict else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    f = sub.add_parser("finalize", help="checkpoint, integrity-check and hash a database")
    f.add_argument("db", type=Path)
    p = sub.add_parser("publish", help="upload a finalized database, update INDEX.md, upload its YAML")
    p.add_argument("db", type=Path)
    p.add_argument("--s3-uri", required=True, help="new s3://bucket/key ending with the database filename")
    p.add_argument("--label", required=True, help="scope label for INDEX.md, e.g. multi-treatment or source-corpus")
    a = sub.add_parser("audit", help=f"list s3://{BUCKET} databases missing a provenance YAML or an INDEX.md row")
    a.add_argument("--prefix", default="")
    a.add_argument("--strict", action="store_true", help="exit 1 if any database has a gap")
    args = ap.parse_args(argv)
    try:
        if args.command == "finalize":
            cmd_finalize(args)
        elif args.command == "publish":
            cmd_publish(args)
        else:
            return cmd_audit(args)
    except PublishError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
