from __future__ import annotations

import asyncio
from types import SimpleNamespace

from bubblegum.core.schemas import ContextRequest, ResolvedTarget, StepIntent, UIContext


def _run_async(coro):
    return asyncio.run(coro)


class _Adapter:
    def __init__(self):
        self.executed_targets: list[ResolvedTarget] = []

    async def collect_context(self, request: ContextRequest) -> UIContext:
        return UIContext(a11y_snapshot='- button "Login"', screen_signature="abc")

    async def execute(self, plan, target):
        self.executed_targets.append(target)
        return SimpleNamespace(success=True, error=None)

    async def screenshot(self):
        raise RuntimeError("no artifact in unit stub")

    async def extract_text(self, ref: str, timeout_ms: int = 10_000):
        self.executed_targets.append(ResolvedTarget(ref=ref, confidence=1.0, resolver_name="extract_probe"))
        return "Login"


class _Engine:
    def __init__(self, ref: str, resolver_name: str = "exact_text"):
        self.ref = ref
        self.resolver_name = resolver_name

    async def ground(self, intent: StepIntent):
        return ResolvedTarget(ref=self.ref, confidence=0.9, resolver_name=self.resolver_name, metadata={}), []


def _patch_sdk(monkeypatch, *, ref: str, resolver_name: str = "exact_text"):
    import bubblegum.core.sdk as sdk

    adapter = _Adapter()
    monkeypatch.setattr(sdk, "_engine", _Engine(ref=ref, resolver_name=resolver_name))
    monkeypatch.setattr(sdk, "_memory_cache", SimpleNamespace(record_success=lambda *args, **kwargs: None))
    monkeypatch.setattr(sdk, "_get_adapter", lambda *args, **kwargs: adapter)
    return sdk, adapter


def test_sdk_does_not_execute_ocr_ref_directly(monkeypatch):
    sdk, adapter = _patch_sdk(monkeypatch, ref="ocr://block/0", resolver_name="ocr")

    result = _run_async(sdk.act("Click Login", page=object()))

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.error_type == "VisualRefHydrationError"
    assert "unsupported_visual_ref_hydration" in result.error.message
    assert adapter.executed_targets == []


def test_sdk_does_not_execute_vision_ref_directly(monkeypatch):
    sdk, adapter = _patch_sdk(monkeypatch, ref="vision://target/0", resolver_name="vision_model")

    result = _run_async(sdk.act("Click Login", page=object()))

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.error_type == "VisualRefHydrationError"
    assert "unsupported_visual_ref_hydration" in result.error.message
    assert adapter.executed_targets == []


def test_non_visual_execution_path_remains_unchanged(monkeypatch):
    sdk, adapter = _patch_sdk(monkeypatch, ref='text="Login"', resolver_name="exact_text")

    result = _run_async(sdk.act("Click Login", page=object()))

    assert result.status == "passed"
    assert len(adapter.executed_targets) == 1
    assert adapter.executed_targets[0].ref == 'text="Login"'
