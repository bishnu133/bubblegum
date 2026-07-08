"""
bubblegum/convert/profile.py
============================
ConvertProfile — the per-team convention layer.

This is the answer to "every team follows their own setup". A team drops a
``bubblegum.convert.yaml`` next to their spreadsheet describing their column
names, which languages to emit, where files go, and how waits/imports should
look. Everything the converter does that could reasonably differ between teams
is driven from here, so the engine itself stays generic.

Example ``bubblegum.convert.yaml``::

    convert:
      input:
        sheet: null            # null = active/first sheet
        header_row: 1
        columns:
          feature: "Feature/Epic"
          title:   "Test Scenario"
          persona: "User Persona"
          jira:    "Functional Jira Story"
          steps:   "Verify"
        backend_markers: ["[Backend]"]   # substrings that mark a row backend-only
      output:
        languages: ["feature", "python", "typescript"]
        dir: "generated"
        python:
          bubblegum_import: "from bubblegum import act, verify, extract"
        typescript:
          client_import: "@bubblegum-ai/node"
      waits:
        strategy: "auto"       # auto | explicit | none
      glossary: {}             # phrase -> canonical step text (domain rules)
      data: {}                 # token -> data-binding expression
      ai:
        enabled: false
        provider: null         # falls back to bubblegum.yaml `ai:` block
        model: null

Only ``convert:`` keys are read; unknown keys are ignored so the file can live
alongside other config.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_DEFAULT_COLUMNS: dict[str, str] = {
    "feature": "Feature/Epic",
    "title": "Test Scenario",
    "persona": "User Persona",
    "jira": "Functional Jira Story",
    "steps": "Verify",
}

# "typescript" is the smart-tests emitter (flow + test). "feature" (Gherkin) and
# "python" (pytest-bdd) remain available for teams that want them.
_DEFAULT_LANGUAGES = ("typescript",)
_DEFAULT_BACKEND_MARKERS = ("[Backend]", "[backend]", "backend")
_VALID_LANGUAGES = {"typescript", "feature", "python"}
_VALID_WAIT_STRATEGIES = {"auto", "explicit", "none"}


@dataclass
class InputProfile:
    sheet: str | None = None
    header_row: int = 1
    columns: dict[str, str] = field(default_factory=lambda: dict(_DEFAULT_COLUMNS))
    backend_markers: tuple[str, ...] = _DEFAULT_BACKEND_MARKERS


@dataclass
class OutputProfile:
    languages: tuple[str, ...] = _DEFAULT_LANGUAGES
    dir: str = "smart-tests"
    bubblegum_import: str = "from bubblegum import act, verify, extract"
    ts_client_import: str = "@bubblegum-ai/node"
    # Import paths from a generated flow/test file to the shared harness.
    ts_helpers_dir: str = "../helpers"
    ts_flows_dir: str = "../flows"
    # "workbook" → one flow + one test per Excel file, with one test method per
    # scenario row (the team's requested default). "feature" → one pair per
    # Feature/Epic value within the workbook.
    group_by: str = "workbook"


@dataclass
class AIProfile:
    enabled: bool = False
    provider: str | None = None
    model: str | None = None


@dataclass
class ConvertProfile:
    """Loaded conversion conventions. Construct with ``ConvertProfile.load()``."""

    input: InputProfile = field(default_factory=InputProfile)
    output: OutputProfile = field(default_factory=OutputProfile)
    ai: AIProfile = field(default_factory=AIProfile)
    wait_strategy: str = "auto"
    glossary: dict[str, str] = field(default_factory=dict)
    data_bindings: dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path | None = None) -> "ConvertProfile":
        """Load a profile from YAML.

        Search order: explicit ``path`` → ``BUBBLEGUM_CONVERT_CONFIG`` env var →
        ``./bubblegum.convert.yaml``. Missing file → all defaults (zero-config).
        """
        resolved: Path | None = None
        if path is not None:
            resolved = Path(path)
        elif env := os.environ.get("BUBBLEGUM_CONVERT_CONFIG"):
            resolved = Path(env)
        elif Path("bubblegum.convert.yaml").exists():
            resolved = Path("bubblegum.convert.yaml")

        if resolved is None or not resolved.exists():
            return cls()

        raw = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict) -> "ConvertProfile":
        """Build a profile from an already-parsed mapping."""
        conv = (raw or {}).get("convert", raw) or {}

        inp = conv.get("input", {}) or {}
        columns = dict(_DEFAULT_COLUMNS)
        columns.update(inp.get("columns", {}) or {})
        markers = inp.get("backend_markers")
        input_profile = InputProfile(
            sheet=inp.get("sheet"),
            header_row=int(inp.get("header_row", 1) or 1),
            columns=columns,
            backend_markers=tuple(markers) if markers else _DEFAULT_BACKEND_MARKERS,
        )

        out = conv.get("output", {}) or {}
        langs = out.get("languages") or list(_DEFAULT_LANGUAGES)
        langs = [str(x).strip().lower() for x in langs if str(x).strip().lower() in _VALID_LANGUAGES]
        py = out.get("python", {}) or {}
        ts = out.get("typescript", {}) or {}
        output_profile = OutputProfile(
            languages=tuple(langs) if langs else _DEFAULT_LANGUAGES,
            dir=str(out.get("dir", "smart-tests")),
            bubblegum_import=str(
                py.get("bubblegum_import", "from bubblegum import act, verify, extract")
            ),
            ts_client_import=str(ts.get("client_import", "@bubblegum-ai/node")),
            ts_helpers_dir=str(ts.get("helpers_dir", "../helpers")),
            ts_flows_dir=str(ts.get("flows_dir", "../flows")),
            group_by=(
                "feature"
                if str(out.get("group_by", "workbook")).strip().lower() == "feature"
                else "workbook"
            ),
        )

        ai = conv.get("ai", {}) or {}
        ai_profile = AIProfile(
            enabled=bool(ai.get("enabled", False)),
            provider=ai.get("provider"),
            model=ai.get("model"),
        )

        waits = conv.get("waits", {}) or {}
        strategy = str(waits.get("strategy", "auto")).strip().lower()
        if strategy not in _VALID_WAIT_STRATEGIES:
            strategy = "auto"

        return cls(
            input=input_profile,
            output=output_profile,
            ai=ai_profile,
            wait_strategy=strategy,
            glossary={str(k): str(v) for k, v in (conv.get("glossary", {}) or {}).items()},
            data_bindings={str(k): str(v) for k, v in (conv.get("data", {}) or {}).items()},
        )
