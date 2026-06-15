"""Unit tests for M5 device-cloud capability building (bubblegum.testing.cloud).

Pure data — no Appium server, device, or cloud account required.
"""

from __future__ import annotations

import pytest

from bubblegum.testing.cloud import (
    SUPPORTED_PROVIDERS,
    CloudConfigError,
    apply_cloud_options,
    build_cloud_capabilities,
    cloud_hub_url,
    get_provider,
    provider_options_block,
    resolve_credentials,
)


@pytest.fixture(autouse=True)
def _clear_cloud_env(monkeypatch):
    """Keep tests hermetic: drop any ambient cloud env vars."""
    for var in (
        "BUBBLEGUM_CLOUD_USERNAME",
        "BUBBLEGUM_CLOUD_ACCESS_KEY",
        "BUBBLEGUM_CLOUD_APPIUM_URL",
        "BROWSERSTACK_USERNAME",
        "BROWSERSTACK_ACCESS_KEY",
        "SAUCE_USERNAME",
        "SAUCE_ACCESS_KEY",
        "LT_USERNAME",
        "LT_ACCESS_KEY",
        "PCLOUDY_USERNAME",
        "PCLOUDY_ACCESS_KEY",
        "PCLOUDY_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

def test_supported_providers_set():
    assert SUPPORTED_PROVIDERS == frozenset(
        {"browserstack", "saucelabs", "lambdatest", "pcloudy", "generic"}
    )


@pytest.mark.parametrize(
    ("provider", "namespace", "url", "user_key"),
    [
        ("browserstack", "bstack:options", "https://hub.browserstack.com/wd/hub", "userName"),
        ("saucelabs", "sauce:options", "https://ondemand.us-west-1.saucelabs.com/wd/hub", "username"),
        ("lambdatest", "LT:Options", "https://mobile-hub.lambdatest.com/wd/hub", "user"),
        ("pcloudy", "pCloudy_Options", "https://device.pcloudy.com/appiumcloud/wd/hub", "username"),
    ],
)
def test_provider_registry(provider, namespace, url, user_key):
    prov = get_provider(provider)
    assert prov.capability_namespace == namespace
    assert prov.default_hub_url == url
    assert prov.username_key == user_key


def test_get_provider_case_insensitive():
    assert get_provider("BrowserStack").name == "browserstack"


def test_get_provider_unknown_raises():
    with pytest.raises(CloudConfigError, match="Unknown cloud provider"):
        get_provider("nope")


# ---------------------------------------------------------------------------
# Hub URL resolution
# ---------------------------------------------------------------------------

def test_hub_url_default():
    assert cloud_hub_url("browserstack") == "https://hub.browserstack.com/wd/hub"


def test_hub_url_override_wins(monkeypatch):
    monkeypatch.setenv("BUBBLEGUM_CLOUD_APPIUM_URL", "https://env/wd/hub")
    assert cloud_hub_url("browserstack", override="https://explicit/wd/hub") == "https://explicit/wd/hub"


def test_hub_url_env_over_default(monkeypatch):
    monkeypatch.setenv("BUBBLEGUM_CLOUD_APPIUM_URL", "https://env/wd/hub")
    assert cloud_hub_url("saucelabs") == "https://env/wd/hub"


def test_hub_url_generic_requires_url():
    with pytest.raises(CloudConfigError, match="No Appium hub URL"):
        cloud_hub_url("generic")


def test_hub_url_generic_from_override():
    assert cloud_hub_url("generic", override="https://my/wd/hub") == "https://my/wd/hub"


# ---------------------------------------------------------------------------
# Credential resolution
# ---------------------------------------------------------------------------

def test_credentials_explicit():
    assert resolve_credentials("browserstack", username="u", access_key="k") == ("u", "k")


def test_credentials_common_env(monkeypatch):
    monkeypatch.setenv("BUBBLEGUM_CLOUD_USERNAME", "envuser")
    monkeypatch.setenv("BUBBLEGUM_CLOUD_ACCESS_KEY", "envkey")
    assert resolve_credentials("saucelabs") == ("envuser", "envkey")


def test_credentials_provider_env_fallback(monkeypatch):
    monkeypatch.setenv("BROWSERSTACK_USERNAME", "bsuser")
    monkeypatch.setenv("BROWSERSTACK_ACCESS_KEY", "bskey")
    assert resolve_credentials("browserstack") == ("bsuser", "bskey")


def test_credentials_common_env_precedes_provider_env(monkeypatch):
    monkeypatch.setenv("BUBBLEGUM_CLOUD_USERNAME", "common")
    monkeypatch.setenv("BROWSERSTACK_USERNAME", "provider")
    monkeypatch.setenv("BUBBLEGUM_CLOUD_ACCESS_KEY", "ckey")
    assert resolve_credentials("browserstack")[0] == "common"


def test_credentials_missing_username_raises():
    with pytest.raises(CloudConfigError, match="Missing cloud username"):
        resolve_credentials("browserstack", access_key="k")


def test_credentials_missing_access_key_raises():
    with pytest.raises(CloudConfigError, match="Missing cloud access key"):
        resolve_credentials("browserstack", username="u")


# ---------------------------------------------------------------------------
# Provider options block
# ---------------------------------------------------------------------------

def test_options_block_credentials_and_metadata():
    block = provider_options_block(
        "lambdatest", username="u", access_key="k", session_name="Smoke", build_name="CI #1"
    )
    assert block == {"user": "u", "accessKey": "k", "name": "Smoke", "build": "CI #1"}


def test_options_block_session_name_key_per_provider():
    bstack = provider_options_block("browserstack", username="u", access_key="k", session_name="S")
    assert bstack["sessionName"] == "S"
    sauce = provider_options_block("saucelabs", username="u", access_key="k", session_name="S")
    assert sauce["name"] == "S"


def test_options_block_generic_has_no_credentials():
    assert provider_options_block("generic") == {}


def test_options_block_generic_extra_only():
    assert provider_options_block("generic", extra={"foo": "bar"}) == {"foo": "bar"}


# ---------------------------------------------------------------------------
# build_cloud_capabilities
# ---------------------------------------------------------------------------

def test_build_android_with_app():
    caps = build_cloud_capabilities(
        "browserstack",
        platform="android",
        device_name="Google Pixel 8",
        app="bs://abc",
        username="u",
        access_key="k",
        session_name="Login",
        build_name="CI #9",
    )
    assert caps["platformName"] == "Android"
    assert caps["appium:platformName"] == "Android"
    assert caps["appium:deviceName"] == "Google Pixel 8"
    assert caps["appium:automationName"] == "UiAutomator2"
    assert caps["appium:app"] == "bs://abc"
    assert caps["bstack:options"] == {
        "userName": "u",
        "accessKey": "k",
        "sessionName": "Login",
        "build": "CI #9",
    }


def test_build_ios_with_bundle_id():
    caps = build_cloud_capabilities(
        "saucelabs",
        platform="ios",
        device_name="iPhone 15",
        bundle_id="com.example.app",
        platform_version="17.0",
        username="u",
        access_key="k",
    )
    assert caps["platformName"] == "iOS"
    assert caps["appium:automationName"] == "XCUITest"
    assert caps["appium:bundleId"] == "com.example.app"
    assert caps["appium:platformVersion"] == "17.0"


def test_build_android_package_activity():
    caps = build_cloud_capabilities(
        "lambdatest",
        platform="android",
        device_name="Pixel 7",
        app_package="com.example",
        app_activity=".Main",
        username="u",
        access_key="k",
    )
    assert caps["appium:appPackage"] == "com.example"
    assert caps["appium:appActivity"] == ".Main"


def test_build_uses_env_credentials(monkeypatch):
    monkeypatch.setenv("BUBBLEGUM_CLOUD_USERNAME", "envu")
    monkeypatch.setenv("BUBBLEGUM_CLOUD_ACCESS_KEY", "envk")
    caps = build_cloud_capabilities(
        "browserstack", platform="android", device_name="Pixel", app="bs://x"
    )
    assert caps["bstack:options"]["userName"] == "envu"


def test_build_automation_name_override():
    caps = build_cloud_capabilities(
        "browserstack",
        platform="android",
        device_name="Pixel",
        app="bs://x",
        automation_name="Espresso",
        username="u",
        access_key="k",
    )
    assert caps["appium:automationName"] == "Espresso"


def test_build_extra_caps_override_top_level():
    caps = build_cloud_capabilities(
        "browserstack",
        platform="android",
        device_name="Pixel",
        app="bs://x",
        username="u",
        access_key="k",
        extra_caps={"appium:autoGrantPermissions": True, "platformName": "Android"},
    )
    assert caps["appium:autoGrantPermissions"] is True


def test_build_provider_options_merge():
    caps = build_cloud_capabilities(
        "browserstack",
        platform="android",
        device_name="Pixel",
        app="bs://x",
        username="u",
        access_key="k",
        provider_options={"local": True, "debug": "true"},
    )
    assert caps["bstack:options"]["local"] is True
    assert caps["bstack:options"]["debug"] == "true"


def test_build_generic_no_namespace():
    caps = build_cloud_capabilities(
        "generic", platform="android", device_name="Pixel", app="bs://x"
    )
    assert "appium:options" not in caps


def test_build_invalid_platform():
    with pytest.raises(CloudConfigError, match="Unsupported platform"):
        build_cloud_capabilities("browserstack", platform="windows", device_name="x", app="a")


def test_build_missing_device_name():
    with pytest.raises(CloudConfigError, match="device_name is required"):
        build_cloud_capabilities("browserstack", platform="android", device_name="", app="a")


def test_build_no_app_strategy():
    with pytest.raises(CloudConfigError, match="No app-launch strategy"):
        build_cloud_capabilities(
            "browserstack", platform="android", device_name="Pixel", username="u", access_key="k"
        )


def test_build_package_without_activity():
    with pytest.raises(CloudConfigError, match="requires app_activity"):
        build_cloud_capabilities(
            "browserstack",
            platform="android",
            device_name="Pixel",
            app_package="com.example",
            username="u",
            access_key="k",
        )


def test_build_bundle_id_on_android_rejected():
    with pytest.raises(CloudConfigError, match="iOS-only"):
        build_cloud_capabilities(
            "browserstack",
            platform="android",
            device_name="Pixel",
            bundle_id="com.example",
            username="u",
            access_key="k",
        )


def test_build_package_on_ios_rejected():
    with pytest.raises(CloudConfigError, match="Android-only"):
        build_cloud_capabilities(
            "saucelabs",
            platform="ios",
            device_name="iPhone",
            app_package="com.example",
            app_activity=".Main",
            username="u",
            access_key="k",
        )


# ---------------------------------------------------------------------------
# apply_cloud_options
# ---------------------------------------------------------------------------

def test_apply_cloud_options_enriches_existing_caps():
    base = {"platformName": "Android", "appium:deviceName": "Pixel", "appium:app": "bs://x"}
    out = apply_cloud_options("browserstack", base, username="u", access_key="k", session_name="S")
    assert out["bstack:options"] == {"userName": "u", "accessKey": "k", "sessionName": "S"}
    # input not mutated
    assert "bstack:options" not in base


def test_apply_cloud_options_preserves_caller_namespace_values():
    base = {"bstack:options": {"local": True, "userName": "preset"}}
    out = apply_cloud_options("browserstack", base, username="u", access_key="k")
    # caller-provided namespace values win over generated ones
    assert out["bstack:options"]["userName"] == "preset"
    assert out["bstack:options"]["local"] is True
    assert out["bstack:options"]["accessKey"] == "k"


def test_apply_cloud_options_generic_noop():
    base = {"platformName": "Android"}
    out = apply_cloud_options("generic", base)
    assert out == base
