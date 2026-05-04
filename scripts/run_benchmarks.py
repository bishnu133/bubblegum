#!/usr/bin/env python3
"""Deterministic benchmark fixture runner."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from html import unescape
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
        a11y_snapshot = _html_to_a11y_snapshot(snapshot)
        context = {
            "a11y_snapshot": a11y_snapshot,
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


def _html_to_a11y_snapshot(html: str) -> str:
    """
    Convert fixture HTML into a minimal aria-snapshot-like line format.

    This is intentionally heuristic and benchmark-harness-only, just enough for
    deterministic text/a11y resolvers that expect lines like:
      button "Login"
      textbox "Email"
      heading "Settings"
    """
    role_lines: list[str] = []

    # button / link / heading / paragraph-ish visible text
    text_roles = [
        (r"<button\b([^>]*)>(.*?)</button>", "button"),
        (r"<a\b([^>]*)>(.*?)</a>", "link"),
        (r"<h[1-6]\b([^>]*)>(.*?)</h[1-6]>", "heading"),
        (r"<p\b([^>]*)>(.*?)</p>", "paragraph"),
        (r"<option\b([^>]*)>(.*?)</option>", "option"),
        (r"<label\b([^>]*)>(.*?)</label>", "paragraph"),
    ]
    for pattern, default_role in text_roles:
        for attrs, body in re.findall(pattern, html, flags=re.IGNORECASE | re.DOTALL):
            role = _extract_attr(attrs, "role") or default_role
            name = _clean_text(body) or _extract_attr(attrs, "aria-label")
            role_lines.append(_fmt_snapshot_line(role, name))

    # input/select controls (self-closing or paired)
    for attrs in re.findall(r"<input\b([^>]*)/?>", html, flags=re.IGNORECASE | re.DOTALL):
        role = _extract_attr(attrs, "role") or "textbox"
        name = _extract_attr(attrs, "aria-label") or _extract_attr(attrs, "name") or _extract_attr(attrs, "id")
        role_lines.append(_fmt_snapshot_line(role, name))

    for attrs in re.findall(r"<select\b([^>]*)>", html, flags=re.IGNORECASE | re.DOTALL):
        role = _extract_attr(attrs, "role") or "combobox"
        name = _extract_attr(attrs, "aria-label") or _extract_attr(attrs, "name") or _extract_attr(attrs, "id")
        role_lines.append(_fmt_snapshot_line(role, name))

    # remove blank lines while preserving order
    cleaned = [line for line in role_lines if line.strip()]
    return "\n".join(cleaned)


def _extract_attr(attrs: str, name: str) -> str:
    m = re.search(rf"""\b{name}\s*=\s*["']([^"']+)["']""", attrs, flags=re.IGNORECASE)
    return unescape(m.group(1)).strip() if m else ""


def _clean_text(value: str) -> str:
    collapsed = re.sub(r"<[^>]+>", " ", value)
    collapsed = unescape(collapsed)
    return re.sub(r"\s+", " ", collapsed).strip()


def _fmt_snapshot_line(role: str, name: str) -> str:
    role_clean = (role or "").strip().lower()
    name_clean = (name or "").strip()
    if not role_clean:
        return ""
    if name_clean:
        return f'{role_clean} "{name_clean}"'
    return role_clean


def _build_deterministic_engine() -> GroundingEngineProtocol:
    from bubblegum.core.grounding.engine import GroundingEngine
    from bubblegum.core.grounding.registry import ResolverRegistry
    from bubblegum.core.grounding.resolvers.accessibility_tree import AccessibilityTreeResolver
    from bubblegum.core.grounding.resolvers.appium_hierarchy import AppiumHierarchyResolver
    from bubblegum.core.grounding.resolvers.exact_text import ExactTextResolver
    from bubblegum.core.grounding.resolvers.explicit_selector import ExplicitSelectorResolver
    from bubblegum.core.grounding.resolvers.fuzzy_text import FuzzyTextResolver
    from bubblegum.core.grounding.resolvers.memory_cache import MemoryCacheResolver

    registry = ResolverRegistry()
    for resolver_name in ("llm_grounding", "ocr", "vision_model"):
        registry.unregister(resolver_name)
    for resolver in [
        ExplicitSelectorResolver(),
        MemoryCacheResolver(),
        AccessibilityTreeResolver(),
        AppiumHierarchyResolver(),
        ExactTextResolver(),
        FuzzyTextResolver(),
    ]:
        registry.register(resolver)
    return GroundingEngine(registry=registry)


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
        engine = _build_deterministic_engine()

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
