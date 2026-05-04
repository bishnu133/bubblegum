from __future__ import annotations

from pathlib import Path

import yaml
import argparse

from bubblegum.core.schemas import StepResult

class _OptionGroup:
    def __init__(self, parser: argparse.ArgumentParser):
        self._parser = parser

    def addoption(self, *args, **kwargs):
        self._parser.add_argument(*args, **kwargs)


class _PublicParserAdapter:
    def __init__(self):
        self._parser = argparse.ArgumentParser(add_help=False)

    def getgroup(self, _name: str):
        return _OptionGroup(self._parser)

    def parse(self, args: list[str]):
        return self._parser.parse_args(args)


def _step_result(action: str = "Click Login", status: str = "passed") -> StepResult:
    return StepResult(status=status, action=action)


def test_plugin_module_importable():
    import bubblegum.pytest_plugin as plugin

    assert plugin is not None


def test_cli_options_registered():
    from bubblegum import pytest_plugin as plugin

    parser = _PublicParserAdapter()
    plugin.pytest_addoption(parser)
    opts = parser.parse(["--bubblegum-artifacts", "out", "--bubblegum-ai"])

    assert opts.bubblegum_config is None
    assert opts.bubblegum_report is None
    assert opts.bubblegum_artifacts == "out"
    assert opts.bubblegum_ai is True
    assert opts.bubblegum_memory is False
    assert opts.bubblegum_benchmark is False


class _Cfg:
    def __init__(self, options: dict[str, object]):
        self._opts = options

    def getoption(self, name: str):
        return self._opts.get(name)


def test_bubblegum_config_default_and_engine_fixture(monkeypatch):
    from bubblegum import pytest_plugin as plugin

    cfg = _Cfg({"--bubblegum-config": None})
    loaded = plugin.bubblegum_config.__wrapped__(cfg)
    engine_handle = plugin.bubblegum_engine.__wrapped__(loaded)

    assert loaded is not None
    assert engine_handle is not None
    assert engine_handle.config is loaded
    assert engine_handle.engine is not None


def test_bubblegum_config_explicit_path(tmp_path):
    from bubblegum import pytest_plugin as plugin

    cfg_data = {
        "grounding": {"memory_ttl_days": 13, "memory_max_failures": 5},
        "ai": {"enabled": False},
    }
    cfg_file = tmp_path / "custom_bubblegum.yaml"
    cfg_file.write_text(yaml.safe_dump(cfg_data), encoding="utf-8")

    cfg = _Cfg({"--bubblegum-config": str(cfg_file)})
    loaded = plugin.bubblegum_config.__wrapped__(cfg)

    assert loaded.grounding.memory_ttl_days == 13
    assert loaded.grounding.memory_max_failures == 5
    assert loaded.ai.enabled is False


def test_bubblegum_artifacts_dir_fixture(tmp_path):
    from bubblegum import pytest_plugin as plugin

    outdir = tmp_path / "tmp_artifacts"
    cfg = _Cfg({"--bubblegum-artifacts": str(outdir)})

    result = plugin.bubblegum_artifacts_dir.__wrapped__(cfg)

    assert result == outdir
    assert outdir.exists()
    assert outdir.is_dir()


def test_bubblegum_reporter_fixture_exists():
    from bubblegum import pytest_plugin as plugin

    cfg = _Cfg({})
    reporter = plugin.bubblegum_reporter.__wrapped__(cfg)

    assert reporter is not None
    assert hasattr(reporter, "results")
    assert reporter.results == []


def test_no_report_emitted_without_flag(tmp_path):
    from bubblegum import pytest_plugin as plugin

    class _Session:
        def __init__(self):
            self.config = _Cfg({"--bubblegum-report": None})

    session = _Session()
    plugin.pytest_sessionfinish(session, 0)

    report_file = tmp_path / "bubblegum_report.html"
    assert not report_file.exists()


def test_bubblegum_reporter_accepts_stepresult_append():
    from bubblegum import pytest_plugin as plugin

    cfg = _Cfg({})
    reporter = plugin.bubblegum_reporter.__wrapped__(cfg)

    step = _step_result(action="Submit form", status="passed")
    reporter.add(step)

    assert len(reporter.results) == 1
    assert reporter.results[0] == step


def test_report_emitted_with_flag_and_results(tmp_path):
    from bubblegum import pytest_plugin as plugin

    report_path = tmp_path / "bubblegum_report.html"
    cfg = _Cfg({"--bubblegum-report": str(report_path)})
    reporter = plugin.bubblegum_reporter.__wrapped__(cfg)
    reporter.add(_step_result(action="Click Login", status="passed"))

    class _Session:
        def __init__(self, config):
            self.config = config

    session = _Session(cfg)
    plugin.pytest_sessionfinish(session, 0)

    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "Click Login" in content
    assert "PASSED" in content


def test_report_emitted_with_flag_and_no_results(tmp_path):
    from bubblegum import pytest_plugin as plugin

    report_path = tmp_path / "bubblegum_report.html"
    cfg = _Cfg({"--bubblegum-report": str(report_path)})
    plugin.bubblegum_reporter.__wrapped__(cfg)

    class _Session:
        def __init__(self, config):
            self.config = config

    session = _Session(cfg)
    plugin.pytest_sessionfinish(session, 0)

    assert report_path.exists()
    assert "No steps recorded" in report_path.read_text(encoding="utf-8")


class _Session:
    def __init__(self, config, exitstatus: int = 0):
        self.config = config
        self.exitstatus = exitstatus


def test_benchmark_not_run_without_flag(monkeypatch):
    from bubblegum import pytest_plugin as plugin

    called = {"count": 0}

    def _fake_run() -> int:
        called["count"] += 1
        return 0

    monkeypatch.setattr("scripts.run_benchmarks.run_benchmark_validation", _fake_run)

    cfg = _Cfg({"--bubblegum-report": None, "--bubblegum-benchmark": False})
    session = _Session(cfg, exitstatus=0)
    plugin.pytest_sessionfinish(session, 0)

    assert called["count"] == 0


def test_benchmark_run_with_flag_success(monkeypatch):
    from bubblegum import pytest_plugin as plugin

    called = {"count": 0}

    def _fake_run() -> int:
        called["count"] += 1
        return 0

    monkeypatch.setattr("scripts.run_benchmarks.run_benchmark_validation", _fake_run)

    cfg = _Cfg({"--bubblegum-report": None, "--bubblegum-benchmark": True})
    session = _Session(cfg, exitstatus=0)
    plugin.pytest_sessionfinish(session, 0)

    assert called["count"] == 1
    assert session.exitstatus == 0


def test_benchmark_run_with_flag_failure_sets_exitstatus(monkeypatch):
    from bubblegum import pytest_plugin as plugin

    def _fake_run() -> int:
        return 1

    monkeypatch.setattr("scripts.run_benchmarks.run_benchmark_validation", _fake_run)

    cfg = _Cfg({"--bubblegum-report": None, "--bubblegum-benchmark": True})
    session = _Session(cfg, exitstatus=0)
    plugin.pytest_sessionfinish(session, 0)

    assert session.exitstatus == 1

    already_failed = _Session(cfg, exitstatus=2)
    plugin.pytest_sessionfinish(already_failed, 2)
    assert already_failed.exitstatus == 2


def test_benchmark_and_report_can_coexist(tmp_path, monkeypatch):
    from bubblegum import pytest_plugin as plugin

    called = {"count": 0}

    def _fake_run() -> int:
        called["count"] += 1
        return 0

    monkeypatch.setattr("scripts.run_benchmarks.run_benchmark_validation", _fake_run)

    report_path = tmp_path / "bubblegum_report.html"
    cfg = _Cfg({"--bubblegum-report": str(report_path), "--bubblegum-benchmark": True})
    reporter = plugin.bubblegum_reporter.__wrapped__(cfg)
    reporter.add(_step_result(action="Click Login", status="passed"))

    session = _Session(cfg, exitstatus=0)
    plugin.pytest_sessionfinish(session, 0)

    assert called["count"] == 1
    assert report_path.exists()
    assert "Click Login" in report_path.read_text(encoding="utf-8")
