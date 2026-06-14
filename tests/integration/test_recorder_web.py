"""A1 real-browser test: record a login flow, then replay the emitted NL steps.

Gated behind --playwright. Attaches the recorder to a context off the shared
``bubblegum_browser`` (so the init script + binding are installed before the
page navigates), drives a manual-style login on the sample app, derives NL
steps, and asserts they (a) read like hand-written Bubblegum steps and (b) pass
on replay against a fresh page — the A1 acceptance criterion.
"""

from __future__ import annotations

import pytest

from bubblegum.core.recorder import ActionRecorder, emit_script
from bubblegum.session import BubblegumSession

pytestmark = [
    pytest.mark.playwright,
    pytest.mark.bubblegum,
    pytest.mark.asyncio(loop_scope="session"),
]


async def _drive_login(page) -> None:
    """Perform a manual-style login. Filling the next field / clicking the
    button blurs the previous input, which fires the ``change`` events the
    recorder listens for."""
    await page.fill("#username", "tester")
    await page.fill("#password", "bubblegum!")
    await page.click("#signin")
    await page.wait_for_url("**/dashboard.html")


async def test_record_login_emits_runnable_nl_steps(bubblegum_browser, sample_app):
    login_url = f"{sample_app}/login.html"

    # --- record -------------------------------------------------------
    recorder = ActionRecorder()
    rec_context = await bubblegum_browser.new_context()
    try:
        await recorder.attach(rec_context)
        page = await rec_context.new_page()
        await page.goto(login_url)
        await _drive_login(page)
    finally:
        await rec_context.close()

    steps = recorder.steps()
    instructions = [s.instruction for s in steps if s.instruction]

    # The recorder produced clean, hand-written-looking NL steps.
    assert 'Enter "tester" into Username' in instructions
    assert 'Enter "bubblegum!" into Password' in instructions
    assert "Click Sign in" in instructions
    assert instructions.index('Enter "tester" into Username') < instructions.index("Click Sign in")

    # The emitted script is valid, runnable Python.
    src = emit_script(steps, login_url, filename="login_recorded.py")
    compile(src, "<login_recorded>", "exec")
    assert "BubblegumSession.web(page)" in src

    # --- replay -------------------------------------------------------
    replay_context = await bubblegum_browser.new_context()
    try:
        replay_page = await replay_context.new_page()
        replay_page.set_default_timeout(5_000)
        await replay_page.goto(login_url)
        async with BubblegumSession.web(replay_page) as s:
            for step in steps:
                if step.instruction:
                    await s.act(step.instruction)
            # Landed on the authenticated dashboard via NL steps alone.
            await replay_page.wait_for_url("**/dashboard.html")
            s.assert_all_passed()
    finally:
        await replay_context.close()
