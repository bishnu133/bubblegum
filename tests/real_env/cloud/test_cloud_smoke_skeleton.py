import pytest

from tests.real_env.conftest import require_target_env


@pytest.mark.real_env
@pytest.mark.cloud_device
@pytest.mark.web_smoke
@pytest.mark.slow
def test_cloud_smoke_harness_gate_only() -> None:
    require_target_env("cloud")
    assert True
