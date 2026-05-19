from __future__ import annotations

import asyncio

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.config import BubblegumConfig, WebviewSwitchingConfig
from bubblegum.core.schemas import ValidationPlan


class _El:
    text = "text"
    def get_attribute(self, _):
        return ""


class _D:
    capabilities = {"platformName": "Android"}
    page_source = "hello"

    class _S:
        def __init__(self, outer): self.o = outer
        def context(self, name: str):
            self.o.calls.append(("switch", name))
            if self.o.fail_switch:
                raise RuntimeError("WEBVIEW_secret_fail")
            self.o.current_context = name

    def __init__(self):
        self.contexts = ["NATIVE_APP", "WEBVIEW_secret"]
        self.current_context = "NATIVE_APP"
        self.calls = []
        self.fail_switch = False
        self.fail_restore = False
        self.switch_to = self._S(self)

    def find_element(self, *_a, **_k):
        return _El()


def _cfg(enabled=True, mode="opt_in", ops=None):
    return BubblegumConfig(webview_switching=WebviewSwitchingConfig(
        enable_webview_switching=enabled,
        webview_switching_mode=mode,
        webview_switch_allowed_operations=ops or ["verify", "extract"],
    ))


def _md(decision="allowed", selected=True, idx=0):
    return {
        "webview_switch_eligibility": {"decision": decision, "safe_metadata_only": True},
        "webview_context_selection": {
            "decision": "selected" if selected else "blocked",
            "selected_context_type": "webview",
            "selected_context_index": idx,
            "safe_metadata_only": True,
        },
    }


def test_default_validate_no_switch_and_execute_unwired():
    ad = AppiumAdapter(_D())
    ad._run_assertion = lambda _p: (True, "ok")
    out = asyncio.run(ad.validate(ValidationPlan(assertion_type="text_visible", expected_value="x")))
    assert out.passed is True
    assert ad._last_webview_switch_execution is None
    assert ad._build_real_switch_execution_args("execute", {"webview_switch_wiring_plan": {"switch_ready": True}}) is None


def test_strict_opt_in_validate_and_extract_switch_and_restore():
    d = _D()
    ad = AppiumAdapter(d)
    ad._config = _cfg()
    ad._webview_validate_metadata = _md()
    assert asyncio.run(ad.validate(ValidationPlan(assertion_type="text_visible", expected_value="hello"))).passed is True
    ref = {"by": "id", "value": "a", "metadata": _md()}
    assert asyncio.run(ad.extract_text(ref)) == "text"
    assert d.calls.count(("switch", "WEBVIEW_secret")) == 2
    assert d.calls.count(("switch", "NATIVE_APP")) == 2
    assert "webview_switch_execution" in ref["metadata"]
    assert "WEBVIEW_secret" not in str(ref["metadata"]["webview_switch_execution"])


def test_blocks_when_selection_or_eligibility_or_context_ref_missing():
    ad = AppiumAdapter(_D())
    ad._config = _cfg()
    ad._webview_validate_metadata = _md(decision="blocked")
    assert asyncio.run(ad.validate(ValidationPlan(assertion_type="text_visible", expected_value="hello"))).passed is True

    ad._webview_validate_metadata = _md(selected=False)
    assert asyncio.run(ad.validate(ValidationPlan(assertion_type="text_visible", expected_value="hello"))).passed is True

    ad._webview_validate_metadata = _md(idx=7)
    assert asyncio.run(ad.validate(ValidationPlan(assertion_type="text_visible", expected_value="hello"))).passed is True


def test_switch_and_restore_fail_closed_validate():
    d = _D()
    ad = AppiumAdapter(d)
    ad._config = _cfg()
    ad._webview_validate_metadata = _md()
    d.fail_switch = True
    out = asyncio.run(ad.validate(ValidationPlan(assertion_type="text_visible", expected_value="hello")))
    assert out.passed is False and out.actual_value == "webview_switch_safety_failed"

    d = _D()
    ad = AppiumAdapter(d)
    ad._config = _cfg()
    ad._webview_validate_metadata = _md()
    ad._webview_restore_context = lambda _orig: (_ for _ in ()).throw(RuntimeError("restore WEBVIEW_secret fail"))
    out = asyncio.run(ad.validate(ValidationPlan(assertion_type="text_visible", expected_value="hello")))
    assert out.passed is False and out.actual_value == "webview_switch_safety_failed"


def test_operation_failure_after_switch_restores_and_metadata_attached():
    d = _D()
    ad = AppiumAdapter(d)
    ad._config = _cfg()
    ad._webview_validate_metadata = _md()
    ad._webview_validate_operation = lambda _p: (_ for _ in ()).throw(RuntimeError("boom"))
    out = asyncio.run(ad.validate(ValidationPlan(assertion_type="text_visible", expected_value="hello")))
    assert out.passed is False
    ws = ad._last_webview_switch_execution["webview_switch_execution"]
    assert ws["switch_status"] == "failed" and ws["restore_status"] == "restored"
