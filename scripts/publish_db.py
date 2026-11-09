#!/usr/bin/env python3
"""Publish PatientPunk databases to s3://patientpunk with a provenance record, and audit the bucket.

Usage:
    # Checkpoint and integrity-check the database, build <stem>_provenance.yaml from its
    # extraction_runs table, upload the database to a new key and the YAML beside it, then
    # rebuild INDEX.md. If it stops after the upload, run the same command again to finish.
    uv run python scripts/publish_db.py publish path/to/example.db \
        --s3-uri s3://patientpunk/<prefix>/example.db --label multi-treatment \
        --purpose "what the database holds" --input "s3://patientpunk/<input>" --command "uv run python src/..."

    # Write a retrospective record beside a database already in S3, from a local copy of it.
    uv run python scripts/publish_db.py publish path/to/copy.db --s3-uri s3://patientpunk/<existing key> \
        --label multi-treatment --purpose "..." --record-only

    # List databases with no published provenance record; --write-index rebuilds INDEX.md.
    uv run python scripts/publish_db.py audit [--prefix scientific_validation/] [--strict] [--write-index]

Both writing commands need S3 versioning on the bucket, so that a rebuilt INDEX.md never loses the
previous one. S3 calls use boto3 with the AWS CLI's credentials (~/.aws or AWS_* variables).
"""
import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml
from botocore.exceptions import ClientError

BUCKET = "patientpunk"
INDEX_KEY = "INDEX.md"
REPOSITORY = "https://github.com/Ely-S/PatientPunk"
# Browsing copies: database_catalog/by-upload-date/uploaded-<date>/<label>/<original key>
CATALOG_COPY = re.compile(r"database_catalog/by-upload-date/uploaded-[\d-]+/([^/]+)/(.+\.db)")
SECRET = re.compile(r"sk-or-v1-|sk-ant-|sk-proj-|\bAKIA[0-9A-Z]{16}\b|X-Amz-Signature=")


class PublishError(Exception):
    """A check failed; the message says what to fix."""


def utc(when) -> str | None:
    if when is None:
        return None
    if not isinstance(when, datetime):
        when = datetime.fromtimestamp(when, UTC)
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def provenance_path(db: Path) -> Path:
    return db.with_name(f"{db.stem}_provenance.yaml")


# ── Local database ────────────────────────────────────────────────────────────

def finalize(db: Path) -> tuple[dict, list[dict]]:
    """Checkpoint, integrity-check and hash a closed database; return its output fields and runs."""
    if not db.is_file():  # sqlite3.connect would quietly create an empty one
        raise PublishError(f"{db} does not exist")
    conn = sqlite3.connect(db)
    try:
        busy, _, _ = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    finally:
        conn.close()
    leftover = [p.name for p in (db.with_name(db.name + "-wal"), db.with_name(db.name + "-journal"))
                if p.exists() and p.stat().st_size > 0]
    if busy or leftover:
        raise PublishError(f"{db.name} is still open in another process; close every writer and retry")
    conn = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
    try:
        integrity = [row[0] for row in conn.execute("PRAGMA integrity_check")]
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        counts = {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
        runs = []
        if "extraction_runs" in tables:
            has_finished = "finished_at" in {r[1] for r in conn.execute("PRAGMA table_info(extraction_runs)")}
            for run_id, run_at, commit, kind, config, finished in conn.execute(
                    "SELECT run_id, run_at, commit_hash, extraction_type, config, "
                    f"{'finished_at' if has_finished else 'NULL'} FROM extraction_runs ORDER BY run_id"):
                try:
                    config = json.loads(config)
                except (TypeError, ValueError):
                    pass  # kept as the stored text
                runs.append({"run_id": run_id, "extraction_type": kind, "commit_sha": commit,
                             "started_utc": utc(run_at),
                             "finished_utc": utc(finished) if has_finished else "not recorded (predates finished_at)",
                             "config": config})
    finally:
        conn.close()
    if integrity != ["ok"]:
        raise PublishError(f"PRAGMA integrity_check failed for {db.name}: {integrity[:5]}")
    output = {"sha256": sha256_file(db), "bytes": db.stat().st_size, "wal_checkpointed": True,
              "sqlite_integrity_check": "ok", "table_row_counts": counts,
              "extraction_run_ids": [r["run_id"] for r in runs]}
    return output, runs


def build_record(db: Path, args, output: dict, runs: list[dict], existing: dict) -> dict:
    """The provenance record, generated from the database. Sections a person added to a local YAML
    beforehand (processing, validation, comments...) are kept; the generated ones replace theirs."""
    dirty = {r["config"].get("git_dirty") for r in runs if isinstance(r["config"], dict)}
    finished = [r["finished_utc"] for r in runs if (r["finished_utc"] or "").endswith("Z")]
    local = existing.get("database") or {}
    record = {
        "schema_version": 1, "record_kind": "database_provenance",
        "record_method": "retrospective" if args.record_only else "contemporaneous",
        "generated_by": "scripts/publish_db.py, from the database's extraction_runs table",
        "database": {"filename": db.name,
                     "purpose": args.purpose or local.get("purpose"),
                     "status": "completed" if all(r["finished_utc"] is not None for r in runs) else "unfinished runs",
                     "started_utc": min((r["started_utc"] for r in runs), default=None),
                     "completed_utc": max(finished, default=None),
                     "supersedes": args.supersedes or local.get("supersedes")},
        "code": {"repository": REPOSITORY, "commit_shas": sorted({r["commit_sha"] for r in runs}),
                 "working_tree": "dirty" if True in dirty else "clean" if dirty == {False} else "not recorded"},
        "inputs": args.input or existing.get("inputs") or [],
        "commands": args.command or existing.get("commands") or [],
        "extraction_runs": runs, "output": output,
    }
    if not record["database"]["purpose"]:
        raise PublishError("--purpose is required: say what the database holds")
    if not record["inputs"] and not args.record_only:
        raise PublishError("--input is required: name each input snapshot, by S3 URI or data: path")
    if not record["commands"] and not args.record_only:
        raise PublishError("--command is required: list the commands that built the database, in order")
    return {**existing, **record}


# ── S3 ────────────────────────────────────────────────────────────────────────

class S3:
    """The few S3 operations publishing needs, through boto3 (same credentials as the AWS CLI)."""

    def __init__(self):
        import boto3  # imported here so the tests never create an AWS client
        self.client = boto3.client("s3")

    def versioning_enabled(self) -> bool:
        return self.client.get_bucket_versioning(Bucket=BUCKET).get("Status") == "Enabled"

    def head(self, key: str) -> dict | None:
        try:
            return self.client.head_object(Bucket=BUCKET, Key=key)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise

    def upload(self, path: Path, key: str, sha256: str) -> None:
        # boto3 sends a checksum with each part and S3 rejects a part that does not match it.
        self.client.upload_file(str(path), BUCKET, key, ExtraArgs={"Metadata": {"sha256": sha256}})

    def get_text(self, key: str) -> str:
        return self.client.get_object(Bucket=BUCKET, Key=key)["Body"].read().decode("utf-8")

    def put_text(self, key: str, text: str, *, if_none_match: bool = False) -> bool:
        """Write a small text object; False if if_none_match is set and the key already exists."""
        kwargs = {"Bucket": BUCKET, "Key": key, "Body": text.encode("utf-8"),
                  "ContentType": "text/markdown" if key.endswith(".md") else "application/yaml"}
        try:
            self.client.put_object(**kwargs, **({"IfNoneMatch": "*"} if if_none_match else {}))
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("PreconditionFailed", "ConditionalRequestConflict"):
                return False
            raise
        return True

    def list_keys(self) -> list[dict]:
        pages = self.client.get_paginator("list_objects_v2").paginate(Bucket=BUCKET)
        return [obj for page in pages for obj in page.get("Contents", [])]


def require_versioning(s3: S3) -> None:
    if not s3.versioning_enabled():
        raise PublishError(f"S3 versioning is off for s3://{BUCKET}; turn it on before publishing, "
                           f"so a rebuilt {INDEX_KEY} keeps the previous version")


def s3_key(uri: str) -> str:
    m = re.fullmatch(rf"s3://{BUCKET}/(.+)", uri)
    if not m:  # audit only looks at this bucket, so a database anywhere else would never be checked
        raise PublishError(f"{uri!r} is not in s3://{BUCKET}/; publish only there")
    return m.group(1)


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_publish(args, s3: S3 | None = None) -> None:
    s3 = s3 or S3()
    db, key = args.db, s3_key(args.s3_uri)
    if Path(key).name != db.name:
        raise PublishError(f"the S3 key must end with {db.name}")
    if re.search(r"[|\r\n]", args.label + key):
        raise PublishError("the label and S3 key cannot contain |, carriage returns or newlines (INDEX.md table)")
    yaml_key = key[: -len(db.name)] + provenance_path(db).name
    require_versioning(s3)
    if s3.head(yaml_key) is not None:
        raise PublishError(f"s3://{BUCKET}/{yaml_key} already exists; a published record is never overwritten")

    output, runs = finalize(db)
    if not runs:
        raise PublishError(f"{db.name} has no extraction_runs, so there is nothing to build its record from")
    unfinished = [r["run_id"] for r in runs if r["finished_utc"] is None]
    if unfinished and not args.record_only:
        raise PublishError(f"extraction runs {unfinished} never finished; publish only a completed database")
    local_yaml = provenance_path(db)
    try:
        existing = yaml.safe_load(local_yaml.read_text(encoding="utf-8")) if local_yaml.exists() else {}
    except yaml.YAMLError as e:
        raise PublishError(f"{local_yaml.name} is not valid YAML (quote values such as 'repo:'): {e}") from e
    record = build_record(db, args, output, runs, existing if isinstance(existing, dict) else {})
    if unfinished:
        record.setdefault("comments", []).append(f"extraction runs {unfinished} have no finished_at")

    obj = s3.head(key)
    if args.record_only:
        if obj is None:
            raise PublishError(f"s3://{BUCKET}/{key} does not exist; --record-only describes a database already there")
        if obj["ContentLength"] != output["bytes"] or obj.get("Metadata", {}).get("sha256", output["sha256"]) != output["sha256"]:
            raise PublishError(f"{db.name} is not a copy of s3://{BUCKET}/{key}: the size or SHA-256 differs")
    elif obj is not None:
        if obj.get("Metadata", {}).get("sha256") != output["sha256"]:
            raise PublishError(f"s3://{BUCKET}/{key} already exists; published snapshots are never overwritten")
        print(f"s3://{BUCKET}/{key} was uploaded by an earlier run with this SHA-256; finishing that publish")
    else:
        s3.upload(db, key, output["sha256"])
        obj = s3.head(key)
    record["publication"] = {"status": "published", "s3_uri": f"s3://{BUCKET}/{key}", "label": args.label,
                             "s3_version_id": obj.get("VersionId"), "uploaded_utc": utc(obj["LastModified"]),
                             "provenance_uri": f"s3://{BUCKET}/{yaml_key}"}
    text = yaml.safe_dump(record, sort_keys=False, allow_unicode=True, width=100)
    if SECRET.search(text):
        raise PublishError("the record looks like it contains a secret; remove it from the run config or arguments")
    if not s3.put_text(yaml_key, text, if_none_match=True):
        raise PublishError(f"s3://{BUCKET}/{yaml_key} appeared just now; someone else published this key")
    local_yaml.write_text(text, encoding="utf-8", newline="\n")
    write_index(s3, audit(s3))
    print(f"published s3://{BUCKET}/{key}\nprovenance s3://{BUCKET}/{yaml_key}\nrebuilt s3://{BUCKET}/{INDEX_KEY}")


def audit(s3: S3) -> list[dict]:
    """One entry per database in the bucket (catalog copies excluded), from the listing and each YAML."""
    keys = {o["Key"]: o for o in s3.list_keys()}
    copies = {m.group(2): (m.group(1), k) for k in keys if (m := CATALOG_COPY.fullmatch(k))}
    databases = sorted(k for k in keys if k.endswith(".db") and not k.startswith("database_catalog/"))
    records = {}
    for key in databases:
        yaml_key = key[: -len(".db")] + "_provenance.yaml"
        try:
            record = yaml.safe_load(s3.get_text(yaml_key)) if yaml_key in keys else {}
        except yaml.YAMLError:
            record = {}
        records[key] = record if isinstance(record, dict) else {}
    superseded = {}  # key -> URI of the snapshot whose YAML says it supersedes that key
    for key, record in records.items():
        old = (record.get("database") or {}).get("supersedes")
        old = old.get("s3_uri") if isinstance(old, dict) else old
        if isinstance(old, str) and old.startswith(f"s3://{BUCKET}/"):
            superseded[old[len(f"s3://{BUCKET}/"):]] = f"s3://{BUCKET}/{key}"
    report = []
    for key in databases:
        obj, record = keys[key], records[key]
        yaml_key = key[: -len(".db")] + "_provenance.yaml"
        published = (record.get("publication") or {}).get("status") == "published"
        label, copy = copies.get(key, (None, None))
        label = (record.get("publication") or {}).get("label") or label
        if key in superseded:
            label = f"{label or 'not recorded'}; superseded by `{superseded[key]}`"
        report.append({
            "key": key, "bytes": obj["Size"], "uploaded": utc(obj["LastModified"])[:10], "copy": copy,
            "label": label,
            "run_date": str((record.get("database") or {}).get("completed_utc") or "")[:10] or None,
            "sha256": (record.get("output") or {}).get("sha256"),
            "provenance": yaml_key if published else None,
            "gap": None if published else "YAML not published" if yaml_key in keys else "no provenance YAML",
        })
    return report


def write_index(s3: S3, report: list[dict]) -> None:
    """Rebuild INDEX.md from the audit; it is never edited in place."""
    rows = ["| Original S3 object | Catalog copy | Label | Original upload date | Bytes | Run date | SHA-256 | Provenance |",
            "| --- | --- | --- | --- | ---: | --- | --- | --- |"]
    code = lambda v, prefix="": f"`{prefix}{v}`" if v else "not recorded"
    for r in report:
        rows.append(f"| `s3://{BUCKET}/{r['key']}` | {code(r['copy'], f's3://{BUCKET}/') if r['copy'] else 'none'} "
                    f"| {r['label'] or 'not recorded'} | {r['uploaded']} | {r['bytes']} | {r['run_date'] or 'not recorded'} "
                    f"| {code(r['sha256'])} | {code(r['provenance'], f's3://{BUCKET}/')} |")
    text = "\n".join([
        "# S3 database catalog", "",
        f"Every SQLite `.db` in `s3://{BUCKET}/` outside `database_catalog/`, rebuilt from the bucket listing and each "
        "database's provenance YAML by `scripts/publish_db.py`. Do not edit it by hand; it is replaced on every publish. "
        "A catalog copy's path segment `uploaded-YYYY-MM-DD` is the original object's S3 upload date, not the run date.",
        "", f"Listed databases: {len(report)} objects, {sum(r['bytes'] for r in report):,} bytes. "
            f"Rebuilt {utc(datetime.now(UTC))}.", "", *rows]) + "\n"
    s3.put_text(INDEX_KEY, text)


def cmd_audit(args, s3: S3 | None = None) -> int:
    s3 = s3 or S3()
    report = audit(s3)
    shown = [r for r in report if r["key"].startswith(args.prefix)]
    for r in shown:
        print(f"{'GAP ' if r['gap'] else 'ok  '} s3://{BUCKET}/{r['key']}" + (f"  ({r['gap']})" if r["gap"] else ""))
    print(f"{len(shown)} databases: {sum(not r['gap'] for r in shown)} with a published provenance YAML")
    if args.write_index:
        require_versioning(s3)
        write_index(s3, report)
        print(f"rebuilt s3://{BUCKET}/{INDEX_KEY}")
    return 1 if args.strict and any(r["gap"] for r in shown) else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("publish", help="finalize a database, upload it with a generated YAML, rebuild INDEX.md")
    p.add_argument("db", type=Path)
    p.add_argument("--s3-uri", required=True, help=f"s3://{BUCKET}/<key> ending with the database filename")
    p.add_argument("--label", required=True, help="scope label for INDEX.md, e.g. multi-treatment or source-corpus")
    p.add_argument("--purpose", help="what the database holds (or database.purpose in a local YAML)")
    p.add_argument("--input", action="append",
                   help="an input snapshot, by S3 URI or data: path; repeat for each (at least one unless --record-only)")
    p.add_argument("--command", action="append", help="a command that built the database, in order; repeat for each")
    p.add_argument("--supersedes",
                   help="S3 URI of the snapshot this one corrects or reruns (or database.supersedes in a local YAML)")
    p.add_argument("--record-only", action="store_true",
                   help="write a retrospective record beside a database already at --s3-uri; nothing is uploaded")
    a = sub.add_parser("audit", help=f"list s3://{BUCKET} databases without a published provenance YAML")
    a.add_argument("--prefix", default="")
    a.add_argument("--strict", action="store_true", help="exit 1 if any listed database has a gap")
    a.add_argument("--write-index", action="store_true", help=f"rebuild s3://{BUCKET}/{INDEX_KEY} from the listing")
    args = ap.parse_args(argv)
    try:
        if args.command == "publish":
            cmd_publish(args)
            return 0
        return cmd_audit(args)
    except PublishError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
