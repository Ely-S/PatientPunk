"""Command-line entrypoint for "The Trial".

Parse a free-text prompt, run the trial against the read-only posts DB, and
print the rendered briefing. With ``--json`` dump the packet, transcript, and
briefing for machine consumption.

Usage::

    uv run python -m agents.TheTrialAgent.cli --prompt "what do people say about LDN?"
    uv run python -m agents.TheTrialAgent.cli --prompt "ivermectin?" --rounds 3 --json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from agents.TheTrialAgent.main import run_trial


def _jsonable(obj):
    """Best-effort coercion of packet/transcript objects into JSON-safe data."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _jsonable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agents.TheTrialAgent.cli",
        description="The Trial — put a drug's patient evidence on the stand.",
    )
    p.add_argument(
        "--db",
        default="data/posts.db",
        help="Path to the read-only SQLite posts DB (default: data/posts.db).",
    )
    p.add_argument(
        "--prompt",
        required=True,
        help="Free-text question, e.g. 'what do people say about LDN?'",
    )
    p.add_argument(
        "--rounds",
        type=int,
        default=2,
        help="Number of debate rounds (Hooper+Vex pairs). Default: 2.",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit packet + transcript + briefing as JSON instead of prose.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    briefing = run_trial(args.prompt, args.db, rounds=args.rounds)

    if args.json:
        payload = {
            "packet": _jsonable(briefing.get("packet")),
            "transcript": _jsonable(briefing.get("transcript", [])),
            "briefing": {
                k: _jsonable(v)
                for k, v in briefing.items()
                if k not in ("packet", "transcript")
            },
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(briefing.get("text", "").rstrip())

    return 0


if __name__ == "__main__":
    sys.exit(main())
