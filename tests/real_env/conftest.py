from __future__ import annotations

import os

import pytest

REAL_ENV_ENABLE_VAR = "BUBBLEGUM_REAL_ENV"


REQUIRED_ENV_BY_TARGET: dict[str, tuple[str, ...]] = {
    "web": (),
    "android": ("BUBBLEGUM_APPIUM_SERVER_URL", "BUBBLEGUM_ANDROID_APP"),
    "ios": ("BUBBLEGUM_APPIUM_SERVER_URL", "BUBBLEGUM_IOS_APP"),
    "cloud": (
        "BUBBLEGUM_CLOUD_PROVIDER",
        "BUBBLEGUM_CLOUD_USERNAME",
        "BUBBLEGUM_CLOUD_ACCESS_KEY",
    ),
}


def _is_real_env_enabled() -> bool:
    return os.getenv(REAL_ENV_ENABLE_VAR) == "1"


def require_real_env_enabled() -> None:
    if not _is_real_env_enabled():
        pytest.skip(
            "Real-environment smoke harness is disabled. "
            "Set BUBBLEGUM_REAL_ENV=1 to opt in."
        )


def require_target_env(target: str) -> None:
    require_real_env_enabled()

    required_vars = REQUIRED_ENV_BY_TARGET[target]
    missing = [name for name in required_vars if not os.getenv(name)]
    if missing:
        missing_list = ", ".join(missing)
        pytest.skip(
            f"Real-environment target '{target}' missing required environment "
            f"variable(s): {missing_list}."
        )


@pytest.fixture
def real_env_enabled() -> bool:
    return _is_real_env_enabled()
