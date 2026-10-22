"""Tests for .claude/hooks/block_direct_db_upload.py -- the Claude Code hook that stops direct .db uploads."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).parent.parent / ".claude" / "hooks" / "block_direct_db_upload.py"
sys.path.insert(0, str(HOOK.parent))

from block_direct_db_upload import command_blocked  # noqa: E402

BLOCKED = [
    "aws s3 cp data/example.db s3://patientpunk/runs/example.db",
    "aws s3 mv example.db s3://patientpunk/runs/",
    "aws --profile pp s3 cp ./out/example.db s3://patientpunk/x/ --only-show-errors",
    r"aws s3 cp C:\Users\me\PatientPunk_data\combined.db s3://patientpunk/combined.db",
    '"C:/Program Files/Amazon/AWSCLIV2/aws.exe" s3 cp combined.db s3://patientpunk/combined.db',
    "aws s3 cp s3://patientpunk/a/x.db s3://patientpunk/database_catalog/a/x.db",
    "aws s3 sync s3://patientpunk/runs/r1/ s3://patientpunk/runs/r2/",
    "aws s3 sync $RUN_DIR s3://patientpunk/runs/r1/",
    "aws s3api put-object --bucket patientpunk --key runs/x.db --body x.db",
    "aws s3api create-multipart-upload --bucket patientpunk --key runs/x.db",
    "cd study && aws s3 cp example.db s3://patientpunk/x/example.db",
    "aws s3 cp example.db \\\n  s3://patientpunk/x/example.db",
    "aws s3 cp example.db `\n  s3://patientpunk/x/example.db",
    "Write-S3Object -BucketName patientpunk -Key runs/x.db -File x.db",
]

ALLOWED = [
    "aws s3 cp s3://patientpunk/raw_data/pushshift/reddit_2026-06-13.db .",
    "aws s3 cp s3://patientpunk/a/x.db ./local/x.db",
    "aws s3 sync s3://patientpunk/runs/r1/ ./run_dir",
    "aws s3 ls s3://patientpunk/ --recursive | grep .db",
    "aws s3 cp notebook.html s3://patientpunk/reports/notebook.html",
    'aws s3 sync s3://patientpunk/runs/r1/ s3://patientpunk/runs/r2/ --exclude "*.db"',
    'aws s3 sync $RUN_DIR s3://patientpunk/runs/r1/ --exclude "*.db"',
    "aws s3 sync ./no_such_folder s3://patientpunk/runs/r1/",
    "aws s3api put-object --bucket patientpunk --key INDEX.md --body INDEX.md --if-match abc",
    "aws s3api head-object --bucket patientpunk --key runs/x.db",
    "uv run python scripts/publish_db.py publish data/x.db --s3-uri s3://patientpunk/runs/x.db --label t",
    "sqlite3 example.db 'PRAGMA integrity_check'",
    "git status",
]


@pytest.mark.parametrize("command", BLOCKED)
def test_direct_db_uploads_are_blocked(command, tmp_path):
    assert command_blocked(command, tmp_path)


@pytest.mark.parametrize("command", ALLOWED)
def test_downloads_listings_and_other_uploads_pass(command, tmp_path):
    assert not command_blocked(command, tmp_path)


# ── Folder uploads: the hook looks inside the local folder ────────────────────

@pytest.fixture
def run_dir(tmp_path):
    """tmp_path/run_dir holding results.csv and notes/readme.md, and nothing else."""
    folder = tmp_path / "run_dir"
    (folder / "notes").mkdir(parents=True)
    (folder / "results.csv").write_text("a,b\n")
    (folder / "notes" / "readme.md").write_text("x")
    return folder


SYNC = "aws s3 sync ./run_dir s3://patientpunk/runs/r1/"
CP_RECURSIVE = "aws s3 cp run_dir s3://patientpunk/runs/r1/ --recursive"


@pytest.mark.parametrize("command", [SYNC, CP_RECURSIVE, "aws s3 mv ./run_dir s3://patientpunk/r/ --recursive"])
def test_a_folder_without_databases_uploads(run_dir, command):
    assert not command_blocked(command, run_dir.parent)


@pytest.mark.parametrize("command", [SYNC, CP_RECURSIVE])
def test_a_folder_with_a_nested_database_is_blocked(run_dir, command):
    (run_dir / "notes" / "posts.db").write_bytes(b"")
    assert command_blocked(command, run_dir.parent)


@pytest.mark.parametrize("filters, blocked", [
    ('--exclude "*.db"', False),
    ("--exclude '*'", False),
    ('--exclude "*" --include "*.csv"', False),
    ('--exclude "*" --include "*.db"', True),
    ('--exclude "*.db" --include "notes/*"', True),   # a later include brings the .db back
    ('--include "notes/*" --exclude "*.db"', False),  # a later exclude wins
    ('--exclude "notes/*"', False),
    ("--exclude=*.db", False),
])
def test_filters_are_applied_in_order(run_dir, filters, blocked):
    (run_dir / "notes" / "posts.db").write_bytes(b"")
    assert command_blocked(f"{SYNC} {filters}", run_dir.parent) is blocked


def test_relative_paths_follow_cd_in_the_same_command(run_dir):
    (run_dir / "posts.db").write_bytes(b"")
    assert command_blocked("cd run_dir && aws s3 sync . s3://patientpunk/runs/r1/", run_dir.parent)
    assert not command_blocked("cd run_dir/notes && aws s3 sync . s3://patientpunk/runs/r1/", run_dir.parent)


def test_an_absolute_folder_path_is_inspected(run_dir, tmp_path):
    (run_dir / "posts.db").write_bytes(b"")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert command_blocked(f'aws s3 sync "{run_dir}" s3://patientpunk/runs/r1/', elsewhere)


@pytest.mark.skipif(sys.platform != "win32", reason="backslash paths are Windows paths")
def test_a_windows_backslash_path_is_inspected(run_dir, tmp_path):
    (run_dir / "posts.db").write_bytes(b"")
    assert "\\" in str(run_dir)
    assert command_blocked(f"aws s3 sync {run_dir} s3://patientpunk/runs/r1/", tmp_path)


def test_a_very_large_folder_falls_back_to_the_cautious_rule(run_dir, monkeypatch):
    import block_direct_db_upload
    monkeypatch.setattr(block_direct_db_upload, "WALK_LIMIT", 1)
    assert command_blocked(SYNC, run_dir.parent)
    assert not command_blocked(f'{SYNC} --exclude "*.db"', run_dir.parent)


def run_hook(event: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True, text=True)


def test_hook_exits_2_with_guidance_for_a_blocked_command():
    proc = run_hook({"tool_name": "Bash",
                     "tool_input": {"command": "aws s3 cp example.db s3://patientpunk/x/example.db"}})
    assert proc.returncode == 2
    assert "scripts/publish_db.py publish" in proc.stderr


def test_hook_exits_0_for_an_allowed_command_and_for_other_tools():
    assert run_hook({"tool_name": "Bash", "tool_input": {"command": "git status"}}).returncode == 0
    assert run_hook({"tool_name": "Read", "tool_input": {"file_path": "x.db"}}).returncode == 0


def test_hook_resolves_folders_against_the_event_cwd(run_dir):
    event = {"tool_name": "Bash", "cwd": str(run_dir.parent), "tool_input": {"command": SYNC}}
    assert run_hook(event).returncode == 0
    (run_dir / "posts.db").write_bytes(b"")
    assert run_hook(event).returncode == 2
