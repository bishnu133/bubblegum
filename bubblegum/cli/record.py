"""
bubblegum/cli/record.py
=======================
The ``bubblegum record`` command (A1).

Launches a (headed) Chromium window, navigates to the start URL, and injects
the recorder. The author clicks through their flow; each interaction streams
back as a structured event. When the browser window is closed the captured
actions are derived into NL steps and written as a runnable ``*_recorded.py``.

Browser orchestration lives here (I/O); the capture/derivation/emission logic
is the browser-free core in ``bubblegum.core.recorder``.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from bubblegum.core.recorder import ActionRecorder, emit_script

logger = logging.getLogger(__name__)


async def record_flow(
    url: str,
    *,
    headless: bool = False,
    emit_headless: bool = True,
    out_filename: str = "flow_recorded.py",
) -> str:
    """Drive an interactive recording session and return emitted script source.

    Opens a browser at ``url``, records until the window is closed, then emits a
    runnable flow. ``headless`` controls the *recording* browser (default
    headed so a human can interact); ``emit_headless`` controls the launch mode
    written into the generated script.
    """
    from playwright.async_api import async_playwright

    recorder = ActionRecorder()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        await recorder.attach(context)
        page = await context.new_page()
        await page.goto(url)

        # Block until the author closes the browser window.
        closed = asyncio.Event()
        browser.on("disconnected", lambda: closed.set())
        print("Recording… interact with the page, then close the browser window to finish.")
        await closed.wait()

    steps = recorder.steps()
    return emit_script(steps, url, headless=emit_headless, filename=out_filename)


def run_record(url: str, out: str, *, headless: bool = False, emit_headless: bool = True) -> int:
    """Synchronous entry point for the ``record`` subcommand. Returns exit code."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        print(
            "Playwright is required for `bubblegum record`. Install it with:\n"
            '    pip install "bubblegum-ai[web]"\n'
            "    python -m playwright install chromium"
        )
        return 2

    out_path = Path(out)
    try:
        source = asyncio.run(
            record_flow(
                url,
                headless=headless,
                emit_headless=emit_headless,
                out_filename=out_path.name,
            )
        )
    except Exception as exc:  # noqa: BLE001 — surface a clean CLI error
        logger.debug("record_flow failed", exc_info=True)
        print(f"Recording failed: {exc}")
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(source, encoding="utf-8")
    print(f"Wrote recorded flow to {out_path}")
    return 0
