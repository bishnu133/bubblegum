from __future__ import annotations

import asyncio
from types import SimpleNamespace

from bubblegum.core.config import BubblegumConfig
from bubblegum.core.schemas import ContextRequest, ResolvedTarget, StepIntent, UIContext
from bubblegum.core.sdk import act, configure_runtime, _set_vision_provider_for_testing


def _run_async(coro):
    return asyncio.run(coro)


class _Adapter:
    def __init__(self, screenshot: bytes | None = None):
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
        md = {"safe": True}
        if intent.context.get("vision_candidates"):
            md["vision_source"] = "injected"
        return ResolvedTarget(ref='role=button[name="Login"]', confidence=0.9, resolver_name="exact_text", metadata=md), []


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
    _set_vision_provider_for_testing(None)
    configure_runtime(config=BubblegumConfig())


def test_default_config_no_screenshot_request_no_provider_call(monkeypatch):
    _, _, adapter = _patch_sdk(monkeypatch)
    provider = _Provider()
    _set_vision_provider_for_testing(provider)
    configure_runtime(config=BubblegumConfig())

    _run_async(act("Click Login", page=object(), max_cost_level="high"))

    assert adapter.requests[-1].include_screenshot is False
    assert provider.calls == 0
    _reset_sdk()


def test_enable_vision_alone_does_not_invoke_provider(monkeypatch):
    _patch_sdk(monkeypatch)
    provider = _Provider()
    _set_vision_provider_for_testing(provider)
    cfg = BubblegumConfig.model_validate({"grounding": {"enable_vision": True}})
    configure_runtime(config=cfg)

    _run_async(act("Click Login", page=object(), max_cost_level="high"))
    assert provider.calls == 0
    _reset_sdk()


def test_send_screenshots_without_process_flag_does_not_invoke_provider(monkeypatch):
    _patch_sdk(monkeypatch)
    provider = _Provider()
    _set_vision_provider_for_testing(provider)
    cfg = BubblegumConfig.model_validate({"grounding": {"enable_vision": True}, "privacy": {"send_screenshots": True, "process_screenshots_for_vision": False}})
    configure_runtime(config=cfg)

    _run_async(act("Click Login", page=object(), max_cost_level="high"))
    assert provider.calls == 0
    _reset_sdk()


def test_all_gates_true_without_provider_is_safe(monkeypatch):
    _, engine, adapter = _patch_sdk(monkeypatch)
    _set_vision_provider_for_testing(None)
    cfg = BubblegumConfig.model_validate({"grounding": {"enable_vision": True}, "privacy": {"send_screenshots": True, "process_screenshots_for_vision": True}})
    configure_runtime(config=cfg)

    result = _run_async(act("Click Login", page=object(), max_cost_level="high"))

    assert result.status == "passed"
    assert adapter.requests[-1].include_screenshot is False
    assert "vision_candidates" not in (engine.last_intent.context if engine.last_intent else {})
    _reset_sdk()


def test_all_gates_true_with_provider_injects_candidates(monkeypatch):
    _, engine, adapter = _patch_sdk(monkeypatch)
    provider = _Provider()
    _set_vision_provider_for_testing(provider)
    cfg = BubblegumConfig.model_validate({"grounding": {"enable_vision": True}, "privacy": {"send_screenshots": True, "process_screenshots_for_vision": True}})
    configure_runtime(config=cfg)
    import bubblegum.core.sdk as sdk
    sdk._engine = engine

    _run_async(act("Click Login", page=object(), max_cost_level="high"))

    assert adapter.requests[-1].include_screenshot is True
    assert provider.calls == 1
    assert engine.last_intent is not None
    assert "vision_candidates" in engine.last_intent.context
    _reset_sdk()


def test_low_cost_level_blocks_provider_and_screenshot_request(monkeypatch):
    _, _, adapter = _patch_sdk(monkeypatch)
    provider = _Provider()
    _set_vision_provider_for_testing(provider)
    cfg = BubblegumConfig.model_validate({"grounding": {"enable_vision": True}, "privacy": {"send_screenshots": True, "process_screenshots_for_vision": True}})
    configure_runtime(config=cfg)

    _run_async(act("Click Login", page=object(), max_cost_level="low"))

    assert adapter.requests[-1].include_screenshot is False
    assert provider.calls == 0
    _reset_sdk()


def test_medium_cost_level_blocks_provider_and_screenshot_request(monkeypatch):
    _, _, adapter = _patch_sdk(monkeypatch)
    provider = _Provider()
    _set_vision_provider_for_testing(provider)
    cfg = BubblegumConfig.model_validate({"grounding": {"enable_vision": True}, "privacy": {"send_screenshots": True, "process_screenshots_for_vision": True}})
    configure_runtime(config=cfg)

    _run_async(act("Click Login", page=object(), max_cost_level="medium"))

    assert adapter.requests[-1].include_screenshot is False
    assert provider.calls == 0
    _reset_sdk()


def test_high_cost_level_allows_provider_and_screenshot_request(monkeypatch):
    _, _, adapter = _patch_sdk(monkeypatch)
    provider = _Provider()
    _set_vision_provider_for_testing(provider)
    cfg = BubblegumConfig.model_validate({"grounding": {"enable_vision": True}, "privacy": {"send_screenshots": True, "process_screenshots_for_vision": True}})
    configure_runtime(config=cfg)

    _run_async(act("Click Login", page=object(), max_cost_level="high"))

    assert adapter.requests[-1].include_screenshot is True
    assert provider.calls == 1
    _reset_sdk()


def test_existing_manual_vision_candidates_not_overwritten(monkeypatch):
    _, engine, _ = _patch_sdk(monkeypatch)
    provider = _Provider()
    _set_vision_provider_for_testing(provider)
    cfg = BubblegumConfig.model_validate({"grounding": {"enable_vision": True}, "privacy": {"send_screenshots": True, "process_screenshots_for_vision": True}})
    configure_runtime(config=cfg)

    import bubblegum.core.sdk as sdk
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


def test_manual_candidates_preserved_when_cost_low(monkeypatch):
    _, engine, adapter = _patch_sdk(monkeypatch)
    provider = _Provider()
    _set_vision_provider_for_testing(provider)
    cfg = BubblegumConfig.model_validate({"grounding": {"enable_vision": True}, "privacy": {"send_screenshots": True, "process_screenshots_for_vision": True}})
    configure_runtime(config=cfg)

    import bubblegum.core.sdk as sdk
    sdk._engine = engine
    original_make_intent = sdk.make_intent

    def _patched_make_intent(*args, **kwargs):
        intent = original_make_intent(*args, **kwargs)
        intent.context["vision_candidates"] = [{"label": "Manual", "bbox": [9, 9, 9, 9], "confidence": 0.9}]
        return intent

    monkeypatch.setattr(sdk, "make_intent", _patched_make_intent)
    _run_async(act("Click Login", page=object(), max_cost_level="low"))

    assert adapter.requests[-1].include_screenshot is False
    assert provider.calls == 0
    assert engine.last_intent is not None
    assert engine.last_intent.context["vision_candidates"][0]["label"] == "Manual"
    _reset_sdk()


def test_provider_exception_fails_safe(monkeypatch):
    _, engine, _ = _patch_sdk(monkeypatch)
    provider = _Provider(raises=True)
    _set_vision_provider_for_testing(provider)
    cfg = BubblegumConfig.model_validate({"grounding": {"enable_vision": True}, "privacy": {"send_screenshots": True, "process_screenshots_for_vision": True}})
    configure_runtime(config=cfg)

    result = _run_async(act("Click Login", page=object(), max_cost_level="high"))

    assert result.status == "passed"
    assert provider.calls == 1
    assert "vision_candidates" not in (engine.last_intent.context if engine.last_intent else {})
    _reset_sdk()


def test_raw_screenshot_not_stored_in_traces_or_target_metadata(monkeypatch):
    _patch_sdk(monkeypatch)
    provider = _Provider()
    _set_vision_provider_for_testing(provider)
    cfg = BubblegumConfig.model_validate({"grounding": {"enable_vision": True}, "privacy": {"send_screenshots": True, "process_screenshots_for_vision": True}})
    configure_runtime(config=cfg)

    result = _run_async(act("Click Login", page=object()))

    assert result.target is not None
    assert "screenshot" not in result.target.metadata
    assert all("screenshot" not in str(t).lower() for t in (result.traces or []))
    _reset_sdk()


def test_public_api_exports_unchanged():
    import bubblegum

    for name in ("act", "verify", "recover", "extract", "configure_runtime"):
        assert hasattr(bubblegum, name)
