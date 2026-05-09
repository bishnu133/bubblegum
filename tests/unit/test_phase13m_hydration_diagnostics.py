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
        return UIContext(a11y_snapshot='- button "Login"', screen_signature='abc')

    async def execute(self, plan, target):
        self.executed_targets.append(target)
        return SimpleNamespace(success=True, error=None)

    async def screenshot(self):
        raise RuntimeError('no artifact in unit stub')

    async def extract_text(self, ref: str, timeout_ms: int = 10_000):
        self.executed_targets.append(ResolvedTarget(ref=ref, confidence=1.0, resolver_name='extract_probe'))
        return 'Login'


class _Engine:
    def __init__(self, *, ref: str, resolver_name: str):
        self.ref = ref
        self.resolver_name = resolver_name

    async def ground(self, intent: StepIntent):
        return ResolvedTarget(ref=self.ref, confidence=0.9, resolver_name=self.resolver_name, metadata={}), []


def _patch_sdk(monkeypatch, *, ref: str, resolver_name: str):
    import bubblegum.core.sdk as sdk

    adapter = _Adapter()
    monkeypatch.setattr(sdk, '_engine', _Engine(ref=ref, resolver_name=resolver_name))
    monkeypatch.setattr(sdk, '_memory_cache', SimpleNamespace(record_success=lambda *args, **kwargs: None))
    monkeypatch.setattr(sdk, '_get_adapter', lambda *args, **kwargs: adapter)
    return sdk, adapter


def test_success_web_ocr_hydration_metadata_visible(monkeypatch):
    sdk, adapter = _patch_sdk(monkeypatch, ref='ocr://block/0', resolver_name='ocr')

    class _Hydrator:
        def hydrate(self, *, target, intent):
            hydrated = ResolvedTarget(ref='text="Login"', confidence=target.confidence, resolver_name=target.resolver_name, metadata={})
            return SimpleNamespace(status='hydrated', target=hydrated, reason='hydrated_text_ref', diagnostics={'source': 'ocr', 'strategy': 'text'}, original_ref=target.ref, hydrated_ref=hydrated.ref)

    monkeypatch.setattr(sdk, '_visual_ref_hydrator', _Hydrator())
    result = _run_async(sdk.act('Click Login', page=object()))
    assert result.status == 'passed'
    md = adapter.executed_targets[0].metadata
    assert md['hydration_status'] == 'hydrated'
    assert md['hydration_reason'] == 'hydrated_text_ref'
    assert md['hydration_source'] == 'ocr'
    assert md['hydration_strategy'] == 'text'


def test_success_web_vision_has_original_and_hydrated_ref(monkeypatch):
    sdk, adapter = _patch_sdk(monkeypatch, ref='vision://target/0', resolver_name='vision_model')

    class _Hydrator:
        def hydrate(self, *, target, intent):
            hydrated = ResolvedTarget(ref='role=button[name="Login"]', confidence=target.confidence, resolver_name=target.resolver_name, metadata={})
            return SimpleNamespace(status='hydrated', target=hydrated, reason='hydrated_visual_ref', diagnostics={'source': 'vision', 'strategy': 'role_text'}, original_ref=target.ref, hydrated_ref=hydrated.ref)

    monkeypatch.setattr(sdk, '_visual_ref_hydrator', _Hydrator())
    _run_async(sdk.act('Click Login', page=object()))
    md = adapter.executed_targets[0].metadata
    assert md['hydration_original_ref'] == 'vision://target/0'
    assert md['hydration_hydrated_ref'] == 'role=button[name="Login"]'


def test_success_mobile_hydration_has_source_strategy_match_field(monkeypatch):
    sdk, adapter = _patch_sdk(monkeypatch, ref='vision://target/0', resolver_name='vision_model')

    class _Hydrator:
        def hydrate(self, *, target, intent):
            hydrated = ResolvedTarget(ref='{"by":"xpath","value":"//*[@content-desc=\'Settings\']"}', confidence=target.confidence, resolver_name=target.resolver_name, metadata={})
            return SimpleNamespace(status='hydrated', target=hydrated, reason='hydrated_mobile_visual_ref', diagnostics={'source': 'vision', 'strategy': 'mobile_content_desc', 'match_field': 'content-desc'}, original_ref=target.ref, hydrated_ref=hydrated.ref)

    monkeypatch.setattr(sdk, '_visual_ref_hydrator', _Hydrator())
    result = _run_async(sdk.extract('Get settings', channel='mobile', driver=object()))
    md = result.target.metadata
    assert md['hydration_source'] == 'vision'
    assert md['hydration_strategy'] == 'mobile_content_desc'
    assert md['match_field'] == 'content-desc'


def test_failed_hydration_has_reason_and_original_ref(monkeypatch):
    sdk, _ = _patch_sdk(monkeypatch, ref='ocr://block/0', resolver_name='ocr')

    class _Hydrator:
        def hydrate(self, *, target, intent):
            return SimpleNamespace(status='not_hydrated', target=None, reason='unsupported_visual_ref_hydration', diagnostics={'source': 'ocr'}, original_ref=target.ref, hydrated_ref=None)

    monkeypatch.setattr(sdk, '_visual_ref_hydrator', _Hydrator())
    result = _run_async(sdk.act('Click Login', page=object()))
    assert result.status == 'failed'
    assert result.error is not None
    assert 'unsupported_visual_ref_hydration' in result.error.message
    assert 'hydration_original_ref' in result.error.message


def test_mobile_ambiguous_includes_match_count_not_hierarchy_xml(monkeypatch):
    sdk, _ = _patch_sdk(monkeypatch, ref='ocr://block/0', resolver_name='ocr')

    class _Hydrator:
        def hydrate(self, *, target, intent):
            return SimpleNamespace(status='not_hydrated', target=None, reason='mobile_visual_hydration_ambiguous_match', diagnostics={'source': 'ocr', 'match_field': 'text', 'match_count': 2}, original_ref=target.ref, hydrated_ref=None)

    monkeypatch.setattr(sdk, '_visual_ref_hydrator', _Hydrator())
    result = _run_async(sdk.act('Click Login', page=object()))
    msg = result.error.message
    assert 'match_count' in msg
    assert 'hierarchy_xml' not in msg


def test_no_match_diagnostics_safe_only(monkeypatch):
    sdk, _ = _patch_sdk(monkeypatch, ref='vision://target/0', resolver_name='vision_model')

    class _Hydrator:
        def hydrate(self, *, target, intent):
            return SimpleNamespace(status='not_hydrated', target=None, reason='mobile_visual_hydration_no_match', diagnostics={'source': 'vision', 'match_count': 0, 'screenshot_bytes': b'png', 'base64': 'abc', 'raw_payload': 'secret', 'hierarchy_xml': '<x/>'}, original_ref=target.ref, hydrated_ref=None)

    monkeypatch.setattr(sdk, '_visual_ref_hydrator', _Hydrator())
    result = _run_async(sdk.act('Click Login', page=object()))
    msg = result.error.message
    assert 'match_count' in msg
    assert 'screenshot_bytes' not in msg
    assert 'base64' not in msg
    assert 'raw_payload' not in msg
    assert 'hierarchy_xml' not in msg


def test_non_visual_path_unchanged_no_hydration_metadata(monkeypatch):
    sdk, adapter = _patch_sdk(monkeypatch, ref='text="Login"', resolver_name='exact_text')
    result = _run_async(sdk.act('Click Login', page=object()))
    assert result.status == 'passed'
    assert not any(k.startswith('hydration_') for k in adapter.executed_targets[0].metadata.keys())
