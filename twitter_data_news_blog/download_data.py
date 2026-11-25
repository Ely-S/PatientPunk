"""Restore the private research inputs with MinIO Client and verify their SHA-256."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

BLOG = Path(__file__).resolve().parent


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alias", default="patientpunk-s3", help="configured mc alias")
    args = parser.parse_args()
    for line in (BLOG / "data-files.sha256").read_text().splitlines():
        expected, key = line.split("  ", 1)
        dest = BLOG.parent / "twitter_data" / key
        if dest.exists():
            if checksum(dest) != expected:
                raise SystemExit(f"Existing file differs from snapshot: {dest}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=dest.parent) as temp:
            partial = Path(temp) / "download"
            remote = f"{args.alias}/patientpunk/twitter_analysis/{key}"
            subprocess.run(["mc", "cp", remote, str(partial)], check=True)
            if checksum(partial) != expected:
                raise SystemExit(f"Checksum mismatch: {key}")
            partial.rename(dest)


if __name__ == "__main__":
    main()
