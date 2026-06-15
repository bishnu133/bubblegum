"""
bubblegum/cli/repl.py
=====================
The ``bubblegum repl`` command (A2) — interactive live-try mode.

Opens a session against a running page (``--url``, web) or app
(``--appium-url`` + ``--caps``, mobile), then evaluates typed natural-language
steps immediately, printing the resolved target + confidence. Thin wrapper over
:class:`BubblegumSession`: command grammar and execution live in
``bubblegum.core.repl``; this module only owns the browser/driver lifecycle and
the read-eval-print loop.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from bubblegum.core.repl import HELP_TEXT, evaluate, parse_repl_line

logger = logging.getLogger(__name__)

_PROMPT = "bubblegum> "


async def repl_loop(
    session,
    *,
    dry_run: bool = False,
    read_line: Callable[[str], Awaitable[str | None]] | None = None,
    emit: Callable[[str], None] = print,
) -> None:
    """Run the read-eval-print loop against an open ``session``.

    ``read_line(prompt)`` returns the next input line, or None on EOF. Defaults
    to reading stdin on a worker thread so the event loop is not blocked.
    ``emit`` prints a line of output (overridable for tests). The loop owns the
    meta commands (help / quit / dry toggle); everything else goes to
    :func:`evaluate`.
    """
    if read_line is None:
        read_line = _stdin_reader()

    emit("Bubblegum REPL — type :help for commands, :quit to exit.")
    if dry_run:
        emit("(resolve-only mode is ON)")

    while True:
        try:
            line = await read_line(_PROMPT)
        except (EOFError, KeyboardInterrupt):
            line = None
        if line is None:
            emit("")  # newline after the prompt on EOF/Ctrl-D
            return

        command = parse_repl_line(line)
        if command.kind == "empty":
            continue
        if command.kind == "quit":
            return
        if command.kind == "help":
            emit(HELP_TEXT)
            continue
        if command.kind == "toggle_dry":
            dry_run = _resolve_toggle(command.text, dry_run)
            emit(f"resolve-only mode is {'ON' if dry_run else 'OFF'}")
            continue

        emit(await evaluate(session, command, dry_run=dry_run))


def _resolve_toggle(arg: str, current: bool) -> bool:
    if arg in {"on", "true", "1", "yes"}:
        return True
    if arg in {"off", "false", "0", "no"}:
        return False
    return not current


def _stdin_reader() -> Callable[[str], Awaitable[str | None]]:
    """Build an async stdin reader that returns None on EOF."""

    async def read(prompt: str) -> str | None:
        def _blocking() -> str | None:
            try:
                return input(prompt)
            except EOFError:
                return None

        return await asyncio.to_thread(_blocking)

    return read


# ---------------------------------------------------------------------------
# Launchers
# ---------------------------------------------------------------------------


async def _run_web(url: str | None, *, headless: bool, dry_run: bool) -> None:
    from playwright.async_api import async_playwright

    from bubblegum.session import BubblegumSession

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            page.set_default_timeout(5_000)
            nav_error: str | None = None
            if url:
                try:
                    await page.goto(url)
                except Exception as exc:  # noqa: BLE001 — keep the REPL alive
                    nav_error = str(exc).splitlines()[0]
            async with BubblegumSession.web(page) as session:
                if nav_error:
                    print(
                        f"Could not open {url}: {nav_error}\n"
                        "Starting the REPL anyway — use ':open <url>' to navigate."
                    )
                await repl_loop(session, dry_run=dry_run)
        finally:
            await browser.close()


async def _run_mobile(appium_url: str, caps_raw: str | None, *, dry_run: bool) -> None:
    from bubblegum.session import BubblegumSession
    from bubblegum.testing.appium_driver import create_appium_driver, load_capabilities

    caps = load_capabilities(caps_raw)
    driver = create_appium_driver(appium_url, caps)
    try:
        async with BubblegumSession.mobile(driver) as session:
            await repl_loop(session, dry_run=dry_run)
    finally:
        try:
            driver.quit()
        except Exception:  # noqa: BLE001
            logger.debug("driver.quit() failed", exc_info=True)


def run_repl(
    *,
    url: str | None = None,
    appium_url: str | None = None,
    caps: str | None = None,
    headless: bool = False,
    dry_run: bool = False,
) -> int:
    """Synchronous entry point for the ``repl`` subcommand. Returns an exit code."""
    if appium_url:
        try:
            asyncio.run(_run_mobile(appium_url, caps, dry_run=dry_run))
        except Exception as exc:  # noqa: BLE001 — clean CLI error
            logger.debug("mobile REPL failed", exc_info=True)
            print(f"Could not start mobile REPL: {exc}")
            return 1
        return 0

    try:
        import playwright  # noqa: F401
    except ImportError:
        print(
            "Playwright is required for `bubblegum repl --url`. Install it with:\n"
            '    pip install "bubblegum-ai[web]"\n'
            "    python -m playwright install chromium"
        )
        return 2

    try:
        asyncio.run(_run_web(url, headless=headless, dry_run=dry_run))
    except Exception as exc:  # noqa: BLE001 — clean CLI error
        logger.debug("web REPL failed", exc_info=True)
        print(f"REPL exited with error: {exc}")
        return 1
    return 0
