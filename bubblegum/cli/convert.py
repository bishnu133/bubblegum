"""
bubblegum/cli/convert.py
========================
``bubblegum convert`` — turn a spreadsheet of manual test scenarios into
smart-tests TypeScript (default) or optional .feature / pytest-bdd scaffolds.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path


def run_convert(
    workbook: str,
    out: str | None,
    config: str | None,
    languages: str | None,
    ai: bool,
    init: bool = False,
    name: str | None = None,
    no_overwrite: bool = False,
    group_by: str | None = None,
) -> int:
    """Execute a conversion run and print a summary. Returns an exit code."""
    from bubblegum.convert.engine import convert_workbook
    from bubblegum.convert.profile import ConvertProfile

    if not Path(workbook).exists():
        print(f"error: workbook not found: {workbook}")
        return 2

    profile = ConvertProfile.load(config)
    overrides = {}
    if languages:
        overrides["languages"] = tuple(
            x.strip().lower() for x in languages.split(",") if x.strip()
        )
    if group_by:
        overrides["group_by"] = group_by
    if overrides:
        profile.output = replace(profile.output, **overrides)
    if ai:
        profile.ai.enabled = True

    try:
        result = convert_workbook(
            workbook,
            out_dir=out,
            profile=profile,
            init=init,
            name=name,
            overwrite=not no_overwrite,
        )
    except ImportError as exc:
        print(f"error: {exc}")
        return 3
    except ValueError as exc:
        print(f"error: {exc}")
        return 4

    stats = result.stats()
    print(f"Converted {stats['scenarios']} scenarios across {stats['features']} features.")
    print(
        f"  steps: {stats['steps']}  |  "
        f"AUTO {stats['auto']}  NEEDS_DATA {stats['needs_data']}  "
        f"BACKEND {stats['backend']}  MANUAL {stats['manual']}"
    )
    print(f"Wrote {len(result.files_written)} files to {out or profile.output.dir}/")
    for warning in result.warnings:
        print(f"  note: {warning}")
    return 0
