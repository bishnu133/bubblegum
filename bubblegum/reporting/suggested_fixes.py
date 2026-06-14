"""Suggested-fix + brittleness dump for self-healed runs (R3).

When self-healing substitutes a different element than the test asked for, the
brittle original is never fixed and teams lean on the heal forever. This writer
turns the healing advisories already attached to ``StepResult`` records into:

  - ``fixes``: a copy-pasteable old→new suggested change per healed step
  - ``brittleness``: the most-healed step labels, ranked (which selectors rot)

It reuses ``safe_healing_metadata`` so only report-safe fields are emitted.
Exposed via the ``--bubblegum-suggest-fixes PATH`` pytest flag.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Sequence

from bubblegum.core.schemas import StepResult
from bubblegum.reporting.html_report import safe_healing_metadata


def build_suggested_fixes(results: Sequence[StepResult], *, top_n: int = 5) -> dict:
    """Build the suggested-fix + brittleness payload from healed step results."""
    fixes: list[dict] = []
    brittle: Counter[str] = Counter()

    for result in results:
        healing = safe_healing_metadata(result.target.metadata if result.target else {})
        if not healing:
            continue
        old_ref = healing.get("old_ref") or healing.get("requested")
        new_ref = healing.get("new_ref") or healing.get("matched")
        fixes.append(
            {
                "action": result.action,
                "old_ref": old_ref,
                "new_ref": new_ref,
                "new_selector": healing.get("new_selector"),
                "suggested_fix": healing.get("suggested_fix"),
                "severity": healing.get("severity"),
                "match_kind": healing.get("match_kind"),
            }
        )
        if old_ref:
            brittle[str(old_ref)] += 1

    brittleness = [
        {"ref": ref, "heals": count} for ref, count in brittle.most_common(top_n)
    ]
    return {
        "version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_healed_steps": len(fixes),
        "fixes": fixes,
        "brittleness": brittleness,
    }


def write_suggested_fixes(
    results: Sequence[StepResult],
    path: str | Path = "bubblegum_suggested_fixes.json",
    *,
    top_n: int = 5,
) -> Path:
    """Write the suggested-fix + brittleness JSON dump to disk."""
    out_path = Path(path)
    payload = build_suggested_fixes(results, top_n=top_n)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path.resolve()
