from __future__ import annotations

from pathlib import Path

import yaml
from _pytest.config.argparsing import Parser


def test_plugin_module_importable():
    import bubblegum.pytest_plugin as plugin

    assert plugin is not None


def test_cli_options_registered():
    from bubblegum import pytest_plugin as plugin

    parser = Parser()
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
