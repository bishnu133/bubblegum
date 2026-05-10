#!/usr/bin/env python3
"""Dependency-free infra-free smoke runner (Phase 17E MVP).

Default behavior:
- Executes only infra-free examples:
  - examples/ocr_callable_hydration_example.py
  - examples/report_artifacts_example.py
- Prints manual-only commands for Playwright/Appium/OpenAI examples.

Dry-run behavior:
- Prints planned commands only.
- Executes nothing.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

INFRA_FREE_EXAMPLES: list[str] = [
    "examples/ocr_callable_hydration_example.py",
    "examples/report_artifacts_example.py",
]

MANUAL_COMMANDS: list[str] = [
    'python -m pip install -e ".[web]"',
    "python -m playwright install chromium",
    "python examples/web_nl_quickstart.py",
    "python examples/appium_quickstart.py",
    "python examples/openai_vision_provider_manual_example.py",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Bubblegum infra-free smoke examples.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned commands only; execute nothing.",
    )
    return parser.parse_args(argv)


def get_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def planned_infra_free_commands() -> list[list[str]]:
    return [[sys.executable, script] for script in INFRA_FREE_EXAMPLES]


def print_manual_commands() -> None:
    print("\nManual-only commands (printed, not executed by this runner):")
    for command in MANUAL_COMMANDS:
        print(f"  - {command}")


def run_infra_free_examples(repo_root: Path) -> int:
    commands = planned_infra_free_commands()
    results: list[tuple[str, int]] = []

    print("Running infra-free smoke examples:")
    for command in commands:
        display = " ".join(command)
        print(f"\n[RUN] {display}")
        env = dict(**__import__("os").environ)
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(repo_root) if not existing else f"{repo_root}:{existing}"
        completed = subprocess.run(command, cwd=repo_root, env=env)
        results.append((command[1], completed.returncode))

    passed = [script for script, code in results if code == 0]
    failed = [(script, code) for script, code in results if code != 0]

    print("\nSmoke summary:")
    for script in passed:
        print(f"  PASS: {script}")
    for script, code in failed:
        print(f"  FAIL: {script} (exit {code})")

    print(f"\nTotal: {len(results)} | Passed: {len(passed)} | Failed: {len(failed)}")
    return 0 if not failed else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = get_repo_root()

    print(f"Repo root: {repo_root}")

    print("\nInfra-free commands:")
    for command in planned_infra_free_commands():
        print(f"  - {' '.join(command)}")

    print_manual_commands()

    if args.dry_run:
        print("\nDry-run mode: no commands executed.")
        return 0

    return run_infra_free_examples(repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
