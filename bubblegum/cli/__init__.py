"""
bubblegum/cli/__init__.py
=========================
The ``bubblegum`` command-line entry point (A1).

First console entry point for the project. Built as an argparse dispatcher with
subcommands so later authoring commands (e.g. A2's ``repl``) slot in beside
``record`` without reshaping the CLI. Registered in ``pyproject.toml`` as
``[project.scripts] bubblegum = "bubblegum.cli:main"``.

Usage:
    bubblegum record --url https://example.com/login --out login_flow.py
"""

from __future__ import annotations

import argparse
from typing import Sequence

from bubblegum import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with its subcommands."""
    parser = argparse.ArgumentParser(
        prog="bubblegum",
        description="Bubblegum — natural-language test authoring tools.",
    )
    parser.add_argument("--version", action="version", version=f"bubblegum {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    record = sub.add_parser(
        "record",
        help="Record a manual click-through and emit Bubblegum NL steps.",
        description=(
            "Open a browser at --url, capture your interactions, and write a "
            "runnable *_recorded.py flow of natural-language steps."
        ),
    )
    record.add_argument("--url", required=True, help="Start URL to open for recording.")
    record.add_argument("--out", required=True, help="Path to write the recorded flow (*.py).")
    record.add_argument(
        "--headless",
        action="store_true",
        help="Record with a headless browser (default: headed, so you can interact).",
    )
    record.add_argument(
        "--emit-headed",
        action="store_true",
        help="Generate a script that launches headed (default: headless).",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "record":
        from bubblegum.cli.record import run_record

        return run_record(
            url=args.url,
            out=args.out,
            headless=args.headless,
            emit_headless=not args.emit_headed,
        )

    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
