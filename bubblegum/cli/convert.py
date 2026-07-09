"""
bubblegum/cli/convert.py
========================
``bubblegum convert`` — turn a spreadsheet of manual test scenarios into
smart-tests TypeScript (default) or optional .feature / pytest-bdd scaffolds.
"""

from __future__ import annotations

import json
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
    feature: str | None = None,
    sheet: str | None = None,
    no_data_file: bool = False,
    validate_only: bool = False,
    update_package_json: bool = False,
) -> int:
    """Execute a conversion run and print a summary. Returns an exit code."""
    from bubblegum.convert.engine import convert_workbook, validate_workbook
    from bubblegum.convert.profile import ConvertProfile

    if not Path(workbook).exists():
        print(f"error: workbook not found: {workbook}")
        return 2

    profile = ConvertProfile.load(config)
    out_overrides = {}
    if languages:
        out_overrides["languages"] = tuple(
            x.strip().lower() for x in languages.split(",") if x.strip()
        )
    if group_by:
        out_overrides["group_by"] = group_by
    if no_data_file:
        out_overrides["extract_data"] = False
    if out_overrides:
        profile.output = replace(profile.output, **out_overrides)
    if sheet:
        sheets = tuple(s.strip() for s in sheet.split(",") if s.strip())
        profile.input = replace(profile.input, sheets=sheets, sheet=None)
    if ai:
        profile.ai.enabled = True

    feature_filter = (
        [t.strip() for t in feature.split(",") if t.strip()] if feature else None
    )

    try:
        if validate_only:
            issues = validate_workbook(workbook, profile, feature_filter=feature_filter)
            if not issues:
                print("Validation OK — no issues found.")
            else:
                print(f"Validation found {len(issues)} issue(s):")
                for issue in issues:
                    print(f"  - {issue}")
            return 0

        result = convert_workbook(
            workbook,
            out_dir=out,
            profile=profile,
            init=init,
            name=name,
            overwrite=not no_overwrite,
            feature_filter=feature_filter,
        )
    except ImportError as exc:
        print(f"error: {exc}")
        return 3
    except ValueError as exc:
        print(f"error: {exc}")
        return 4

    stats = result.stats()
    out_dir = out or profile.output.dir
    print(f"Converted {stats['scenarios']} scenarios across {stats['features']} features.")
    print(
        f"  steps: {stats['steps']}  |  "
        f"AUTO {stats['auto']}  NEEDS_DATA {stats['needs_data']}  "
        f"BACKEND {stats['backend']}  MANUAL {stats['manual']}"
    )
    print(f"Wrote {len(result.files_written)} files to {out_dir}/")
    for warning in result.warnings:
        print(f"  note: {warning}")

    _npm_scripts(result, out_dir, update_package_json)
    return 0


def _npm_scripts(result, out_dir: str, do_update: bool) -> None:
    """Print (and optionally merge into package.json) test:smart:<name> scripts."""
    tests = [p for p in result.files_written if p.endswith(".test.mts")]
    if not tests:
        return
    scripts = {}
    for path in tests:
        stem = Path(path).name[: -len(".test.mts")]
        scripts[f"test:smart:{stem}"] = f"npx tsx {path}"

    if do_update:
        pkg = Path("package.json")
        if not pkg.exists():
            print("  note: --update-package-json given but ./package.json not found; printing instead.")
        else:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            data.setdefault("scripts", {}).update(scripts)
            pkg.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            print(f"  updated package.json with {len(scripts)} test:smart:* script(s).")
            return

    print("[info] Add these to your package.json scripts:")
    for name, cmd in scripts.items():
        print(f'  "{name}": "{cmd}"')
