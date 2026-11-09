"""The direct-upload hook's rule, on the commands it must block and the ones it must let through."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "hooks"))

from block_direct_db_upload import command_blocked  # noqa: E402

BUCKET = "s3://patientpunk"


@pytest.mark.parametrize(("command", "blocked"), [
    # Uploads of a database, however they are spelled.
    (f"aws s3 cp x.db {BUCKET}/runs/x.db", True),
    (f"aws s3 cp --copy-props none x.db {BUCKET}/runs/", True),  # an unknown option
    (f"pushd data >/dev/null && aws s3 sync . {BUCKET}/data/", True),  # a folder, after a redirect
    (f"cat x.db | aws s3 cp - {BUCKET}/runs/upload", True),  # stdin, to a key not ending in .db
    (f"python -m awscli s3 cp x.db {BUCKET}/runs/", True),  # not spelled aws
    (f"aws s3 cp x.db {BUCKET}/runs/ --content-type application/x-sqlite3", True),
    (f"aws s3 cp dump {BUCKET}/runs/x.db", True),  # only the key says .db
    (f"aws s3 cp {BUCKET}/a/x.db {BUCKET}/b/x.db", True),  # a copy within S3
    (f"aws s3 cp data {BUCKET}/data/ --recursive", True),  # a folder with no --exclude
    (f'aws s3 sync . {BUCKET}/data/ --exclude "*.db" --include "*"', True),  # the include lets it back
    (f"aws s3 cp \\\n  x.db {BUCKET}/runs/", True),  # a continued line
    ("aws s3api put-object --bucket patientpunk --key runs/x.db --body x.db", True),
    ("Write-S3Object -BucketName patientpunk -Key runs/x.db -File x.db", True),
    # Everything else passes.
    (f'aws s3 sync . {BUCKET}/data/ --exclude "*.db"', False),
    (f"aws s3 sync . {BUCKET}/data/ --exclude=*.db", False),
    (f"aws s3 cp report.csv {BUCKET}/reports/report.csv", False),
    (f"aws s3 cp {BUCKET}/runs/x.db ./x.db", False),  # a download
    (f"aws s3 sync {BUCKET}/runs ./runs", False),  # a folder download
    (f"aws --region us-east-1 s3 cp {BUCKET}/runs/x.db .", False),
    ('sqlite3 x.db "select count(*) from treatment"', False),
    (f"uv run python scripts/publish_db.py publish x.db --s3-uri {BUCKET}/runs/x.db --label test", False),
])
def test_command_blocked(command, blocked):
    assert command_blocked(command) is blocked
