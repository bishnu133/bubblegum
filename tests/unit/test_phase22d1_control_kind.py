"""Phase 22D-1: ControlKind enum + matching rules for new widget kinds.

Covers: link, combobox, dialog, tab, switch, plus the `select` alias of
`dropdown`. Existing kinds (button, input, dropdown, checkbox, radio) are
covered indirectly by test_phase19g_*; this file pins the unit-level
behavior of the matcher for the new vocabulary.
"""

from __future__ import annotations

from bubblegum.core.elements import (
    ControlKind,
    KNOWN_CONTROL_KINDS,
    NormalizedElement,
)
from bubblegum.core.elements.query import _match_control_kind


def _el(**kw) -> NormalizedElement:
    base = dict(channel="web", platform="web", source_kind="test", visible=True, enabled=True)
    base.update(kw)
    return NormalizedElement(**base)


def _match(elements: list[NormalizedElement], hint: str, action: str | None = None) -> tuple[set[str], set[str]]:
    matched, excluded = _match_control_kind(elements, hint, action)
    return set(matched), set(excluded)


# ---------------------------------------------------------------------------
# ControlKind vocabulary
# ---------------------------------------------------------------------------


def test_control_kind_enum_values_are_closed_vocabulary():
    expected = {
        "none", "button", "input", "dropdown", "select", "combobox",
        "checkbox", "radio", "link", "dialog", "tab", "switch", "slider",
    }
    assert KNOWN_CONTROL_KINDS == expected


def test_control_kind_constants_match_string_values():
    assert ControlKind.LINK == "link"
    assert ControlKind.COMBOBOX == "combobox"
    assert ControlKind.DIALOG == "dialog"
    assert ControlKind.TAB == "tab"
    assert ControlKind.SWITCH == "switch"
    assert ControlKind.SELECT == "select"
    assert ControlKind.DROPDOWN == "dropdown"
    assert ControlKind.SLIDER == "slider"


# ---------------------------------------------------------------------------
# Link
# ---------------------------------------------------------------------------


def test_link_hint_matches_role_link_anchor_tag_and_aria_role():
    elements = [
        _el(id="link_role", role="link", text="Action"),
        _el(id="anchor", tag="a", text="Action"),
        _el(id="aria_link", tag="span", attributes={"role": "link"}, text="Action"),
        _el(id="btn", role="button", tag="button", text="Action"),
        _el(id="div", tag="div", text="Action"),
    ]

    matched, excluded = _match(elements, ControlKind.LINK)

    assert matched == {"link_role", "anchor", "aria_link"}
    assert excluded == {"btn", "div"}


def test_button_hint_still_matches_links_for_backwards_compat():
    # The button-vs-link tiebreaker is a ranker concern; at the filter level
    # button continues to accept links so existing fuzzy-fallback flows
    # ("Click Sign in" → Login button) keep working.
    elements = [
        _el(id="link_role", role="link", text="Action"),
        _el(id="btn", role="button", tag="button", text="Action"),
    ]

    matched, _ = _match(elements, ControlKind.BUTTON)

    assert matched == {"link_role", "btn"}


# ---------------------------------------------------------------------------
# Combobox vs Dropdown
# ---------------------------------------------------------------------------


def test_combobox_hint_is_narrower_than_dropdown():
    elements = [
        _el(id="cb", role="combobox", text="Action"),
        _el(id="sel", tag="select", text="Action"),
        _el(id="aria_cb", tag="div", attributes={"role": "combobox"}, text="Action"),
    ]

    cb_matched, cb_excluded = _match(elements, ControlKind.COMBOBOX)
    dd_matched, _ = _match(elements, ControlKind.DROPDOWN)

    # Combobox (new) picks up the ARIA-only combobox via attributes.role.
    assert cb_matched == {"cb", "aria_cb"}
    assert "sel" in cb_excluded
    # Dropdown keeps its existing behavior: role/tag based, no attributes.role
    # fallback. Native <select> and role=combobox match; attributes-only ARIA
    # combobox does not (was not in scope of the dropdown kind before 22D-1).
    assert dd_matched == {"cb", "sel"}
    assert "aria_cb" not in dd_matched


def test_select_alias_normalizes_to_dropdown():
    elements = [
        _el(id="sel", tag="select", text="Action"),
        _el(id="cb", role="combobox", text="Action"),
        _el(id="btn", role="button", text="Action"),
    ]

    matched, excluded = _match(elements, ControlKind.SELECT)

    assert matched == {"sel", "cb"}
    assert "btn" in excluded


# ---------------------------------------------------------------------------
# Radio (native + ARIA)
# ---------------------------------------------------------------------------


def test_radio_hint_matches_native_input_aria_and_role():
    elements = [
        _el(id="r1", tag="input", attributes={"type": "radio"}, text="Action"),
        _el(id="r2", tag="div", attributes={"role": "radio"}, text="Action"),
        _el(id="r3", role="radio", text="Action"),
        _el(id="cbx", tag="input", attributes={"type": "checkbox"}, text="Action"),
    ]

    matched, excluded = _match(elements, ControlKind.RADIO)

    assert matched == {"r1", "r2", "r3"}
    assert "cbx" in excluded


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------


def test_dialog_hint_matches_role_dialog_alertdialog_and_widget_type():
    elements = [
        _el(id="d1", role="dialog", text="Action"),
        _el(id="d2", role="alertdialog", text="Action"),
        _el(id="d3", tag="div", attributes={"role": "dialog"}, text="Action"),
        _el(id="d4", widget_type="modal", text="Action"),
        _el(id="d5", widget_type="ConfirmDialog", text="Action"),
        _el(id="grp", role="group", text="Action"),
    ]

    matched, excluded = _match(elements, ControlKind.DIALOG)

    assert matched == {"d1", "d2", "d3", "d4", "d5"}
    assert "grp" in excluded


# ---------------------------------------------------------------------------
# Tab
# ---------------------------------------------------------------------------


def test_tab_hint_matches_role_tab_and_aria_role():
    elements = [
        _el(id="t1", role="tab", text="Action"),
        _el(id="t2", tag="button", attributes={"role": "tab"}, text="Action"),
        _el(id="btn", role="button", text="Action"),
    ]

    matched, excluded = _match(elements, ControlKind.TAB)

    assert matched == {"t1", "t2"}
    assert "btn" in excluded


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------


def test_switch_hint_matches_role_switch_aria_and_widget_type():
    elements = [
        _el(id="s1", role="switch", text="Action"),
        _el(id="s2", tag="button", attributes={"role": "switch"}, text="Action"),
        _el(id="s3", widget_type="ToggleSwitch", text="Action"),
        _el(id="cbx", role="checkbox", text="Action"),
    ]

    matched, excluded = _match(elements, ControlKind.SWITCH)

    assert matched == {"s1", "s2", "s3"}
    assert "cbx" in excluded


# ---------------------------------------------------------------------------
# None hint preserves prior behavior
# ---------------------------------------------------------------------------


def test_none_hint_does_not_filter():
    elements = [
        _el(id="btn", role="button", text="Action"),
        _el(id="lk", tag="a", text="Action"),
        _el(id="div", tag="div", text="Action"),
    ]

    matched, excluded = _match(elements, ControlKind.NONE)

    assert matched == {"btn", "lk", "div"}
    assert excluded == set()


# ---------------------------------------------------------------------------
# Action-based defaults are unchanged (regression guard)
# ---------------------------------------------------------------------------


def test_no_hint_with_action_select_still_matches_dropdown_set():
    elements = [
        _el(id="sel", tag="select", text="Action"),
        _el(id="cb", role="combobox", text="Action"),
        _el(id="btn", role="button", text="Action"),
    ]

    matched, _ = _match(elements, ControlKind.NONE, action="select")

    assert matched == {"sel", "cb"}


def test_no_hint_with_action_check_still_matches_checkboxes():
    elements = [
        _el(id="cb1", tag="input", attributes={"type": "checkbox"}, text="Action"),
        _el(id="r1", tag="input", attributes={"type": "radio"}, text="Action"),
    ]

    matched, _ = _match(elements, ControlKind.NONE, action="check")

    assert matched == {"cb1"}
