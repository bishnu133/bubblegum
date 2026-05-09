"""Standalone JSON/HTML report artifact example.

Creates sample StepResult records and writes report artifacts locally.
No browser/device dependency.
"""

from __future__ import annotations

from pathlib import Path

from bubblegum.core.schemas import ResolvedTarget, StepResult
from bubblegum.reporting.html_report import write_html_report
from bubblegum.reporting.json_report import write_json_report


def build_sample_results() -> list[StepResult]:
    step_ok = StepResult(
        status="passed",
        action="click",
        confidence=0.94,
        duration_ms=45,
        target=ResolvedTarget(
            ref='role=button[name="Buy now"]',
            confidence=0.94,
            resolver_name="SemanticResolver",
            metadata={
                "hydration_status": "hydrated",
                "hydration_channel": "web",
                "hydration_source": "ocr",
                "hydration_strategy": "text_exact",
                "hydration_reason": "matched_text",
                "match_field": "text",
                "match_count": 1,
            },
        ),
    )

    step_recovered = StepResult(
        status="recovered",
        action="verify",
        confidence=0.86,
        duration_ms=73,
        target=ResolvedTarget(
            ref="text=order placed",
            confidence=0.86,
            resolver_name="TextResolver",
            metadata={
                "hydration_status": "not_needed",
                "hydration_channel": "web",
            },
        ),
    )

    return [step_ok, step_recovered]


def main() -> None:
    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    results = build_sample_results()
    json_path = write_json_report(results, artifacts_dir / "report-artifacts-example.json", title="Report Artifacts Example")
    html_path = write_html_report(results, artifacts_dir / "report-artifacts-example.html", title="Report Artifacts Example")

    print(f"Wrote JSON report: {json_path}")
    print(f"Wrote HTML report: {html_path}")


if __name__ == "__main__":
    main()
