"""Default-safe end-to-end scaffold for Phase 3C.

This e2e scaffold is deterministic and uses only local fake objects. No browser,
mobile automation, LLM, OCR, vision, or network dependencies are used.
"""

from __future__ import annotations


class FakeSDK:
    def __init__(self) -> None:
        self._state = {"clicked": False}

    def act(self, instruction: str) -> dict:
        if instruction == "Click Login":
            self._state["clicked"] = True
            return {"status": "passed", "action": instruction}
        return {"status": "failed", "action": instruction}

    def verify(self, instruction: str) -> dict:
        if instruction == "Login was clicked" and self._state["clicked"]:
            return {"passed": True}
        return {"passed": False}


def test_e2e_scaffold_happy_path_is_deterministic():
    sdk = FakeSDK()
    act_result = sdk.act("Click Login")
    verify_result = sdk.verify("Login was clicked")

    assert act_result["status"] == "passed"
    assert verify_result["passed"] is True


def test_e2e_scaffold_failure_path_is_deterministic():
    sdk = FakeSDK()
    act_result = sdk.act("Click Missing Button")
    verify_result = sdk.verify("Login was clicked")

    assert act_result["status"] == "failed"
    assert verify_result["passed"] is False
