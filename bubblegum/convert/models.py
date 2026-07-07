"""
bubblegum/convert/models.py
===========================
Data model for the manual → automation converter.

The pipeline is:

    RawScenario  (one spreadsheet row, raw text)
        │  ingest
        ▼
    GherkinStep[]  (Given/When/Then lines parsed out of the steps cell)
        │  normalize (+ decompose + optional AI)
        ▼
    CanonicalStep[]  (action/target/value + a StepKind classification)
        │  group
        ▼
    Scenario → Feature → ConvertResult
        │  emit
        ▼
    .feature / .py / .ts files

Everything here is a plain dataclass so the model has no heavy dependencies and
is trivial to construct in tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StepKind(str, Enum):
    """How automatable a single step is — drives what the emitters produce.

    AUTO       The step maps cleanly to a Bubblegum ``act``/``verify`` call.
    NEEDS_DATA The step depends on test data / preconditions a human must wire
               (e.g. "the group has 8 eligible badges"). Emitted with a TODO.
    BACKEND    A backend / data-state behaviour, not a UI interaction (e.g. the
               Feature/Epic is tagged ``[Backend]``). Emitted as a skipped stub.
    MANUAL     Could not be interpreted as an action or assertion — left for a
               human to author. Emitted as a TODO.
    """

    AUTO = "auto"
    NEEDS_DATA = "needs_data"
    BACKEND = "backend"
    MANUAL = "manual"


# Canonical Gherkin keywords. "And"/"But" inherit the section (given/when/then)
# of the preceding primary keyword during normalization.
GHERKIN_KEYWORDS = ("given", "when", "then", "and", "but")


@dataclass
class GherkinStep:
    """One parsed line from the steps cell.

    Attributes:
        keyword: normalized lower-case keyword (given/when/then/and/but).
        text:    the step text after the keyword.
    """

    keyword: str
    text: str


@dataclass
class RawScenario:
    """A single spreadsheet row before any interpretation.

    ``fields`` carries every mapped metadata column (feature, title, persona,
    jira, ...) so the profile can name columns however a team likes without the
    model hard-coding them. ``steps_text`` is the raw content of the steps
    column (the Gherkin body).
    """

    row: int
    steps_text: str
    fields: dict[str, str] = field(default_factory=dict)

    # Convenience accessors for the well-known metadata columns. They fall back
    # to empty strings so emitters never crash on a missing column.
    @property
    def feature(self) -> str:
        return self.fields.get("feature", "").strip()

    @property
    def title(self) -> str:
        return self.fields.get("title", "").strip()

    @property
    def persona(self) -> str:
        return self.fields.get("persona", "").strip()

    @property
    def jira(self) -> str:
        return self.fields.get("jira", "").strip()


@dataclass
class CanonicalStep:
    """A normalized, classified step ready for emission.

    Attributes:
        keyword:     given/when/then (and/but resolved to their section).
        text:        cleaned step text (used as the Gherkin step + step-def name).
        action_type: decompose() action (click/type/verify/...), or None.
        target:      element phrase to act on, or None.
        value:       value to type/select, or None.
        kind:        StepKind classification.
        confident:   True when the rule-based grammar matched cleanly.
        todo:        human-readable reason a step is not AUTO (for TODO markers).
    """

    keyword: str
    text: str
    action_type: str | None = None
    target: str | None = None
    value: str | None = None
    kind: StepKind = StepKind.MANUAL
    confident: bool = False
    todo: str | None = None
    # The subject-stripped instruction passed to act/verify at runtime, e.g.
    # display text "I enter \"x\" into Username" → instruction "enter \"x\" into
    # Username" (which Bubblegum's grammar parses cleanly). Defaults to `text`.
    instruction: str = ""

    def __post_init__(self) -> None:
        if not self.instruction:
            self.instruction = self.text


@dataclass
class Scenario:
    """A single test scenario (one spreadsheet row) after normalization."""

    title: str
    steps: list[CanonicalStep]
    persona: str = ""
    jira: str = ""
    feature: str = ""
    source_row: int = 0
    tags: list[str] = field(default_factory=list)

    @property
    def is_backend(self) -> bool:
        return all(s.kind is StepKind.BACKEND for s in self.steps) and bool(self.steps)

    @property
    def auto_count(self) -> int:
        return sum(1 for s in self.steps if s.kind is StepKind.AUTO)


@dataclass
class Feature:
    """A group of scenarios sharing the same Feature/Epic value."""

    name: str
    slug: str
    scenarios: list[Scenario] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    is_backend: bool = False


@dataclass
class ConvertResult:
    """Top-level output of a conversion run."""

    features: list[Feature] = field(default_factory=list)
    files_written: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def scenario_count(self) -> int:
        return sum(len(f.scenarios) for f in self.features)

    @property
    def step_count(self) -> int:
        return sum(len(s.steps) for f in self.features for s in f.scenarios)

    def stats(self) -> dict[str, int]:
        """Aggregate step counts by StepKind, plus feature/scenario totals."""
        counts = {k.value: 0 for k in StepKind}
        for f in self.features:
            for s in f.scenarios:
                for step in s.steps:
                    counts[step.kind.value] += 1
        counts["features"] = len(self.features)
        counts["scenarios"] = self.scenario_count
        counts["steps"] = self.step_count
        return counts
