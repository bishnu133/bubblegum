"""Guard: every browser-side JS constant that uses a template placeholder must
have it substituted at import time.

The web adapter builds its in-page resolvers from string templates that inline
shared helpers via ``.replace("__DIALOG_JS", _DIALOG_ROOT_JS)`` /
``.replace("__SECTION_JS", _SECTION_HEADING_JS)``. Forgetting the ``.replace``
on a new (or edited) resolver leaves a bare ``__DIALOG_JS`` token in the source
that Playwright ships to the page, where it throws a ``ReferenceError`` at
runtime — a failure only a real browser would surface. This cheap, browser-free
check fails fast in the unit suite instead.
"""

from __future__ import annotations

import bubblegum.adapters.web.playwright.adapter as adapter

# Every module-level constant that holds page-side JS.
_JS_CONSTANTS = [n for n in dir(adapter) if n.endswith("_JS")]


def test_no_unsubstituted_placeholders_remain():
    offenders = {}
    for name in _JS_CONSTANTS:
        js = getattr(adapter, name)
        if not isinstance(js, str):
            continue
        leftovers = [tok for tok in ("__DIALOG_JS", "__SECTION_JS") if tok in js]
        if leftovers:
            offenders[name] = leftovers
    assert not offenders, f"JS templates with unsubstituted placeholders: {offenders}"


def test_dialog_scoped_resolvers_inline_the_helper():
    # Resolvers that scope to the open modal must carry the __bgTopDialog helper
    # (inlined from _DIALOG_ROOT_JS), or their modal-scoping silently no-ops.
    for name in ("_FIND_INPUT_JS", "_FIND_FILE_INPUT_JS", "_FIND_RADIO_JS",
                 "_FIND_CHECKBOX_JS", "_FIND_DATE_RANGE_JS"):
        js = getattr(adapter, name)
        assert "__bgTopDialog" in js, f"{name} is missing the __bgTopDialog helper"


def test_reader_js_has_visibility_helper_inlined():
    # The page-reader templates inline the shared __bgVis helper via
    # .replace("__VIS_JS", …); a forgotten replace would ship a bare token.
    for name in ("_COUNT_ELEMENTS_JS", "_READ_PAGE_HEADER_JS", "_ITEM_ACTIVE_JS"):
        js = getattr(adapter, name)
        assert "__VIS_JS" not in js, f"{name} has an unsubstituted __VIS_JS placeholder"
        assert "__bgVis" in js, f"{name} is missing the __bgVis helper"


def test_radio_and_checkbox_have_exactness_tiebreak():
    # The exact-label preference (fewest extra words) must be present so a phrase
    # that is a whole-word subset of two labels ("Required" ⊂ "Not Required")
    # resolves to the exact option, not by DOM order.
    for name in ("_FIND_RADIO_JS", "_FIND_CHECKBOX_JS"):
        assert "extraWords" in getattr(adapter, name), f"{name} lost its exactness tiebreak"
