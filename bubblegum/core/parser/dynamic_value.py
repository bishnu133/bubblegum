"""Dynamic value tokens for step inputs (parameterised dates/times).

Lets a tester express a *relative* value inside any step phrase instead of
hard-coding a literal that goes stale the next day. The classic case is a date
picker that needs "a future date":

    act('Enter "{{today+7d|%d/%m/%Y}}" into Start date')
    act('Enter "{{now+2h|%d/%m/%Y %H:%M}}" into Appointment')

Substitution runs on the *resolved input value* (see ``_decompose_for`` in
``sdk.py``), so it works for every channel and for both the Python SDK and the
Node client driving the engine over the bridge. A phrase with no ``{{ }}`` token
is returned untouched, so existing literal values are unaffected.

Token grammar
-------------
    {{ <base> [<offset>...] [ | <strftime-format> ] }}

* ``base``    — ``today`` / ``now`` (also ``tomorrow`` / ``yesterday``).
* ``offset``  — signed unit steps, chainable: ``+7d``, ``-3d``, ``+2w+1d``,
  ``+1mo``, ``-1y``, ``+2h``, ``+30min``, ``+45s``.
* ``format``  — any ``strftime`` string after a ``|``. Defaults:
  ``today`` → ``%Y-%m-%d`` and ``now`` → ``%Y-%m-%d %H:%M``.

Units: ``d`` days, ``w`` weeks, ``mo`` months, ``y`` years, ``h`` hours,
``min`` minutes, ``s`` seconds. (``mo``/``min`` are spelled out so a bare ``m``
is never ambiguous between months and minutes.)
"""

from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta

__all__ = ["substitute_dynamic_tokens", "render_token"]

# A {{ ... }} placeholder. Non-greedy so adjacent tokens don't merge.
_TOKEN_RE = re.compile(r"\{\{\s*(.*?)\s*\}\}")

# One signed offset step, e.g. "+7d", "-30min", "+1mo". Units are matched
# longest-first by the alternation so "min"/"mo" win over "m"-prefixed reads.
_OFFSET_RE = re.compile(r"([+-]\d+)\s*(mo|min|[dwyhs])", re.IGNORECASE)

_DEFAULT_FORMATS = {
    "today": "%Y-%m-%d",
    "tomorrow": "%Y-%m-%d",
    "yesterday": "%Y-%m-%d",
    "now": "%Y-%m-%d %H:%M",
}

_BASE_DAY_OFFSET = {"today": 0, "tomorrow": 1, "yesterday": -1}


def _add_months(dt: datetime, months: int) -> datetime:
    """Shift ``dt`` by whole months, clamping the day to the target month.

    e.g. Jan 31 + 1mo -> Feb 28/29. Avoids a python-dateutil dependency.
    """
    total = dt.month - 1 + months
    year = dt.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return dt.replace(year=year, month=month, day=min(dt.day, last_day))


def render_token(expr: str, *, now: datetime | None = None) -> str | None:
    """Render a single token's inner ``expr`` (the text between ``{{`` ``}}``).

    Returns the formatted string, or ``None`` when ``expr`` is not a recognised
    dynamic-value expression (so the caller can leave it verbatim).
    """
    base_now = now or datetime.now()

    body, sep, fmt = expr.partition("|")
    fmt = fmt.strip() if sep else ""
    body = body.strip()

    base_match = re.match(r"^(today|tomorrow|yesterday|now)", body, re.IGNORECASE)
    if not base_match:
        return None
    base = base_match.group(1).lower()
    remainder = body[base_match.end():]

    if base == "now":
        dt = base_now
    else:
        dt = base_now.replace(hour=0, minute=0, second=0, microsecond=0)
        dt += timedelta(days=_BASE_DAY_OFFSET[base])

    # Apply each offset step; reject the token if any leftover junk remains so
    # we never silently mis-render a typo'd expression.
    consumed = 0
    for m in _OFFSET_RE.finditer(remainder):
        if remainder[consumed:m.start()].strip():
            return None
        amount = int(m.group(1))
        unit = m.group(2).lower()
        if unit == "d":
            dt += timedelta(days=amount)
        elif unit == "w":
            dt += timedelta(weeks=amount)
        elif unit == "h":
            dt += timedelta(hours=amount)
        elif unit == "min":
            dt += timedelta(minutes=amount)
        elif unit == "s":
            dt += timedelta(seconds=amount)
        elif unit == "mo":
            dt = _add_months(dt, amount)
        elif unit == "y":
            dt = _add_months(dt, amount * 12)
        consumed = m.end()
    if remainder[consumed:].strip():
        return None

    return dt.strftime(fmt or _DEFAULT_FORMATS[base])


def substitute_dynamic_tokens(value: str | None, *, now: datetime | None = None) -> str | None:
    """Replace every ``{{ ... }}`` dynamic-value token in ``value``.

    Unrecognised tokens are left exactly as written. ``None`` and token-free
    strings pass straight through (cheap fast-path), so literal values are never
    altered. ``now`` is injectable for deterministic tests.
    """
    if not value or "{{" not in value:
        return value

    def _replace(match: re.Match[str]) -> str:
        rendered = render_token(match.group(1), now=now)
        return rendered if rendered is not None else match.group(0)

    return _TOKEN_RE.sub(_replace, value)
