"""JUnit XML report writer for Bubblegum StepResult outputs.

Jenkins, GitLab CI, Azure DevOps and CircleCI all consume JUnit XML natively
for pass/fail dashboards and history. This writer mirrors the shape of
``html_report`` / ``json_report``: it takes the same ``Sequence[StepResult]``
the pytest plugin already aggregates and emits a standards-compliant
``<testsuites>`` document.

Status mapping (per StepResult.status):
  - ``passed``    → a passing ``<testcase>``
  - ``recovered`` → a passing ``<testcase>`` whose heal is surfaced in
                    ``<system-out>`` so it is visible without failing the build
  - ``failed``    → ``<testcase>`` carrying a ``<failure>``
  - ``skipped``   → ``<testcase>`` carrying a ``<skipped>``
  - ``dry_run``   → ``<testcase>`` carrying a ``<skipped>`` (resolve-only, not run)

One ``<testcase>`` is emitted per StepResult (one logical step), matching the
per-step row model the HTML/JSON reports already use. Screenshot / artifact
paths are attached as ``<property>`` elements on the testcase.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from xml.etree import ElementTree as ET

from bubblegum.core.schemas import StepResult
from bubblegum.reporting.html_report import safe_healing_metadata

# Statuses that count as a passing testcase (do not fail the CI build).
_PASS_STATUSES = {"passed", "recovered"}
# Statuses surfaced as <skipped> rather than pass/fail.
_SKIP_STATUSES = {"skipped", "dry_run"}


def _seconds(duration_ms: int) -> str:
    """Render a millisecond duration as JUnit's fractional-seconds string."""
    try:
        return f"{max(int(duration_ms), 0) / 1000:.3f}"
    except (TypeError, ValueError):
        return "0.000"


def _healing_system_out(result: StepResult) -> str | None:
    """Build a <system-out> body describing a recovered step's heal, if any.

    Reuses the same sanitized healing fields the JSON/HTML reports surface so
    secrets / raw payloads never leak into CI output.
    """
    metadata = {}
    if result.target is not None and isinstance(result.target.metadata, dict):
        metadata = result.target.metadata
    healing = safe_healing_metadata(metadata)
    if healing:
        requested = healing.get("requested")
        matched = healing.get("matched")
        parts = ["Self-healing applied."]
        if requested is not None and matched is not None:
            parts.append(f"requested {requested!r} → matched {matched!r}")
        for key in ("resolver", "match_kind", "similarity", "severity", "message"):
            if key in healing:
                parts.append(f"{key}={healing[key]}")
        return " ".join(parts)
    # Recovered without structured healing metadata — still note the recovery.
    if result.status == "recovered":
        note = "Step recovered by Bubblegum self-healing."
        if result.error is not None and result.error.message:
            note += f" ({result.error.message})"
        return note
    return None


def _failure_text(result: StepResult) -> tuple[str, str]:
    """Return (message, body) for a failed step's <failure> element."""
    err = result.error
    if err is not None:
        message = err.message or err.error_type or "Step failed"
        lines = [f"{err.error_type}: {err.message}" if err.error_type else (err.message or "")]
        if getattr(err, "resolver_name", None):
            lines.append(f"resolver: {err.resolver_name}")
        if getattr(err, "candidates", None):
            lines.append(f"candidates considered: {len(err.candidates)}")
        body = "\n".join(line for line in lines if line)
        return message, body
    message = f"Step failed: {result.action}"
    return message, message


def _add_artifact_properties(testcase: ET.Element, result: StepResult) -> None:
    """Attach screenshot / artifact paths as <property> elements."""
    if not result.artifacts:
        return
    props = ET.SubElement(testcase, "properties")
    for index, artifact in enumerate(result.artifacts):
        ET.SubElement(
            props,
            "property",
            {
                "name": f"{artifact.type}:{index}" if artifact.type else f"artifact:{index}",
                "value": str(artifact.path),
            },
        )


def build_junit_tree(
    results: Sequence[StepResult],
    *,
    suite_name: str = "bubblegum",
    classname: str = "bubblegum",
) -> ET.ElementTree:
    """Build the JUnit XML ElementTree for a sequence of StepResult records."""
    total = len(results)
    failures = sum(1 for r in results if r.status == "failed")
    skipped = sum(1 for r in results if r.status in _SKIP_STATUSES)
    total_time = _seconds(sum(int(r.duration_ms or 0) for r in results))
    timestamp = datetime.now(timezone.utc).isoformat()

    testsuites = ET.Element(
        "testsuites",
        {
            "name": suite_name,
            "tests": str(total),
            "failures": str(failures),
            "errors": "0",
            "skipped": str(skipped),
            "time": total_time,
        },
    )
    testsuite = ET.SubElement(
        testsuites,
        "testsuite",
        {
            "name": suite_name,
            "tests": str(total),
            "failures": str(failures),
            "errors": "0",
            "skipped": str(skipped),
            "time": total_time,
            "timestamp": timestamp,
        },
    )

    for index, result in enumerate(results):
        name = result.action or f"step-{index}"
        testcase = ET.SubElement(
            testsuite,
            "testcase",
            {
                "name": name,
                "classname": classname,
                "time": _seconds(result.duration_ms),
            },
        )

        if result.status == "failed":
            message, body = _failure_text(result)
            failure = ET.SubElement(
                testcase,
                "failure",
                {
                    "message": message,
                    "type": (result.error.error_type if result.error else "AssertionError"),
                },
            )
            failure.text = body
        elif result.status in _SKIP_STATUSES:
            reason = "dry-run (resolve only, not executed)" if result.status == "dry_run" else "skipped"
            ET.SubElement(testcase, "skipped", {"message": reason})

        system_out = _healing_system_out(result)
        if system_out:
            out_el = ET.SubElement(testcase, "system-out")
            out_el.text = system_out

        _add_artifact_properties(testcase, result)

    return ET.ElementTree(testsuites)


def write_junit_report(
    results: Sequence[StepResult],
    path: str | Path = "bubblegum_report.xml",
    *,
    suite_name: str = "bubblegum",
    classname: str = "bubblegum",
) -> Path:
    """Write a JUnit XML report to disk for a sequence of StepResult records."""
    out_path = Path(path)
    tree = build_junit_tree(results, suite_name=suite_name, classname=classname)
    ET.indent(tree, space="  ")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return out_path.resolve()
