"""Accessibility (axe-core) assertion helpers (V2).

Bubblegum already parses the accessibility tree for grounding; this adds an
actual a11y *audit* via axe-core. The browser-side injection lives in the web
adapter; everything here is pure, browser-free logic so it is fully unit
testable: resolving which axe-core build to inject, deciding the failing
severity, and turning a raw ``axe.run()`` result into a pass/fail summary.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Vendored axe-core build shipped with Bubblegum (see vendor/axe-core/NOTICE).
DEFAULT_AXE_PATH = Path(__file__).resolve().parent.parent / "testing" / "vendor" / "axe-core" / "axe.min.js"

# axe-core impact ordering, least → most severe.
IMPACT_ORDER = {"minor": 0, "moderate": 1, "serious": 2, "critical": 3}
_DEFAULT_IMPACT = "critical"


def load_axe_script(axe_script_path: str | Path | None = None) -> str:
    """Return the axe-core JavaScript source to inject.

    Reads the explicit path when given, otherwise the vendored default. Raises
    FileNotFoundError with a clear message if neither is present.
    """
    path = Path(axe_script_path) if axe_script_path else DEFAULT_AXE_PATH
    if not path.is_file():
        raise FileNotFoundError(
            f"axe-core script not found at {path}. Install Bubblegum's [a11y] "
            "extra or set a11y.axe_script_path / a11y.axe_url."
        )
    return path.read_text(encoding="utf-8")


def impact_from_instruction(instruction: str, default: str = _DEFAULT_IMPACT) -> str:
    """Infer the failing impact threshold from the NL instruction.

    "no critical a11y violations" → critical; "no serious ..." → serious, etc.
    Falls back to ``default`` when the instruction names no level.
    """
    lowered = (instruction or "").lower()
    # Least-severe first: if several levels are named (e.g. "serious or critical")
    # we return the lowest, i.e. the strictest threshold the user asked for.
    for level in ("minor", "moderate", "serious", "critical"):
        if level in lowered:
            return level
    return normalize_impact(default)


def normalize_impact(value: str | None) -> str:
    norm = str(value or "").strip().lower()
    return norm if norm in IMPACT_ORDER else _DEFAULT_IMPACT


def filter_violations(results: dict[str, Any], impact_threshold: str) -> list[dict[str, Any]]:
    """Return violations whose impact is at or above the threshold.

    axe sometimes reports ``impact: null`` for a violation; those are treated as
    below any threshold (not failing) since they carry no severity.
    """
    threshold_rank = IMPACT_ORDER[normalize_impact(impact_threshold)]
    out: list[dict[str, Any]] = []
    for violation in results.get("violations", []) or []:
        impact = violation.get("impact")
        if impact is None:
            continue
        if IMPACT_ORDER.get(str(impact).lower(), -1) >= threshold_rank:
            out.append(violation)
    return out


def safe_violation_summary(violations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reduce raw axe violations to report-safe structured records."""
    summary: list[dict[str, Any]] = []
    for v in violations:
        nodes = v.get("nodes") or []
        targets: list[str] = []
        for node in nodes[:5]:
            target = node.get("target")
            if isinstance(target, list):
                targets.append(" ".join(str(t) for t in target))
            elif target is not None:
                targets.append(str(target))
        summary.append(
            {
                "id": v.get("id"),
                "impact": v.get("impact"),
                "help": v.get("help"),
                "help_url": v.get("helpUrl"),
                "node_count": len(nodes),
                "sample_targets": targets,
            }
        )
    return summary


def format_violation_message(violations: list[dict[str, Any]], impact_threshold: str) -> str:
    """Build a one-line-per-rule human summary for the failure message."""
    if not violations:
        return f"no a11y violations at or above '{normalize_impact(impact_threshold)}'"
    lines = [f"{len(violations)} a11y violation(s) ≥ '{normalize_impact(impact_threshold)}':"]
    for v in violations:
        node_count = len(v.get("nodes") or [])
        lines.append(f"  - [{v.get('impact')}] {v.get('id')}: {v.get('help')} ({node_count} node(s))")
    return "\n".join(lines)


def evaluate_axe_results(
    results: dict[str, Any], impact_threshold: str
) -> tuple[bool, str, list[dict[str, Any]]]:
    """Turn a raw axe.run() result into (passed, message, safe_violations)."""
    threshold = normalize_impact(impact_threshold)
    failing = filter_violations(results, threshold)
    passed = not failing
    message = format_violation_message(failing, threshold)
    return passed, message, safe_violation_summary(failing)
