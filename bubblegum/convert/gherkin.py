"""
bubblegum/convert/gherkin.py
============================
Parse the free-text contents of the "steps" column into structured Gherkin
steps. Deliberately lenient: real spreadsheets contain smart quotes, bullet
sub-lists, wrapped continuation lines, and the occasional ``Scenario:`` header.

We keep only the step lines (Given/When/Then/And/But). A line with no leading
keyword is treated as a continuation of the previous step (common when a long
"Then" wraps, or when a step is followed by an indented sub-list of fields).
"""

from __future__ import annotations

import re

from bubblegum.convert.models import GHERKIN_KEYWORDS, GherkinStep

# Leading keyword, e.g. "Given ", "  And ", "Then:" — case-insensitive.
_KEYWORD_RE = re.compile(
    r"^\s*(given|when|then|and|but)\b[\s:]*",
    re.IGNORECASE,
)

# Structural lines we skip entirely (headers, tables, comments, blank).
_SKIP_RE = re.compile(
    r"^\s*(?:@|#|feature:|scenario(?:\s+outline)?:|examples:|background:|\|)",
    re.IGNORECASE,
)

# Normalize the curly quotes / dashes that Word/Excel love to insert, so
# downstream matching and emitted code use plain ASCII.
_SMART = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", " ": " ",
}


def clean_text(text: str) -> str:
    """Collapse whitespace and replace smart punctuation with ASCII."""
    if text is None:
        return ""
    for bad, good in _SMART.items():
        text = text.replace(bad, good)
    return re.sub(r"\s+", " ", text).strip()


def parse_gherkin(cell: str) -> list[GherkinStep]:
    """Split a steps-cell string into a list of GherkinStep.

    Rules:
      * Lines starting with a Gherkin keyword begin a new step.
      * Lines without a keyword continue the previous step (joined with a space).
      * Structural lines (Feature:/Scenario:/tables/comments) are skipped.
      * If nothing matches a keyword at all, every non-empty line becomes a
        bare step (keyword "" ) so an imperative "Steps" column still works.
    """
    if not cell:
        return []

    raw_lines = str(cell).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    steps: list[GherkinStep] = []
    saw_keyword = False

    for raw in raw_lines:
        line = clean_text(raw)
        if not line:
            continue
        if _SKIP_RE.match(line):
            continue

        m = _KEYWORD_RE.match(line)
        if m:
            saw_keyword = True
            keyword = m.group(1).lower()
            body = line[m.end():].strip()
            steps.append(GherkinStep(keyword=keyword, text=clean_text(body)))
        elif steps and steps[-1].keyword:
            # Continuation of a *keyworded* step (wrapped line or sub-field list).
            prev = steps[-1]
            prev.text = clean_text(f"{prev.text} {line}")
        elif steps:
            # Previous line was also keyword-less → imperative list: new step.
            steps.append(GherkinStep(keyword="", text=line))
        else:
            # Leading line with no keyword and nothing to attach to — hold it as
            # a keyword-less step; resolved below if no keywords ever appear.
            steps.append(GherkinStep(keyword="", text=line))

    if not saw_keyword:
        # Imperative / plain-list column: keep the bare steps as-is.
        return [s for s in steps if s.text]

    # Drop any keyword-less leading noise that preceded the first real keyword.
    return [s for s in steps if s.keyword in GHERKIN_KEYWORDS and s.text]
