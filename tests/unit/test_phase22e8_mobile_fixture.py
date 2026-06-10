"""Phase 22E-8: bubblegum_mobile fixture + Appium driver helpers.

Covers (no Appium server / device required):
  - load_capabilities: empty, inline JSON, JSON file, error paths
  - build_appium_options: platform selection + missing/unknown platform
    (gated on appium-python-client being importable)
  - bubblegum_mobile fixture is exposed by the plugin
  - --bubblegum-appium-url / --bubblegum-capabilities options registered
  - BubblegumSession.mobile failure screenshot uses the Appium driver

The fixture is exercised against a real Appium session in
tests/integration/test_phase22e8_mobile_fixture.py (gated by --appium).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import bubblegum.pytest_plugin as plugin
from bubblegum.session import BubblegumSession
from bubblegum.testing.appium_driver import (
    AppiumNotInstalledError,
    build_appium_options,
    load_capabilities,
)


# ---------------------------------------------------------------------------
# load_capabilities
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_load_capabilities_empty_returns_empty_dict(raw):
    assert load_capabilities(raw) == {}


def test_load_capabilities_parses_inline_json():
    caps = load_capabilities('{"platformName": "Android", "appium:deviceName": "emu"}')
    assert caps == {"platformName": "Android", "appium:deviceName": "emu"}


def test_load_capabilities_reads_json_file(tmp_path: Path):
    f = tmp_path / "caps.json"
    f.write_text(json.dumps({"platformName": "iOS", "appium:platformVersion": "17"}))

    caps = load_capabilities(str(f))

    assert caps == {"platformName": "iOS", "appium:platformVersion": "17"}


def test_load_capabilities_rejects_non_object_json():
    with pytest.raises(ValueError, match="must be a JSON object"):
        load_capabilities('["not", "an", "object"]')


def test_load_capabilities_rejects_garbage():
    with pytest.raises(ValueError, match="neither a readable file nor valid"):
        load_capabilities("platformName=Android")


def test_load_capabilities_rejects_invalid_json_file(tmp_path: Path):
    f = tmp_path / "bad.json"
    f.write_text("{ not valid json ")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_capabilities(str(f))


# ---------------------------------------------------------------------------
# build_appium_options (needs appium-python-client importable)
# ---------------------------------------------------------------------------


def test_build_appium_options_requires_platform_name():
    with pytest.raises(ValueError, match="platformName"):
        build_appium_options({"appium:deviceName": "emu"})


def test_build_appium_options_rejects_unknown_platform():
    pytest.importorskip("appium")
    # Unknown platform is rejected before any options class import.
    with pytest.raises(ValueError, match="Unsupported platformName"):
        build_appium_options({"platformName": "Symbian"})


def test_build_appium_options_android_selects_uiautomator2():
    pytest.importorskip("appium")
    options = build_appium_options(
        {"platformName": "Android", "appium:deviceName": "emulator-5554"}
    )
    assert type(options).__name__ == "UiAutomator2Options"
    assert options.platform_name.lower() == "android"


def test_build_appium_options_ios_selects_xcuitest():
    pytest.importorskip("appium")
    options = build_appium_options(
        {"platformName": "iOS", "appium:deviceName": "iPhone 15"}
    )
    assert type(options).__name__ == "XCUITestOptions"


# ---------------------------------------------------------------------------
# Plugin surface
# ---------------------------------------------------------------------------


def test_bubblegum_mobile_fixture_is_exposed_when_pytest_asyncio_present():
    pytest.importorskip("pytest_asyncio")
    assert hasattr(plugin, "bubblegum_mobile")


def test_appium_url_option_has_default(pytestconfig: pytest.Config):
    assert pytestconfig.getoption("--bubblegum-appium-url") == "http://localhost:4723"


def test_capabilities_option_defaults_to_none(pytestconfig: pytest.Config):
    assert pytestconfig.getoption("--bubblegum-capabilities") is None


# ---------------------------------------------------------------------------
# Mobile failure screenshot parity
# ---------------------------------------------------------------------------


class _FakeDriver:
    def __init__(self) -> None:
        self.screenshot_calls = 0

    def get_screenshot_as_png(self) -> bytes:
        self.screenshot_calls += 1
        return b"\x89PNG\r\n\x1a\n-fake-mobile-shot"


def test_mobile_capture_failure_screenshot_uses_driver(tmp_path: Path):
    driver = _FakeDriver()
    session = BubblegumSession.mobile(driver)
    session.label = "tests/mobile/test_login::test_tap"
    session.artifacts_dir = tmp_path

    path = asyncio.run(session.capture_failure_screenshot(suffix="final"))

    assert path is not None
    assert path.exists()
    assert path.read_bytes().startswith(b"\x89PNG")
    assert driver.screenshot_calls == 1
    assert session.failure_screenshots == [path]


def test_mobile_capture_failure_screenshot_skips_without_label(tmp_path: Path):
    driver = _FakeDriver()
    session = BubblegumSession.mobile(driver)
    session.artifacts_dir = tmp_path

    path = asyncio.run(session.capture_failure_screenshot())

    assert path is None
    assert driver.screenshot_calls == 0
