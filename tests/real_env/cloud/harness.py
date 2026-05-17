from __future__ import annotations

import os
from dataclasses import dataclass

import pytest

_CLOUD_PROVIDER_ENV_VAR = "BUBBLEGUM_CLOUD_PROVIDER"

_ALLOWED_CLOUD_PROVIDERS: frozenset[str] = frozenset(
    {"pcloudy", "browserstack", "saucelabs", "lambdatest", "generic"}
)

_PROVIDER_CAPABILITY_NAMESPACE: dict[str, str] = {
    "pcloudy": "pCloudy_Options",
    "browserstack": "bstack:options",
    "saucelabs": "sauce:options",
    "lambdatest": "LT:Options",
    "generic": "appium:options",
}

_PROVIDER_DEFAULT_APPIUM_URL: dict[str, str] = {
    "pcloudy": "https://device.pcloudy.com/appiumcloud/wd/hub",
    "browserstack": "https://hub.browserstack.com/wd/hub",
    "saucelabs": "https://ondemand.us-west-1.saucelabs.com/wd/hub",
    "lambdatest": "https://mobile-hub.lambdatest.com/wd/hub",
    "generic": "",
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
    appium_server_url = os.getenv("BUBBLEGUM_APPIUM_SERVER_URL", "").strip()
    if not appium_server_url:
        appium_server_url = _PROVIDER_DEFAULT_APPIUM_URL[provider]

    if not appium_server_url:
        pytest.skip(
            "Real-environment cloud smoke harness requires BUBBLEGUM_APPIUM_SERVER_URL "
            "for provider='generic'."
        )

    return CloudHarnessConfig(
        provider=provider,
        appium_server_url=appium_server_url,
        capability_namespace=_PROVIDER_CAPABILITY_NAMESPACE[provider],
    )
