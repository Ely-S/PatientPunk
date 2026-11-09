"""PreToolUse hook for Claude Code and Codex: stop shell commands that upload a SQLite database to S3.

Databases are published only with scripts/publish_db.py, which builds the provenance YAML and
rebuilds s3://patientpunk/INDEX.md (see docs/database-provenance.md). The hook reads the command's
words only; it never looks at files or folders. When the command line uploads to S3, it blocks if:

- any word ends in .db (a file, a key, or a pattern such as --include "*.db"), anywhere on the
  line, so `cat x.db | aws s3 cp - s3://...` is caught too; or
- it uploads a folder (sync, --recursive, or Write-S3Object -Folder) without --exclude "*.db".

A command is an upload when it uses cp, mv or sync with an s3:// URI and is not a download, or when
it is an s3api put/copy call or Write-S3Object. A download has one s3:// URI, as the first word after
cp, mv or sync that is not an option or a filter pattern; anything else, including a copy between two
s3:// URIs, counts as an upload, so an option value before a download's source blocks it. With S3
versioning on, a missed upload is unrecorded rather than destructive, and `publish_db.py audit` lists
it.

Registered in .claude/settings.json and .codex/hooks.json. Both tools send the hook event as JSON on
stdin with the command at tool_input.command; exit code 2 blocks the command and shows the message
on stderr to the agent. Standard library only, so it runs without the project environment.
"""
import fnmatch
import json
import re
import shlex
import sys

MESSAGE = (
    "Blocked: this command would upload a SQLite database to S3 directly. Publish databases with "
    "`uv run python scripts/publish_db.py publish <db> --s3-uri s3://patientpunk/<key>.db --label <label> "
    "--purpose \"<what it holds>\" --input <input> --command \"<command that built it>\"`, which builds the "
    "provenance YAML and rebuilds s3://patientpunk/INDEX.md (docs/database-provenance.md). To upload the "
    "rest of a folder, add --exclude \"*.db\". Downloads are not blocked."
)
UPLOAD_VERBS = {"cp", "mv", "sync"}
API_UPLOADS = {"put-object", "copy-object", "create-multipart-upload", "upload-part", "upload-part-copy"}
SEGMENT_SPLIT = re.compile(r"&&|\|\||[;|\n]")
LINE_CONTINUATION = re.compile(r"[\\`]\r?\n")  # bash backslash, PowerShell backtick


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


def option_values(words: list[str], name: str) -> list[str]:
    """Values of --name value and --name=value, in order."""
    values = []
    for i, word in enumerate(words):
        if word.lower() == name and i + 1 < len(words):
            values.append(words[i + 1])
        elif word.lower().startswith(name + "="):
            values.append(word.split("=", 1)[1])
    return values


def is_upload(words: list[str]) -> bool:
    """An upload or S3-to-S3 copy. Only a download, whose one s3:// URI is its source, is not."""
    lower = [w.lower() for w in words]
    if "write-s3object" in lower or ("s3api" in lower and API_UPLOADS & set(lower)):
        return True
    if not UPLOAD_VERBS & set(lower):
        return False
    uris = [w for w in lower if w.startswith("s3://")]
    if len(uris) != 1:
        return len(uris) > 1
    filter_values = {v.lower() for v in option_values(words, "--exclude") + option_values(words, "--include")}
    verb = next(i for i, w in enumerate(lower) if w in UPLOAD_VERBS)
    # Every other word after the verb counts, "-" (stdin or stdout) included. An unknown option's
    # value can only make a download look like an upload: a false block, never a missed upload.
    paths = [w for w in lower[verb + 1:] if w == "-" or (not w.startswith("-") and w not in filter_values)]
    return not paths or paths[0] != uris[0]


def excludes_databases(words: list[str]) -> bool:
    """--exclude covers every .db, and no --include lets one back in."""
    def matches_db(pattern: str) -> bool:
        return fnmatch.fnmatch("any/dir/x.db", pattern.strip("'\""))
    return (any(matches_db(p) for p in option_values(words, "--exclude"))
            and not any(matches_db(p) for p in option_values(words, "--include")))


def command_blocked(command: str) -> bool:
    """True if this shell command line uploads a .db to S3."""
    segments = [split(s) for s in SEGMENT_SPLIT.split(LINE_CONTINUATION.sub(" ", command))]
    uploads = [words for words in segments if words and is_upload(words)]
    if not uploads:
        return False
    excluded = {v for words in uploads for v in option_values(words, "--exclude")}
    if any(w.lower().split("?", 1)[0].rstrip("/\\").endswith(".db")  # a copy source may end in ?versionId=
           and w not in excluded and not w.lower().startswith("--exclude=")
           for words in segments for w in words):
        return True
    for words in uploads:
        lower = [w.lower() for w in words]
        folder = "sync" in lower or "--recursive" in lower or "-folder" in lower
        if folder and not excludes_databases(words):
            return True
    return False


def main() -> int:
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))  # PowerShell pipes add a BOM
    except ValueError:  # not JSON, or not UTF-8
        return 0
    if not isinstance(event, dict) or not isinstance(event.get("tool_input"), dict):
        return 0  # not a shell tool event
    command = event["tool_input"].get("command")
    if isinstance(command, str) and command_blocked(command):
        print(MESSAGE, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
