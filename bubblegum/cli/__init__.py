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

    repl = sub.add_parser(
        "repl",
        help="Live-try natural-language steps against a running page/app.",
        description=(
            "Open a session and evaluate typed NL steps immediately, printing "
            "the resolved target + confidence. Use --url for web or "
            "--appium-url (+ --caps) for mobile."
        ),
    )
    repl.add_argument("--url", help="Web: start URL to open (Playwright).")
    repl.add_argument("--appium-url", help="Mobile: Appium server URL (e.g. http://127.0.0.1:4723).")
    repl.add_argument(
        "--caps",
        help="Mobile: Appium capabilities as inline JSON or a path to a .json file.",
    )
    repl.add_argument("--headless", action="store_true", help="Web: run headless (default: headed).")
    repl.add_argument(
        "--dry-run",
        action="store_true",
        help="Start in resolve-only mode (preview targets without acting).",
    )

    convert = sub.add_parser(
        "convert",
        help="Convert a spreadsheet of manual scenarios into automation scaffolds.",
        description=(
            "Read manual test scenarios (Gherkin-style steps in a designated "
            "column) from an .xlsx workbook and generate reviewable scaffolds: "
            "normalized .feature files plus pytest-bdd (Python) and "
            "playwright-bdd (TypeScript) step definitions that call Bubblegum. "
            "Conventions come from bubblegum.convert.yaml."
        ),
    )
    convert.add_argument("workbook", help="Path to the .xlsx scenarios workbook.")
    convert.add_argument("-o", "--out", help="Output directory (default: from profile, else 'generated').")
    convert.add_argument(
        "--config",
        help="Path to bubblegum.convert.yaml (default: ./bubblegum.convert.yaml if present).",
    )
    convert.add_argument(
        "--languages",
        help="Comma-separated output languages to emit: feature,python,typescript.",
    )
    convert.add_argument(
        "--ai",
        action="store_true",
        help="Enable the optional AI fallback for steps the grammar can't split.",
    )
    convert.add_argument(
        "--init",
        action="store_true",
        help="Also scaffold the shared TypeScript harness (helpers/ + flows/login.flow.ts + .env example) if absent.",
    )
    convert.add_argument(
        "--name",
        help="Base name for the generated test/flow file (workbook grouping). Defaults to the workbook filename.",
    )
    convert.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Leave existing generated flow/test files in place instead of regenerating them.",
    )
    convert.add_argument(
        "--group-by",
        choices=["workbook", "feature"],
        help="workbook (default): one test file per Excel with a test method per scenario. feature: one file per Feature/Epic.",
    )
    convert.add_argument(
        "--feature",
        help="Only generate features whose Feature/Epic contains one of these (comma-separated, case-insensitive) terms.",
    )
    convert.add_argument(
        "--sheet",
        help="Only read these worksheet(s) (comma-separated). Default: all sheets that have the steps column.",
    )
    convert.add_argument(
        "--no-data-file",
        action="store_true",
        help="Do not extract static literals into a <name>.data.ts file.",
    )
    convert.add_argument(
        "--dedup-subflows",
        action="store_true",
        help="Extract identical 3+ step runs shared by 3+ scenarios into shared flow functions.",
    )
    convert.add_argument(
        "--validate-only",
        action="store_true",
        help="Report issues (unmapped personas, missing navigation, TODOs, bad templates) without generating files.",
    )
    convert.add_argument(
        "--update-package-json",
        action="store_true",
        help="Merge suggested test:smart:<name> scripts into ./package.json (otherwise just printed).",
    )

    sub.add_parser(
        "bridge",
        help="Run the JSON-RPC bridge over stdio (for non-Python clients).",
        description=(
            "Expose the engine over newline-delimited JSON-RPC 2.0 on "
            "stdin/stdout so a non-Python client (e.g. the @bubblegum-ai/node "
            "npm package) can drive act/verify/extract/recover. One request per "
            "line in, one response per line out. See "
            "docs/distribution-npm-and-pypi.md."
        ),
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

    if args.command == "repl":
        from bubblegum.cli.repl import run_repl

        if not args.url and not args.appium_url:
            parser.error("repl requires --url (web) or --appium-url (mobile)")
        return run_repl(
            url=args.url,
            appium_url=args.appium_url,
            caps=args.caps,
            headless=args.headless,
            dry_run=args.dry_run,
        )

    if args.command == "convert":
        from bubblegum.cli.convert import run_convert

        return run_convert(
            workbook=args.workbook,
            out=args.out,
            config=args.config,
            languages=args.languages,
            ai=args.ai,
            init=args.init,
            name=args.name,
            no_overwrite=args.no_overwrite,
            group_by=args.group_by,
            feature=args.feature,
            sheet=args.sheet,
            no_data_file=args.no_data_file,
            dedup_subflows=args.dedup_subflows,
            validate_only=args.validate_only,
            update_package_json=args.update_package_json,
        )

    if args.command == "bridge":
        from bubblegum.cli.bridge import run_bridge

        return run_bridge()

    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
