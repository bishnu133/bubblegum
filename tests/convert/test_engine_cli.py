"""End-to-end tests: ingest workbook → emit files, plus the CLI dispatcher."""

from __future__ import annotations

from pathlib import Path

import pytest

from bubblegum.convert.engine import convert_workbook
from bubblegum.convert.ingest import read_workbook
from bubblegum.convert.profile import ConvertProfile

FIXTURE = Path(__file__).parent / "fixtures" / "sample_scenarios.xlsx"

pytest.importorskip("openpyxl")


def test_read_workbook_maps_columns_and_skips_blank_rows():
    scenarios = read_workbook(FIXTURE, ConvertProfile())
    # 4 data rows; the spacer row with an empty Verify cell is skipped
    assert len(scenarios) == 4
    first = scenarios[0]
    assert first.feature == "[F][Web] Checkout coupon"
    assert first.persona == "Shopper"
    assert first.jira == "PROJ-101"
    assert "Coupon code" in first.steps_text


def test_default_workbook_grouping_one_file_per_workbook(tmp_path):
    # Default: one flow + one test per workbook, named from the workbook stem
    # ("sample_scenarios"), with every scenario as a test method inside it.
    result = convert_workbook(FIXTURE, out_dir=tmp_path)
    stats = result.stats()
    assert stats["scenarios"] == 4

    assert (tmp_path / "flows" / "sample_scenarios.flow.ts").exists()
    test_file = tmp_path / "tests" / "sample_scenarios.test.mts"
    assert test_file.exists()
    # exactly one .test.mts for the whole workbook
    assert len(list((tmp_path / "tests").glob("*.test.mts"))) == 1
    # all 4 scenarios present as test-method registry entries
    body = test_file.read_text()
    assert body.count("], ") + body.count("],\n") >= 4 or body.count("[") >= 4
    assert (tmp_path / "CONVERT_REPORT.md").exists()


def test_name_override_sets_output_basename(tmp_path):
    convert_workbook(FIXTURE, out_dir=tmp_path, name="challenge-creation")
    assert (tmp_path / "flows" / "challenge_creation.flow.ts").exists()
    assert (tmp_path / "tests" / "challenge_creation.test.mts").exists()


def test_feature_grouping_one_file_per_feature(tmp_path):
    from dataclasses import replace

    profile = ConvertProfile()
    profile.output = replace(profile.output, group_by="feature")
    convert_workbook(FIXTURE, out_dir=tmp_path, profile=profile)
    # 3 features → 3 test files
    assert len(list((tmp_path / "tests").glob("*.test.mts"))) == 3
    assert (tmp_path / "tests" / "login_web.test.mts").exists()


def test_init_scaffolds_shared_harness(tmp_path):
    convert_workbook(FIXTURE, out_dir=tmp_path, init=True)
    assert (tmp_path / "helpers" / "engine.ts").exists()
    assert (tmp_path / "helpers" / "actions.ts").exists()
    assert (tmp_path / "helpers" / "reporter.ts").exists()
    assert (tmp_path / "flows" / "login.flow.ts").exists()


def test_no_overwrite_preserves_existing_generated_files(tmp_path):
    convert_workbook(FIXTURE, out_dir=tmp_path)
    flow = tmp_path / "flows" / "sample_scenarios.flow.ts"
    flow.write_text("// hand-edited\n")
    result = convert_workbook(FIXTURE, out_dir=tmp_path, overwrite=False)
    assert flow.read_text() == "// hand-edited\n"  # preserved
    assert any("no-overwrite" in w for w in result.warnings)


def test_convert_respects_language_subset(tmp_path):
    from dataclasses import replace

    profile = ConvertProfile()
    profile.output = replace(profile.output, languages=("feature",))
    result = convert_workbook(FIXTURE, out_dir=tmp_path, profile=profile)
    assert (tmp_path / "features").exists()
    assert not (tmp_path / "tests").exists()
    assert not (tmp_path / "flows").exists()
    assert result.stats()["features"] == 3


def test_dry_run_builds_ir_without_writing(tmp_path):
    result = convert_workbook(FIXTURE, out_dir=tmp_path, write=False)
    assert result.stats()["scenarios"] == 4
    # nothing on disk
    assert not any(tmp_path.iterdir())


def test_missing_steps_column_raises(tmp_path):
    profile = ConvertProfile()
    profile.input.columns = dict(profile.input.columns)
    profile.input.columns["steps"] = "NoSuchColumn"
    with pytest.raises(ValueError, match="Steps column"):
        read_workbook(FIXTURE, profile)


def test_cli_convert_runs(tmp_path, capsys):
    from bubblegum.cli import main

    code = main(["convert", str(FIXTURE), "-o", str(tmp_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Converted 4 scenarios" in out
    assert (tmp_path / "tests" / "sample_scenarios.test.mts").exists()


def test_cli_missing_workbook_returns_error():
    from bubblegum.cli import main

    code = main(["convert", "does_not_exist.xlsx", "-o", "x"])
    assert code == 2


def _multi_sheet_wb(tmp_path):
    import openpyxl

    wb = openpyxl.Workbook()
    h = ["#", "Feature/Epic", "Test Scenario", "User Persona",
         "Functional Jira Story", "Verify", "Result", "Remarks"]
    a = wb.active
    a.title = "UAT Scenario"
    a.append(h)
    a.append([1, "[F][Web] Login", "Valid login", "User", "J-1",
              "Given I open the Login page\nThen I see the Dashboard", "", ""])
    b = wb.create_sheet("Regression")
    b.append(h)
    b.append([1, "[F][Web] Search", "Search works", "User", "J-9",
              "Given I open the Search page\nThen I see the Results", "", ""])
    p = tmp_path / "Book.xlsx"
    wb.save(p)
    return p


def test_multi_sheet_emits_one_file_per_sheet(tmp_path):
    wb = _multi_sheet_wb(tmp_path)
    out = tmp_path / "gen"
    convert_workbook(wb, out_dir=out)
    tests = {p.name for p in (out / "tests").glob("*.test.mts")}
    assert tests == {"uat_scenario.test.mts", "regression.test.mts"}


def test_sheet_selection_restricts_to_one(tmp_path):
    from dataclasses import replace

    wb = _multi_sheet_wb(tmp_path)
    out = tmp_path / "gen"
    profile = ConvertProfile()
    profile.input = replace(profile.input, sheets=("Regression",))
    convert_workbook(wb, out_dir=out, profile=profile)
    tests = {p.name for p in (out / "tests").glob("*.test.mts")}
    # single sheet → named from the workbook stem, not the sheet
    assert tests == {"book.test.mts"}


def test_feature_filter_limits_output(tmp_path):
    out = tmp_path / "gen"
    result = convert_workbook(FIXTURE, out_dir=out, feature_filter=["Login"])
    assert result.stats()["features"] == 1
    assert (out / "tests").exists()


def test_validate_workbook_reports_issues():
    from bubblegum.convert.engine import validate_workbook

    issues = validate_workbook(FIXTURE)
    # the [Backend] feature + login preconditions produce TODO + persona notes
    assert any(i.startswith("[todo]") for i in issues)
