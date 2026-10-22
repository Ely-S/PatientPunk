"""Tests for scripts/publish_db.py -- finalize, publish and audit. S3 is faked; no network."""

import hashlib
import shutil
import sqlite3
import sys
from argparse import Namespace
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import publish_db  # noqa: E402
from publish_db import PublishError  # noqa: E402

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
            self._store(bucket, key, data.encode() if isinstance(data, str) else data, {})
        self.before_put = None  # called once before the next conditional put, to simulate a racing writer

    def _store(self, bucket, key, data, metadata):
        self.objects[(bucket, key)] = (data, metadata)

    def etag(self, bucket, key):
        return '"' + hashlib.md5(self.objects[(bucket, key)][0]).hexdigest() + '"'

    def head(self, bucket, key):
        if (bucket, key) not in self.objects:
            return None
        data, metadata = self.objects[(bucket, key)]
        return {"ContentLength": len(data), "ETag": self.etag(bucket, key), "Metadata": metadata}

    def upload(self, path, bucket, key, sha256):
        self._store(bucket, key, Path(path).read_bytes(), {"sha256": sha256})

    def download(self, bucket, key, path):
        Path(path).write_bytes(self.objects[(bucket, key)][0])

    def copy(self, bucket, src_key, dst_key):
        self.objects[(bucket, dst_key)] = self.objects[(bucket, src_key)]

    def get_text(self, bucket, key):
        if (bucket, key) not in self.objects:
            return None
        return self.objects[(bucket, key)][0].decode(), self.etag(bucket, key)

    def put_text(self, bucket, key, text, *, content_type, if_match=None, if_none_match=False):
        if self.before_put:
            hook, self.before_put = self.before_put, None
            hook(self)
        exists = (bucket, key) in self.objects
        if (if_none_match and exists) or (if_match and (not exists or self.etag(bucket, key) != if_match)):
            return False
        self._store(bucket, key, text.encode(), {"sha256": hashlib.sha256(text.encode()).hexdigest()})
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


def write_record(db: Path, **overrides) -> Path:
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
    for dotted, value in overrides.items():
        section, field = dotted.split("__")
        record[section][field] = value
    path = publish_db.provenance_path(db)
    path.write_text(yaml.safe_dump(record, sort_keys=False), encoding="utf-8")
    return path


def finalized(tmp_path: Path, **overrides) -> Path:
    db = make_db(tmp_path / "example.db")
    write_record(db, **overrides)
    publish_db.cmd_finalize(Namespace(db=db))
    return db


def publish_args(db: Path, catalog_copy: bool = False) -> Namespace:
    return Namespace(db=db, s3_uri=f"s3://patientpunk/runs/{db.name}", label="multi-treatment",
                     catalog_copy=catalog_copy)


# ── finalize ──────────────────────────────────────────────────────────────────

def test_finalize_folds_wal_into_the_db_and_records_output(tmp_path):
    db = make_db(tmp_path / "example.db")
    write_record(db)
    writer = sqlite3.connect(db)  # stays open, so its committed rows sit in the -wal file
    writer.execute("PRAGMA journal_mode=WAL")
    writer.executemany("INSERT INTO users (user_id, source_subreddit, scraped_at) VALUES (?, 'x', 0)",
                       [(f"w{i}",) for i in range(50)])
    writer.commit()
    assert (tmp_path / "example.db-wal").stat().st_size > 0

    publish_db.cmd_finalize(Namespace(db=db))
    writer.close()

    output = yaml.safe_load(publish_db.provenance_path(db).read_text(encoding="utf-8"))["output"]
    assert output["location"] == "data:smoke/example.db"  # existing fields are kept
    assert output["table_row_counts"]["users"] == 51
    assert output["extraction_run_ids"] == [7]
    assert output["sha256"] == publish_db.sha256_file(db)
    assert output["sqlite_integrity_check"] == "ok" and output["wal_checkpointed"] is True
    alone = tmp_path / "db_only_copy.db"  # the .db by itself now holds every row
    shutil.copyfile(db, alone)
    assert sqlite3.connect(alone).execute("SELECT COUNT(*) FROM users").fetchone()[0] == 51


def test_finalize_refuses_while_a_reader_holds_the_wal(tmp_path):
    db = make_db(tmp_path / "example.db")
    write_record(db)
    writer = sqlite3.connect(db)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("INSERT INTO users (user_id, source_subreddit, scraped_at) VALUES ('w', 'x', 0)")
    writer.commit()
    reader = sqlite3.connect(db, isolation_level=None)
    reader.execute("BEGIN")
    reader.execute("SELECT COUNT(*) FROM users").fetchone()
    with pytest.raises(PublishError, match="still open"):
        publish_db.finalize_database(db)
    reader.close()
    writer.close()


def test_invalid_yaml_is_a_clear_error(tmp_path):
    db = make_db(tmp_path / "example.db")
    publish_db.provenance_path(db).write_text("commands:\n- cwd: repo:\n  exit_code: 0\n", encoding="utf-8")
    with pytest.raises(PublishError, match="not valid YAML"):
        publish_db.cmd_finalize(Namespace(db=db))


def test_finalize_does_not_create_a_missing_database(tmp_path):
    with pytest.raises(PublishError, match="does not exist"):
        publish_db.cmd_finalize(Namespace(db=tmp_path / "missing.db"))
    assert not (tmp_path / "missing.db").exists()


# ── check_record ──────────────────────────────────────────────────────────────

def test_a_complete_finalized_record_has_no_problems(tmp_path):
    db = finalized(tmp_path)
    record = publish_db.load_record(publish_db.provenance_path(db))
    assert publish_db.check_record(record, db) == []


@pytest.mark.parametrize("overrides, problem", [
    ({"database__status": "running"}, "publish only a completed run"),
    ({"code__commit_sha": "abc123"}, "full 40-character SHA"),
    ({"output__location": "C:\\Users\\me\\example.db"}, "machine-local absolute path"),
    ({"output__location": "/home/me/example.db"}, "machine-local absolute path"),
    ({"code__repository": "https://x?X-Amz-Signature=abc"}, "secret"),
    ({"publication__status": "published"}, "frozen"),
])
def test_record_problems_are_reported(tmp_path, overrides, problem):
    db = finalized(tmp_path)
    path = publish_db.provenance_path(db)
    record = publish_db.load_record(path)
    for dotted, value in overrides.items():
        section, field = dotted.split("__")
        record[section][field] = value
    assert any(problem in p for p in publish_db.check_record(record, db))


def test_s3_and_repo_paths_are_not_mistaken_for_local_paths(tmp_path):
    db = finalized(tmp_path, output__location="s3://patientpunk/home/x.db")
    record = publish_db.load_record(publish_db.provenance_path(db))
    record["commands"][0]["command"] = "uv run python scripts/x.py --db data:runs/home/x.db https://a.b/Users/x"
    assert publish_db.check_record(record, db) == []


def test_a_write_after_finalize_blocks_publication(tmp_path):
    db = finalized(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO users (user_id, source_subreddit, scraped_at) VALUES ('late', 'x', 0)")
    conn.close()
    record = publish_db.load_record(publish_db.provenance_path(db))
    assert any("changed after finalizing" in p for p in publish_db.check_record(record, db))


# ── INDEX.md ──────────────────────────────────────────────────────────────────

ROW = {"Original S3 object": "`s3://patientpunk/m/middle.db`", "Catalog copy": "none", "Label": "test",
       "Original upload date": "2026-10-22", "Bytes": "300", "Run date": "2026-10-21",
       "SHA-256": "`" + "cd" * 32 + "`", "Provenance": "`s3://patientpunk/m/middle_provenance.yaml`"}


def test_add_index_row_extends_columns_sorts_and_totals():
    text = publish_db.add_index_row(INDEX, ROW)
    rows = publish_db.index_rows(text)
    assert [r["Original S3 object"] for r in rows] == [
        "`s3://patientpunk/a/first.db`", "`s3://patientpunk/m/middle.db`", "`s3://patientpunk/z/last.db`"]
    assert rows[0]["SHA-256"] == "not recorded" and rows[1]["SHA-256"] == ROW["SHA-256"]
    assert "Listed databases: 3 objects, 600 bytes." in text
    assert "All 2 SQLite `.db` objects" in text  # the historical paragraph is kept


def test_add_index_row_is_stable_across_updates():
    once = publish_db.add_index_row(INDEX, ROW)
    twice = publish_db.add_index_row(once, {**ROW, "Original S3 object": "`s3://patientpunk/b/second.db`"})
    assert twice.count("Listed databases:") == 1
    assert "\n\n\n" not in twice
    assert "Listed databases: 4 objects, 900 bytes." in twice


def test_add_index_row_refuses_a_duplicate():
    with pytest.raises(PublishError, match="already lists"):
        publish_db.add_index_row(INDEX, {**ROW, "Original S3 object": "`s3://patientpunk/a/first.db`"})


def test_update_index_retries_when_another_writer_wins():
    s3 = FakeS3({("patientpunk", "INDEX.md"): INDEX})
    other = {**ROW, "Original S3 object": "`s3://patientpunk/b/other.db`"}
    s3.before_put = lambda fake: fake.put_text("patientpunk", "INDEX.md",
                                               publish_db.add_index_row(INDEX, other), content_type="x")
    publish_db.update_index(s3, "patientpunk", ROW)
    listed = [r["Original S3 object"] for r in publish_db.index_rows(s3.get_text("patientpunk", "INDEX.md")[0])]
    assert "`s3://patientpunk/b/other.db`" in listed and "`s3://patientpunk/m/middle.db`" in listed


# ── publish ───────────────────────────────────────────────────────────────────

def test_publish_uploads_verifies_catalogs_and_freezes_the_yaml(tmp_path):
    db = finalized(tmp_path)
    s3 = FakeS3({("patientpunk", "INDEX.md"): INDEX})
    publish_db.cmd_publish(publish_args(db), s3=s3)

    data, metadata = s3.objects[("patientpunk", "runs/example.db")]
    assert data == db.read_bytes() and metadata["sha256"] == publish_db.sha256_file(db)
    local_yaml = publish_db.provenance_path(db).read_text(encoding="utf-8")
    assert s3.get_text("patientpunk", "runs/example_provenance.yaml")[0] == local_yaml
    publication = yaml.safe_load(local_yaml)["publication"]
    assert publication["status"] == "published"
    assert publication["s3_uri"] == "s3://patientpunk/runs/example.db"
    assert publication["downloaded_sha256_matches"] is True and publication["catalog_verified_utc"]
    row = next(r for r in publish_db.index_rows(s3.get_text("patientpunk", "INDEX.md")[0])
               if r["Original S3 object"] == "`s3://patientpunk/runs/example.db`")
    assert row["Provenance"] == "`s3://patientpunk/runs/example_provenance.yaml`"
    assert row["Run date"] == "2026-10-22" and row["Catalog copy"] == "none"

    with pytest.raises(PublishError, match="frozen"):  # a second publish is refused
        publish_db.cmd_publish(publish_args(db), s3=s3)


def test_uploaded_time_is_taken_before_the_verification_download(tmp_path):
    db = finalized(tmp_path)
    s3 = FakeS3({("patientpunk", "INDEX.md"): INDEX})
    stamps = {}
    real_download = s3.download

    def slow_download(bucket, key, path):
        stamps["download"] = publish_db.datetime.now(publish_db.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")
        real_download(bucket, key, path)

    s3.download = slow_download
    publish_db.cmd_publish(publish_args(db), s3=s3)
    uploaded = yaml.safe_load(publish_db.provenance_path(db).read_text(encoding="utf-8"))["publication"]["uploaded_utc"]
    assert uploaded <= stamps["download"][:19] + "Z"


def test_publish_with_catalog_copy(tmp_path):
    db = finalized(tmp_path)
    s3 = FakeS3({("patientpunk", "INDEX.md"): INDEX})
    publish_db.cmd_publish(publish_args(db, catalog_copy=True), s3=s3)
    copies = [k for (_, k) in s3.objects if k.startswith("database_catalog/")]
    assert len(copies) == 1 and copies[0].endswith("/multi-treatment/runs/example.db")


def test_publish_never_overwrites_an_existing_key(tmp_path):
    db = finalized(tmp_path)
    s3 = FakeS3({("patientpunk", "INDEX.md"): INDEX, ("patientpunk", "runs/example.db"): b"older"})
    with pytest.raises(PublishError, match="never overwritten"):
        publish_db.cmd_publish(publish_args(db), s3=s3)
    assert s3.objects[("patientpunk", "runs/example.db")][0] == b"older"


def test_publish_stops_if_the_download_does_not_match(tmp_path):
    db = finalized(tmp_path)
    s3 = FakeS3({("patientpunk", "INDEX.md"): INDEX})
    s3.download = lambda bucket, key, path: Path(path).write_bytes(b"corrupt")
    with pytest.raises(PublishError, match="is uploaded but publishing is incomplete"):
        publish_db.cmd_publish(publish_args(db), s3=s3)
    assert s3.get_text("patientpunk", "INDEX.md")[0] == INDEX  # nothing catalogued
    assert yaml.safe_load(publish_db.provenance_path(db).read_text(encoding="utf-8"))["publication"]["status"] == "local"


def test_publish_requires_the_key_to_keep_the_filename(tmp_path):
    db = finalized(tmp_path)
    args = publish_args(db)
    args.s3_uri = "s3://patientpunk/runs/renamed.db"
    with pytest.raises(PublishError, match="must end with example.db"):
        publish_db.cmd_publish(args, s3=FakeS3({("patientpunk", "INDEX.md"): INDEX}))


# ── audit ─────────────────────────────────────────────────────────────────────

def test_audit_reports_missing_yaml_and_index_rows():
    s3 = FakeS3({
        ("patientpunk", "INDEX.md"): INDEX,
        ("patientpunk", "a/first.db"): b"1",
        ("patientpunk", "a/first_provenance.yaml"): b"x",
        ("patientpunk", "z/last.db"): b"2",
        ("patientpunk", "new/unlisted.db"): b"3",
        ("patientpunk", "database_catalog/x/a/first.db"): b"1",
    })
    report = {r["s3_uri"]: r for r in publish_db.audit(s3, "patientpunk", "", include_catalog=False)}
    assert set(report) == {"s3://patientpunk/a/first.db", "s3://patientpunk/z/last.db",
                           "s3://patientpunk/new/unlisted.db"}
    assert report["s3://patientpunk/a/first.db"]["provenance"]
    assert report["s3://patientpunk/a/first.db"]["in_index"]
    assert not report["s3://patientpunk/z/last.db"]["provenance"]
    assert not report["s3://patientpunk/new/unlisted.db"]["in_index"]
