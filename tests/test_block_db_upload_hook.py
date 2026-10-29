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
    "aws s3 cp ./run_dir s3://patientpunk/runs/r1/ --recursive",
    "aws s3 sync ./run_dir s3://patientpunk/runs/r1/",
    'aws s3 sync ./run_dir s3://patientpunk/runs/r1/ --exclude "*" --include "*.db"',
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
    'aws s3 sync ./run_dir s3://patientpunk/runs/r1/ --exclude "*.db"',
    "aws s3api put-object --bucket patientpunk --key INDEX.md --body INDEX.md --if-match abc",
    "aws s3api head-object --bucket patientpunk --key runs/x.db",
    "uv run python scripts/publish_db.py publish data/x.db --s3-uri s3://patientpunk/runs/x.db --label t",
    "sqlite3 example.db 'PRAGMA integrity_check'",
    "git status",
]


@pytest.mark.parametrize("command", BLOCKED)
def test_direct_db_uploads_are_blocked(command):
    assert command_blocked(command)


@pytest.mark.parametrize("command", ALLOWED)
def test_downloads_listings_and_other_uploads_pass(command):
    assert not command_blocked(command)


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
