"""Test for scripts/publish_db.py: finalize, publish and audit one database. S3 is faked; no network."""

import sqlite3
import sys
from argparse import Namespace
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import publish_db  # noqa: E402


class FakeS3:
    """Just enough of publish_db.S3 for a successful publish: one bucket, held in a dict."""

    def __init__(self):
        self.files = {"INDEX.md": b"| Original S3 object | Bytes |\n| --- | ---: |\n"}

    def head(self, bucket, key):
        return {} if key in self.files else None

    def upload(self, path, bucket, key, sha256):
        self.files[key] = Path(path).read_bytes()

    def download(self, bucket, key, path):
        Path(path).write_bytes(self.files[key])

    def get_text(self, bucket, key):
        return (self.files[key].decode(), "etag") if key in self.files else None

    def put_text(self, bucket, key, text, **conditions):
        self.files[key] = text.encode()
        return True

    def list_keys(self, bucket, prefix=""):
        return [{"Key": k, "Size": len(v)} for k, v in self.files.items() if k.startswith(prefix)]


def test_finalize_publish_and_audit_one_database(tmp_path):
    # A small database and the provenance YAML a completed run leaves beside it.
    db = tmp_path / "example.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE posts (id INTEGER)")
    conn.execute("INSERT INTO posts VALUES (1)")
    conn.commit()
    conn.close()
    publish_db.provenance_path(db).write_text(yaml.safe_dump({
        "record_kind": "database_provenance",
        "database": {"filename": "example.db", "status": "completed", "completed_utc": "2026-10-22T07:30:00Z"},
        "code": {"commit_sha": "0123456789abcdef0123456789abcdef01234567", "working_tree": "clean"},
        "inputs": [],
        "commands": [{"command": "uv run python src/import_posts.py", "cwd": "repo:", "exit_code": 0}],
        "publication": {"status": "local"},
    }), encoding="utf-8")

    publish_db.cmd_finalize(Namespace(db=db))
    s3 = FakeS3()
    publish_db.cmd_publish(Namespace(db=db, s3_uri="s3://patientpunk/runs/example.db", label="test",
                                     catalog_copy=False), s3=s3)

    # The database and its YAML are in S3, the YAML says published, and INDEX.md lists the database.
    assert s3.files["runs/example.db"] == db.read_bytes()
    assert yaml.safe_load(s3.files["runs/example_provenance.yaml"])["publication"]["status"] == "published"
    assert "s3://patientpunk/runs/example.db" in s3.files["INDEX.md"].decode()
    # And audit finds nothing missing.
    assert publish_db.audit(s3, "patientpunk", "runs/", include_catalog=False) == [
        {"s3_uri": "s3://patientpunk/runs/example.db", "bytes": db.stat().st_size,
         "provenance": True, "in_index": True}]
