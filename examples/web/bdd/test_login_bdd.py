"""Bubblegum BDD example — Acme Notes login via Given/When/Then.

Run on a machine with a browser (no --playwright needed; the BDD fixtures own
their own headless Chromium):

    pip install -e ".[web,test,bdd]"
    python -m playwright install chromium
    pytest examples/web/bdd/
    # watch it run:  BUBBLEGUM_BDD_HEADED=1 pytest examples/web/bdd/ -s

The When/Then steps come from bubblegum.bdd.steps (plain-English actions and
assertions, routed through the NL engine). The bubblegum_web + bubblegum_bdd_loop
fixtures come from bubblegum.bdd.fixtures. This module supplies only the
project-specific Given (navigation), using the `sample_app` fixture (from the
installed Bubblegum pytest plugin) that serves the bundled login/dashboard pages.
"""

from __future__ import annotations

from pytest_bdd import given, scenarios

# Registers the catch-all When + Then step fixtures (note: `import *` is required
# so pytest-bdd's generated step-definition fixtures are collected).
from bubblegum.bdd.steps import *  # noqa: F401,F403

# Self-contained session + event-loop fixtures for BDD.
from bubblegum.bdd.fixtures import bubblegum_web, bubblegum_bdd_loop  # noqa: F401

scenarios("login.feature")


@given("I am on the login page")
def _open_login(bubblegum_web, bubblegum_bdd_loop, sample_app):
    bubblegum_bdd_loop.run_until_complete(
        bubblegum_web.goto(f"{sample_app}/login.html")
    )
