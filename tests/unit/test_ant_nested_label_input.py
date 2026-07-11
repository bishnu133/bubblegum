"""Regression: Ant Design nested form-item label resolution.

Ant wraps a form control in ``.ant-form-item-control-input-content``, whose
class name *also* contains the substring ``form-item``. A naive
``e.closest('[class*="form-item"]')`` therefore stops on that inner wrapper —
which holds no ``<label>`` — so label-based disambiguation returned an empty
string and every field tied on DOM order. The first input then won for *every*
phrase, and (e.g.) "Challenge Name" and "Challenge Tagline" both typed into the
Challenge Name field.

The fix climbs to the nearest form-item-ish ancestor that actually contains a
label (``__bgField``). These tests lock in both the structural fix and the
observable behaviour.
"""
from __future__ import annotations

import pytest

from bubblegum.adapters.web.playwright import adapter as A


# The four DOM-scoring blocks that disambiguate controls by their form-item label.
_LABEL_SCORING_BLOCKS = (
    "_FIND_SELECT_TRIGGER_JS",
    "_FIND_INPUT_JS",
    "_FIND_DATE_RANGE_JS",
    "_FIND_FILE_INPUT_JS",
)


@pytest.mark.parametrize("block", _LABEL_SCORING_BLOCKS)
def test_label_lookup_uses_climbing_helper(block: str) -> None:
    """Each label-scoring block must climb via __bgField, never a bare closest().

    A bare ``e.closest('.ant-form-item, ... [class*="form-item"] ...')`` feeding a
    label ``querySelector`` is the exact bug: Ant's inner control wrapper swallows
    it. Guard against reintroducing that pattern.
    """
    src = getattr(A, block)
    assert "const __bgField = (e, sel) =>" in src, f"{block} lost the climbing helper"
    assert "__bgField(e," in src, f"{block} no longer calls __bgField for label lookup"


# --- Behavioural check against a real browser (skips when none is available) ---

_ANT_FORM = """
<form>
  <div class="ant-form-item"><div class="ant-row ant-form-item-row">
    <div class="ant-col ant-form-item-label">
      <label for="name" title="Challenge Name">Challenge Name</label></div>
    <div class="ant-col ant-form-item-control"><div class="ant-form-item-control-input">
      <div class="ant-form-item-control-input-content">
        <span class="ant-input-affix-wrapper">
          <input maxlength="50" data-testid="name" class="ant-input" type="text">
        </span></div></div></div>
  </div></div>
  <div class="ant-form-item"><div class="ant-row ant-form-item-row">
    <div class="ant-col ant-form-item-label">
      <label for="tagline" title="Challenge Tagline">Challenge Tagline</label></div>
    <div class="ant-col ant-form-item-control"><div class="ant-form-item-control-input">
      <div class="ant-form-item-control-input-content">
        <span class="ant-input-affix-wrapper">
          <input maxlength="100" data-testid="tagline" class="ant-input" type="text">
        </span></div></div></div>
  </div></div>
</form>
"""


@pytest.mark.playwright
def test_find_input_disambiguates_ant_nested_labels() -> None:
    """"Challenge Name" and "Challenge Tagline" must resolve to *different* inputs."""
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        pw = sync_api.sync_playwright().start()
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"Playwright unavailable: {exc}")
    try:
        try:
            browser = pw.chromium.launch()
        except Exception as exc:  # pragma: no cover - no matching browser binary
            pytest.skip(f"No usable browser binary: {exc}")
        try:
            page = browser.new_page()
            page.set_content(_ANT_FORM)
            resolved = {}
            for phrase in ("Challenge Name", "Challenge Tagline"):
                res = page.evaluate(A._FIND_INPUT_JS, {"phrase": phrase})
                assert res, f"no input resolved for {phrase!r}"
                resolved[phrase] = page.locator(res["selector"]).get_attribute("data-testid")
        finally:
            browser.close()
    finally:
        pw.stop()

    assert resolved["Challenge Name"] == "name"
    assert resolved["Challenge Tagline"] == "tagline"


# Two Quill rich-text editors, plus a tagline input pre-filled so its value leaks
# into the a11y tree as `- textbox: EDSH Auto Challenge` — the exact state that
# made "About this Challenge" mis-ground onto the tagline input.
_ANT_RTE_FORM = """
<form>
  <div class="ant-form-item"><div class="ant-row ant-form-item-row">
    <div class="ant-col ant-form-item-label">
      <label for="tagline" title="Challenge Tagline">Challenge Tagline</label></div>
    <div class="ant-col ant-form-item-control"><div class="ant-form-item-control-input">
      <div class="ant-form-item-control-input-content"><span class="ant-input-affix-wrapper">
        <input data-testid="tagline" class="ant-input" type="text" value="EDSH Auto Challenge">
      </span></div></div></div>
  </div></div>
  <div class="ant-form-item"><div class="ant-row ant-form-item-row">
    <div class="ant-col ant-form-item-label">
      <label for="description" title="About this Challenge">About this Challenge</label></div>
    <div class="ant-col ant-form-item-control"><div class="ant-form-item-control-input">
      <div class="ant-form-item-control-input-content"><div id="txt-description" class="quill">
        <div role="toolbar" class="ql-toolbar ql-snow">
          <span class="ql-formats"><span class="ql-header ql-picker">
            <span class="ql-picker-label" role="button">Normal</span></span></span>
          <span class="ql-formats"><span class="ql-color ql-picker ql-color-picker">
            <span class="ql-picker-label" role="button"></span></span></span>
        </div>
        <pre class="ql-container"><div class="ql-editor" contenteditable="true"><p><br></p></div></pre>
      </div></div></div></div>
  </div></div>
  <div class="ant-form-item"><div class="ant-row ant-form-item-row">
    <div class="ant-col ant-form-item-label">
      <label for="details" title="Key Details">Key Details</label></div>
    <div class="ant-col ant-form-item-control"><div class="ant-form-item-control-input">
      <div class="ant-form-item-control-input-content"><div id="txt-details" class="quill">
        <div role="toolbar" class="ql-toolbar ql-snow">
          <span class="ql-formats"><span class="ql-header ql-picker">
            <span class="ql-picker-label" role="button">Normal</span></span></span>
        </div>
        <pre class="ql-container"><div class="ql-editor" contenteditable="true"><p><br></p></div></pre>
      </div></div></div></div>
  </div></div>
</form>
"""


@pytest.mark.playwright
def test_find_rich_text_resolves_contenteditable_editors() -> None:
    """RTE steps hit the right contenteditable; plain-input phrases fall through."""
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        pw = sync_api.sync_playwright().start()
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"Playwright unavailable: {exc}")
    try:
        try:
            browser = pw.chromium.launch()
        except Exception as exc:  # pragma: no cover - no matching browser binary
            pytest.skip(f"No usable browser binary: {exc}")
        try:
            page = browser.new_page()
            page.set_content(_ANT_RTE_FORM)

            def container_id(res):
                return page.locator(res["selector"]).evaluate(
                    "e => (e.closest('[id]') || {}).id || ''"
                )

            hits = {}
            # Includes phrase variants (extra/fewer words, different order): the
            # resolver ranks fillable controls relatively, so it must not depend
            # on an exact full-token label match.
            for phrase in ("About this Challenge", "Key Details",
                           "the About this Challenge section", "About this Challenge details",
                           "Key Detail"):
                res = page.evaluate(A._FIND_RICH_TEXT_JS, {"phrase": phrase})
                assert res, f"RTE not resolved for {phrase!r}"
                hits[phrase] = container_id(res)

            # A full label match must not be hijacked from a plain input, and the
            # value-leaking tagline must not steal the RTE step.
            misses = {
                phrase: page.evaluate(A._FIND_RICH_TEXT_JS, {"phrase": phrase})
                for phrase in ("Challenge Tagline", "Challenge Name")
            }
        finally:
            browser.close()
    finally:
        pw.stop()

    assert hits["About this Challenge"] == "txt-description"
    assert hits["the About this Challenge section"] == "txt-description"
    assert hits["About this Challenge details"] == "txt-description"
    assert hits["Key Details"] == "txt-details"
    assert hits["Key Detail"] == "txt-details"
    assert misses["Challenge Tagline"] is None
    assert misses["Challenge Name"] is None
