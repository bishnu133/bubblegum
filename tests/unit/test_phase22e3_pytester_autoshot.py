"""Phase 22E-3: end-to-end test of the bubblegum_web fixture finalizer.

Uses pytester to run a sub-pytest with the real ``bubblegum.pytest_plugin``
loaded; the test inside the sub-pytest stubs the Playwright launch so we
don't need Chromium, but the *fixture* and *hookwrapper* code paths run
unchanged. Verifies:

  * The rep_call hook pins reports on the item.
  * On test failure, the fixture finalizer calls
    ``capture_failure_screenshot`` and the artifact lands at
    ``<artifacts>/<sanitized-nodeid>-final.png``.
  * On test pass, no artifact is written.
  * The ``--bubblegum-artifacts`` flag controls the directory.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


pytest_plugins = ["pytester"]


_INNER_TEST = textwrap.dedent(
    """
    import pytest

    # The bubblegum entry point loads the plugin automatically.

    class _StubPage:
        def __init__(self):
            self.screenshots = []

        def set_default_timeout(self, _):
            pass

        async def screenshot(self, *, path=None, **_):
            if path is not None:
                from pathlib import Path
                Path(path).write_bytes(b"\\x89PNG\\r\\n\\x1a\\nstub")
                self.screenshots.append(path)
            return b"\\x89PNG"


    class _StubContext:
        async def new_page(self):
            return _StubPage()


    class _StubBrowser:
        async def new_context(self):
            return _StubContext()

        async def close(self):
            pass


    class _StubChromium:
        async def launch(self, **_):
            return _StubBrowser()


    class _StubPW:
        chromium = _StubChromium()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass


    @pytest.fixture(autouse=True)
    def _patch_playwright(monkeypatch):
        import bubblegum.pytest_plugin as plugin

        def _fake_async_playwright():
            return _StubPW()

        # The fixture imports lazily; preload the module then swap.
        import sys, types

        fake_module = types.ModuleType("playwright.async_api")
        fake_module.async_playwright = _fake_async_playwright
        monkeypatch.setitem(sys.modules, "playwright.async_api", fake_module)
        # Also ensure parent package present so the `from ... import` resolves.
        if "playwright" not in sys.modules:
            sys.modules["playwright"] = types.ModuleType("playwright")
    """
).strip()


def test_autoshot_written_on_test_failure(pytester: pytest.Pytester, tmp_path: Path):
    artifacts = tmp_path / "artifacts_fail"
    pytester.makepyfile(
        test_inner=_INNER_TEST
        + "\n\n"
        + textwrap.dedent(
            """
            import pytest

            @pytest.mark.asyncio
            async def test_deliberate_failure(bubblegum_web):
                # Touch the page so the session is fully initialized.
                assert bubblegum_web.page is not None
                assert False, "deliberate failure to trigger auto-screenshot"
            """
        )
    )
    result = pytester.runpytest(
        "-q",
        f"--bubblegum-artifacts={artifacts}",
        "-p", "no:cacheprovider",
    )
    result.assert_outcomes(failed=1)

    pngs = sorted(artifacts.glob("*.png"))
    assert pngs, f"expected an auto-screenshot in {artifacts}, found: {list(artifacts.iterdir()) if artifacts.exists() else 'no dir'}"
    # Filename ends with -final.png and contains the test function name.
    assert pngs[0].name.endswith("-final.png")
    assert "test_deliberate_failure" in pngs[0].name


def test_autoshot_skipped_on_test_pass(pytester: pytest.Pytester, tmp_path: Path):
    artifacts = tmp_path / "artifacts_pass"
    pytester.makepyfile(
        test_inner=_INNER_TEST
        + "\n\n"
        + textwrap.dedent(
            """
            import pytest

            @pytest.mark.asyncio
            async def test_clean_pass(bubblegum_web):
                assert bubblegum_web.page is not None
            """
        )
    )
    result = pytester.runpytest(
        "-q",
        f"--bubblegum-artifacts={artifacts}",
        "-p", "no:cacheprovider",
    )
    result.assert_outcomes(passed=1)

    # No artifacts written on a passing test.
    assert not artifacts.exists() or not any(artifacts.glob("*.png"))
