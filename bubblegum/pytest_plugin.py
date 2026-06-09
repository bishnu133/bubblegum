"""Pytest plugin for Bubblegum.

Originally Phase 4A (report writers + engine handle). Phase 22E-2 adds
the ``bubblegum_web`` and ``widget_lab`` fixtures plus the
``@pytest.mark.bubblegum`` marker so tests no longer need to repeat the
Playwright launch / BubblegumSession setup boilerplate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import pytest

try:
    import pytest_asyncio
    _HAS_PYTEST_ASYNCIO = True
except ImportError:
    pytest_asyncio = None  # type: ignore[assignment]
    _HAS_PYTEST_ASYNCIO = False

from bubblegum.core.config import BubblegumConfig
from bubblegum.core.schemas import StepResult
from bubblegum.core.sdk import configure_runtime


@dataclass
class BubblegumReporter:
    """Session container for StepResult aggregation."""

    results: list[StepResult] = field(default_factory=list)

    def add(self, result: StepResult) -> None:
        self.results.append(result)

    def extend(self, results: Iterable[StepResult]) -> None:
        self.results.extend(results)


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
        "--bubblegum-report-json",
        action="store",
        default=None,
        metavar="PATH",
        help="Write Bubblegum JSON report to this path at session end (optional).",
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
    group.addoption(
        "--bubblegum-headed",
        action="store_true",
        default=False,
        help="Launch the bubblegum_web fixture browser in headed mode.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "bubblegum: marks a test as using Bubblegum fixtures (web/mobile).",
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call):
    """Pin per-phase reports on the item so fixture finalizers can branch on pass/fail.

    Standard pytest cookbook pattern: each phase report (setup/call/teardown)
    is stored as ``item.rep_<phase>``. The ``bubblegum_web`` fixture reads
    ``rep_call`` during teardown to decide whether to write a failure
    screenshot.
    """
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


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
    report_json_path = session.config.getoption("--bubblegum-report-json")

    if report_path or report_json_path:
        reporter = getattr(session.config, "_bubblegum_reporter", None)
        results = getattr(reporter, "results", []) if reporter is not None else []

        if report_path:
            from bubblegum.reporting.html_report import write_html_report

            write_html_report(results, path=report_path)

        if report_json_path:
            from bubblegum.reporting.json_report import write_json_report

            write_json_report(results, path=report_json_path)

    if not session.config.getoption("--bubblegum-benchmark"):
        return

    from scripts.run_benchmarks import run_benchmark_validation

    benchmark_exit = run_benchmark_validation()
    if benchmark_exit != 0 and getattr(session, "exitstatus", exitstatus) == 0:
        session.exitstatus = 1


# ---------------------------------------------------------------------------
# Phase 22E-2 fixtures: widget_lab + bubblegum_web
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def widget_lab():
    """Yield the base URL of an HTTP server serving widget lab pages.

    Session-scoped so the server binds one port for the whole run rather
    than restarting per test. Shuts down at session end.
    """
    from bubblegum.testing.widget_lab import start_widget_lab_server

    server, base_url = start_widget_lab_server()
    try:
        yield base_url
    finally:
        server.shutdown()


if _HAS_PYTEST_ASYNCIO:

    @pytest_asyncio.fixture
    async def bubblegum_web(request: pytest.FixtureRequest, pytestconfig: pytest.Config):
        """Yield a ``BubblegumSession.web`` wrapping a fresh Playwright Page.

        Launches Chromium, creates a context + page, and wraps them in a
        BubblegumSession. Honours ``--bubblegum-headed``. Tears the browser
        down at the end of the test.

        On test failure, writes a screenshot to ``<artifacts>/<test>-final.png``
        (the directory is set via ``--bubblegum-artifacts``, default
        ``artifacts/``). Step-level failures inside the session are captured
        separately as ``<test>-stepN.png`` by ``BubblegumSession``.

        Requires ``pytest-asyncio`` and Playwright. When Playwright is not
        installed the test is skipped with a clear hint.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            pytest.skip(
                "Playwright is not installed; install with `pip install -e \".[web]\"` "
                "and then `python -m playwright install chromium`."
            )
            return

        from pathlib import Path as _Path
        from bubblegum.session import BubblegumSession

        headed = bool(pytestconfig.getoption("--bubblegum-headed"))
        artifacts_dir = _Path(pytestconfig.getoption("--bubblegum-artifacts") or "artifacts")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=not headed)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                page.set_default_timeout(5_000)
                async with BubblegumSession.web(page) as session:
                    session.label = request.node.nodeid
                    session.artifacts_dir = artifacts_dir
                    try:
                        yield session
                    finally:
                        # rep_call is set by the makereport hookwrapper above
                        # if the call phase ran; missing => fixture errored before call.
                        rep_call = getattr(request.node, "rep_call", None)
                        if rep_call is not None and rep_call.failed:
                            await session.capture_failure_screenshot(suffix="final")
            finally:
                await browser.close()
