"""Claude Code PreToolUse hook: stop shell commands that upload a SQLite database to S3.

Databases are published only with scripts/publish_db.py, which checks the provenance
YAML, verifies the upload by hash and updates s3://patientpunk/INDEX.md (see
docs/database-provenance.md). Downloads and uploads of other files pass through. For a
folder upload (sync, or cp/mv --recursive) from a local folder, the hook looks inside the
folder and blocks only if a .db file would be uploaded after the command's --exclude and
--include filters. When it cannot look (an S3 source, a path with a shell variable, or a
very large folder), it blocks unless the filters keep every .db out.

Reads the hook event as JSON on stdin; exit code 2 blocks the command and shows the
message on stderr to the agent. Standard library only, so it runs without the project
environment.
"""
import fnmatch
import json
import os
import re
import shlex
import sys
from pathlib import Path

MESSAGE = (
    "Blocked: this command would upload a SQLite database to S3 directly. Publish databases with "
    "`uv run python scripts/publish_db.py publish <db> --s3-uri s3://<bucket>/<key>.db --label <label>`, "
    "which checks the provenance YAML, verifies the upload and updates s3://patientpunk/INDEX.md "
    "(docs/database-provenance.md). To upload the rest of a folder that holds a database, add "
    "--exclude \"*.db\". Downloads and other files are not blocked."
)
WALK_LIMIT = 200_000  # files to look at before falling back to the cautious rule
CD_COMMANDS = {"cd", "pushd", "set-location", "push-location", "sl"}
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
    """The cautious rule, used when the folder cannot be inspected."""
    excluded = any(v.strip("'\"") in ("*", "*.db") for v in option_values(tokens, "--exclude"))
    included = any(v.strip("'\"").lower().endswith(".db") or v.strip("'\"") == "*"
                   for v in option_values(tokens, "--include"))
    return not excluded or included


def filters(tokens: list[str]) -> list[tuple[str, str]]:
    """--exclude and --include patterns in command order, as the AWS CLI applies them."""
    rules = []
    for i, tok in enumerate(tokens):
        for kind in ("--exclude", "--include"):
            if tok == kind and i + 1 < len(tokens):
                rules.append((kind, tokens[i + 1].strip("'\"")))
            elif tok.startswith(kind + "="):
                rules.append((kind, tok.split("=", 1)[1].strip("'\"")))
    return rules


def uploaded(relpath: str, rules: list[tuple[str, str]]) -> bool:
    """Whether the AWS CLI would upload a file at this path relative to the source folder.

    Every file starts included; each matching filter in order decides, so later ones win.
    The CLI uses fnmatch, where * also matches path separators.
    """
    keep = True
    for kind, pattern in rules:
        if fnmatch.fnmatch(relpath, pattern):
            keep = kind == "--include"
    return keep


def folder_uploads_db(folder: Path, rules: list[tuple[str, str]]) -> bool | None:
    """Whether any .db in the folder survives the filters; None if the folder is too large to check."""
    seen = 0
    for root, _, files in os.walk(folder):
        for name in files:
            seen += 1
            if seen > WALK_LIMIT:
                return None
            if is_db(name) and uploaded(os.path.relpath(os.path.join(root, name), folder), rules):
                return True
    return False


def folder_upload_blocked(source: str, tokens: list[str], cwd: Path) -> bool:
    if source.startswith("s3://") or "$" in source or "%" in source:
        return directory_upload_may_include_db(tokens)  # cannot look inside
    path = Path(os.path.expanduser(source))
    path = path if path.is_absolute() else cwd / path
    if path.is_file():
        return is_db(source)
    if not path.is_dir():
        return False  # nothing there; the AWS CLI fails on its own
    found = folder_uploads_db(path, filters(tokens))
    return directory_upload_may_include_db(tokens) if found is None else found


def blocks(tokens: list[str], cwd: Path) -> bool:
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
            return folder_upload_blocked(source, tokens, cwd)
        return is_db(source) or is_db(dest)
    if service == "s3api" and action in ("put-object", "copy-object", "create-multipart-upload", "upload-part"):
        return any(is_db(v) for v in option_values(tokens, "--key") + option_values(tokens, "--body"))
    return False


def split(segment: str) -> list[str]:
    """Shell-style words, keeping backslashes so Windows paths survive."""
    lexer = shlex.shlex(segment, posix=True)
    lexer.whitespace_split = True
    lexer.escape = ""
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:
        return segment.split()


def command_blocked(command: str, cwd: str | Path | None = None) -> bool:
    """True if any simple command in this shell command line uploads a .db to S3.

    Relative paths resolve against cwd, following any cd earlier in the same line.
    """
    here = Path(cwd) if cwd else Path.cwd()
    for segment in SEGMENT_SPLIT.split(LINE_CONTINUATION.sub(" ", command)):
        tokens = split(segment)
        if not tokens:
            continue
        if tokens[0].lower() in CD_COMMANDS and len(tokens) >= 2:
            target = Path(os.path.expanduser(tokens[-1]))
            here = target if target.is_absolute() else here / target
        elif blocks(tokens, here):
            return True
    return False


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    command = (event.get("tool_input") or {}).get("command")
    if isinstance(command, str) and command_blocked(command, event.get("cwd")):
        print(MESSAGE, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
