"""Unit tests for parameterised dynamic-value tokens (relative dates/times).

Covers ``substitute_dynamic_tokens`` / ``render_token`` directly with an
injected ``now`` so the expected output is deterministic, plus the integration
point: a date-picker-style phrase carries the expanded value through
``decompose`` is *not* enough (substitution runs in the SDK), so the unit layer
is exercised here and the SDK wiring is covered in the integration suite.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from bubblegum.core.parser import render_token, substitute_dynamic_tokens

# A fixed reference instant: Tue 16 Jun 2026, 02:00:00.
NOW = datetime(2026, 6, 16, 2, 0, 0)


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("today", "2026-06-16"),
        ("tomorrow", "2026-06-17"),
        ("yesterday", "2026-06-15"),
        ("today+7d", "2026-06-23"),
        ("today-1d", "2026-06-15"),
        ("today+2w", "2026-06-30"),
        ("today+1mo", "2026-07-16"),
        ("today-1y", "2025-06-16"),
        ("today+1mo+2d", "2026-07-18"),
        # Custom strftime via the "|" separator (the date-picker use case).
        ("today|%d/%m/%Y", "16/06/2026"),
        ("today+7d|%d/%m/%Y", "23/06/2026"),
        ("now|%d/%m/%Y %H:%M", "16/06/2026 02:00"),
        ("now+2h|%H:%M", "04:00"),
        ("now+30min|%H:%M", "02:30"),
    ],
)
def test_render_token(expr, expected):
    assert render_token(expr, now=NOW) == expected


def test_default_formats():
    assert render_token("today", now=NOW) == "2026-06-16"
    assert render_token("now", now=NOW) == "2026-06-16 02:00"


def test_month_clamps_to_end_of_short_month():
    # Jan 31 + 1mo -> Feb 28 (2026 is not a leap year).
    assert render_token("today|%Y-%m-%d", now=datetime(2026, 1, 31)) == "2026-01-31"
    assert render_token("today+1mo|%Y-%m-%d", now=datetime(2026, 1, 31)) == "2026-02-28"


def test_substitute_inside_a_phrase():
    out = substitute_dynamic_tokens('Enter {{today+7d|%d/%m/%Y}} now', now=NOW)
    assert out == "Enter 23/06/2026 now"


def test_multiple_tokens_in_one_value():
    out = substitute_dynamic_tokens("{{today|%d/%m/%Y}} to {{today+7d|%d/%m/%Y}}", now=NOW)
    assert out == "16/06/2026 to 23/06/2026"


def test_literal_values_are_untouched():
    assert substitute_dynamic_tokens("16/06/2026 02:00", now=NOW) == "16/06/2026 02:00"
    assert substitute_dynamic_tokens("Password@123", now=NOW) == "Password@123"
    assert substitute_dynamic_tokens(None, now=NOW) is None
    assert substitute_dynamic_tokens("", now=NOW) == ""


def test_unknown_token_is_left_verbatim():
    # Not a recognised expression -> leave the braces exactly as written.
    assert substitute_dynamic_tokens("{{not a date}}", now=NOW) == "{{not a date}}"
    assert render_token("today+5x", now=NOW) is None
    assert render_token("today garbage", now=NOW) is None


def test_whitespace_tolerance():
    assert substitute_dynamic_tokens("{{  today+7d | %d/%m/%Y  }}", now=NOW) == "23/06/2026"
