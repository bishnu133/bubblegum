#!/usr/bin/env python3
"""Deterministic benchmark fixture runner."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Protocol

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bubblegum.core.schemas import ExecutionOptions, StepIntent

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


class GroundingEngineProtocol(Protocol):
    async def ground(self, intent: StepIntent) -> tuple[Any, list[Any]]:
        """Ground a StepIntent and return (target, traces)."""


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


def run_static_validation(repo_root: Path) -> dict[str, Any]:
    cases = load_cases(repo_root)
    diagnostics: list[dict[str, Any]] = []
    winners = Counter()

    for case in cases:
        ok, message = validate_case(case, repo_root)
        diagnostics.append({"id": case.get("id"), "ok": ok, "message": message})
        if ok:
            winners[case["expected_resolver_winner"]] += 1

    passed = sum(1 for d in diagnostics if d["ok"])
    failed = len(diagnostics) - passed
    return {
        "total": len(cases),
        "passed": passed,
        "failed": failed,
        "success_rate": (passed / len(cases) * 100.0) if cases else 0.0,
        "winner_distribution": dict(sorted(winners.items())),
        "diagnostics": diagnostics,
        "ok": failed == 0,
    }


def _map_case_to_intent(case: dict, repo_root: Path) -> StepIntent:
    snapshot_file = repo_root / "tests/benchmarks/fixtures" / case["snapshot_path"]
    snapshot = snapshot_file.read_text(encoding="utf-8")

    platform = case["platform"].lower()
    if platform == "web":
        channel = "web"
        context = {
            "a11y_snapshot": snapshot,
            "dom_snapshot": snapshot,
        }
    elif platform == "android":
        channel = "mobile"
        context = {"hierarchy_xml": snapshot}
    else:
        raise ValueError(f"Unsupported platform in benchmark case: {case['platform']}")

    return StepIntent(
        instruction=case["instruction"],
        action_type=case["action_type"],
        channel=channel,
        context=context,
        options=ExecutionOptions(max_cost_level="low"),
    )


async def _execute_cases_async(
    repo_root: Path,
    engine: GroundingEngineProtocol,
    cases: list[dict],
) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []

    for case in cases:
        intent = _map_case_to_intent(case, repo_root)
        expected_winner = case["expected_resolver_winner"]
        cmin = case["confidence_min"]
        cmax = case["confidence_max"]

        try:
            target, traces = await engine.ground(intent)
            actual_winner = target.resolver_name
            actual_conf = float(target.confidence)

            winner_ok = actual_winner == expected_winner
            conf_ok = cmin <= actual_conf <= cmax
            status = "pass" if (winner_ok and conf_ok) else "fail"

            diagnostics.append(
                {
                    "id": case["id"],
                    "category": case["category"],
                    "expected_winner": expected_winner,
                    "actual_winner": actual_winner,
                    "actual_confidence": round(actual_conf, 4),
                    "confidence_min": cmin,
                    "confidence_max": cmax,
                    "winner_ok": winner_ok,
                    "confidence_ok": conf_ok,
                    "status": status,
                    "error": None,
                    "trace_count": len(traces),
                }
            )
        except Exception as exc:  # noqa: BLE001
            diagnostics.append(
                {
                    "id": case["id"],
                    "category": case["category"],
                    "expected_winner": expected_winner,
                    "actual_winner": None,
                    "actual_confidence": None,
                    "confidence_min": cmin,
                    "confidence_max": cmax,
                    "winner_ok": False,
                    "confidence_ok": False,
                    "status": "fail",
                    "error": f"{type(exc).__name__}: {exc}",
                    "trace_count": 0,
                }
            )

    passed = sum(1 for d in diagnostics if d["status"] == "pass")
    failed = len(diagnostics) - passed
    return {
        "total": len(diagnostics),
        "passed": passed,
        "failed": failed,
        "success_rate": (passed / len(diagnostics) * 100.0) if diagnostics else 0.0,
        "diagnostics": diagnostics,
        "ok": failed == 0,
    }


def run_execution_validation(
    repo_root: Path,
    engine: GroundingEngineProtocol | None = None,
    cases: list[dict] | None = None,
) -> dict[str, Any]:
    if engine is None:
        from bubblegum.core.grounding.engine import GroundingEngine

        engine = GroundingEngine()

    selected_cases = cases if cases is not None else load_cases(repo_root)
    return asyncio.run(_execute_cases_async(repo_root, engine, selected_cases))


def _print_static_summary(result: dict[str, Any]) -> None:
    print("[static validation]")
    print(f"total cases: {result['total']}")
    print(f"passed cases: {result['passed']}")
    print(f"failed cases: {result['failed']}")
    print(f"success rate: {result['success_rate']:.2f}%")
    print("resolver winner distribution:")
    for winner, count in result["winner_distribution"].items():
        print(f"  - {winner}: {count}")


def _print_execution_summary(result: dict[str, Any]) -> None:
    print("\n[execution validation]")
    print(f"total cases: {result['total']}")
    print(f"passed cases: {result['passed']}")
    print(f"failed cases: {result['failed']}")
    print(f"success rate: {result['success_rate']:.2f}%")


def run_benchmark_validation(
    repo_root: Path | None = None,
    *,
    execute: bool = False,
    engine: GroundingEngineProtocol | None = None,
) -> int:
    root = repo_root or Path(__file__).resolve().parents[1]
    static_result = run_static_validation(root)
    _print_static_summary(static_result)

    execution_result: dict[str, Any] | None = None
    if execute:
        execution_result = run_execution_validation(root, engine=engine)
        _print_execution_summary(execution_result)

    static_ok = static_result["ok"]
    exec_ok = True if execution_result is None else execution_result["ok"]
    return 0 if (static_ok and exec_ok) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run benchmark validation checks.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run static validation plus deterministic GroundingEngine execution checks.",
    )
    args = parser.parse_args()
    return run_benchmark_validation(execute=args.execute)


if __name__ == "__main__":
    raise SystemExit(main())
