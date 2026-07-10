"""Radio selection (DOM resolver) and checked-state verification.

Radios are commonly a hidden ``<input type=radio>`` inside a styled wrapper
(Ant / MUI), so name grounding misses them and a ``select`` step wrongly falls to
the dropdown resolver. ``_maybe_resolve_radio`` pins the wrapper and coerces the
step to a click; ``_verify_selected`` asserts the checked state.
"""
from __future__ import annotations

import asyncio

import bubblegum.core.sdk as sdk
from bubblegum.core.schemas import StepIntent


def _run(c):
    return asyncio.run(c)


class _Adapter:
    def __init__(self, res=None):
        self._res = {"selector": '[data-bg-radio="1"]', "checked": True, "name": "Cumulative"} if res is None else res

    async def find_radio(self, target_phrase):
        return self._res


def _intent(action="select", target="Create cumulative milestone(s)", instr=None):
    return StepIntent(
        instruction=instr if instr is not None else f"Select the {target} radio button",
        channel="web", action_type=action, target_phrase=target, context={},
    )


# --- selection ---------------------------------------------------------------


def test_resolves_radio_and_coerces_to_click():
    a, intent = _Adapter(), _intent("select")
    t = _run(sdk._maybe_resolve_radio(a, "web", intent))
    assert t is not None and t.resolver_name == "radio_dom"
    assert intent.action_type == "click"      # select coerced to click


def test_skips_when_no_radio_word():
    a = _Adapter()
    intent = _intent("select", target="Country", instr="Select California from Country")
    assert _run(sdk._maybe_resolve_radio(a, "web", intent)) is None


def test_skips_mobile_and_typing():
    assert _run(sdk._maybe_resolve_radio(_Adapter(), "mobile", _intent())) is None
    assert _run(sdk._maybe_resolve_radio(_Adapter(), "web", _intent("type"))) is None


def test_none_when_no_radio_on_page():
    a = _Adapter(res=None if False else None)
    a._res = None
    assert _run(sdk._maybe_resolve_radio(a, "web", _intent())) is None


# --- state assertion detection + label extraction ----------------------------


def test_selected_assertion_detection():
    f = sdk._looks_like_selected_assertion
    assert f("Create cumulative milestone(s) radio is selected", {})
    assert f("Newsletter checkbox is checked", {})
    assert not f("Welcome banner is visible", {})
    assert not f("Submit button", {})
    # explicit assertion_type opts out
    assert not f("X radio is selected", {"assertion_type": "text_visible"})


def test_radio_label_extraction():
    g = sdk._radio_label_from_assertion
    assert g("Verify Create cumulative milestone(s) radio is selected") == "Create cumulative milestone(s)"
    assert g("the None radio is not selected") == "None"
    assert g("Consecutive option is selected") == "Consecutive"


def test_negated_state():
    assert sdk._NEGATED_STATE_RE.search("None radio is not selected")
    assert sdk._NEGATED_STATE_RE.search("box is unchecked")
    assert not sdk._NEGATED_STATE_RE.search("radio is selected")


# --- state verification via the finder --------------------------------------


def test_verify_selected_pass_and_fail():
    checked = _Adapter(res={"selector": "[data-bg-radio='1']", "checked": True, "name": "Cumulative"})
    r = _run(sdk._verify_selected(checked, "web", "Cumulative radio is selected", {}, 0.0))
    assert r.status == "passed"
    # Same element, asserting NOT selected -> fails.
    r2 = _run(sdk._verify_selected(checked, "web", "Cumulative radio is not selected", {}, 0.0))
    assert r2.status == "failed"


def test_verify_selected_element_not_found():
    missing = _Adapter(res=None)
    missing._res = None
    r = _run(sdk._verify_selected(missing, "web", "Ghost radio is selected", {}, 0.0))
    assert r.status == "failed"
