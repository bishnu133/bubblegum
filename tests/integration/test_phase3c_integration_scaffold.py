"""Default-safe integration scaffold for Phase 3C.

This module intentionally avoids real Playwright/Appium/LLM/OCR/Vision/network
usage. It validates integration-style contracts using deterministic fakes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FakeContext:
    a11y_snapshot: str
    screen_signature: str


class FakeAdapter:
    def collect_context(self) -> FakeContext:
        return FakeContext(
            a11y_snapshot='- button "Login"',
            screen_signature='screen:web:login:v1',
        )

    def execute(self, target_ref: str) -> bool:
        return target_ref == 'role=button[name="Login"]'


class FakeResolver:
    name = "fake_resolver"

    def resolve(self, instruction: str, ctx: FakeContext) -> str | None:
        if "login" in instruction.lower() and "Login" in ctx.a11y_snapshot:
            return 'role=button[name="Login"]'
        return None


def _run_flow(instruction: str) -> dict:
    adapter = FakeAdapter()
    resolver = FakeResolver()

    ctx = adapter.collect_context()
    target_ref = resolver.resolve(instruction, ctx)

    if target_ref is None:
        return {"status": "failed", "resolver": resolver.name, "target_ref": None}

    ok = adapter.execute(target_ref)
    return {
        "status": "passed" if ok else "failed",
        "resolver": resolver.name,
        "target_ref": target_ref,
        "screen_signature": ctx.screen_signature,
    }


def test_scaffold_integration_flow_passes_deterministically():
    result = _run_flow("Click Login")
    assert result["status"] == "passed"
    assert result["resolver"] == "fake_resolver"
    assert result["target_ref"].startswith("role=button")


def test_scaffold_integration_flow_reports_failure_for_missing_intent():
    result = _run_flow("Click Delete Account")
    assert result["status"] == "failed"
    assert result["target_ref"] is None
