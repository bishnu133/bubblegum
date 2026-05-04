#!/usr/bin/env python3
"""Deterministic benchmark fixture runner (Phase 2 scaffold)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

REQUIRED_KEYS = {
    "id",
    "category",
    "platform",
    "instruction",
    "action_type",
    "snapshot_path",
    "expected_resolver_winner",
    "confidence_min",
    "confidence_max",
}


def load_cases(repo_root: Path) -> list[dict]:
    cases_path = repo_root / "tests/benchmarks/fixtures/cases.json"
    with cases_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("cases.json must contain a list")
    return data


def validate_case(case: dict, repo_root: Path) -> tuple[bool, str]:
    missing = REQUIRED_KEYS - case.keys()
    if missing:
        return False, f"missing keys: {sorted(missing)}"
    if not 0 <= case["confidence_min"] <= case["confidence_max"] <= 1:
        return False, "invalid confidence range"
    snapshot_file = repo_root / "tests/benchmarks/fixtures" / case["snapshot_path"]
    if not snapshot_file.exists():
        return False, f"missing snapshot file: {case['snapshot_path']}"
    return True, "ok"


def run_benchmark_validation(repo_root: Path | None = None) -> int:
    root = repo_root or Path(__file__).resolve().parents[1]
    cases = load_cases(root)

    total = len(cases)
    passed = 0
    failed = 0
    winners = Counter()

    for case in cases:
        ok, _ = validate_case(case, root)
        if ok:
            passed += 1
            winners[case["expected_resolver_winner"]] += 1
        else:
            failed += 1

    success_rate = (passed / total * 100.0) if total else 0.0

    print(f"total cases: {total}")
    print(f"passed cases: {passed}")
    print(f"failed cases: {failed}")
    print(f"success rate: {success_rate:.2f}%")
    print("resolver winner distribution:")
    for winner, count in sorted(winners.items()):
        print(f"  - {winner}: {count}")

    return 0 if failed == 0 else 1


def main() -> int:
    return run_benchmark_validation()


if __name__ == "__main__":
    raise SystemExit(main())
