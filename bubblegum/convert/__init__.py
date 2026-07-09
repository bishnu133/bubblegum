"""
bubblegum.convert
=================
Manual-test-scenario → automated-script converter.

Takes a spreadsheet of manually authored test scenarios (Gherkin-style steps in
a designated column, plus metadata columns like Feature/Epic, Test Scenario,
User Persona, Jira story) and generates reviewable automation *scaffolds*:

  * normalized ``.feature`` files (one per Feature/Epic),
  * Python step definitions (pytest-bdd) that call Bubblegum's ``act`` / ``verify``,
  * TypeScript step definitions (playwright-bdd) that call ``@bubblegum-ai/node``.

Design posture (mirrors the rest of Bubblegum):
  * **Deterministic-first.** Each step is parsed with the existing rule-based
    ``bubblegum.core.parser.decompose`` grammar. AI is an *optional* fallback,
    off by default, for steps the grammar can't confidently split.
  * **Honest scaffolds, not magic.** Steps that need a human (locators for
    abstract assertions, test-data setup, backend/API behaviour) are emitted
    with explicit ``TODO`` markers rather than silently-wrong code.
  * **Generic / team-agnostic.** Column names, output languages, directories and
    conventions all come from a ``bubblegum.convert.yaml`` profile so any team
    can point it at their own spreadsheet layout.

Public API:
    from bubblegum.convert import convert_workbook, ConvertProfile
    result = convert_workbook("scenarios.xlsx", out_dir="generated")
"""

from __future__ import annotations

from bubblegum.convert.engine import convert_workbook
from bubblegum.convert.models import (
    CanonicalStep,
    ConvertResult,
    Feature,
    GherkinStep,
    RawScenario,
    Scenario,
    StepKind,
)
from bubblegum.convert.profile import ConvertProfile

__all__ = [
    "convert_workbook",
    "ConvertProfile",
    "RawScenario",
    "GherkinStep",
    "CanonicalStep",
    "Scenario",
    "Feature",
    "ConvertResult",
    "StepKind",
]
