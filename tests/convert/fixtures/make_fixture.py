"""Regenerate the sample scenarios workbook used by the convert tests.

Run:  python tests/convert/fixtures/make_fixture.py

The data here is synthetic (no client/proprietary content) but mirrors the real
column layout: #, Feature/Epic, Test Scenario, User Persona, Functional Jira
Story, Verify (Gherkin), Result, Remarks.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

HEADERS = [
    "#", "Feature/Epic", "Test Scenario", "User Persona",
    "Functional Jira Story", "Verify", "Result", "Remarks",
]

ROWS = [
    (1, "[F][Web] Checkout coupon", "Verify a valid coupon applies a discount",
     "Shopper", "PROJ-101",
     'Given I am logged in as a "Shopper"\n'
     "And I open the Checkout page\n"
     'When I enter "SAVE10" into the Coupon code field\n'
     "And I click the Apply button\n"
     "Then I see the Discount applied message"),
    (2, "[F][Web] Checkout coupon", "Verify an invalid coupon is rejected",
     "Shopper", "PROJ-101",
     "Given I open the Checkout page\n"
     'When I enter "BOGUS" into the Coupon code field\n'
     "And I click the Apply button\n"
     "Then I see the Invalid coupon error"),
    (3, "[F][Web] Login", "Verify login with valid credentials",
     "Registered user", "PROJ-102",
     "Given I open the Login page\n"
     'When I enter "tomsmith" into the Username field\n'
     'And I enter "SuperSecret" into the Password field\n'
     "And I click the Sign in button\n"
     "Then I see the Dashboard heading"),
    (4, "[F][Backend] Rewards engine", "Verify points accrue after purchase",
     "Registered user", "PROJ-200",
     "Given a user with 0 reward points\n"
     "When an order of 100 dollars is completed\n"
     "Then the user has 100 reward points"),
]


def build() -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "UAT Scenario"
    ws.append(HEADERS)
    for r in ROWS:
        ws.append(list(r) + ["", ""])
    # A spacer row with an empty Verify cell — must be skipped by ingest.
    ws.append([5, "[F][Web] Login", "spacer", "", "", None, "", ""])
    out = Path(__file__).with_name("sample_scenarios.xlsx")
    wb.save(out)
    return out


if __name__ == "__main__":
    print("wrote", build())
