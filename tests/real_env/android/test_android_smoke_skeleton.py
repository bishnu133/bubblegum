import pytest

from tests.real_env.conftest import require_target_env


@pytest.mark.real_env
@pytest.mark.android_emulator
@pytest.mark.android_device
@pytest.mark.hybrid_webview
@pytest.mark.system_dialog
@pytest.mark.slow
def test_android_smoke_harness_gate_only() -> None:
    require_target_env("android")
    assert True
