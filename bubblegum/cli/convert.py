"""
bubblegum/cli/convert.py
========================
``bubblegum convert`` — turn a spreadsheet of manual test scenarios into
automation scaffolds (.feature + pytest-bdd + playwright-bdd).
"""

from __future__ import annotations

from pathlib import Path


def run_convert(
    workbook: str,
    out: str | None,
    config: str | None,
    languages: str | None,
    ai: bool,
) -> int:
    """Execute a conversion run and print a summary. Returns an exit code."""
    from bubblegum.convert.engine import convert_workbook
    from bubblegum.convert.profile import ConvertProfile

    if not Path(workbook).exists():
        print(f"error: workbook not found: {workbook}")
        return 2

    profile = ConvertProfile.load(config)
    if languages:
        langs = tuple(x.strip().lower() for x in languages.split(",") if x.strip())
        from dataclasses import replace

        profile.output = replace(profile.output, languages=langs)
    if ai:
        profile.ai.enabled = True

    try:
        result = convert_workbook(workbook, out_dir=out, profile=profile)
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
    return 0
