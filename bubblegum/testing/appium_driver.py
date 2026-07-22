"""Appium driver construction helpers for the ``bubblegum_mobile`` fixture.

Kept separate from the pytest plugin so the capability-loading and
options-selection logic is unit-testable without a running Appium server
or a connected device (mirrors ``bubblegum/testing/widget_lab.py``).

The fixture itself only needs:
    caps = load_capabilities(raw)
    driver = create_appium_driver(appium_url, caps)
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any


class AppiumNotInstalledError(RuntimeError):
    """Raised when appium-python-client is not importable."""


def load_capabilities(raw: str | None) -> dict[str, Any]:
    """Parse Appium capabilities from a CLI value.

    ``raw`` may be:
      - ``None`` / empty   → ``{}`` (caller supplies its own caps)
      - a path to a ``.json`` file → the parsed file contents
      - an inline JSON object string → the parsed object

    Raises ``ValueError`` when the value is non-empty but neither a
    readable JSON file nor valid inline JSON object.
    """
    if raw is None:
        return {}
    text = raw.strip()
    if not text:
        return {}

    # File path takes precedence: a value that names an existing file is
    # read as JSON. This lets testers keep caps in version control.
    candidate = Path(text)
    if candidate.is_file():
        try:
            data = json.loads(candidate.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(f"Capabilities file {text!r} is not valid JSON: {exc}") from exc
    else:
        # If the value clearly looks like a file path (e.g. "caps.json") but no
        # such file exists, say so plainly instead of trying to parse the
        # filename as inline JSON and reporting a misleading "invalid JSON".
        looks_like_path = (
            text.endswith(".json")
            or "/" in text
            or os.sep in text
            or text.startswith(("~", "."))
        )
        if looks_like_path and "{" not in text:
            raise ValueError(
                f"Capabilities file not found: {text!r} (resolved to "
                f"{candidate.resolve()}). Pass a readable .json path or inline JSON."
            )
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"--bubblegum-capabilities is neither a readable file nor valid "
                f"inline JSON: {text!r}"
            ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"Appium capabilities must be a JSON object, got {type(data).__name__}"
        )
    return data


# Map the platformName capability to the right Appium Options class. Each
# value is a list of (module_path, class_name) candidates tried in order to
# span Appium Python Client v3.x–v5.x import layouts.
_OPTIONS_BY_PLATFORM: dict[str, list[tuple[str, str]]] = {
    "android": [
        ("appium.options.android", "UiAutomator2Options"),
        ("appium.options", "UiAutomator2Options"),
    ],
    "ios": [
        ("appium.options.ios", "XCUITestOptions"),
        ("appium.options", "XCUITestOptions"),
    ],
}


def _import_options_class(platform: str):
    candidates = _OPTIONS_BY_PLATFORM.get(platform)
    if candidates is None:
        raise ValueError(
            f"Unsupported platformName {platform!r}; expected 'android' or 'ios'. "
            "Set it in --bubblegum-capabilities."
        )
    for module_path, class_name in candidates:
        try:
            mod = importlib.import_module(module_path)
            return getattr(mod, class_name)
        except (ImportError, AttributeError):
            continue
    raise AppiumNotInstalledError(
        f"Could not import the Appium options class for {platform!r}. "
        "Run: pip install --upgrade Appium-Python-Client"
    )


def build_appium_options(caps: dict[str, Any]):
    """Build a platform-appropriate Appium Options object from a caps dict.

    Selects ``UiAutomator2Options`` / ``XCUITestOptions`` based on the
    ``platformName`` capability (case-insensitive) and loads the full caps
    dict onto it via ``load_capabilities``.
    """
    platform = str(caps.get("platformName", "")).strip().lower()
    if not platform:
        raise ValueError(
            "Appium capabilities must include 'platformName' (\"Android\" or \"iOS\")."
        )
    options_cls = _import_options_class(platform)
    options = options_cls()
    # All recent Options classes expose load_capabilities() to bulk-apply a
    # W3C caps dict (handling appium: prefixing internally).
    options.load_capabilities(caps)
    return options


def create_appium_driver(appium_url: str, caps: dict[str, Any]):
    """Create an Appium ``webdriver.Remote`` from a URL + capabilities dict.

    Raises ``AppiumNotInstalledError`` when appium-python-client is missing.
    Connection / session errors propagate to the caller (the fixture turns
    them into a clear skip).
    """
    try:
        import appium.webdriver as appium_webdriver
    except ImportError as exc:
        raise AppiumNotInstalledError(
            "appium-python-client is not installed. "
            "Run: pip install Appium-Python-Client"
        ) from exc

    options = build_appium_options(caps)
    return appium_webdriver.Remote(appium_url, options=options)


def attach_to_appium_session(
    appium_url: str,
    session_id: str,
    caps: dict[str, Any] | None = None,
):
    """Attach to an Appium session that another test already created.

    Cloud device farms (pCloudy, BrowserStack, …) allow only one Appium session
    per device, so an in-test Bubblegum fallback cannot open a second session —
    it must reuse the one the host test (e.g. WebdriverIO) is already driving.

    This constructs an Appium ``webdriver.Remote`` bound to ``session_id`` without
    issuing a ``newSession`` command: the ``newSession`` request is intercepted
    and short-circuited to the existing id, then normal dispatch is restored. The
    returned driver shares the live session — **the caller still owns its
    lifecycle**; Bubblegum must never call ``driver.quit()`` on it.

    ``caps`` should include ``platformName`` (\"iOS\"/\"Android\") so the correct
    options/automation name is selected; when omitted a bare options object is
    used and the platform is inferred from the live session.
    """
    try:
        import appium.webdriver as appium_webdriver
    except ImportError as exc:
        raise AppiumNotInstalledError(
            "appium-python-client is not installed. "
            "Run: pip install Appium-Python-Client"
        ) from exc

    caps = caps or {}
    # Build options when platformName is known; otherwise fall back to a bare
    # AppiumOptions so Remote() still constructs.
    if str(caps.get("platformName", "")).strip():
        options = build_appium_options(caps)
    else:
        options = _bare_appium_options()

    original_execute = appium_webdriver.Remote.execute

    def _patched_execute(self, driver_command, params=None):  # type: ignore[no-untyped-def]
        # Selenium/Appium name the session-creation command "newSession".
        if driver_command == "newSession":
            return {"success": 0, "value": dict(caps), "sessionId": session_id}
        return original_execute(self, driver_command, params)

    appium_webdriver.Remote.execute = _patched_execute  # type: ignore[assignment]
    try:
        driver = appium_webdriver.Remote(appium_url, options=options)
    finally:
        # Always restore the real dispatch so other drivers create sessions normally.
        appium_webdriver.Remote.execute = original_execute  # type: ignore[assignment]
    # Guarantee the id even if the stubbed newSession value wasn't threaded through.
    driver.session_id = session_id
    return driver


def _bare_appium_options():
    """A minimal Appium options object usable when platformName is unknown."""
    for module_path, class_name in (
        ("appium.options.common", "AppiumOptions"),
        ("appium.options", "AppiumOptions"),
    ):
        try:
            mod = importlib.import_module(module_path)
            return getattr(mod, class_name)()
        except (ImportError, AttributeError):
            continue
    raise AppiumNotInstalledError(
        "Could not import a base Appium options class. "
        "Run: pip install --upgrade Appium-Python-Client"
    )


def create_cloud_appium_driver(
    provider: str,
    caps: dict[str, Any],
    *,
    appium_url: str | None = None,
    username: str | None = None,
    access_key: str | None = None,
    session_name: str | None = None,
    build_name: str | None = None,
):
    """Create an Appium driver against a device cloud (M5).

    Enriches ``caps`` with the provider's credential/metadata namespace (via
    :func:`bubblegum.testing.cloud.apply_cloud_options`) and resolves the
    provider hub URL (``appium_url`` override → ``BUBBLEGUM_CLOUD_APPIUM_URL`` →
    provider default), then delegates to :func:`create_appium_driver`.

    Credentials fall back to environment variables when omitted — see
    :func:`bubblegum.testing.cloud.resolve_credentials`.
    """
    from bubblegum.testing.cloud import apply_cloud_options, cloud_hub_url

    enriched = apply_cloud_options(
        provider,
        caps,
        username=username,
        access_key=access_key,
        session_name=session_name,
        build_name=build_name,
    )
    url = cloud_hub_url(provider, override=appium_url)
    return create_appium_driver(url, enriched)
