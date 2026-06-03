"""Phase 22D-6: per-session scope stack and close_dialog helper.

A SessionScope narrows where subsequent resolvers should look. When a step
opens a dialog, the next steps should search inside that dialog first; when
the dialog closes, scope pops back to the page.

This module defines:

  - SessionScope: a single frame on the stack (type/label/root_locator/...)
  - ScopeStack: LIFO stack, always anchored at a base "page" scope
  - close_dialog_web: SDK helper that locates the open dialog, clicks a
    close affordance, falls back to Escape, and pops the dialog scope

Resolver integration that threads `scope_root` through the grounding chain
(so every resolver searches inside the active scope first) lands in a
follow-up PR. Until then, the stack is available for SDK helpers like
close_dialog() and for trace artifacts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from bubblegum.core.grounding.dom_helpers import find_open_dialog

ScopeType = Literal["page", "dialog", "tab_panel", "iframe"]


@dataclass
class SessionScope:
    """Single frame on the per-session scope stack."""

    type: ScopeType = "page"
    label: str | None = None
    root_locator: Any = None  # Playwright Locator or platform-equivalent
    opened_by: int | None = None  # session step index that pushed this scope


class ScopeStack:
    """LIFO stack of SessionScope. Always non-empty: the base is the page."""

    def __init__(self) -> None:
        self._stack: list[SessionScope] = [SessionScope(type="page")]

    def current(self) -> SessionScope:
        return self._stack[-1]

    def push(self, scope: SessionScope) -> SessionScope:
        self._stack.append(scope)
        return scope

    def pop(self) -> SessionScope | None:
        """Pop the top frame unless it is the base page scope."""
        if len(self._stack) <= 1:
            return None
        return self._stack.pop()

    def depth(self) -> int:
        """How many frames are stacked above the always-present page scope."""
        return len(self._stack) - 1

    def is_dialog_active(self) -> bool:
        return any(s.type == "dialog" for s in self._stack)

    def snapshot(self) -> list[dict[str, Any]]:
        """JSON-safe view of the stack for traces / diagnostics."""
        return [{"type": s.type, "label": s.label} for s in self._stack]


# ---------------------------------------------------------------------------
# close_dialog (web / Playwright)
# ---------------------------------------------------------------------------

# Accessible name matcher for the close affordance inside a dialog.
# Covers "Close", "Cancel", "Dismiss", "X", "x", and the multiplication sign
# "×" that some component libraries render as the close icon.
_CLOSE_BUTTON_RE = re.compile(r"^\s*(close|cancel|dismiss|×|x)\s*$", re.IGNORECASE)


async def close_dialog_web(page: Any, stack: ScopeStack) -> dict[str, Any]:
    """Close the currently-open dialog on a Playwright page.

    Resolution order:
      1. If the current scope is a dialog with a `root_locator`, use that
         as the dialog root.
      2. Otherwise call find_open_dialog(page) which scans a fixed set of
         dialog-shaped selectors and returns the first match.
      3. If a dialog root is found, look for a button whose accessible
         name matches _CLOSE_BUTTON_RE inside it. If found, click it.
      4. If no close button is found (or no dialog at all), press Escape
         on the page as a best-effort fallback.
      5. If the current scope is a dialog, pop it off the stack.

    Returns a small report describing how the dialog was closed and the
    resulting scope state — useful for trace artifacts and tests.
    """
    current = stack.current()
    dialog_root = current.root_locator if current.type == "dialog" else None
    detected_via: str | None = None

    if dialog_root is None:
        dialog_root, detected_via = await find_open_dialog(page)

    closed_by = "escape"  # default fallback
    if dialog_root is not None:
        close_btn = dialog_root.get_by_role("button", name=_CLOSE_BUTTON_RE)
        if await close_btn.count() > 0:
            await close_btn.first.click()
            closed_by = "close_button"

    if closed_by == "escape":
        await page.keyboard.press("Escape")

    popped = None
    if stack.current().type == "dialog":
        popped_frame = stack.pop()
        if popped_frame is not None:
            popped = {"type": popped_frame.type, "label": popped_frame.label}

    return {
        "closed_by": closed_by,
        "dialog_detected_via": "scope" if current.type == "dialog" else detected_via,
        "popped_scope": popped,
        "scope_after": stack.current().type,
    }
