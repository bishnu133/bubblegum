"""
bubblegum/core/recorder/emit.py
===============================
Emit a runnable ``*_recorded.py`` flow from recorded steps (A1).

Produces a self-contained async script that drives a fresh Playwright page
through the recorded NL steps via the :class:`BubblegumSession` API. The
resolved selector for each step rides along as a ``# fallback:`` comment, and
actions that could not be phrased as NL are emitted as ``# skipped:`` comments
so nothing is silently lost. The script ends with ``assert_all_passed()`` so a
replay surfaces any step that no longer resolves.
"""

from __future__ import annotations

from bubblegum.core.recorder.models import RecordedStep

_HEADER = '''"""Recorded with `bubblegum record` — Bubblegum natural-language flow.

Edit the steps freely; each ``# fallback:`` comment shows the selector the
recorder resolved at capture time. Run with:

    python {filename}
"""
import asyncio

from playwright.async_api import async_playwright

from bubblegum import BubblegumSession


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless={headless})
        page = await browser.new_page()
        await page.goto({url!r})
        async with BubblegumSession.web(page) as s:
'''

_FOOTER = '''            s.assert_all_passed()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
'''

_INDENT = " " * 12  # inside `async with ... as s:` block


def _render_step(step: RecordedStep) -> str:
    if step.instruction is None:
        reason = step.skipped_reason or "no accessible name"
        return f"{_INDENT}# skipped: {reason}"
    comment = f"  # fallback: {step.fallback_ref}" if step.fallback_ref else ""
    return f"{_INDENT}await s.act({step.instruction!r}){comment}"


def emit_script(
    steps: list[RecordedStep],
    url: str,
    *,
    headless: bool = True,
    filename: str = "flow_recorded.py",
) -> str:
    """Render recorded steps into a runnable Python source string.

    ``url`` is the page the flow starts on; ``headless`` sets the launch mode in
    the generated script; ``filename`` only feeds the docstring run hint.
    """
    header = _HEADER.format(filename=filename, headless=headless, url=url)
    body_lines = [_render_step(s) for s in steps]
    if not any(s.instruction for s in steps):
        # Keep the block syntactically valid when nothing actionable was recorded.
        body_lines.append(f"{_INDENT}pass  # no actionable steps were recorded")
    body = "\n".join(body_lines)
    return f"{header}{body}\n{_FOOTER}"
