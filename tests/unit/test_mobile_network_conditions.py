"""Unit tests for mobile network-condition simulation (M6).

Browser/device-free: parser recognition of network verbs, AppiumAdapter
dispatch to the right `mobile:` command per platform (captured via a fake
driver), and the sdk.act routing that sends network verbs to the system path
before grounding (reusing the M2 machinery).
"""

from __future__ import annotations

import asyncio

import pytest

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core import sdk
from bubblegum.core.mobile.network_conditions import parse_network_condition


# ---------------------------------------------------------------------------
# parse_network_condition
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "instruction,kind,arg",
    [
        ("go offline", "set_connectivity", {"state": "offline"}),
        ("simulate no network", "set_connectivity", {"state": "offline"}),
        ("disable connectivity", "set_connectivity", {"state": "offline"}),
        ("disconnect network", "set_connectivity", {"state": "offline"}),
        ("go online", "set_connectivity", {"state": "online"}),
        ("restore the network", "set_connectivity", {"state": "online"}),
        ("reset network", "set_connectivity", {"state": "online"}),
        ("reconnect", "set_connectivity", {"state": "online"}),
        ("enable airplane mode", "set_connectivity", {"state": "airplane_on"}),
        ("turn on airplane mode", "set_connectivity", {"state": "airplane_on"}),
        ("disable airplane mode", "set_connectivity", {"state": "airplane_off"}),
        ("turn off flight mode", "set_connectivity", {"state": "airplane_off"}),
        ("turn off wifi", "set_connectivity", {"state": "wifi_off"}),
        ("enable wi-fi", "set_connectivity", {"state": "wifi_on"}),
        ("turn off mobile data", "set_connectivity", {"state": "data_off"}),
        ("enable data", "set_connectivity", {"state": "data_on"}),
        ("simulate 3g network", "set_network_speed", {"profile": "3g", "netspeed": "umts"}),
        ("set network to 2g", "set_network_speed", {"profile": "2g", "netspeed": "gsm"}),
        ("throttle network to edge", "set_network_speed", {"profile": "edge", "netspeed": "edge"}),
        ("simulate lte", "set_network_speed", {"profile": "lte", "netspeed": "lte"}),
        ("simulate 4g network", "set_network_speed", {"profile": "4g", "netspeed": "lte"}),
        ("simulate slow network", "set_network_speed", {"profile": "slow", "netspeed": "gsm"}),
        ("set network speed to full", "set_network_speed", {"profile": "full", "netspeed": "full"}),
    ],
)
def test_parse_network_condition(instruction, kind, arg):
    action = parse_network_condition(instruction)
    assert action is not None, instruction
    assert action.kind == kind
    assert action.arg == arg


def test_parse_network_condition_ignores_normal_steps():
    # Real UI controls / unrelated phrasing must not be hijacked.
    assert parse_network_condition("Click the Wi-Fi settings row") is None
    assert parse_network_condition("Verify airplane mode banner is visible") is None
    assert parse_network_condition("Enable notifications") is None
    assert parse_network_condition("Tap 3G icon") is None
    assert parse_network_condition("") is None


# ---------------------------------------------------------------------------
# AppiumAdapter dispatch
# ---------------------------------------------------------------------------


class _FakeDriver:
    def __init__(self, platform="Android"):
        self.capabilities = {"platformName": platform}
        self.scripts: list[tuple] = []

    def execute_script(self, name, args=None):
        self.scripts.append((name, args or {}))


def _run_system(driver, kind, arg=None):
    adapter = AppiumAdapter(driver)
    return asyncio.run(adapter.execute_system_action(kind, arg or {}))


def test_offline_cuts_all_radios():
    d = _FakeDriver("Android")
    out = _run_system(d, "set_connectivity", {"state": "offline"})
    assert d.scripts == [("mobile: setConnectivity", {"wifi": False, "data": False, "airplane": True})]
    assert out["state"] == "offline"
    assert out["airplane"] is True


def test_online_restores_wifi_and_data():
    d = _FakeDriver("Android")
    _run_system(d, "set_connectivity", {"state": "online"})
    assert d.scripts == [("mobile: setConnectivity", {"wifi": True, "data": True, "airplane": False})]


@pytest.mark.parametrize(
    "state,params",
    [
        ("airplane_on", {"airplane": True}),
        ("airplane_off", {"airplane": False}),
        ("wifi_on", {"wifi": True}),
        ("wifi_off", {"wifi": False}),
        ("data_on", {"data": True}),
        ("data_off", {"data": False}),
    ],
)
def test_single_radio_toggles(state, params):
    d = _FakeDriver("Android")
    _run_system(d, "set_connectivity", {"state": state})
    assert d.scripts == [("mobile: setConnectivity", params)]


def test_connectivity_unknown_state_raises():
    with pytest.raises(ValueError):
        _run_system(_FakeDriver("Android"), "set_connectivity", {"state": "warp"})


def test_connectivity_ios_unsupported():
    with pytest.raises(ValueError, match="Android-only"):
        _run_system(_FakeDriver("iOS"), "set_connectivity", {"state": "offline"})


def test_network_speed_dispatch():
    d = _FakeDriver("Android")
    out = _run_system(d, "set_network_speed", {"profile": "3g", "netspeed": "umts"})
    assert d.scripts == [("mobile: networkSpeed", {"netspeed": "umts"})]
    assert out["profile"] == "3g"
    assert out["netspeed"] == "umts"


def test_network_speed_requires_netspeed():
    with pytest.raises(ValueError):
        _run_system(_FakeDriver("Android"), "set_network_speed", {})


def test_network_speed_ios_unsupported():
    with pytest.raises(ValueError, match="emulator-only"):
        _run_system(_FakeDriver("iOS"), "set_network_speed", {"netspeed": "lte"})


# ---------------------------------------------------------------------------
# sdk.act routing
# ---------------------------------------------------------------------------


class _RoutingAdapter:
    def __init__(self):
        self.system_calls: list[tuple] = []
        self.grounded = False

    async def execute_system_action(self, kind, arg=None):
        self.system_calls.append((kind, arg))
        return {"detail": f"did {kind}"}

    async def collect_context(self, _req):
        from bubblegum.core.schemas import UIContext

        self.grounded = True
        return UIContext(hierarchy_xml="<hierarchy/>", screen_signature="sig")


@pytest.mark.asyncio
async def test_act_routes_network_verb_before_grounding(monkeypatch):
    adapter = _RoutingAdapter()
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)

    result = await sdk.act("simulate 3g network", channel="mobile", driver=object())

    assert result.status == "passed"
    assert result.target.ref == "system:set_network_speed"
    assert adapter.system_calls == [("set_network_speed", {"profile": "3g", "netspeed": "umts"})]
    assert adapter.grounded is False
    # Outcome metadata is surfaced on the synthetic target.
    assert result.target.metadata["system_action"]["netspeed"] == "umts"


@pytest.mark.asyncio
async def test_act_offline_routes_to_connectivity(monkeypatch):
    adapter = _RoutingAdapter()
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)

    result = await sdk.act("go offline", channel="mobile", driver=object())

    assert result.status == "passed"
    assert adapter.system_calls == [("set_connectivity", {"state": "offline"})]
