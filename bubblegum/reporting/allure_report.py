"""Allure results writer for Bubblegum StepResult outputs.

Allure is the de-facto rich-reporting standard in many enterprise QA teams,
and Bubblegum's per-step resolver / confidence / screenshot / healing data maps
onto it directly. This writer emits the Allure 2 *result* JSON format straight
into an ``allure-results/`` directory — no ``allure-pytest`` runtime dependency
is required to produce results; only the Allure command-line tool is needed to
render them (``allure serve allure-results``).

Each StepResult becomes one Allure test result (``<uuid>-result.json``):
  - status: passed/recovered → ``passed`` (a heal is added as a passing step so
    it never fails the build), failed → ``failed``, skipped/dry_run → ``skipped``
  - parameters: resolver name, confidence, and the soft-assertion flag
  - attachments: screenshot artifacts copied into the results directory
  - steps: a grounding step plus, when present, a self-healing step
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Sequence

from bubblegum.core.schemas import StepResult
from bubblegum.reporting.html_report import safe_healing_metadata

# StepResult.status → Allure status
_STATUS_MAP = {
    "passed": "passed",
    "recovered": "passed",
    "failed": "failed",
    "skipped": "skipped",
    "dry_run": "skipped",
}

_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _history_id(action: str, index: int) -> str:
    """Stable id so Allure can track a step's history across runs."""
    return hashlib.sha1(f"bubblegum::{index}::{action}".encode("utf-8")).hexdigest()


def _status_details(result: StepResult) -> dict[str, str] | None:
    if result.status == "failed" and result.error is not None:
        details: dict[str, str] = {}
        if result.error.message:
            details["message"] = result.error.message
        trace_parts = []
        if result.error.error_type:
            trace_parts.append(result.error.error_type)
        if getattr(result.error, "resolver_name", None):
            trace_parts.append(f"resolver={result.error.resolver_name}")
        if getattr(result.error, "candidates", None):
            trace_parts.append(f"candidates={len(result.error.candidates)}")
        if trace_parts:
            details["trace"] = " | ".join(trace_parts)
        return details or None
    if result.status == "recovered":
        return {"message": "Recovered by Bubblegum self-healing."}
    return None


def _parameters(result: StepResult) -> list[dict[str, str]]:
    params: list[dict[str, str]] = []
    if result.target is not None:
        if result.target.resolver_name:
            params.append({"name": "resolver", "value": str(result.target.resolver_name)})
        params.append({"name": "confidence", "value": f"{result.confidence:.2f}"})
        if isinstance(result.target.metadata, dict) and result.target.metadata.get("soft"):
            params.append({"name": "soft", "value": "true"})
    return params


def _heal_step(result: StepResult, now_ms: int) -> dict[str, Any] | None:
    metadata = result.target.metadata if (result.target and isinstance(result.target.metadata, dict)) else {}
    healing = safe_healing_metadata(metadata)
    if not healing:
        if result.status != "recovered":
            return None
        name = "Self-healing applied"
    else:
        requested = healing.get("requested")
        matched = healing.get("matched")
        name = "Self-healing applied"
        if requested is not None and matched is not None:
            name = f"Self-healing: {requested!r} → {matched!r}"
    return {
        "name": name,
        "status": "passed",
        "stage": "finished",
        "start": now_ms,
        "stop": now_ms,
        "parameters": [
            {"name": key, "value": str(value)}
            for key, value in healing.items()
            if key not in {"requested", "matched"}
        ],
    }


def _copy_attachments(result: StepResult, output_dir: Path) -> list[dict[str, str]]:
    """Copy screenshot artifacts into the results dir and return Allure refs."""
    attachments: list[dict[str, str]] = []
    for artifact in result.artifacts:
        if artifact.type != "screenshot":
            continue
        src = Path(artifact.path)
        suffix = src.suffix.lower() or ".png"
        content_type = _CONTENT_TYPES.get(suffix, "image/png")
        source_name = f"{uuid.uuid4()}-attachment{suffix}"
        try:
            if src.is_file():
                shutil.copyfile(src, output_dir / source_name)
            else:
                continue
        except OSError:
            continue
        attachments.append(
            {"name": src.name, "source": source_name, "type": content_type}
        )
    return attachments


def build_allure_result(
    result: StepResult,
    index: int,
    output_dir: Path,
    *,
    suite_name: str = "bubblegum",
) -> dict[str, Any]:
    """Build one Allure result dict for a StepResult, copying its attachments."""
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - max(int(result.duration_ms or 0), 0)
    name = result.action or f"step-{index}"

    grounding_step = {
        "name": f"Ground & {result.status}",
        "status": _STATUS_MAP.get(result.status, "broken"),
        "stage": "finished",
        "start": start_ms,
        "stop": now_ms,
    }
    steps = [grounding_step]
    heal = _heal_step(result, now_ms)
    if heal is not None:
        steps.append(heal)

    payload: dict[str, Any] = {
        "uuid": str(uuid.uuid4()),
        "historyId": _history_id(name, index),
        "name": name,
        "fullName": f"{suite_name}#{name}",
        "status": _STATUS_MAP.get(result.status, "broken"),
        "stage": "finished",
        "start": start_ms,
        "stop": now_ms,
        "labels": [
            {"name": "suite", "value": suite_name},
            {"name": "framework", "value": "bubblegum"},
        ],
        "parameters": _parameters(result),
        "steps": steps,
        "attachments": _copy_attachments(result, output_dir),
    }
    details = _status_details(result)
    if details:
        payload["statusDetails"] = details
    return payload


def write_allure_results(
    results: Sequence[StepResult],
    output_dir: str | Path = "allure-results",
    *,
    suite_name: str = "bubblegum",
) -> Path:
    """Write Allure 2 result files for a sequence of StepResult records.

    Returns the resolved results directory. View with ``allure serve <dir>``.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for index, result in enumerate(results):
        payload = build_allure_result(result, index, out_dir, suite_name=suite_name)
        result_path = out_dir / f"{payload['uuid']}-result.json"
        result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_dir.resolve()
