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


# --- Uniqueness tokens: {{timestamp}} / {{uuid}} / {{random}} ----------------


def test_timestamp_seconds_default():
    # Default is Unix epoch seconds; compare against the same clock the test uses
    # so it is deterministic regardless of the machine's timezone.
    assert render_token("timestamp", now=NOW) == str(int(NOW.timestamp()))


def test_timestamp_milliseconds():
    assert render_token("timestamp:ms", now=NOW) == str(int(NOW.timestamp() * 1000))


def test_timestamp_with_strftime_format():
    # The readable-stamp form used for unique record names.
    assert render_token("timestamp|%Y%m%d%H%M%S", now=NOW) == "20260616020000"


def test_timestamp_bad_unit_is_left_verbatim():
    assert render_token("timestamp:nanos", now=NOW) is None
    assert substitute_dynamic_tokens("{{timestamp:nanos}}", now=NOW) == "{{timestamp:nanos}}"


def test_uuid_full_and_truncated():
    full = render_token("uuid", now=NOW)
    assert full is not None and len(full) == 32
    int(full, 16)  # valid hex
    assert len(render_token("uuid:8", now=NOW)) == 8


def test_uuid_is_unique_each_call():
    assert render_token("uuid", now=NOW) != render_token("uuid", now=NOW)


def test_uuid_bad_length_is_left_verbatim():
    assert render_token("uuid:0", now=NOW) is None
    assert render_token("uuid:abc", now=NOW) is None


def test_random_digits_default_and_sized():
    default = render_token("random", now=NOW)
    assert default.isdigit() and len(default) == 6
    sized = render_token("random:4", now=NOW)
    assert sized.isdigit() and len(sized) == 4


def test_random_bad_arg_is_left_verbatim():
    assert render_token("random:0", now=NOW) is None
    assert render_token("random:x", now=NOW) is None


def test_uniqueness_token_inside_a_phrase():
    out = substitute_dynamic_tokens("Badge_{{timestamp}}", now=NOW)
    assert out == f"Badge_{int(NOW.timestamp())}"


# --- Absolute time-of-day pin: {{today+2d@07:00}} ---------------------------


@pytest.mark.parametrize(
    "expr,expected",
    [
        # The headline use case: N days out at a fixed clock time.
        ("today+2d@07:00|%d/%m/%Y %H:%M", "18/06/2026 07:00"),
        ("today@07:00|%d/%m/%Y %H:%M", "16/06/2026 07:00"),
        ("tomorrow@9am|%d/%m/%Y %H:%M", "17/06/2026 09:00"),
        ("today@9:30pm|%H:%M", "21:30"),
        ("today@23:59|%H:%M", "23:59"),
        ("today@7|%H:%M", "07:00"),
        ("today+1mo+2d@07:00:00|%Y-%m-%d %H:%M:%S", "2026-07-18 07:00:00"),
        # "now" base: the "@" overrides the wall-clock, offsets still apply.
        ("now@00:00|%H:%M", "00:00"),
        ("now-1d@12:00|%d/%m/%Y %H:%M", "15/06/2026 12:00"),
    ],
)
def test_absolute_time_pin(expr, expected):
    assert render_token(expr, now=NOW) == expected


def test_absolute_time_default_format_includes_clock():
    # No "|" format given, but "@" is present -> default shows the time too.
    assert render_token("today+2d@07:00", now=NOW) == "2026-06-18 07:00"


def test_absolute_time_bad_value_is_left_verbatim():
    assert render_token("today@25:00", now=NOW) is None
    assert render_token("today@13pm", now=NOW) is None
    assert render_token("today@notatime", now=NOW) is None
    assert substitute_dynamic_tokens("{{today@25:00}}", now=NOW) == "{{today@25:00}}"


def test_absolute_time_inside_a_phrase():
    out = substitute_dynamic_tokens("Start {{today+2d@07:00|%d/%m/%Y %H:%M}}", now=NOW)
    assert out == "Start 18/06/2026 07:00"


# --- Named capture & recall: {{... as name}} / {{$name}} --------------------


def test_capture_and_recall_roundtrip():
    store: dict[str, str] = {}
    v = substitute_dynamic_tokens("Badge_{{timestamp|%Y%m%d%H%M%S as badgeName}}",
                                  now=NOW, store=store)
    assert v == "Badge_20260616020000"
    assert store == {"badgeName": "20260616020000"}
    # Recall the SAME value in a later call sharing the store.
    assert substitute_dynamic_tokens("{{$badgeName}}", now=NOW, store=store) == "20260616020000"
    # Reconstruct the full field value with the literal prefix.
    assert substitute_dynamic_tokens("Badge_{{$badgeName}}", now=NOW, store=store) == "Badge_20260616020000"


def test_recall_unknown_is_left_verbatim():
    store: dict[str, str] = {}
    assert substitute_dynamic_tokens("{{$missing}}", now=NOW, store=store) == "{{$missing}}"


def test_capture_uuid_and_random():
    store: dict[str, str] = {}
    u = substitute_dynamic_tokens("{{uuid:8 as rid}}", now=NOW, store=store)
    assert len(u) == 8 and store["rid"] == u
    assert substitute_dynamic_tokens("{{$rid}}", now=NOW, store=store) == u


def test_capture_does_not_leak_between_explicit_stores():
    a: dict[str, str] = {}
    b: dict[str, str] = {}
    substitute_dynamic_tokens("{{timestamp as x}}", now=NOW, store=a)
    assert "x" in a and "x" not in b


def test_variables_helpers():
    from bubblegum.core.parser import clear_variables, recall, remember, variables
    clear_variables()
    remember("k", "v")
    assert recall("k") == "v"
    assert variables() == {"k": "v"}
    clear_variables()
    assert variables() == {}
