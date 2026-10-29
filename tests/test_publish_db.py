"""Test for scripts/publish_db.py -- finalize, publish and audit one database. S3 is faked; no network."""

import hashlib
import sqlite3
import sys
from argparse import Namespace
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import publish_db  # noqa: E402

SCHEMA_SQL = REPO_ROOT / "schema.sql"
SHA = "0123456789abcdef0123456789abcdef01234567"
INDEX = """# S3 database catalog

All 2 SQLite `.db` objects present in `s3://patientpunk/` at inventory time were copied.

| Original S3 object | Catalog copy | Label | Original upload date | Bytes |
| --- | --- | --- | --- | ---: |
| `s3://patientpunk/a/first.db` | `s3://patientpunk/database_catalog/x/a/first.db` | source-corpus | 2026-06-01 | 100 |
| `s3://patientpunk/z/last.db` | `s3://patientpunk/database_catalog/x/z/last.db` | multi-treatment | 2026-06-02 | 200 |

"""


class FakeS3:
    """In-memory stand-in for publish_db.S3, with ETags and conditional writes."""

    def __init__(self, objects=None):
        self.objects = {}  # (bucket, key) -> (bytes, metadata)
        for (bucket, key), data in (objects or {}).items():
            self.objects[(bucket, key)] = (data.encode(), {})

    def etag(self, bucket, key):
        return '"' + hashlib.md5(self.objects[(bucket, key)][0]).hexdigest() + '"'

    def head(self, bucket, key):
        if (bucket, key) not in self.objects:
            return None
        data, metadata = self.objects[(bucket, key)]
        return {"ContentLength": len(data), "ETag": self.etag(bucket, key), "Metadata": metadata}

    def upload(self, path, bucket, key, sha256):
        self.objects[(bucket, key)] = (Path(path).read_bytes(), {"sha256": sha256})

    def download(self, bucket, key, path):
        Path(path).write_bytes(self.objects[(bucket, key)][0])

    def get_text(self, bucket, key):
        if (bucket, key) not in self.objects:
            return None
        return self.objects[(bucket, key)][0].decode(), self.etag(bucket, key)

    def put_text(self, bucket, key, text, *, content_type, if_match=None, if_none_match=False):
        exists = (bucket, key) in self.objects
        if (if_none_match and exists) or (if_match and (not exists or self.etag(bucket, key) != if_match)):
            return False
        self.objects[(bucket, key)] = (text.encode(), {"sha256": hashlib.sha256(text.encode()).hexdigest()})
        return True

    def list_keys(self, bucket, prefix=""):
        return [{"Key": k, "Size": len(v[0])} for (b, k), v in self.objects.items()
                if b == bucket and k.startswith(prefix)]


def make_db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO extraction_runs (run_id, run_at, commit_hash, extraction_type, config) "
                 "VALUES (7, 0, 'abc', 'sentiment', '{}')")
    conn.execute("INSERT INTO users (user_id, source_subreddit, scraped_at) VALUES ('u1', 'x', 0)")
    conn.commit()
    conn.close()
    return path


def write_record(db: Path) -> Path:
    record = {
        "schema_version": 1,
        "record_kind": "database_provenance",
        "record_method": "contemporaneous",
        "database": {"filename": db.name, "purpose": "test", "run_id": "r1", "status": "completed",
                     "started_utc": "2026-10-22T07:00:00Z", "completed_utc": "2026-10-22T07:30:00Z",
                     "supersedes": None},
        "code": {"repository": "https://github.com/Ely-S/PatientPunk", "branch": "main", "commit_sha": SHA,
                 "commit_url": f"https://github.com/Ely-S/PatientPunk/commit/{SHA}", "commit_on_github": True,
                 "working_tree": "clean", "code_outside_commit": []},
        "inputs": [{"name": "synthetic", "location": "data:smoke/in.json", "sha256": "ab" * 32}],
        "commands": [{"stage": "import", "cwd": "repo:", "command": "uv run python src/import_posts.py",
                      "exit_code": 0}],
        "output": {"location": f"data:smoke/{db.name}"},
        "publication": {"status": "local", "s3_uri": None},
        "comments": [],
    }
    path = publish_db.provenance_path(db)
    path.write_text(yaml.safe_dump(record, sort_keys=False), encoding="utf-8")
    return path


def test_finalize_publish_and_audit_one_database(tmp_path):
    db = make_db(tmp_path / "example.db")
    write_record(db)
    publish_db.cmd_finalize(Namespace(db=db))

    s3 = FakeS3({("patientpunk", "INDEX.md"): INDEX})
    publish_db.cmd_publish(Namespace(db=db, s3_uri="s3://patientpunk/runs/example.db", label="multi-treatment",
                                     catalog_copy=False), s3=s3)

    data, metadata = s3.objects[("patientpunk", "runs/example.db")]
    assert data == db.read_bytes() and metadata["sha256"] == publish_db.sha256_file(db)
    local_yaml = publish_db.provenance_path(db).read_text(encoding="utf-8")
    assert s3.get_text("patientpunk", "runs/example_provenance.yaml")[0] == local_yaml
    publication = yaml.safe_load(local_yaml)["publication"]
    assert publication["status"] == "published"
    assert publication["downloaded_sha256_matches"] is True and publication["catalog_verified_utc"]
    row = next(r for r in publish_db.index_rows(s3.get_text("patientpunk", "INDEX.md")[0])
               if r["Original S3 object"] == "`s3://patientpunk/runs/example.db`")
    assert row["Provenance"] == "`s3://patientpunk/runs/example_provenance.yaml`"

    report = publish_db.audit(s3, "patientpunk", "runs/", include_catalog=False)
    assert report == [{"s3_uri": "s3://patientpunk/runs/example.db", "bytes": db.stat().st_size,
                       "provenance": True, "in_index": True}]
