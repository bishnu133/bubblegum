"""Phase 22D-7: DOM helpers for resolving overlay / scoped widgets.

Two pure async helpers that operate on Playwright Page / Locator objects:

  - find_open_dialog(page): locate the topmost open dialog on the page.
    Returns (locator | None, selector | None) where the selector tells
    callers which probe matched -- useful for trace artifacts.
  - follow_aria_controls(page, trigger): given a combobox / disclosure
    trigger, follow its aria-controls or aria-owns attribute to the
    controlled element (typically a portal-rendered listbox or panel).

These are pure helpers -- they do not modify page state and have no side
effects. The accessibility-tree resolver integration that uses them when
scoring candidates lands in a follow-up PR; this commit ships the helpers
and updates scope.close_dialog_web to consume find_open_dialog so the two
modules share one source of truth for "what counts as a dialog".
"""

from __future__ import annotations

from typing import Any, Tuple


# Probes ordered from most specific (aria-modal=true) to least. dialog[open]
# covers the HTML5 <dialog> element when used without an explicit role=.
_OPEN_DIALOG_SELECTORS: tuple[str, ...] = (
    "[role='dialog'][aria-modal='true']",
    "[role='alertdialog']",
    "dialog[open]",
    "[role='dialog']",
)


async def find_open_dialog(page: Any) -> Tuple[Any | None, str | None]:
    """Locate the topmost open dialog on the page.

    Returns (locator, selector_used) for the first probe that has at least
    one match, or (None, None) when no dialog is found.
    """
    for selector in _OPEN_DIALOG_SELECTORS:
        locator = page.locator(selector)
        if await locator.count() > 0:
            return locator.first, selector
    return None, None


async def follow_aria_controls(page: Any, trigger: Any) -> Any | None:
    """Follow aria-controls or aria-owns from a trigger element.

    Reads aria-controls first (preferred for combobox/listbox pairing) and
    falls back to aria-owns. The attribute may contain one or more
    space-separated IDREFs; only the first is returned (the common
    single-target case for comboboxes and disclosure widgets). Returns
    None when neither attribute is set, the value is empty, or the
    referenced element does not exist in the DOM.
    """
    controls = await trigger.get_attribute("aria-controls")
    target_id = (controls or "").strip()
    if not target_id:
        owns = await trigger.get_attribute("aria-owns")
        target_id = (owns or "").strip()
    if not target_id:
        return None

    first_id = target_id.split()[0]
    if not first_id:
        return None

    target = page.locator(f"#{_css_escape_id(first_id)}")
    if await target.count() == 0:
        return None
    return target.first


def _css_escape_id(idref: str) -> str:
    """Conservatively escape an ID for use in a CSS `#id` selector.

    Non-alphanumeric characters other than `_` and `-` are backslash-escaped;
    a leading digit is rewritten using the hex-escape form. For typical
    component-library ARIA authoring (kebab-case, alphanumerics) this is a
    no-op.
    """
    if not idref:
        return idref
    out: list[str] = []
    for ch in idref:
        if ch.isalnum() or ch in "_-":
            out.append(ch)
        else:
            out.append("\\" + ch)
    if out and out[0].isdigit():
        out[0] = "\\3" + out[0] + " "
    return "".join(out)
