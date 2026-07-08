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
) -> ConvertResult:
    """Convert a spreadsheet of manual scenarios into automation scaffolds.

    Args:
        path:    the .xlsx workbook.
        out_dir: output directory (defaults to the profile's output.dir).
        profile: a ConvertProfile; loaded from bubblegum.convert.yaml if None.
        write:   when False, build the IR + files-in-memory but write nothing
                 (used by tests / dry-run).
        init:    when True, also scaffold the shared TypeScript harness
                 (helpers/ + flows/login.flow.ts + .env example) if absent.
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

    result = ConvertResult(features=features)
    langs = profile.output.languages

    if init and write and "typescript" in langs:
        from bubblegum.convert.scaffold import scaffold_harness

        result.files_written.extend(scaffold_harness(out_root))

    for feature in features:
        if "typescript" in langs:
            _emit_typescript(feature, out_root, profile, result, write)

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


def _emit_typescript(feature, out_root: Path, profile, result: ConvertResult, write: bool) -> None:
    """Emit the smart-tests <feature>.flow.ts + <feature>.test.mts pair."""
    from bubblegum.convert.emitters.ts_smart import (
        _fn_name,
        emit_flow_file,
        emit_test_file,
    )

    used: set[str] = set()
    fn_names = [_fn_name(s.title, used) for s in feature.scenarios]

    flow_path = out_root / "flows" / f"{feature.slug}.flow.ts"
    test_path = out_root / "tests" / f"{feature.slug}.test.mts"
    result.files_written.append(str(flow_path))
    result.files_written.append(str(test_path))
    if write:
        _write(flow_path, emit_flow_file(feature, fn_names, profile))
        _write(test_path, emit_test_file(feature, fn_names, profile))


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
