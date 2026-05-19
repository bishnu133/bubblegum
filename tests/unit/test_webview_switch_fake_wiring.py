from __future__ import annotations

import asyncio

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.config import BubblegumConfig, WebviewSwitchingConfig
from bubblegum.core.schemas import ResolvedTarget, StepResult, ValidationPlan
from bubblegum.reporting.html_report import write_html_report
from bubblegum.reporting.json_report import write_json_report
import json


class _Element:
    def __init__(self, text: str = ""):
        self.text = text

    def get_attribute(self, name: str):
        return "attr-text" if name == "text" else ""


class _Driver:
    capabilities = {"platformName": "Android"}
    page_source = "hello"

    def find_element(self, *_args, **_kwargs):
        return _Element("base-text")


def _cfg(enabled=True, mode="opt_in", ops=None):
    return BubblegumConfig(
        webview_switching=WebviewSwitchingConfig(
            enable_webview_switching=enabled,
            webview_switching_mode=mode,
            webview_switch_allowed_operations=ops or ["verify", "extract"],
        )
    )


def _metadata():
    return {
        "webview_switch_eligibility": {"decision": "allowed", "safe_metadata_only": True},
        "webview_context_selection": {
            "decision": "selected",
            "selected_context_type": "webview",
            "selected_context": "WEBVIEW_secret",
            "safe_metadata_only": True,
        },
    }


def test_default_validate_noop_unchanged():
    ad = AppiumAdapter(_Driver())
    ad._run_assertion = lambda _plan: (True, "ok")
    out = asyncio.run(ad.validate(ValidationPlan(assertion_type="text_visible", expected_value="x")))
    assert out.passed is True
    assert ad._last_webview_switch_execution is None


def test_default_extract_noop_unchanged():
    ad = AppiumAdapter(_Driver())
    out = asyncio.run(ad.extract_text({"by": "id", "value": "a", "metadata": _metadata()}))
    assert out == "base-text"
    assert ad._last_webview_switch_execution is None


def test_execute_remains_unwired():
    ad = AppiumAdapter(_Driver())
    assert ad._build_fake_switch_execution_args("execute", {"webview_switch_wiring_plan": {"switch_ready": True}}) is None


def test_opt_in_fake_validate_success_calls_switch_restore():
    ad = AppiumAdapter(_Driver())
    ad._config = _cfg()
    ad._webview_validate_metadata = _metadata()
    ad._run_assertion = lambda _plan: (True, "ok")
    calls = []
    ad._webview_get_current_context = lambda: "NATIVE_APP"
    ad._webview_switch_context = lambda _sel: calls.append("switch")
    ad._webview_restore_context = lambda _orig: calls.append("restore")
    out = asyncio.run(ad.validate(ValidationPlan(assertion_type="text_visible", expected_value="x")))
    assert out.passed is True
    assert calls == ["switch", "restore"]


def test_opt_in_fake_extract_success_calls_switch_restore_and_metadata():
    ad = AppiumAdapter(_Driver())
    ad._config = _cfg()
    ref = {"by": "id", "value": "a", "metadata": _metadata()}
    calls = []
    ad._webview_switch_context = lambda _sel: calls.append("switch")
    ad._webview_restore_context = lambda _orig: calls.append("restore")
    out = asyncio.run(ad.extract_text(ref))
    assert out == "base-text"
    assert calls == ["switch", "restore"]
    assert "webview_switch_execution" in ref["metadata"]


def test_fake_switch_failure_fail_closed_validate():
    ad = AppiumAdapter(_Driver())
    ad._config = _cfg()
    ad._webview_validate_metadata = _metadata()
    ad._run_assertion = lambda _plan: (True, "ok")
    ad._webview_switch_context = lambda _sel: (_ for _ in ()).throw(RuntimeError("WEBVIEW_secret fail"))
    out = asyncio.run(ad.validate(ValidationPlan(assertion_type="text_visible", expected_value="x")))
    assert out.passed is False
    assert out.actual_value == "webview_switch_safety_failed"
    assert "WEBVIEW_secret" not in str(ad._last_webview_switch_execution)


def test_fake_restore_failure_fail_closed_validate():
    ad = AppiumAdapter(_Driver())
    ad._config = _cfg()
    ad._webview_validate_metadata = _metadata()
    ad._run_assertion = lambda _plan: (True, "ok")
    ad._webview_switch_context = lambda _sel: None
    ad._webview_restore_context = lambda _orig: (_ for _ in ()).throw(RuntimeError("restore WEBVIEW_secret fail"))
    out = asyncio.run(ad.validate(ValidationPlan(assertion_type="text_visible", expected_value="x")))
    assert out.passed is False
    assert out.actual_value == "webview_switch_safety_failed"


def test_operation_failure_after_switch_still_restores():
    ad = AppiumAdapter(_Driver())
    ad._config = _cfg()
    ad._webview_validate_metadata = _metadata()
    calls = []
    ad._webview_switch_context = lambda _sel: calls.append("switch")
    ad._webview_restore_context = lambda _orig: calls.append("restore")
    ad._webview_validate_operation = lambda _plan: (_ for _ in ()).throw(RuntimeError("boom"))
    out = asyncio.run(ad.validate(ValidationPlan(assertion_type="text_visible", expected_value="x")))
    assert out.passed is False
    assert calls == ["switch", "restore"]


def test_no_fake_callables_means_no_switch_attempt():
    ad = AppiumAdapter(_Driver())
    ad._config = _cfg()
    ad._webview_validate_metadata = _metadata()
    ad._run_assertion = lambda _plan: (True, "ok")
    out = asyncio.run(ad.validate(ValidationPlan(assertion_type="text_visible", expected_value="x")))
    assert out.passed is True
    assert ad._last_webview_switch_execution is None


def test_json_report_accepts_fake_wiring_extract_metadata(tmp_path):
    ad = AppiumAdapter(_Driver())
    ad._config = _cfg()
    ref = {"by": "id", "value": "a", "metadata": _metadata()}
    ad._webview_switch_context = lambda _sel: None
    ad._webview_restore_context = lambda _orig: None
    assert asyncio.run(ad.extract_text(ref)) == "base-text"

    report_path = tmp_path / "report.json"
    result = StepResult(status="passed", action="extract", confidence=1.0, target=ResolvedTarget(
        ref="r", confidence=1.0, resolver_name="x", metadata=ref["metadata"]))
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    ws = payload["results"][0]["target"]["metadata"]["webview_switch_execution"]
    assert ws["switch_status"] == "switched"
    assert ws["restore_status"] == "restored"
    assert "selected_context" not in ws
    summary = payload["analytics"]["webview_switch_execution_summary"]
    assert summary["switch_status_counts"] == {"switched": 1}
    assert summary["restore_status_counts"] == {"restored": 1}


def test_html_report_renders_fake_wiring_webview_switch_execution_and_escapes(tmp_path):
    ad = AppiumAdapter(_Driver())
    ad._config = _cfg()
    ref = {"by": "id", "value": "a", "metadata": _metadata()}
    ad._webview_switch_context = lambda _sel: None
    ad._webview_restore_context = lambda _orig: None
    assert asyncio.run(ad.extract_text(ref)) == "base-text"
    ref["metadata"]["webview_switch_execution"]["warnings"] = ["<warn>"]

    out = tmp_path / "report.html"
    result = StepResult(status="passed", action="extract", confidence=1.0, target=ResolvedTarget(
        ref="r", confidence=1.0, resolver_name="x", metadata=ref["metadata"]))
    write_html_report([result], path=out)
    text = out.read_text(encoding="utf-8")
    assert "WebView Switch Execution" in text
    assert "&lt;warn&gt;" in text
    assert "WEBVIEW_secret" not in text
