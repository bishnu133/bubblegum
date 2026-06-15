"""Device-cloud integration (M5): BrowserStack / Sauce Labs / LambdaTest / pCloudy.

Real-device clouds all speak Appium, but each one expects its credentials and
run metadata inside a *vendor-specific capability namespace* (``bstack:options``,
``sauce:options``, ``LT:Options``, ``pCloudy_Options``) and exposes its own
Appium hub URL. This module turns "I want a Pixel 8 on BrowserStack running my
app" into the right W3C capabilities + hub URL, so the same Bubblegum test runs
locally or on any supported cloud by changing one provider name.

Kept browser/Appium-free and pytest-free on purpose: capability building is pure
data, so it is fully unit-testable without a device, an Appium server, or a
cloud account (mirrors ``appium_driver.py`` and ``widget_lab.py``). The pytest
plugin and the real-env smoke harness both build on top of it.

Typical use (programmatic)::

    from bubblegum.testing.cloud import build_cloud_capabilities, cloud_hub_url
    from bubblegum.testing.appium_driver import create_appium_driver

    caps = build_cloud_capabilities(
        provider="browserstack",
        platform="android",
        device_name="Google Pixel 8",
        app="bs://<app-id>",
        session_name="Login smoke",
        build_name="CI #128",
    )                                   # credentials pulled from env if omitted
    driver = create_appium_driver(cloud_hub_url("browserstack"), caps)

Or enrich a caps dict you already loaded from ``--bubblegum-capabilities``::

    caps = apply_cloud_options("saucelabs", caps, session_name="Login smoke")
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


class CloudConfigError(ValueError):
    """Raised when cloud provider / capability inputs are missing or invalid.

    A plain ``ValueError`` subclass so library callers can catch it; the pytest
    plugin and real-env harness translate it into a clear skip/error at their
    own boundary instead of this module reaching for ``pytest``.
    """


@dataclass(frozen=True)
class CloudProvider:
    """Static description of a supported device cloud.

    - ``capability_namespace`` — the vendor key under which options/credentials
      are nested in the W3C caps (e.g. ``bstack:options``).
    - ``default_hub_url`` — the provider's Appium hub endpoint (empty for the
      ``generic`` provider, which always requires an explicit URL).
    - ``username_key`` / ``access_key_key`` — the credential field names *inside*
      the namespace (vendors disagree: ``userName`` vs ``username`` vs ``user``).
    - ``session_name_key`` — field name for the human-readable run/session label.
    - ``env_username`` / ``env_access_key`` — the provider's own conventional
      environment variables, accepted as a fallback so existing CI secrets work
      without renaming.
    """

    name: str
    capability_namespace: str
    default_hub_url: str
    username_key: str
    access_key_key: str
    session_name_key: str
    env_username: tuple[str, ...] = ()
    env_access_key: tuple[str, ...] = ()


# Registry of supported clouds. The real-env smoke harness imports this so the
# library stays the single source of truth for namespaces / hub URLs / key names.
_PROVIDERS: dict[str, CloudProvider] = {
    "browserstack": CloudProvider(
        name="browserstack",
        capability_namespace="bstack:options",
        default_hub_url="https://hub.browserstack.com/wd/hub",
        username_key="userName",
        access_key_key="accessKey",
        session_name_key="sessionName",
        env_username=("BROWSERSTACK_USERNAME",),
        env_access_key=("BROWSERSTACK_ACCESS_KEY",),
    ),
    "saucelabs": CloudProvider(
        name="saucelabs",
        capability_namespace="sauce:options",
        default_hub_url="https://ondemand.us-west-1.saucelabs.com/wd/hub",
        username_key="username",
        access_key_key="accessKey",
        session_name_key="name",
        env_username=("SAUCE_USERNAME",),
        env_access_key=("SAUCE_ACCESS_KEY",),
    ),
    "lambdatest": CloudProvider(
        name="lambdatest",
        capability_namespace="LT:Options",
        default_hub_url="https://mobile-hub.lambdatest.com/wd/hub",
        username_key="user",
        access_key_key="accessKey",
        session_name_key="name",
        env_username=("LT_USERNAME",),
        env_access_key=("LT_ACCESS_KEY",),
    ),
    "pcloudy": CloudProvider(
        name="pcloudy",
        capability_namespace="pCloudy_Options",
        default_hub_url="https://device.pcloudy.com/appiumcloud/wd/hub",
        username_key="username",
        access_key_key="accessKey",
        session_name_key="sessionName",
        env_username=("PCLOUDY_USERNAME",),
        env_access_key=("PCLOUDY_ACCESS_KEY", "PCLOUDY_API_KEY"),
    ),
    # An escape hatch for any other W3C-compliant Appium cloud: no namespace,
    # no default URL — the caller supplies the hub URL and bakes credentials
    # into their caps however the vendor wants.
    "generic": CloudProvider(
        name="generic",
        capability_namespace="appium:options",
        default_hub_url="",
        username_key="username",
        access_key_key="accessKey",
        session_name_key="sessionName",
    ),
}

#: Provider names accepted by :func:`get_provider` and the CLI.
SUPPORTED_PROVIDERS: frozenset[str] = frozenset(_PROVIDERS)

# Shared credential env vars (provider-agnostic), tried before the provider's
# own conventional names so a single pair of secrets works everywhere.
_COMMON_ENV_USERNAME = "BUBBLEGUM_CLOUD_USERNAME"
_COMMON_ENV_ACCESS_KEY = "BUBBLEGUM_CLOUD_ACCESS_KEY"


def get_provider(provider: str) -> CloudProvider:
    """Return the :class:`CloudProvider` for ``provider`` (case-insensitive).

    Raises :class:`CloudConfigError` with the list of supported names when the
    provider is unknown.
    """
    key = str(provider or "").strip().lower()
    try:
        return _PROVIDERS[key]
    except KeyError:
        allowed = ", ".join(sorted(SUPPORTED_PROVIDERS))
        raise CloudConfigError(
            f"Unknown cloud provider {provider!r}. Supported: {allowed}."
        ) from None


def cloud_hub_url(provider: str, *, override: str | None = None) -> str:
    """Resolve the Appium hub URL for ``provider``.

    Precedence: explicit ``override`` → ``BUBBLEGUM_CLOUD_APPIUM_URL`` env →
    the provider's ``default_hub_url``. The ``generic`` provider has no default,
    so one of the first two must be supplied or a :class:`CloudConfigError` is
    raised.
    """
    prov = get_provider(provider)
    chosen = (override or "").strip() or os.getenv("BUBBLEGUM_CLOUD_APPIUM_URL", "").strip()
    if not chosen:
        chosen = prov.default_hub_url
    if not chosen:
        raise CloudConfigError(
            f"No Appium hub URL for provider {prov.name!r}. Pass override= or set "
            "BUBBLEGUM_CLOUD_APPIUM_URL (required for the 'generic' provider)."
        )
    return chosen


def resolve_credentials(
    provider: str,
    *,
    username: str | None = None,
    access_key: str | None = None,
) -> tuple[str, str]:
    """Resolve ``(username, access_key)`` for ``provider``.

    Precedence for each value: explicit argument → ``BUBBLEGUM_CLOUD_USERNAME`` /
    ``BUBBLEGUM_CLOUD_ACCESS_KEY`` → the provider's own conventional env vars
    (e.g. ``BROWSERSTACK_USERNAME``). Raises :class:`CloudConfigError` naming the
    missing value so the failure is actionable.
    """
    prov = get_provider(provider)
    user = (username or "").strip() or _first_env(_COMMON_ENV_USERNAME, *prov.env_username)
    key = (access_key or "").strip() or _first_env(_COMMON_ENV_ACCESS_KEY, *prov.env_access_key)
    if not user:
        raise CloudConfigError(
            f"Missing cloud username for {prov.name!r}: pass username= or set "
            f"{_COMMON_ENV_USERNAME}" + (f" / {prov.env_username[0]}" if prov.env_username else "") + "."
        )
    if not key:
        raise CloudConfigError(
            f"Missing cloud access key for {prov.name!r}: pass access_key= or set "
            f"{_COMMON_ENV_ACCESS_KEY}" + (f" / {prov.env_access_key[0]}" if prov.env_access_key else "") + "."
        )
    return user, key


def _first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _normalize_platform(platform: str) -> str:
    norm = str(platform or "").strip().lower()
    if norm not in {"android", "ios"}:
        raise CloudConfigError(
            f"Unsupported platform {platform!r}; expected 'android' or 'ios'."
        )
    return norm


def provider_options_block(
    provider: str,
    *,
    username: str | None = None,
    access_key: str | None = None,
    session_name: str | None = None,
    build_name: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the vendor namespace block (credentials + run metadata).

    Returns the dict that belongs under e.g. ``bstack:options``. For the
    ``generic`` provider this returns an empty dict (W3C-compliant clouds that
    take credentials another way) unless ``extra`` is supplied — credentials are
    *not* injected because there is no agreed key layout.
    """
    prov = get_provider(provider)
    options: dict[str, Any] = {}
    if prov.name != "generic":
        user, key = resolve_credentials(prov.name, username=username, access_key=access_key)
        options[prov.username_key] = user
        options[prov.access_key_key] = key
    if session_name:
        options[prov.session_name_key] = session_name
    if build_name:
        options["build"] = build_name
    if extra:
        options.update(extra)
    return options


def apply_cloud_options(
    provider: str,
    caps: dict[str, Any],
    *,
    username: str | None = None,
    access_key: str | None = None,
    session_name: str | None = None,
    build_name: str | None = None,
    provider_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a copy of ``caps`` with the provider's namespace block merged in.

    Use this to "cloud-ify" a capabilities dict you already built locally (e.g.
    loaded from ``--bubblegum-capabilities``). Existing keys in an existing
    namespace block are preserved; new credential / metadata keys are added.
    The input dict is not mutated.
    """
    prov = get_provider(provider)
    merged = dict(caps)
    block = provider_options_block(
        prov.name,
        username=username,
        access_key=access_key,
        session_name=session_name,
        build_name=build_name,
        extra=provider_options,
    )
    if not block:
        return merged
    existing = merged.get(prov.capability_namespace)
    if isinstance(existing, dict):
        combined = dict(block)
        combined.update(existing)  # caller-provided namespace values win
        merged[prov.capability_namespace] = combined
    else:
        merged[prov.capability_namespace] = block
    return merged


def build_cloud_capabilities(
    provider: str,
    *,
    platform: str,
    device_name: str,
    app: str | None = None,
    app_package: str | None = None,
    app_activity: str | None = None,
    bundle_id: str | None = None,
    platform_version: str | None = None,
    automation_name: str | None = None,
    username: str | None = None,
    access_key: str | None = None,
    session_name: str | None = None,
    build_name: str | None = None,
    extra_caps: dict[str, Any] | None = None,
    provider_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a complete W3C capabilities dict for a cloud device run.

    Exactly one app-launch strategy must be given:
      - ``app`` — an uploaded app reference / URL (e.g. ``bs://…``), or
      - ``app_package`` + ``app_activity`` (Android), or
      - ``bundle_id`` (iOS).

    Credentials are resolved via :func:`resolve_credentials` (explicit args or
    env). ``extra_caps`` is merged at the top level last (override anything);
    ``provider_options`` is merged into the vendor namespace block. Raises
    :class:`CloudConfigError` on missing/contradictory inputs.
    """
    prov = get_provider(provider)
    norm_platform = _normalize_platform(platform)
    if not str(device_name or "").strip():
        raise CloudConfigError("device_name is required for a cloud run.")

    platform_name = "Android" if norm_platform == "android" else "iOS"
    default_automation = "UiAutomator2" if norm_platform == "android" else "XCUITest"

    caps: dict[str, Any] = {
        "platformName": platform_name,
        "appium:platformName": platform_name,
        "appium:deviceName": str(device_name).strip(),
        "appium:automationName": (automation_name or "").strip() or default_automation,
    }
    if platform_version:
        caps["appium:platformVersion"] = str(platform_version).strip()

    _apply_app_launch(
        caps,
        platform=norm_platform,
        app=app,
        app_package=app_package,
        app_activity=app_activity,
        bundle_id=bundle_id,
    )

    block = provider_options_block(
        prov.name,
        username=username,
        access_key=access_key,
        session_name=session_name,
        build_name=build_name,
        extra=provider_options,
    )
    if block:
        caps[prov.capability_namespace] = block

    if extra_caps:
        caps.update(extra_caps)
    return caps


def _apply_app_launch(
    caps: dict[str, Any],
    *,
    platform: str,
    app: str | None,
    app_package: str | None,
    app_activity: str | None,
    bundle_id: str | None,
) -> None:
    """Stamp the chosen app-launch capability onto ``caps`` (in place)."""
    app = (app or "").strip()
    app_package = (app_package or "").strip()
    app_activity = (app_activity or "").strip()
    bundle_id = (bundle_id or "").strip()

    if app:
        caps["appium:app"] = app
        return
    if app_package:
        if platform != "android":
            raise CloudConfigError("app_package/app_activity are Android-only.")
        if not app_activity:
            raise CloudConfigError("app_package requires app_activity (Android).")
        caps["appium:appPackage"] = app_package
        caps["appium:appActivity"] = app_activity
        return
    if bundle_id:
        if platform != "ios":
            raise CloudConfigError("bundle_id is iOS-only.")
        caps["appium:bundleId"] = bundle_id
        return

    raise CloudConfigError(
        "No app-launch strategy: pass app=, (app_package + app_activity), or bundle_id=."
    )
