"""Claude Code PreToolUse hook: stop shell commands that upload a SQLite database to S3.

Databases are published only with scripts/publish_db.py, which checks the provenance
YAML, verifies the upload by hash and updates s3://patientpunk/INDEX.md (see
docs/database-provenance.md). Downloads and uploads of other files pass through.

Reads the hook event as JSON on stdin; exit code 2 blocks the command and shows the
message on stderr to the agent. Standard library only, so it runs without the project
environment.
"""
import json
import re
import shlex
import sys

MESSAGE = (
    "Blocked: this command would upload a SQLite database to S3 directly. Publish databases with "
    "`uv run python scripts/publish_db.py publish <db> --s3-uri s3://<bucket>/<key>.db --label <label>`, "
    "which checks the provenance YAML, verifies the upload and updates s3://patientpunk/INDEX.md "
    "(docs/database-provenance.md). For a directory upload, add --exclude \"*.db\". Downloads are not blocked."
)
# AWS CLI options that take a value, so the value is not mistaken for a path.
VALUE_OPTIONS = {
    "--acl", "--cache-control", "--content-disposition", "--content-encoding", "--content-language",
    "--content-type", "--endpoint-url", "--exclude", "--expires", "--grants", "--include", "--metadata",
    "--metadata-directive", "--profile", "--region", "--sse", "--sse-c", "--sse-c-key", "--sse-kms-key-id",
    "--storage-class", "--website-redirect", "--expected-size", "--checksum-algorithm", "--source-region",
    "--output", "--query", "--color", "--cli-read-timeout", "--cli-connect-timeout", "--page-size",
}
SEGMENT_SPLIT = re.compile(r"&&|\|\||[;|\n]")
LINE_CONTINUATION = re.compile(r"[\\`]\r?\n")  # bash backslash, PowerShell backtick


def is_aws(token: str) -> bool:
    return token.lower().replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".exe") == "aws"


def is_db(path: str) -> bool:
    return path.lower().rstrip("/\\").endswith(".db")


def option_values(tokens: list[str], name: str) -> list[str]:
    values = []
    for i, tok in enumerate(tokens):
        if tok == name and i + 1 < len(tokens):
            values.append(tokens[i + 1])
        elif tok.startswith(name + "="):
            values.append(tok.split("=", 1)[1])
    return values


def positionals(tokens: list[str]) -> list[str]:
    out, skip = [], False
    for tok in tokens:
        if skip:
            skip = False
        elif tok.startswith("-"):
            skip = tok in VALUE_OPTIONS
        else:
            out.append(tok)
    return out


def directory_upload_may_include_db(tokens: list[str]) -> bool:
    excluded = any(v.strip("'\"") in ("*", "*.db") for v in option_values(tokens, "--exclude"))
    included = any(v.strip("'\"").lower().endswith(".db") or v.strip("'\"") == "*"
                   for v in option_values(tokens, "--include"))
    return not excluded or included


def blocks(tokens: list[str]) -> bool:
    """True if this one simple command uploads or copies a .db into S3."""
    if any(t.lower() == "write-s3object" for t in tokens):  # AWS Tools for PowerShell
        return any(is_db(t) for t in tokens)
    i = next((i for i, t in enumerate(tokens) if is_aws(t)), None)
    if i is None:
        return False
    rest = positionals(tokens[i + 1:])
    if len(rest) < 2:
        return False
    service, action, args = rest[0].lower(), rest[1].lower(), rest[2:]
    if service == "s3" and action in ("cp", "mv", "sync"):
        if len(args) < 2 or not args[1].startswith("s3://"):
            return False  # a download or a listing
        source, dest = args[0], args[1]
        if "--recursive" in tokens or action == "sync":
            return directory_upload_may_include_db(tokens)
        return is_db(source) or is_db(dest)
    if service == "s3api" and action in ("put-object", "copy-object", "create-multipart-upload", "upload-part"):
        return any(is_db(v) for v in option_values(tokens, "--key") + option_values(tokens, "--body"))
    return False


def command_blocked(command: str) -> bool:
    for segment in SEGMENT_SPLIT.split(LINE_CONTINUATION.sub(" ", command)):
        try:
            tokens = shlex.split(segment, posix=True)
        except ValueError:
            tokens = segment.split()
        if tokens and blocks(tokens):
            return True
    return False


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    command = (event.get("tool_input") or {}).get("command")
    if isinstance(command, str) and command_blocked(command):
        print(MESSAGE, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
