from __future__ import annotations

import asyncio

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.mobile.webview_context_selection import select_webview_context
from bubblegum.core.schemas import ContextRequest


class _Driver:
    capabilities = {"platformName": "Android"}
    current_activity = ".MainActivity"
    page_source = "<hierarchy/>"
    contexts = ["NATIVE_APP", "WEBVIEW_com.example", "WEBVIEW_private"]
    current_context = "NATIVE_APP"

    def get_screenshot_as_png(self):
        return b""


def _inv(count=1):
    return {
        "webview_context_count": count,
        "has_webview_context": count > 0,
        "context_types": ["native", "webview"] if count > 0 else ["native"],
        "safe_metadata_only": True,
    }


def test_eligibility_not_allowed_blocks_selection():
    out = select_webview_context(context_inventory=_inv(1), webview_switch_eligibility={"decision": "blocked"})
    assert out["decision"] == "blocked"


def test_missing_inventory_unknown():
    out = select_webview_context(context_inventory=None, webview_switch_eligibility={"decision": "allowed"})
    assert out["decision"] == "unknown"


def test_single_webview_selected():
    out = select_webview_context(context_inventory=_inv(1), webview_switch_eligibility={"decision": "allowed"})
    assert out["decision"] == "selected"
    assert out["selected_context_index"] == 0


def test_multiple_webviews_deferred_for_single_policy():
    out = select_webview_context(context_inventory=_inv(2), webview_switch_eligibility={"decision": "allowed"})
    assert out["decision"] == "deferred"


def test_multiple_webviews_first_available_selects_index_zero():
    out = select_webview_context(
        context_inventory=_inv(2),
        webview_switch_eligibility={"decision": "allowed"},
        selection_policy="first_available",
    )
    assert out["decision"] == "selected"
    assert out["selected_context_index"] == 0


def test_hint_match_selected_when_deterministic():
    out = select_webview_context(
        context_inventory=_inv(2),
        webview_switch_eligibility={"decision": "allowed"},
        selection_policy="hint_match",
        preferred_context_hint="webview",
    )
    assert out["decision"] == "selected"


def test_hint_match_deferred_when_not_deterministic():
    out = select_webview_context(
        context_inventory=_inv(2),
        webview_switch_eligibility={"decision": "allowed"},
        selection_policy="hint_match",
        preferred_context_hint="secondary",
    )
    assert out["decision"] == "deferred"


def test_unsupported_policy_blocked():
    out = select_webview_context(
        context_inventory=_inv(2),
        webview_switch_eligibility={"decision": "allowed"},
        selection_policy="round_robin",
    )
    assert out["decision"] == "blocked"


def test_raw_context_names_not_leaked_and_switch_never_attempted():
    out = select_webview_context(
        context_inventory={
            "webview_context_count": 2,
            "raw_context_names": ["WEBVIEW_secret"],
            "has_webview_context": True,
        },
        webview_switch_eligibility={"decision": "allowed"},
        selection_policy="first_available",
    )
    rendered = str(out)
    assert "WEBVIEW_secret" not in rendered
    assert "raw_context_names" not in rendered
    assert out["switch_attempted"] is False


def test_collect_context_attaches_webview_context_selection():
    ctx = asyncio.run(AppiumAdapter(_Driver()).collect_context(ContextRequest(include_screenshot=False)))
    assert "webview_context_selection" in ctx.app_state
    assert ctx.app_state["webview_context_selection"]["switch_attempted"] is False


def test_runtime_package_has_no_switch_to_context_usage():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / "bubblegum"
    matches = []
    for path in root.rglob("*.py"):
        if "switch_to.context" in path.read_text(encoding="utf-8"):
            matches.append(str(path))
    assert matches == [str(root / "adapters/mobile/appium/adapter.py")]
