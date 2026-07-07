"""
bubblegum/convert/engine.py
===========================
Orchestrator: workbook → RawScenarios → Feature IR → emitted files.

    convert_workbook("scenarios.xlsx", out_dir="generated")

Directory layout produced (languages configurable via the profile)::

    generated/
      features/     badge_album_grouping.feature
      python/       test_badge_album_grouping.py
      typescript/   badge_album_grouping.steps.ts
"""

from __future__ import annotations

from pathlib import Path

from bubblegum.convert.emitters import (
    emit_feature_file,
    emit_python_steps,
    emit_typescript_steps,
)
from bubblegum.convert.ingest import read_workbook
from bubblegum.convert.models import ConvertResult
from bubblegum.convert.normalize import build_features
from bubblegum.convert.profile import ConvertProfile


def convert_workbook(
    path: str | Path,
    out_dir: str | Path | None = None,
    profile: ConvertProfile | None = None,
    write: bool = True,
) -> ConvertResult:
    """Convert a spreadsheet of manual scenarios into automation scaffolds.

    Args:
        path:    the .xlsx workbook.
        out_dir: output directory (defaults to the profile's output.dir).
        profile: a ConvertProfile; loaded from bubblegum.convert.yaml if None.
        write:   when False, build the IR + files-in-memory but write nothing
                 (used by tests / dry-run).
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

    for feature in features:
        feature_filename = f"{feature.slug}.feature"

        if "feature" in langs:
            content = emit_feature_file(feature)
            result.files_written.append(str(out_root / "features" / feature_filename))
            if write:
                _write(out_root / "features" / feature_filename, content)

        if "python" in langs:
            # The step module references the .feature by relative path.
            rel = f"../features/{feature_filename}" if "feature" in langs else feature_filename
            content = emit_python_steps(feature, rel, profile)
            result.files_written.append(str(out_root / "python" / f"test_{feature.slug}.py"))
            if write:
                _write(out_root / "python" / f"test_{feature.slug}.py", content)

        if "typescript" in langs:
            content = emit_typescript_steps(feature, profile)
            result.files_written.append(str(out_root / "typescript" / f"{feature.slug}.steps.ts"))
            if write:
                _write(out_root / "typescript" / f"{feature.slug}.steps.ts", content)

    if write:
        _write(out_root / "CONVERT_REPORT.md", _report(result))
        result.files_written.append(str(out_root / "CONVERT_REPORT.md"))

    return result


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
