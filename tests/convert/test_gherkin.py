"""Unit tests for the lenient Gherkin parser."""

from __future__ import annotations

from bubblegum.convert.gherkin import clean_text, parse_gherkin


def test_parses_given_when_then_and():
    cell = (
        "Given I open the Login page\n"
        "When I enter \"tom\" into Username\n"
        "And I click Sign in\n"
        "Then I see the Dashboard"
    )
    steps = parse_gherkin(cell)
    assert [s.keyword for s in steps] == ["given", "when", "and", "then"]
    assert steps[1].text == 'I enter "tom" into Username'


def test_smart_quotes_and_dashes_normalized():
    assert clean_text("badge ‘View All’ — done") == "badge 'View All' - done"


def test_continuation_lines_join_previous_step():
    cell = (
        "Then they will see existing fields appear under this section:\n"
        "  Consecutive Count\n"
        "  Cycle of Award"
    )
    steps = parse_gherkin(cell)
    assert len(steps) == 1
    assert "Consecutive Count" in steps[0].text
    assert "Cycle of Award" in steps[0].text


def test_structural_lines_skipped():
    cell = (
        "@tag\n"
        "Scenario: something\n"
        "Given a page\n"
        "| a | b |\n"
        "Then done"
    )
    steps = parse_gherkin(cell)
    assert [s.keyword for s in steps] == ["given", "then"]


def test_keywordless_imperative_column():
    cell = "Open the login page\nClick Sign in"
    steps = parse_gherkin(cell)
    assert len(steps) == 2
    assert steps[0].keyword == ""
    assert steps[0].text == "Open the login page"


def test_empty_cell_returns_empty():
    assert parse_gherkin("") == []
    assert parse_gherkin(None) == []
