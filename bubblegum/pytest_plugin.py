"""Pytest plugin for Bubblegum.

Originally Phase 4A (report writers + engine handle). Phase 22E-2 adds
the ``bubblegum_web`` and ``widget_lab`` fixtures plus the
``@pytest.mark.bubblegum`` marker so tests no longer need to repeat the
Playwright launch / BubblegumSession setup boilerplate. Phase 22E-7 adds
the session-scoped ``bubblegum_browser`` / function-scoped
``bubblegum_page`` split so large suites launch Chromium once.
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
        "--bubblegum-report-junit",
        action="store",
        default=None,
        metavar="PATH",
        help="Write Bubblegum JUnit XML report to this path at session end "
        "(optional). Consumed natively by Jenkins/GitLab/Azure/CircleCI.",
    )
    group.addoption(
        "--bubblegum-report-allure",
        action="store",
        default=None,
        metavar="DIR",
        help="Write Bubblegum Allure result files to this directory at session "
        "end (optional). View with `allure serve <DIR>`.",
    )
    group.addoption(
        "--bubblegum-suggest-fixes",
        action="store",
        default=None,
        metavar="PATH",
        help="Write a JSON dump of self-healing suggested fixes + a brittleness "
        "ranking (most-healed selectors) to this path at session end (optional).",
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
    group.addoption(
        "--bubblegum-update-baselines",
        action="store_true",
        default=False,
        help="Visual regression: (re)write baselines instead of comparing "
        "(verify(..., assertion_type='visual')).",
    )
    group.addoption(
        "--bubblegum-flaky-report",
        action="store",
        default=None,
        metavar="PATH",
        help="Write a flaky-test report (ranked by historical pass-rate) to this "
        "JSON path at session end. Tracks per-step pass-rate across runs (X1).",
    )
    group.addoption(
        "--bubblegum-quarantine",
        action="store_true",
        default=False,
        help="Quarantine flaky steps: a known-flaky step's failure is reported "
        "but does not fail the JUnit build (mark-but-not-fail).",
    )
    group.addoption(
        "--bubblegum-appium-url",
        action="store",
        default="http://localhost:4723",
        metavar="URL",
        help="Appium server URL for the bubblegum_mobile fixture "
        "(default: http://localhost:4723).",
    )
    group.addoption(
        "--bubblegum-capabilities",
        action="store",
        default=None,
        metavar="JSON_OR_PATH",
        help="Appium capabilities for the bubblegum_mobile fixture: either a "
        "path to a .json file or an inline JSON object. Must include "
        "platformName.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "bubblegum: marks a test as using Bubblegum fixtures (web/mobile).",
    )
    # Visual regression: --bubblegum-update-baselines must take effect even for
    # tests that don't pull in the bubblegum_config fixture, so apply it to the
    # runtime config here as well.
    if config.getoption("--bubblegum-update-baselines"):
        cfg = BubblegumConfig.load(config.getoption("--bubblegum-config") or None)
        cfg.visual.update_baselines = True
        configure_runtime(config=cfg)


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
    if pytestconfig.getoption("--bubblegum-update-baselines"):
        cfg.visual.update_baselines = True
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
    report_junit_path = session.config.getoption("--bubblegum-report-junit")
    report_allure_dir = session.config.getoption("--bubblegum-report-allure")
    suggest_fixes_path = session.config.getoption("--bubblegum-suggest-fixes")
    flaky_report_path = session.config.getoption("--bubblegum-flaky-report")
    quarantine_flag = bool(session.config.getoption("--bubblegum-quarantine"))

    if (report_path or report_json_path or report_junit_path or report_allure_dir
            or suggest_fixes_path or flaky_report_path):
        reporter = getattr(session.config, "_bubblegum_reporter", None)
        results = getattr(reporter, "results", []) if reporter is not None else []

        # X1: record this run's outcomes into the flaky history and build the
        # flaky index used to annotate / quarantine steps in the JUnit report.
        flaky_index = None
        quarantine = quarantine_flag
        cfg = BubblegumConfig.load(session.config.getoption("--bubblegum-config") or None)
        quarantine = quarantine or cfg.flaky.quarantine
        if cfg.flaky.enabled and results:
            try:
                from bubblegum.core.flaky import FlakyTracker
                from bubblegum.core.memory.layer import MemoryLayer

                tracker = FlakyTracker(
                    MemoryLayer(),
                    stability_threshold=cfg.flaky.stability_threshold,
                    min_runs=cfg.flaky.min_runs,
                )
                tracker.record_run(results)
                flaky_index = tracker.flaky_index()
                if flaky_report_path:
                    from bubblegum.reporting.flaky_report import write_flaky_report

                    write_flaky_report(
                        tracker.summary(),
                        path=flaky_report_path,
                        stability_threshold=cfg.flaky.stability_threshold,
                        min_runs=cfg.flaky.min_runs,
                    )
            except Exception:  # noqa: BLE001 — flaky tracking must never break a run
                flaky_index = None

        if report_path:
            from bubblegum.reporting.html_report import write_html_report

            write_html_report(results, path=report_path)

        if report_json_path:
            from bubblegum.reporting.json_report import write_json_report

            write_json_report(results, path=report_json_path)

        if report_junit_path:
            from bubblegum.reporting.junit_report import write_junit_report

            write_junit_report(
                results, path=report_junit_path,
                flaky_index=flaky_index, quarantine=quarantine,
            )

        if report_allure_dir:
            from bubblegum.reporting.allure_report import write_allure_results

            write_allure_results(results, output_dir=report_allure_dir)

        if suggest_fixes_path:
            from bubblegum.reporting.suggested_fixes import write_suggested_fixes

            write_suggested_fixes(results, path=suggest_fixes_path)

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


@pytest.fixture(scope="session")
def sample_app():
    """Yield the base URL of the Acme Notes sample app (Phase 22E-9).

    Serves ``examples/web/real_local/pages`` — a three-page login →
    dashboard → settings app used by the tester quickstart. Session-scoped,
    same server semantics as ``widget_lab``.
    """
    from pathlib import Path as _Path

    from bubblegum.testing.widget_lab import find_pages_dir, start_widget_lab_server

    pages = find_pages_dir(rel=_Path("examples/web/real_local/pages"))
    server, base_url = start_widget_lab_server(pages_dir=pages)
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

    # -------------------------------------------------------------------
    # Phase 22E-7: session-scoped browser + function-scoped page split.
    # Launching Chromium costs ~1-2 s; suites with many tests pay it once
    # via bubblegum_browser while bubblegum_page still gives each test a
    # fresh incognito context (cookies / storage / pages isolated).
    # -------------------------------------------------------------------

    @pytest_asyncio.fixture(scope="session", loop_scope="session")
    async def bubblegum_browser(pytestconfig: pytest.Config):
        """Yield a Chromium browser shared by every test in the session.

        Playwright objects are bound to the event loop they were created
        on, so this fixture (and anything built on it, like
        ``bubblegum_page``) runs on the session-scoped loop. Tests that
        consume it must opt onto that loop:

            pytestmark = pytest.mark.asyncio(loop_scope="session")

        Honours ``--bubblegum-headed``. Skips dependents when Playwright
        is not installed.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            pytest.skip(
                "Playwright is not installed; install with `pip install -e \".[web]\"` "
                "and then `python -m playwright install chromium`."
            )
            return

        headed = bool(pytestconfig.getoption("--bubblegum-headed"))
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=not headed)
            try:
                yield browser
            finally:
                await browser.close()

    @pytest_asyncio.fixture(loop_scope="session")
    async def bubblegum_page(
        bubblegum_browser, request: pytest.FixtureRequest, pytestconfig: pytest.Config
    ):
        """Yield a ``BubblegumSession.web`` on the shared session browser.

        Same contract as ``bubblegum_web`` (label, artifacts dir, failure
        screenshot on teardown) but reuses ``bubblegum_browser`` instead of
        launching Chromium per test — the per-test cost drops to a new
        context + page. Tests must run on the session event loop:

            pytestmark = pytest.mark.asyncio(loop_scope="session")
        """
        from pathlib import Path as _Path
        from bubblegum.session import BubblegumSession

        artifacts_dir = _Path(pytestconfig.getoption("--bubblegum-artifacts") or "artifacts")

        context = await bubblegum_browser.new_context()
        try:
            page = await context.new_page()
            page.set_default_timeout(5_000)
            async with BubblegumSession.web(page) as session:
                session.label = request.node.nodeid
                session.artifacts_dir = artifacts_dir
                try:
                    yield session
                finally:
                    rep_call = getattr(request.node, "rep_call", None)
                    if rep_call is not None and rep_call.failed:
                        await session.capture_failure_screenshot(suffix="final")
        finally:
            await context.close()

    # -------------------------------------------------------------------
    # Phase 22E-8: bubblegum_mobile — Appium driver fixture (mobile parity
    # with bubblegum_web). Builds a driver from --bubblegum-appium-url +
    # --bubblegum-capabilities and wraps it in BubblegumSession.mobile.
    # -------------------------------------------------------------------

    @pytest_asyncio.fixture
    async def bubblegum_mobile(request: pytest.FixtureRequest, pytestconfig: pytest.Config):
        """Yield a ``BubblegumSession.mobile`` wrapping a fresh Appium driver.

        Reads the Appium server URL from ``--bubblegum-appium-url`` and the
        capabilities from ``--bubblegum-capabilities`` (a path to a JSON file
        or an inline JSON object; must include ``platformName``). Quits the
        driver at the end of the test.

        Mirrors ``bubblegum_web``: sets the session label / artifacts dir and
        writes ``<artifacts>/<test>-final.png`` (via the Appium driver) on
        test-level failure.

        Skips when appium-python-client is not installed, no capabilities are
        provided, or the Appium server cannot be reached.
        """
        from pathlib import Path as _Path

        from bubblegum.session import BubblegumSession
        from bubblegum.testing.appium_driver import (
            AppiumNotInstalledError,
            create_appium_driver,
            load_capabilities,
        )

        raw_caps = pytestconfig.getoption("--bubblegum-capabilities")
        if not raw_caps:
            pytest.skip(
                "bubblegum_mobile requires --bubblegum-capabilities "
                "(a JSON file path or inline JSON object including platformName)."
            )
            return

        appium_url = pytestconfig.getoption("--bubblegum-appium-url")
        artifacts_dir = _Path(pytestconfig.getoption("--bubblegum-artifacts") or "artifacts")

        caps = load_capabilities(raw_caps)
        try:
            driver = create_appium_driver(appium_url, caps)
        except AppiumNotInstalledError as exc:
            pytest.skip(str(exc))
            return
        except Exception as exc:  # connection / session creation failure
            pytest.skip(f"Cannot start Appium session at {appium_url}: {exc}")
            return

        try:
            async with BubblegumSession.mobile(driver) as session:
                session.label = request.node.nodeid
                session.artifacts_dir = artifacts_dir
                try:
                    yield session
                finally:
                    rep_call = getattr(request.node, "rep_call", None)
                    if rep_call is not None and rep_call.failed:
                        await session.capture_failure_screenshot(suffix="final")
        finally:
            driver.quit()
