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


def _flaky_for(result: StepResult, flaky_index: dict | None):
    """Return the FlakyRecord for a step if it is currently classified flaky."""
    if not flaky_index:
        return None
    from bubblegum.core.flaky import step_identity

    key, _label = step_identity(result)
    return flaky_index.get(key)


def _flaky_note(record) -> str:
    pct = f"{record.pass_rate * 100:.0f}%"
    return (
        f"FLAKY: historical pass rate {pct} over {record.runs} run(s) "
        f"({record.passes} passed, {record.fails} failed)."
    )


def build_junit_tree(
    results: Sequence[StepResult],
    *,
    suite_name: str = "bubblegum",
    classname: str = "bubblegum",
    flaky_index: dict | None = None,
    quarantine: bool = False,
) -> ET.ElementTree:
    """Build the JUnit XML ElementTree for a sequence of StepResult records.

    ``flaky_index`` maps a step key (``flaky.step_identity``) → FlakyRecord for
    steps classified flaky (X1); matching steps get ``flaky`` / ``pass_rate``
    properties and a ``<system-out>`` note. When ``quarantine`` is True, a
    *failed* flaky step is downgraded to ``<skipped>`` (mark-but-not-fail) so it
    does not fail the CI build.
    """
    # Pre-compute each step's flaky record + effective status (quarantine may
    # downgrade a flaky failure to skipped) so the suite tallies stay correct.
    flaky_records = [_flaky_for(r, flaky_index) for r in results]
    quarantined = [
        bool(quarantine and fr is not None and r.status == "failed")
        for r, fr in zip(results, flaky_records)
    ]
    total = len(results)
    failures = sum(
        1 for r, q in zip(results, quarantined) if r.status == "failed" and not q
    )
    skipped = sum(
        1 for r, q in zip(results, quarantined) if r.status in _SKIP_STATUSES or q
    )
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

        flaky_record = flaky_records[index]
        is_quarantined = quarantined[index]
        out_messages: list[str] = []

        if is_quarantined:
            # Flaky failure, quarantined: surface as skipped (does not fail CI).
            _, body = _failure_text(result)
            ET.SubElement(
                testcase,
                "skipped",
                {"message": f"quarantined flaky step — {_flaky_note(flaky_record)}"},
            )
            out_messages.append(f"Quarantined flaky failure. {body}")
        elif result.status == "failed":
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

        # X1: flaky badge — properties + a system-out note for any flaky step.
        if flaky_record is not None:
            props = ET.SubElement(testcase, "properties")
            ET.SubElement(props, "property", {"name": "flaky", "value": "true"})
            ET.SubElement(props, "property", {"name": "pass_rate", "value": f"{flaky_record.pass_rate:.4f}"})
            ET.SubElement(props, "property", {"name": "runs", "value": str(flaky_record.runs)})
            out_messages.append(_flaky_note(flaky_record))

        healing_out = _healing_system_out(result)
        if healing_out:
            out_messages.append(healing_out)
        if out_messages:
            out_el = ET.SubElement(testcase, "system-out")
            out_el.text = " ".join(out_messages)

        _add_artifact_properties(testcase, result)

    return ET.ElementTree(testsuites)


def write_junit_report(
    results: Sequence[StepResult],
    path: str | Path = "bubblegum_report.xml",
    *,
    suite_name: str = "bubblegum",
    classname: str = "bubblegum",
    flaky_index: dict | None = None,
    quarantine: bool = False,
) -> Path:
    """Write a JUnit XML report to disk for a sequence of StepResult records."""
    out_path = Path(path)
    tree = build_junit_tree(
        results,
        suite_name=suite_name,
        classname=classname,
        flaky_index=flaky_index,
        quarantine=quarantine,
    )
    ET.indent(tree, space="  ")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return out_path.resolve()
