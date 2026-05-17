from __future__ import annotations

import pytest

from tests.real_env.cloud.harness import build_cloud_capabilities, build_cloud_harness_config, cloud_config_safe_summary


def _set_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUBBLEGUM_CLOUD_USERNAME", "user")
    monkeypatch.setenv("BUBBLEGUM_CLOUD_ACCESS_KEY", "key")
    monkeypatch.setenv("BUBBLEGUM_CLOUD_PLATFORM", "android")
    monkeypatch.setenv("BUBBLEGUM_CLOUD_DEVICE_NAME", "Pixel 8")
    monkeypatch.setenv("BUBBLEGUM_CLOUD_APP", "bs://app")


@pytest.mark.parametrize(
    ("provider", "expected_namespace", "expected_url", "user_key"),
    [
        ("pcloudy", "pCloudy_Options", "https://device.pcloudy.com/appiumcloud/wd/hub", "username"),
        ("browserstack", "bstack:options", "https://hub.browserstack.com/wd/hub", "userName"),
        ("saucelabs", "sauce:options", "https://ondemand.us-west-1.saucelabs.com/wd/hub", "username"),
        ("lambdatest", "LT:Options", "https://mobile-hub.lambdatest.com/wd/hub", "user"),
    ],
)
def test_cloud_harness_maps_supported_providers(monkeypatch, provider, expected_namespace, expected_url, user_key):
    monkeypatch.setenv("BUBBLEGUM_CLOUD_PROVIDER", provider)
    monkeypatch.delenv("BUBBLEGUM_APPIUM_SERVER_URL", raising=False)
    _set_required_env(monkeypatch)

    config = build_cloud_harness_config()
    caps = build_cloud_capabilities()

    assert config.provider == provider
    assert config.capability_namespace == expected_namespace
    assert config.appium_server_url == expected_url
    assert expected_namespace in caps
    assert caps[expected_namespace][user_key] == "user"


def test_generic_has_no_provider_namespace(monkeypatch):
    monkeypatch.setenv("BUBBLEGUM_CLOUD_PROVIDER", "generic")
    monkeypatch.setenv("BUBBLEGUM_CLOUD_APPIUM_URL", "https://generic/wd/hub")
    _set_required_env(monkeypatch)
    caps = build_cloud_capabilities()
    assert "appium:options" not in caps


def test_cloud_harness_generic_requires_appium_server_url(monkeypatch):
    monkeypatch.setenv("BUBBLEGUM_CLOUD_PROVIDER", "generic")
    monkeypatch.delenv("BUBBLEGUM_CLOUD_APPIUM_URL", raising=False)
    monkeypatch.delenv("BUBBLEGUM_APPIUM_SERVER_URL", raising=False)
    with pytest.raises(pytest.skip.Exception):
        build_cloud_harness_config()


def test_cloud_harness_rejects_missing_provider(monkeypatch):
    monkeypatch.delenv("BUBBLEGUM_CLOUD_PROVIDER", raising=False)
    with pytest.raises(pytest.skip.Exception):
        build_cloud_harness_config()


def test_cloud_harness_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("BUBBLEGUM_CLOUD_PROVIDER", "some-vendor")
    with pytest.raises(pytest.skip.Exception):
        build_cloud_harness_config()


def test_cloud_harness_prefers_cloud_appium_url(monkeypatch):
    monkeypatch.setenv("BUBBLEGUM_CLOUD_PROVIDER", "browserstack")
    monkeypatch.setenv("BUBBLEGUM_CLOUD_APPIUM_URL", "https://example-cloud/wd/hub")
    monkeypatch.setenv("BUBBLEGUM_APPIUM_SERVER_URL", "https://example-fallback/wd/hub")
    config = build_cloud_harness_config()
    assert config.appium_server_url == "https://example-cloud/wd/hub"


def test_cloud_harness_uses_appium_fallback_url(monkeypatch):
    monkeypatch.setenv("BUBBLEGUM_CLOUD_PROVIDER", "browserstack")
    monkeypatch.delenv("BUBBLEGUM_CLOUD_APPIUM_URL", raising=False)
    monkeypatch.setenv("BUBBLEGUM_APPIUM_SERVER_URL", "https://example-fallback/wd/hub")
    config = build_cloud_harness_config()
    assert config.appium_server_url == "https://example-fallback/wd/hub"


@pytest.mark.parametrize(
    "missing_key",
    ["BUBBLEGUM_CLOUD_USERNAME", "BUBBLEGUM_CLOUD_ACCESS_KEY", "BUBBLEGUM_CLOUD_DEVICE_NAME"],
)
def test_required_env_validation(monkeypatch, missing_key):
    monkeypatch.setenv("BUBBLEGUM_CLOUD_PROVIDER", "browserstack")
    _set_required_env(monkeypatch)
    monkeypatch.delenv(missing_key, raising=False)
    with pytest.raises(pytest.skip.Exception):
        build_cloud_capabilities()


def test_missing_platform(monkeypatch):
    monkeypatch.setenv("BUBBLEGUM_CLOUD_PROVIDER", "browserstack")
    _set_required_env(monkeypatch)
    monkeypatch.delenv("BUBBLEGUM_CLOUD_PLATFORM", raising=False)
    with pytest.raises(pytest.skip.Exception):
        build_cloud_capabilities()


def test_invalid_platform(monkeypatch):
    monkeypatch.setenv("BUBBLEGUM_CLOUD_PROVIDER", "browserstack")
    _set_required_env(monkeypatch)
    monkeypatch.setenv("BUBBLEGUM_CLOUD_PLATFORM", "windows")
    with pytest.raises(pytest.skip.Exception):
        build_cloud_capabilities()


def test_missing_app_launch_selector(monkeypatch):
    monkeypatch.setenv("BUBBLEGUM_CLOUD_PROVIDER", "browserstack")
    _set_required_env(monkeypatch)
    monkeypatch.delenv("BUBBLEGUM_CLOUD_APP", raising=False)
    with pytest.raises(pytest.skip.Exception):
        build_cloud_capabilities()


def test_safe_summary_excludes_secrets(monkeypatch, capsys):
    monkeypatch.setenv("BUBBLEGUM_CLOUD_PROVIDER", "browserstack")
    monkeypatch.setenv("BUBBLEGUM_CLOUD_APPIUM_URL", "https://example-cloud/wd/hub")
    _set_required_env(monkeypatch)

    summary = cloud_config_safe_summary()
    captured = capsys.readouterr()

    assert "username" not in summary
    assert "access_key" not in summary
    assert "capabilities" not in summary
    assert captured.out == ""
    assert captured.err == ""
