"""
bubblegum/core/flaky.py
=======================
Flaky-test detection / quarantine (X1).

A *flaky* step is one that passes intermittently — it has both passed and
failed across runs and its historical pass-rate is below a stability
threshold. That is distinct from a *broken* step (always fails) and a *stable*
step (always passes). This module holds the pure classification logic plus a
``FlakyTracker`` that records one outcome per step per run into the SQLite
memory layer and summarizes the accumulated history.

Recording is keyed by a stable step identity derived from the NL instruction
(and screen signature when available), so the same logical step re-running
across sessions accumulates a pass-rate. The pytest plugin records a run at
session end and reports/JUnit annotate flaky steps.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable, Sequence

# Outcomes that count as an observation (others — skipped/dry_run — are ignored).
_PASS_STATUSES = {"passed", "recovered"}
_FAIL_STATUSES = {"failed"}

_WS_RE = re.compile(r"\s+")


def outcome_passed(status: str) -> bool | None:
    """Map a StepResult.status to a pass(True)/fail(False)/ignore(None) outcome."""
    if status in _PASS_STATUSES:
        return True
    if status in _FAIL_STATUSES:
        return False
    return None  # skipped / dry_run → not a flakiness observation


def step_identity(result) -> tuple[str, str]:
    """Return ``(step_key, label)`` for a StepResult.

    The label is the (whitespace-normalized) NL action; the key is a stable
    hash of the screen signature + label so the same logical step re-running
    across sessions maps to one history row. ``screen_signature`` is used when a
    resolver left it on ``target.metadata``.
    """
    label = _WS_RE.sub(" ", str(getattr(result, "action", "") or "")).strip()
    screen_sig = ""
    target = getattr(result, "target", None)
    if target is not None and isinstance(getattr(target, "metadata", None), dict):
        screen_sig = str(target.metadata.get("screen_signature") or "")
    raw = f"{screen_sig}\x1f{label.lower()}"
    key = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return key, label


@dataclass
class FlakyRecord:
    """A step's flakiness summary across runs."""

    step_key: str
    label: str
    runs: int
    passes: int
    fails: int
    pass_rate: float
    flaky: bool


def classify(
    runs: int,
    passes: int,
    *,
    stability_threshold: float = 0.90,
    min_runs: int = 3,
) -> tuple[bool, float]:
    """Return ``(is_flaky, pass_rate)``.

    Flaky ⇔ enough runs, at least one pass AND one fail (intermittent), and the
    pass-rate is below the stability threshold. A step that always fails (no
    passes) is broken, not flaky; one that always passes is stable.
    """
    runs = max(int(runs), 0)
    passes = max(int(passes), 0)
    fails = runs - passes
    pass_rate = (passes / runs) if runs else 0.0
    is_flaky = (
        runs >= min_runs
        and passes > 0
        and fails > 0
        and pass_rate < stability_threshold
    )
    return is_flaky, round(pass_rate, 4)


def summarize(
    rows: Iterable[dict],
    *,
    stability_threshold: float = 0.90,
    min_runs: int = 3,
) -> list[FlakyRecord]:
    """Turn flaky-history rows into FlakyRecords, flaky-first, lowest pass-rate first."""
    records: list[FlakyRecord] = []
    for row in rows:
        runs = int(row.get("runs", 0))
        passes = int(row.get("passes", 0))
        is_flaky, pass_rate = classify(
            runs, passes, stability_threshold=stability_threshold, min_runs=min_runs
        )
        records.append(
            FlakyRecord(
                step_key=str(row.get("step_key", "")),
                label=str(row.get("label", "")),
                runs=runs,
                passes=passes,
                fails=runs - passes,
                pass_rate=pass_rate,
                flaky=is_flaky,
            )
        )
    # Flaky steps first; within each group, least-stable then most-observed.
    records.sort(key=lambda r: (not r.flaky, r.pass_rate, -r.runs))
    return records


class FlakyTracker:
    """Records run outcomes into a MemoryLayer and summarizes flakiness."""

    def __init__(self, memory_layer, *, stability_threshold: float = 0.90, min_runs: int = 3):
        self._mem = memory_layer
        self._threshold = float(stability_threshold)
        self._min_runs = int(min_runs)

    def record_run(self, results: Sequence) -> int:
        """Record one run: one outcome per unique step.

        Within a run a step may appear more than once (retries, loops); it is
        collapsed to a single observation — a fail if *any* occurrence failed,
        else a pass. Steps with no pass/fail outcome (skipped/dry-run) are
        ignored. Returns the number of distinct steps recorded.
        """
        # key -> (label, passed) where passed is False if any occurrence failed.
        observed: dict[str, list] = {}
        for result in results:
            decided = outcome_passed(getattr(result, "status", ""))
            if decided is None:
                continue
            key, label = step_identity(result)
            if key not in observed:
                observed[key] = [label, decided]
            elif not decided:
                observed[key][1] = False  # a fail anywhere makes the run a fail

        for key, (label, passed) in observed.items():
            self._mem.record_flaky_outcome(key, label, bool(passed))
        return len(observed)

    def summary(self) -> list[FlakyRecord]:
        """FlakyRecords for all tracked steps (flaky-first)."""
        return summarize(
            self._mem.flaky_rows(),
            stability_threshold=self._threshold,
            min_runs=self._min_runs,
        )

    def flaky_index(self) -> dict[str, FlakyRecord]:
        """Map step_key → FlakyRecord for steps currently classified flaky."""
        return {r.step_key: r for r in self.summary() if r.flaky}
