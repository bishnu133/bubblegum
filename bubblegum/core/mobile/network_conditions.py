"""
bubblegum/core/mobile/network_conditions.py
============================================
Parse mobile network-condition verbs from natural language (M6).

Network conditions are device-level — go offline, toggle airplane/wifi/data,
throttle to a 2G/3G/4G profile — with no UI element to ground.
``parse_network_condition`` recognizes them (start-anchored, so a real button
named "Wi-Fi" is not hijacked) and returns a ``SystemAction`` (reusing the M2
type) so the existing ``sdk._act_system`` + ``AppiumAdapter.execute_system_action``
machinery runs them with no extra result/error plumbing.

Two kinds are produced:
  - ``set_connectivity`` — arg ``{"state": offline|online|airplane_on|airplane_off|
    wifi_on|wifi_off|data_on|data_off}``. Real, supported on Android devices and
    emulators (``mobile: setConnectivity``).
  - ``set_network_speed`` — arg ``{"profile": <as-typed>, "netspeed": <emulator
    token>}``. Android **emulator** only (throughput/latency profiles).
"""

from __future__ import annotations

import re

from bubblegum.core.mobile.system_actions import SystemAction

I = re.IGNORECASE

# NL speed words → Android emulator ``netspeed`` tokens (see `emulator -netspeed`
# / `network speed`). Slowest → fastest; "full" is unthrottled.
_SPEED_PROFILES: dict[str, str] = {
    "gsm": "gsm",
    "2g": "gsm",
    "slow": "gsm",
    "gprs": "gprs",
    "edge": "edge",
    "2.5g": "edge",
    "umts": "umts",
    "3g": "umts",
    "hsdpa": "hsdpa",
    "3.5g": "hsdpa",
    "lte": "lte",
    "4g": "lte",
    "5g": "full",
    "full": "full",
    "fast": "full",
}

# Connectivity (on/off) verbs — most-specific first, all start-anchored.
_OFFLINE_RE = re.compile(
    r"^(?:go\s+offline"
    r"|simulate\s+(?:going\s+)?(?:offline|no\s+(?:network|connection|connectivity)|network\s+loss)"
    r"|disable\s+(?:the\s+)?(?:network|connectivity)"
    r"|disconnect(?:\s+(?:the\s+)?network)?)$",
    I,
)
_ONLINE_RE = re.compile(
    r"^(?:go\s+online"
    r"|restore\s+(?:the\s+)?(?:network|connectivity)"
    r"|reset\s+(?:the\s+)?(?:network|connectivity)"
    r"|enable\s+(?:the\s+)?(?:network|connectivity)"
    r"|reconnect(?:\s+(?:the\s+)?network)?)$",
    I,
)
_AIRPLANE_RE = re.compile(
    r"^(?P<onoff>enable|disable|turn\s+on|turn\s+off|activate|deactivate)\s+"
    r"(?:the\s+)?(?:airplane|flight)\s*mode$",
    I,
)
_WIFI_RE = re.compile(
    r"^(?P<onoff>enable|disable|turn\s+on|turn\s+off)\s+(?:the\s+)?wi-?fi$", I
)
_DATA_RE = re.compile(
    r"^(?P<onoff>enable|disable|turn\s+on|turn\s+off)\s+(?:the\s+)?(?:mobile\s+|cellular\s+)?data$",
    I,
)

# Speed-profile verbs.
_speed_alt = "|".join(re.escape(k) for k in sorted(_SPEED_PROFILES, key=len, reverse=True))
_SPEED_RE = re.compile(
    r"^(?:simulate|set|throttle|emulate|switch\s+to|change\s+to)\s+"
    r"(?:the\s+)?(?:network\s+(?:speed\s+|condition\s+|connection\s+)?)?(?:to\s+)?"
    rf"(?P<profile>{_speed_alt})"
    r"(?:\s+(?:network|speed|connection))?$",
    I,
)


def _is_on(token: str) -> bool:
    t = token.strip().lower()
    return t in {"enable", "turn on", "activate"}


def parse_network_condition(instruction: str) -> SystemAction | None:
    """Return the SystemAction for a mobile network verb, or None.

    Conservative and start-anchored; non-network phrasing returns None so normal
    grounding handles it.
    """
    text = (instruction or "").strip()
    if not text:
        return None

    if _OFFLINE_RE.match(text):
        return SystemAction("set_connectivity", {"state": "offline"})
    if _ONLINE_RE.match(text):
        return SystemAction("set_connectivity", {"state": "online"})

    m = _AIRPLANE_RE.match(text)
    if m:
        # Airplane mode ON disconnects, so "on" maps to the airplane_on state.
        return SystemAction(
            "set_connectivity",
            {"state": "airplane_on" if _is_on(m.group("onoff")) else "airplane_off"},
        )

    m = _WIFI_RE.match(text)
    if m:
        return SystemAction(
            "set_connectivity",
            {"state": "wifi_on" if _is_on(m.group("onoff")) else "wifi_off"},
        )

    m = _DATA_RE.match(text)
    if m:
        return SystemAction(
            "set_connectivity",
            {"state": "data_on" if _is_on(m.group("onoff")) else "data_off"},
        )

    m = _SPEED_RE.match(text)
    if m:
        profile = m.group("profile").lower()
        return SystemAction(
            "set_network_speed",
            {"profile": profile, "netspeed": _SPEED_PROFILES[profile]},
        )

    return None
