"""
bubblegum/convert/engine.py
===========================
Orchestrator: workbook → RawScenarios → Feature IR → emitted files.

    convert_workbook("scenarios.xlsx", out_dir="smart-tests")

Everything is derived from the workbook — file names come from each row's
Feature/Epic value, nothing is project-specific. Default (smart-tests) layout::

    smart-tests/
      helpers/    engine.ts, actions.ts, reporter.ts   (only with init=True)
      flows/      <feature-slug>.flow.ts               (one fn per scenario)
      tests/      <feature-slug>.test.mts              (composes the flows)

Optional languages ("feature", "python") add::

    smart-tests/features/<feature-slug>.feature
    smart-tests/python/test_<feature-slug>.py
"""

from __future__ import annotations

from pathlib import Path

from bubblegum.convert.emitters import emit_feature_file, emit_python_steps
from bubblegum.convert.ingest import read_workbook
from bubblegum.convert.models import ConvertResult
from bubblegum.convert.normalize import build_features
from bubblegum.convert.profile import ConvertProfile


def convert_workbook(
    path: str | Path,
    out_dir: str | Path | None = None,
    profile: ConvertProfile | None = None,
    write: bool = True,
    init: bool = False,
    name: str | None = None,
    overwrite: bool = True,
    feature_filter: list[str] | None = None,
) -> ConvertResult:
    """Convert a spreadsheet of manual scenarios into automation scaffolds.

    Args:
        path:           the .xlsx workbook.
        out_dir:        output directory (defaults to the profile's output.dir).
        profile:        a ConvertProfile; loaded from bubblegum.convert.yaml if None.
        write:          when False, build the IR + files but write nothing.
        init:           also scaffold the shared TypeScript harness if absent.
        name:           base name for the generated test/flow (workbook grouping).
        overwrite:      when False, keep existing generated flow/test files.
        feature_filter: keep only features whose name contains one of these
                        (case-insensitive substring) terms.
    """
    profile = profile or ConvertProfile.load()
    out_root = Path(out_dir) if out_dir is not None else Path(profile.output.dir)

    # AI fallback is opt-in; build_ai_hook returns None when disabled.
    ai_hook = None
    if profile.ai.enabled:
        from bubblegum.convert.ai import build_ai_hook

        ai_hook = build_ai_hook(profile)

    raw = read_workbook(path, profile)
    features = build_features(raw, profile, ai_hook=ai_hook)
    features = _apply_feature_filter(features, feature_filter)

    result = ConvertResult(features=features)
    langs = profile.output.languages

    if init and write and "typescript" in langs:
        from bubblegum.convert.scaffold import scaffold_harness

        result.files_written.extend(scaffold_harness(out_root))

    if "typescript" in langs:
        if profile.output.group_by == "workbook":
            # One flow + one test per workbook — but split by sheet so a
            # multi-sheet workbook yields one file per sheet.
            for bundle in _workbook_bundles(path, name, features):
                _emit_typescript(bundle, out_root, profile, result, write, overwrite)
        else:
            for feature in features:
                _emit_typescript(feature, out_root, profile, result, write, overwrite)

    for feature in features:
        if "feature" in langs:
            content = emit_feature_file(feature)
            result.files_written.append(str(out_root / "features" / f"{feature.slug}.feature"))
            if write:
                _write(out_root / "features" / f"{feature.slug}.feature", content)

        if "python" in langs:
            rel = f"../features/{feature.slug}.feature" if "feature" in langs else f"{feature.slug}.feature"
            content = emit_python_steps(feature, rel, profile)
            result.files_written.append(str(out_root / "python" / f"test_{feature.slug}.py"))
            if write:
                _write(out_root / "python" / f"test_{feature.slug}.py", content)

    if write:
        _write(out_root / "CONVERT_REPORT.md", _report(result))
        result.files_written.append(str(out_root / "CONVERT_REPORT.md"))

    return result


def validate_workbook(
    path: str | Path,
    profile: ConvertProfile | None = None,
    feature_filter: list[str] | None = None,
) -> list[str]:
    """Parse the workbook + config and report issues WITHOUT generating files.

    Flags: unmapped login personas, navigation pages not configured, steps that
    will become TODOs, and malformed template expressions.
    """
    from bubblegum.convert.emitters.ts_smart import _is_login_step, _nav_page_name
    from bubblegum.convert.models import StepKind

    profile = profile or ConvertProfile.load()
    raw = read_workbook(path, profile)
    features = _apply_feature_filter(build_features(raw, profile), feature_filter)

    issues: list[str] = []
    personas_seen: set[str] = set()
    nav_missing: set[str] = set()
    todo = 0

    for feature in features:
        for scenario in feature.scenarios:
            for step in scenario.steps:
                if _is_login_step(step) and scenario.persona:
                    personas_seen.add(scenario.persona)
                if step.kind is StepKind.AUTO:
                    page = _nav_page_name(step.instruction)
                    if page and profile.project.navigation and not _nav_present(page, profile):
                        nav_missing.add(page)
                elif step.kind in (StepKind.NEEDS_DATA, StepKind.MANUAL, StepKind.BACKEND):
                    todo += 1
                if step.text.count("{{") != step.text.count("}}"):
                    issues.append(f"[template] unbalanced {{{{ }}}} in step: {step.text!r}")

    for persona in sorted(personas_seen):
        if not profile.project.persona_credentials(persona):
            issues.append(
                f"[persona] '{persona}' has no credential mapping "
                "(add it under convert.personas or set convert.imports.credentials)."
            )
    for page in sorted(nav_missing):
        issues.append(
            f"[navigation] page '{page}' is not in convert.navigation "
            "(will emit a generic act call)."
        )
    if todo:
        issues.append(f"[todo] {todo} step(s) will be emitted as TODO (needs_data/manual/backend).")
    return issues


def _nav_present(page: str, profile: ConvertProfile) -> bool:
    key = page.casefold()
    return any(name.casefold() == key for name in profile.project.navigation)


def _apply_feature_filter(features, terms: list[str] | None):
    """Keep only features whose name contains one of ``terms`` (case-insensitive)."""
    if not terms:
        return features
    wanted = [t.strip().casefold() for t in terms if t.strip()]
    return [f for f in features if any(t in f.name.casefold() for t in wanted)]


def _workbook_bundles(path, name: str | None, features):
    """One synthetic Feature per sheet (every scenario becomes a test method).

    A single-sheet workbook yields one bundle named from ``name`` or the file
    stem; a multi-sheet workbook yields one bundle per sheet, named from the
    sheet so files don't collide.
    """
    from bubblegum.convert.models import Feature
    from bubblegum.convert.normalize import _slugify

    scenarios = [s for f in features for s in f.scenarios]
    if not scenarios:
        return []
    tags = sorted({t for f in features for t in f.tags})

    # Preserve first-seen sheet order.
    sheets: list[str] = []
    for s in scenarios:
        if s.sheet not in sheets:
            sheets.append(s.sheet)
    multi = len([x for x in sheets if x]) > 1

    stem = Path(path).stem
    base_slug = _slugify(name) if name else _slugify(stem)
    base_display = name or stem

    bundles = []
    if not multi:
        bundles.append(
            Feature(name=base_display, slug=base_slug or "workbook", scenarios=scenarios, tags=tags)
        )
        return bundles

    for sheet in sheets:
        sheet_scenarios = [s for s in scenarios if s.sheet == sheet]
        slug = _slugify(sheet) or "sheet"
        bundles.append(
            Feature(name=sheet or base_display, slug=slug, scenarios=sheet_scenarios, tags=tags)
        )
    return bundles


def _emit_typescript(feature, out_root: Path, profile, result: ConvertResult, write: bool, overwrite: bool = True) -> None:
    """Emit the smart-tests <name>.flow.ts + <name>.test.mts (+ .data.ts) group."""
    from bubblegum.convert.emitters.ts_smart import (
        _fn_name,
        emit_data_file,
        emit_flow_file,
        emit_test_file,
    )

    used: set[str] = set()
    fn_names = [_fn_name(s.title, used) for s in feature.scenarios]

    targets = [
        (out_root / "flows" / f"{feature.slug}.flow.ts", emit_flow_file(feature, fn_names, profile)),
        (out_root / "tests" / f"{feature.slug}.test.mts", emit_test_file(feature, fn_names, profile)),
    ]
    data_content = emit_data_file(feature, fn_names, profile)
    if data_content is not None:
        targets.append((out_root / "data" / f"{feature.slug}.data.ts", data_content))

    for target, _ in targets:
        result.files_written.append(str(target))
    if not write:
        return
    for target, content in targets:
        if target.exists() and not overwrite:
            result.warnings.append(f"skipped existing (no-overwrite): {target}")
            continue
        _write(target, content)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _report(result: ConvertResult) -> str:
    stats = result.stats()
    lines = [
        "# Conversion report",
        "",
        f"- Features: **{stats['features']}**",
        f"- Scenarios: **{stats['scenarios']}**",
        f"- Steps: **{stats['steps']}**",
        "",
        "## Step classification",
        "",
        f"- ✅ AUTO (ready): **{stats['auto']}**",
        f"- ⚠️ NEEDS_DATA (wire test data / fixture): **{stats['needs_data']}**",
        f"- 🔧 BACKEND (non-UI): **{stats['backend']}**",
        f"- ✋ MANUAL (author by hand): **{stats['manual']}**",
        "",
        "Review the `# ^ ...` annotations in the .feature files and the "
        "`pytest.skip` / `TODO` markers in the step definitions before running.",
        "",
    ]
    return "\n".join(lines)
