"""Pytest plugin skeleton for Bubblegum (Phase 4A)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from bubblegum.core.config import BubblegumConfig
from bubblegum.core.sdk import configure_runtime


@dataclass
class BubblegumReporter:
    """Minimal session container for future StepResult aggregation."""

    results: list[Any] = field(default_factory=list)


class BubblegumEngineHandle:
    """Safe wrapper that exposes engine/config from pytest runtime state."""

    def __init__(self, config: BubblegumConfig):
        self.config = config

    @property
    def engine(self):
        # Import lazily to avoid import-time side effects in plugin discovery.
        from bubblegum.core import sdk as sdk_module

        return getattr(sdk_module, "_engine", None)



def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("bubblegum")
    group.addoption(
        "--bubblegum-config",
        action="store",
        default=None,
        metavar="PATH",
        help="Path to bubblegum YAML config file.",
    )
    group.addoption(
        "--bubblegum-report",
        action="store",
        default=None,
        metavar="PATH",
        help="Write Bubblegum HTML report to this path at session end (optional).",
    )
    group.addoption(
        "--bubblegum-artifacts",
        action="store",
        default="artifacts",
        metavar="DIR",
        help="Directory for Bubblegum artifacts (default: artifacts).",
    )
    group.addoption(
        "--bubblegum-ai",
        action="store_true",
        default=False,
        help="Enable Bubblegum AI-related test behavior (reserved for future phases).",
    )
    group.addoption(
        "--bubblegum-memory",
        action="store_true",
        default=False,
        help="Enable Bubblegum memory-related test behavior (reserved for future phases).",
    )
    group.addoption(
        "--bubblegum-benchmark",
        action="store_true",
        default=False,
        help="Enable Bubblegum benchmark behavior (reserved for future phases).",
    )


@pytest.fixture(scope="session")
def bubblegum_config(pytestconfig: pytest.Config) -> BubblegumConfig:
    config_path = pytestconfig.getoption("--bubblegum-config")
    cfg = BubblegumConfig.load(config_path) if config_path else BubblegumConfig.load()
    configure_runtime(config=cfg)
    return cfg


@pytest.fixture(scope="session")
def bubblegum_engine(bubblegum_config: BubblegumConfig) -> BubblegumEngineHandle:
    return BubblegumEngineHandle(config=bubblegum_config)


@pytest.fixture(scope="session")
def bubblegum_reporter(pytestconfig: pytest.Config) -> BubblegumReporter:
    reporter = BubblegumReporter()
    setattr(pytestconfig, "_bubblegum_reporter", reporter)
    return reporter


@pytest.fixture(scope="session")
def bubblegum_artifacts_dir(pytestconfig: pytest.Config) -> Path:
    raw = pytestconfig.getoption("--bubblegum-artifacts") or "artifacts"
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    report_path = session.config.getoption("--bubblegum-report")
    if not report_path:
        return

    reporter = getattr(session.config, "_bubblegum_reporter", None)
    results = getattr(reporter, "results", []) if reporter is not None else []

    if not results:
        return

    from bubblegum.reporting.html_report import write_html_report

    write_html_report(results, path=report_path)
