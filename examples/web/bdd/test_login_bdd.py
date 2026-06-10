"""Bubblegum BDD example — Acme Notes login via Given/When/Then.

Run on a machine with a browser:

    pip install -e ".[web,test,bdd]"
    python -m playwright install chromium
    pytest examples/web/bdd/ --playwright

The When/Then steps come from bubblegum.bdd.steps (plain-English actions and
assertions); this module supplies only the project-specific Given (navigation),
using the `sample_app` fixture that serves the bundled login/dashboard pages.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, scenarios

# Registers the catch-all When + Then steps that route to the NL engine.
from bubblegum.bdd.steps import *  # noqa: F401,F403

pytestmark = [pytest.mark.playwright, pytest.mark.bubblegum]

scenarios("login.feature")


@given("I am on the login page")
async def _open_login(bubblegum_web, sample_app):
    await bubblegum_web.goto(f"{sample_app}/login.html")
