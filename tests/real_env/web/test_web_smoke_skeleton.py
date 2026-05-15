import pytest

from tests.real_env.conftest import require_target_env


@pytest.mark.real_env
@pytest.mark.web_smoke
def test_web_smoke_harness_gate_only() -> None:
    require_target_env("web")
    assert True
