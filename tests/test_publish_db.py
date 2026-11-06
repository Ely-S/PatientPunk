"""Test for scripts/publish_db.py: publish one database and rebuild the catalog. S3 is faked; no network."""

import sqlite3
import sys
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import publish_db  # noqa: E402

WHEN = datetime(2026, 11, 5, tzinfo=UTC)


class FakeS3:
    """Just enough of publish_db.S3: one versioned bucket, held in a dict of key -> (bytes, metadata)."""

    def __init__(self, files):
        self.files = {k: (v, {}) for k, v in files.items()}

    def versioning_enabled(self):
        return True

    def head(self, key):
        if key not in self.files:
            return None
        data, meta = self.files[key]
        return {"ContentLength": len(data), "Metadata": meta, "LastModified": WHEN, "VersionId": "v1"}

    def upload(self, path, key, sha256):
        self.files[key] = (Path(path).read_bytes(), {"sha256": sha256})

    def get_text(self, key):
        return self.files[key][0].decode()

    def put_text(self, key, text, if_none_match=False):
        if if_none_match and key in self.files:
            return False
        self.files[key] = (text.encode(), {})
        return True

    def list_keys(self):
        return [{"Key": k, "Size": len(v), "LastModified": WHEN} for k, (v, _) in self.files.items()]


def test_publish_builds_the_record_from_the_database_and_rebuilds_the_index(tmp_path):
    db = tmp_path / "example.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE extraction_runs (run_id INTEGER PRIMARY KEY, run_at INTEGER, commit_hash TEXT, "
                 "extraction_type TEXT, config TEXT, finished_at INTEGER)")
    conn.execute("INSERT INTO extraction_runs VALUES (1, 1793000000, 'abc123', 'treatment_sentiment', "
                 "'{\"model\": \"m\", \"git_dirty\": false}', 1793003600)")
    conn.commit()
    conn.close()
    # An older database already in the bucket, with only a catalog copy to give its label.
    s3 = FakeS3({"old/a.db": b"x" * 10,
                 "database_catalog/by-upload-date/uploaded-2026-06-13/multi-treatment/old/a.db": b"x" * 10})
    args = Namespace(db=db, s3_uri="s3://patientpunk/runs/example.db", label="test", purpose="a test database",
                     input=["data:posts.db"], command=["uv run python src/run_sentiment_pipeline.py"],
                     supersedes=None, record_only=False)

    publish_db.cmd_publish(args, s3=s3)

    record = yaml.safe_load(s3.get_text("runs/example_provenance.yaml"))
    assert s3.files["runs/example.db"][0] == db.read_bytes()
    assert record["publication"]["status"] == "published"
    assert record["code"] == {"repository": publish_db.REPOSITORY, "commit_shas": ["abc123"], "working_tree": "clean"}
    assert record["database"]["completed_utc"] == "2026-10-26T08:33:20Z"
    index = s3.get_text("INDEX.md")
    assert "| `s3://patientpunk/runs/example.db` | none | test |" in index
    assert "| `s3://patientpunk/old/a.db` | `s3://patientpunk/database_catalog/" in index and "| multi-treatment |" in index
    assert [r["gap"] for r in publish_db.audit(s3)] == ["no provenance YAML", None]
    with pytest.raises(publish_db.PublishError, match="never overwritten"):
        publish_db.cmd_publish(args, s3=s3)
