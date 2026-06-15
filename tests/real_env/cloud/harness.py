from __future__ import annotations

import os
from dataclasses import dataclass

import pytest

from bubblegum.testing.cloud import SUPPORTED_PROVIDERS, get_provider

_CLOUD_PROVIDER_ENV_VAR = "BUBBLEGUM_CLOUD_PROVIDER"

# Single source of truth: the shipped provider registry in
# bubblegum.testing.cloud (M5). The harness derives its namespace / default-URL
# maps from it so the two never drift.
_ALLOWED_CLOUD_PROVIDERS: frozenset[str] = SUPPORTED_PROVIDERS

_PROVIDER_CAPABILITY_NAMESPACE: dict[str, str] = {
    name: get_provider(name).capability_namespace for name in SUPPORTED_PROVIDERS
}

_PROVIDER_DEFAULT_APPIUM_URL: dict[str, str] = {
    name: get_provider(name).default_hub_url for name in SUPPORTED_PROVIDERS
}


@dataclass(frozen=True)
class CloudHarnessConfig:
    provider: str
    appium_server_url: str
    capability_namespace: str


def resolve_cloud_provider() -> str:
    provider = os.getenv(_CLOUD_PROVIDER_ENV_VAR, "").strip().lower()
    if provider not in _ALLOWED_CLOUD_PROVIDERS:
        allowed_values = ", ".join(sorted(_ALLOWED_CLOUD_PROVIDERS))
        pytest.skip(
            "Real-environment cloud smoke harness requires "
            f"{_CLOUD_PROVIDER_ENV_VAR} to be one of: {allowed_values}."
        )
    return provider


def build_cloud_harness_config() -> CloudHarnessConfig:
    provider = resolve_cloud_provider()
    appium_server_url = os.getenv("BUBBLEGUM_CLOUD_APPIUM_URL", "").strip()
    if not appium_server_url:
        appium_server_url = os.getenv("BUBBLEGUM_APPIUM_SERVER_URL", "").strip()
    if not appium_server_url:
        appium_server_url = _PROVIDER_DEFAULT_APPIUM_URL[provider]

    if not appium_server_url:
        pytest.skip(
            "Real-environment cloud smoke harness requires BUBBLEGUM_CLOUD_APPIUM_URL or BUBBLEGUM_APPIUM_SERVER_URL "
            "for provider='generic'."
        )

    return CloudHarnessConfig(
        provider=provider,
        appium_server_url=appium_server_url,
        capability_namespace=_PROVIDER_CAPABILITY_NAMESPACE[provider],
    )


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        pytest.skip(f"Cloud device smoke requires {name}.")
    return value


def _optional_env(name: str) -> str:
    return os.getenv(name, "").strip()


def _resolve_platform() -> str:
    platform = _optional_env("BUBBLEGUM_CLOUD_PLATFORM").lower()
    if not platform:
        pytest.skip("Cloud device smoke requires BUBBLEGUM_CLOUD_PLATFORM (android or ios).")
    if platform not in {"android", "ios"}:
        pytest.skip("Cloud device smoke requires BUBBLEGUM_CLOUD_PLATFORM to be 'android' or 'ios'.")
    return platform


def _resolve_app_launch_capability() -> tuple[str, str]:
    cloud_app = _optional_env("BUBBLEGUM_CLOUD_APP")
    cloud_app_id = _optional_env("BUBBLEGUM_CLOUD_APP_ID")
    android_package = _optional_env("BUBBLEGUM_CLOUD_ANDROID_PACKAGE")
    android_activity = _optional_env("BUBBLEGUM_CLOUD_ANDROID_ACTIVITY")
    ios_bundle_id = _optional_env("BUBBLEGUM_CLOUD_IOS_BUNDLE_ID")

    if cloud_app:
        return ("appium:app", cloud_app)
    if cloud_app_id:
        return ("appium:app", cloud_app_id)
    if android_package and android_activity:
        return ("appium:appPackage", android_package)
    if ios_bundle_id:
        return ("appium:bundleId", ios_bundle_id)

    pytest.skip(
        "Cloud device smoke requires one of BUBBLEGUM_CLOUD_APP, BUBBLEGUM_CLOUD_APP_ID, "
        "(BUBBLEGUM_CLOUD_ANDROID_PACKAGE + BUBBLEGUM_CLOUD_ANDROID_ACTIVITY), or BUBBLEGUM_CLOUD_IOS_BUNDLE_ID."
    )


def build_cloud_capabilities() -> dict[str, object]:
    cfg = build_cloud_harness_config()
    platform = _resolve_platform()
    device_name = _required_env("BUBBLEGUM_CLOUD_DEVICE_NAME")
    username = _required_env("BUBBLEGUM_CLOUD_USERNAME")
    access_key = _required_env("BUBBLEGUM_CLOUD_ACCESS_KEY")

    platform_name = "Android" if platform == "android" else "iOS"
    automation_default = "UiAutomator2" if platform == "android" else "XCUITest"
    app_key, app_value = _resolve_app_launch_capability()

    caps: dict[str, object] = {
        "platformName": platform_name,
        "appium:platformName": platform_name,
        "appium:deviceName": device_name,
        "appium:automationName": _optional_env("BUBBLEGUM_CLOUD_AUTOMATION_NAME") or automation_default,
        app_key: app_value,
    }

    platform_version = _optional_env("BUBBLEGUM_CLOUD_PLATFORM_VERSION")
    if platform_version:
        caps["appium:platformVersion"] = platform_version

    if app_key == "appium:appPackage":
        caps["appium:appActivity"] = _required_env("BUBBLEGUM_CLOUD_ANDROID_ACTIVITY")

    namespace_key = cfg.capability_namespace
    if cfg.provider != "generic":
        provider_options: dict[str, str] = {"deviceName": device_name}
        if cfg.provider == "pcloudy":
            provider_options["username"] = username
            provider_options["accessKey"] = access_key
        elif cfg.provider == "browserstack":
            provider_options["userName"] = username
            provider_options["accessKey"] = access_key
        elif cfg.provider == "saucelabs":
            provider_options["username"] = username
            provider_options["accessKey"] = access_key
        elif cfg.provider == "lambdatest":
            provider_options["user"] = username
            provider_options["accessKey"] = access_key

        session_name = _optional_env("BUBBLEGUM_CLOUD_SESSION_NAME")
        build_name = _optional_env("BUBBLEGUM_CLOUD_BUILD_NAME")
        if session_name:
            provider_options["name" if cfg.provider in {"saucelabs", "lambdatest"} else "sessionName"] = session_name
        if build_name:
            provider_options["build"] = build_name

        caps[namespace_key] = provider_options

    return caps


def cloud_config_safe_summary() -> dict[str, str]:
    cfg = build_cloud_harness_config()
    platform = _optional_env("BUBBLEGUM_CLOUD_PLATFORM").lower()
    automation_name = _optional_env("BUBBLEGUM_CLOUD_AUTOMATION_NAME")
    app_launch_strategy = "unknown"
    if _optional_env("BUBBLEGUM_CLOUD_APP"):
        app_launch_strategy = "app_path_or_url"
    elif _optional_env("BUBBLEGUM_CLOUD_APP_ID"):
        app_launch_strategy = "app_id"
    elif _optional_env("BUBBLEGUM_CLOUD_ANDROID_PACKAGE") and _optional_env("BUBBLEGUM_CLOUD_ANDROID_ACTIVITY"):
        app_launch_strategy = "android_package_activity"
    elif _optional_env("BUBBLEGUM_CLOUD_IOS_BUNDLE_ID"):
        app_launch_strategy = "ios_bundle_id"

    url_source = "provider_default"
    if _optional_env("BUBBLEGUM_CLOUD_APPIUM_URL"):
        url_source = "cloud_appium_url"
    elif _optional_env("BUBBLEGUM_APPIUM_SERVER_URL"):
        url_source = "appium_server_url"

    return {
        "provider": cfg.provider,
        "provider_namespace": cfg.capability_namespace,
        "platform": platform,
        "device_name_present": "1" if bool(_optional_env("BUBBLEGUM_CLOUD_DEVICE_NAME")) else "0",
        "app_launch_strategy": app_launch_strategy,
        "url_source": url_source,
        "automation_name": automation_name or ("UiAutomator2" if platform == "android" else "XCUITest" if platform == "ios" else ""),
        "session_name_present": "1" if bool(_optional_env("BUBBLEGUM_CLOUD_SESSION_NAME")) else "0",
        "build_name_present": "1" if bool(_optional_env("BUBBLEGUM_CLOUD_BUILD_NAME")) else "0",
        "safe_metadata_only": "1",
    }
