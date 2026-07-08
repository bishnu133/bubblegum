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


def test_convert_workbook_default_emits_smart_tests(tmp_path):
    # Default language is the smart-tests TypeScript pair (flow + test).
    result = convert_workbook(FIXTURE, out_dir=tmp_path)
    stats = result.stats()
    assert stats["features"] == 3
    assert stats["scenarios"] == 4
    assert stats["backend"] == 3  # the [Backend] feature's 3 steps

    assert (tmp_path / "flows" / "login_web.flow.ts").exists()
    assert (tmp_path / "tests" / "login_web.test.mts").exists()
    assert (tmp_path / "CONVERT_REPORT.md").exists()


def test_init_scaffolds_shared_harness(tmp_path):
    convert_workbook(FIXTURE, out_dir=tmp_path, init=True)
    assert (tmp_path / "helpers" / "engine.ts").exists()
    assert (tmp_path / "helpers" / "actions.ts").exists()
    assert (tmp_path / "helpers" / "reporter.ts").exists()
    # scaffolded login.flow.ts (exports loginFlow) coexists with the generated
    # feature flow for the "Login" feature (disambiguated slug), no clobber
    assert (tmp_path / "flows" / "login.flow.ts").exists()
    assert (tmp_path / "flows" / "login_web.flow.ts").exists()


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
    assert (tmp_path / "tests" / "login_web.test.mts").exists()


def test_cli_missing_workbook_returns_error():
    from bubblegum.cli import main

    code = main(["convert", "does_not_exist.xlsx", "-o", "x"])
    assert code == 2
