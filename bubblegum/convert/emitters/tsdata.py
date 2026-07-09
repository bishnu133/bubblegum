"""
bubblegum/convert/emitters/tsdata.py
====================================
Static test-data extraction for the smart-tests emitter.

Pulls the quoted literals out of ``Enter "X" into <field>`` / ``Select "X" from
<field>`` steps into a per-scenario data object in ``<name>.data.ts`` so testers
edit values in one place. Rules:

  * Only static literals are extracted — anything containing a ``{{...}}``
    template expression stays inline.
  * One object per scenario, named ``<flowFn>Data``; keys are the camelCase of
    the field the value goes into (``From account`` → ``fromAccount``).
  * Button labels are never extracted — they live in ``Click ...`` steps, which
    carry no value slot, so scanning only Enter/Select naturally excludes them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bubblegum.convert.models import Scenario, StepKind

# decompose() action types that carry a value literal worth extracting.
_VALUE_ACTIONS = {"type", "select", "set", "upload"}

# Words dropped from a field phrase when deriving the data key.
_KEY_DROP = {
    "the", "a", "an", "dropdown", "field", "input", "menu", "button", "box",
    "list", "picker", "toggle", "checkbox", "radio", "selector", "option",
}


@dataclass
class ScenarioData:
    object_name: str
    entries: list[tuple[str, str]]              # (key, value) in order
    lookup: dict[tuple[str, str], str]          # (field, value) -> key


def data_key(field: str) -> str:
    """camelCase data key from a field phrase ("From account" -> fromAccount)."""
    words = [w for w in re.findall(r"[A-Za-z0-9]+", field or "") if w.lower() not in _KEY_DROP]
    if not words:
        words = ["value"]
    key = words[0].lower() + "".join(w.capitalize() for w in words[1:])
    return key if key[:1].isalpha() else "v" + key


def extract_scenario_data(scenario: Scenario, object_name: str) -> ScenarioData | None:
    """Collect static Enter/Select literals for one scenario, or None if none."""
    entries: list[tuple[str, str]] = []
    lookup: dict[tuple[str, str], str] = {}
    key_values: dict[str, str] = {}

    for step in scenario.steps:
        if step.kind is not StepKind.AUTO:
            continue
        val = step.value
        if not val or "{{" in val or step.action_type not in _VALUE_ACTIONS:
            continue
        field = step.target or "value"
        fk = (field, val)
        if fk in lookup:
            continue
        key = data_key(field)
        base, n = key, 2
        while key in key_values and key_values[key] != val:
            key, n = f"{base}{n}", n + 1
        key_values[key] = val
        if (key, val) not in entries:
            entries.append((key, val))
        lookup[fk] = key

    if not entries:
        return None
    return ScenarioData(object_name=object_name, entries=entries, lookup=lookup)
