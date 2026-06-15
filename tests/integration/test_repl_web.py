"""A2 real-browser test: the REPL evaluates typed NL steps live.

Gated behind --playwright. Drives the REPL's execution surface (the same path
the interactive loop uses) against the sample app and asserts a typed step
executes and reports its resolver + confidence — the A2 acceptance criterion —
plus that ``explain`` returns rationale and the loop runs end-to-end to :quit.
"""

from __future__ import annotations

import pytest

from bubblegum.cli.repl import repl_loop
from bubblegum.core.repl import evaluate, parse_repl_line

pytestmark = [
    pytest.mark.playwright,
    pytest.mark.bubblegum,
    pytest.mark.asyncio(loop_scope="session"),
]


def _scripted_reader(lines):
    it = iter(lines)

    async def read(_prompt):
        try:
            return next(it)
        except StopIteration:
            return None

    return read


async def test_repl_executes_and_reports_resolver(bubblegum_page, sample_app):
    s = bubblegum_page
    await s.goto(f"{sample_app}/login.html")

    # A typed act executes and reports the resolver + confidence.
    out = await evaluate(s, parse_repl_line('act("Enter \\"tester\\" into Username")'))
    assert "✓" in out
    assert "conf=" in out
    assert "✗ error" not in out

    # explain returns a (non-empty) rationale and does not raise.
    rationale = await evaluate(s, parse_repl_line('explain("Click Sign in")'))
    assert rationale.strip()
    assert "✗ error" not in rationale

    # dry(...) previews without acting.
    preview = await evaluate(s, parse_repl_line('dry("Click Sign in")'))
    assert "conf=" in preview


async def test_repl_loop_end_to_end_until_quit(bubblegum_page, sample_app):
    s = bubblegum_page
    await s.goto(f"{sample_app}/login.html")

    out_lines: list[str] = []
    await repl_loop(
        s,
        read_line=_scripted_reader(
            [
                'Enter "tester" into Username',
                'Enter "bubblegum!" into Password',
                "Click Sign in",
                ":quit",
                "this line is never read",
            ]
        ),
        emit=out_lines.append,
    )

    text = "\n".join(out_lines)
    assert "conf=" in text
    assert "✗ error" not in text
    # Landed on the authenticated dashboard via NL steps typed into the REPL.
    await s.page.wait_for_url("**/dashboard.html")
