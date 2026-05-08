from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from bubblegum.core.config import BubblegumConfig
from bubblegum.core.schemas import ContextRequest, ResolvedTarget, StepIntent, UIContext
from bubblegum.core.sdk import act, clear_vision_provider, configure_runtime, configure_vision_provider


def _run_async(coro):
    return asyncio.run(coro)


class _Adapter:
    def __init__(self, screenshot: bytes | None = b"png"):
        self._screenshot_bytes = screenshot
        self.requests: list[ContextRequest] = []

    async def collect_context(self, request: ContextRequest) -> UIContext:
        self.requests.append(request)
        return UIContext(a11y_snapshot='- button "Login"', screenshot=self._screenshot_bytes, screen_signature="abc")

    async def execute(self, plan, target):
        return SimpleNamespace(success=True, error=None)

    async def screenshot(self):
        raise RuntimeError("no artifact in unit stub")


class _Engine:
    def __init__(self):
        self.last_intent: StepIntent | None = None

    async def ground(self, intent: StepIntent):
        self.last_intent = intent
        return ResolvedTarget(ref='role=button[name="Login"]', confidence=0.9, resolver_name="exact_text", metadata={"safe": True}), []


class _Provider:
    def __init__(self, *, raises: bool = False):
        self.calls = 0
        self.raises = raises

    def detect_targets(self, image_bytes: bytes, instruction: str, context=None):
        self.calls += 1
        if self.raises:
            raise RuntimeError("boom")
        return [{"label": "Login", "bbox": [1, 2, 3, 4], "confidence": 0.8, "role": "button"}]


def _patch_sdk(monkeypatch, screenshot: bytes | None = b"png"):
    import bubblegum.core.sdk as sdk

    engine = _Engine()
    adapter = _Adapter(screenshot=screenshot)
    monkeypatch.setattr(sdk, "_engine", engine)
    monkeypatch.setattr(sdk, "_memory_cache", SimpleNamespace(record_success=lambda *args, **kwargs: None))
    monkeypatch.setattr(sdk, "_get_adapter", lambda *args, **kwargs: adapter)
    return sdk, engine, adapter


def _reset_sdk():
    clear_vision_provider()
    configure_runtime(config=BubblegumConfig())


def test_configure_vision_provider_registers_provider(monkeypatch):
    _, _, adapter = _patch_sdk(monkeypatch)
    provider = _Provider()
    configure_vision_provider(provider)
    configure_runtime(config=BubblegumConfig())

    assert provider.calls == 0
    assert adapter.requests == []
    _reset_sdk()


def test_clear_vision_provider_clears_registration(monkeypatch):
    _patch_sdk(monkeypatch)
    provider = _Provider()
    configure_vision_provider(provider)
    clear_vision_provider()
    cfg = BubblegumConfig.model_validate({"grounding": {"enable_vision": True}, "privacy": {"send_screenshots": True, "process_screenshots_for_vision": True}})
    configure_runtime(config=cfg)

    _run_async(act("Click Login", page=object(), max_cost_level="high"))

    assert provider.calls == 0
    _reset_sdk()


def test_clear_vision_provider_is_idempotent():
    clear_vision_provider()
    clear_vision_provider()


def test_invalid_provider_raises_clear_error():
    with pytest.raises(TypeError, match="detect_targets"):
        configure_vision_provider(object())


def test_registered_provider_used_only_when_all_gates_pass(monkeypatch):
    _, _, adapter = _patch_sdk(monkeypatch)
    provider = _Provider()
    configure_vision_provider(provider)

    cfg = BubblegumConfig.model_validate({"grounding": {"enable_vision": True}, "privacy": {"send_screenshots": True, "process_screenshots_for_vision": True}})
    configure_runtime(config=cfg)

    _run_async(act("Click Login", page=object(), max_cost_level="high"))

    assert adapter.requests[-1].include_screenshot is True
    assert provider.calls == 1
    _reset_sdk()


def test_registered_provider_not_invoked_when_cost_low(monkeypatch):
    _, _, adapter = _patch_sdk(monkeypatch)
    provider = _Provider()
    configure_vision_provider(provider)
    cfg = BubblegumConfig.model_validate({"grounding": {"enable_vision": True}, "privacy": {"send_screenshots": True, "process_screenshots_for_vision": True}})
    configure_runtime(config=cfg)

    _run_async(act("Click Login", page=object(), max_cost_level="low"))

    assert adapter.requests[-1].include_screenshot is False
    assert provider.calls == 0
    _reset_sdk()


def test_registered_provider_not_invoked_when_cost_medium(monkeypatch):
    _, _, adapter = _patch_sdk(monkeypatch)
    provider = _Provider()
    configure_vision_provider(provider)
    cfg = BubblegumConfig.model_validate({"grounding": {"enable_vision": True}, "privacy": {"send_screenshots": True, "process_screenshots_for_vision": True}})
    configure_runtime(config=cfg)

    _run_async(act("Click Login", page=object(), max_cost_level="medium"))

    assert adapter.requests[-1].include_screenshot is False
    assert provider.calls == 0
    _reset_sdk()


def test_registered_provider_invoked_when_cost_high(monkeypatch):
    _, _, adapter = _patch_sdk(monkeypatch)
    provider = _Provider()
    configure_vision_provider(provider)
    cfg = BubblegumConfig.model_validate({"grounding": {"enable_vision": True}, "privacy": {"send_screenshots": True, "process_screenshots_for_vision": True}})
    configure_runtime(config=cfg)

    _run_async(act("Click Login", page=object(), max_cost_level="high"))

    assert adapter.requests[-1].include_screenshot is True
    assert provider.calls == 1
    _reset_sdk()


def test_manual_candidates_prevent_provider_invocation(monkeypatch):
    sdk, engine, _ = _patch_sdk(monkeypatch)
    provider = _Provider()
    configure_vision_provider(provider)
    cfg = BubblegumConfig.model_validate({"grounding": {"enable_vision": True}, "privacy": {"send_screenshots": True, "process_screenshots_for_vision": True}})
    configure_runtime(config=cfg)
    sdk._engine = engine

    original_make_intent = sdk.make_intent

    def _patched_make_intent(*args, **kwargs):
        intent = original_make_intent(*args, **kwargs)
        intent.context["vision_candidates"] = [{"label": "Manual", "bbox": [9, 9, 9, 9], "confidence": 0.9}]
        return intent

    monkeypatch.setattr(sdk, "make_intent", _patched_make_intent)
    _run_async(act("Click Login", page=object()))

    assert provider.calls == 0
    assert engine.last_intent is not None
    assert engine.last_intent.context["vision_candidates"][0]["label"] == "Manual"
    _reset_sdk()


def test_provider_exception_fails_safe(monkeypatch):
    _, engine, _ = _patch_sdk(monkeypatch)
    provider = _Provider(raises=True)
    configure_vision_provider(provider)
    cfg = BubblegumConfig.model_validate({"grounding": {"enable_vision": True}, "privacy": {"send_screenshots": True, "process_screenshots_for_vision": True}})
    configure_runtime(config=cfg)

    result = _run_async(act("Click Login", page=object(), max_cost_level="high"))

    assert result.status == "passed"
    assert provider.calls == 1
    assert "vision_candidates" not in (engine.last_intent.context if engine.last_intent else {})
    _reset_sdk()


def test_no_raw_screenshot_persistence(monkeypatch):
    _patch_sdk(monkeypatch)
    provider = _Provider()
    configure_vision_provider(provider)
    cfg = BubblegumConfig.model_validate({"grounding": {"enable_vision": True}, "privacy": {"send_screenshots": True, "process_screenshots_for_vision": True}})
    configure_runtime(config=cfg)

    result = _run_async(act("Click Login", page=object()))

    assert result.target is not None
    assert "screenshot" not in result.target.metadata
    assert all("screenshot" not in str(t).lower() for t in (result.traces or []))
    _reset_sdk()


def test_public_api_exports_include_registration_functions():
    import bubblegum

    assert hasattr(bubblegum, "configure_vision_provider")
    assert hasattr(bubblegum, "clear_vision_provider")
