from __future__ import annotations

import pytest

from tests.real_env.cloud.harness import build_cloud_harness_config


@pytest.mark.parametrize(
    ("provider", "expected_namespace", "expected_url"),
    [
        ("pcloudy", "pCloudy_Options", "https://device.pcloudy.com/appiumcloud/wd/hub"),
        ("browserstack", "bstack:options", "https://hub.browserstack.com/wd/hub"),
        ("saucelabs", "sauce:options", "https://ondemand.us-west-1.saucelabs.com/wd/hub"),
        ("lambdatest", "LT:Options", "https://mobile-hub.lambdatest.com/wd/hub"),
    ],
)
def test_cloud_harness_maps_supported_providers(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    expected_namespace: str,
    expected_url: str,
) -> None:
    monkeypatch.setenv("BUBBLEGUM_CLOUD_PROVIDER", provider)
    monkeypatch.setenv("BUBBLEGUM_CLOUD_USERNAME", "user")
    monkeypatch.setenv("BUBBLEGUM_CLOUD_ACCESS_KEY", "key")
    monkeypatch.delenv("BUBBLEGUM_APPIUM_SERVER_URL", raising=False)

    config = build_cloud_harness_config()

    assert config.provider == provider
    assert config.capability_namespace == expected_namespace
    assert config.appium_server_url == expected_url


def test_cloud_harness_generic_requires_appium_server_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BUBBLEGUM_CLOUD_PROVIDER", "generic")
    monkeypatch.setenv("BUBBLEGUM_CLOUD_USERNAME", "user")
    monkeypatch.setenv("BUBBLEGUM_CLOUD_ACCESS_KEY", "key")
    monkeypatch.delenv("BUBBLEGUM_APPIUM_SERVER_URL", raising=False)

    with pytest.raises(pytest.skip.Exception):
        build_cloud_harness_config()


def test_cloud_harness_rejects_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BUBBLEGUM_CLOUD_PROVIDER", "some-vendor")

    with pytest.raises(pytest.skip.Exception):
        build_cloud_harness_config()


def test_cloud_harness_prefers_cloud_appium_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BUBBLEGUM_CLOUD_PROVIDER", "browserstack")
    monkeypatch.setenv("BUBBLEGUM_CLOUD_APPIUM_URL", "https://example-cloud/wd/hub")
    monkeypatch.setenv("BUBBLEGUM_APPIUM_SERVER_URL", "https://example-fallback/wd/hub")

    config = build_cloud_harness_config()

    assert config.appium_server_url == "https://example-cloud/wd/hub"
