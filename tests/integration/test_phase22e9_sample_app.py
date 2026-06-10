"""Phase 22E-9: Acme Notes sample app — live integration.

Gated by ``--playwright``. Runs the exact flows the tester quickstart
documents (docs/getting-started-for-testers.md) through the public
``bubblegum_web`` + ``sample_app`` fixtures, so the docs are continuously
proven against real Chromium:

  - happy-path login lands on the dashboard
  - wrong password surfaces the error alert, no navigation
  - settings round trip: checkbox + select + save + status text
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.bubblegum, pytest.mark.asyncio]


async def test_login_reaches_dashboard(bubblegum_web, sample_app):
    await bubblegum_web.goto(f"{sample_app}/login.html")

    await bubblegum_web.act('Enter "tester" into Username')
    await bubblegum_web.act('Enter "bubblegum!" into Password')
    await bubblegum_web.act("Click Sign in")

    assert bubblegum_web.page.url.endswith("dashboard.html")
    assert await bubblegum_web.is_visible("Dashboard")
    assert await bubblegum_web.is_visible("Welcome back, tester.")
    bubblegum_web.assert_all_passed()


async def test_wrong_password_shows_error(bubblegum_web, sample_app):
    await bubblegum_web.goto(f"{sample_app}/login.html")

    await bubblegum_web.act('Enter "tester" into Username')
    await bubblegum_web.act('Enter "nope" into Password')
    await bubblegum_web.act("Click Sign in")

    assert bubblegum_web.page.url.endswith("login.html")
    assert await bubblegum_web.page.locator("#error").is_visible()
    bubblegum_web.assert_all_passed()


async def test_settings_round_trip(bubblegum_web, sample_app):
    await bubblegum_web.goto(f"{sample_app}/settings.html")

    await bubblegum_web.act("Check Email notifications")
    await bubblegum_web.act("Select German from Language")
    await bubblegum_web.act("Click Save")

    assert await bubblegum_web.is_checked("Email notifications")
    assert await bubblegum_web.selected_value("Language") == "de"
    assert await bubblegum_web.is_visible("Settings saved.")
    bubblegum_web.assert_all_passed()
