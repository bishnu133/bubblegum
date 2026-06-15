"""
Unit coverage for the bridge CDP-attach (client-owned browser) path.

Exercises the pure pieces — `OpenSpec` parsing/validation and `select_cdp_page`
page selection over a fake browser — plus capability advertisement, with no real
Chromium or CDP endpoint. The live attach is integration-only.
"""

from __future__ import annotations

import json

import pytest

from bubblegum.bridge import protocol as p
from bubblegum.bridge.handlers import build_server
from bubblegum.bridge.sessions import OpenSpec, OpenedSession, select_cdp_page


# --- fakes ----------------------------------------------------------------
class _FakePage:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeContext:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages


class _FakeBrowser:
    def __init__(self, contexts: list[_FakeContext]) -> None:
        self.contexts = contexts


# --- OpenSpec parsing -----------------------------------------------------
def test_openspec_parses_cdp_endpoint_and_page_index():
    spec = OpenSpec.from_params(
        {"channel": "web", "cdp_endpoint": "http://localhost:9222", "page_index": 2}
    )
    assert spec.cdp_endpoint == "http://localhost:9222"
    assert spec.page_index == 2


def test_openspec_page_index_defaults_to_zero():
    spec = OpenSpec.from_params({"channel": "web", "cdp_endpoint": "http://x"})
    assert spec.page_index == 0


def test_openspec_cdp_on_mobile_is_invalid():
    with pytest.raises(p.BridgeError) as exc:
        OpenSpec.from_params({"channel": "mobile", "cdp_endpoint": "http://x"})
    assert exc.value.code == p.INVALID_PARAMS


@pytest.mark.parametrize("bad", [-1, True, "0", 1.5])
def test_openspec_rejects_bad_page_index(bad):
    with pytest.raises(p.BridgeError) as exc:
        OpenSpec.from_params({"channel": "web", "page_index": bad})
    assert exc.value.code == p.INVALID_PARAMS


# --- select_cdp_page ------------------------------------------------------
def test_select_cdp_page_flattens_contexts_and_indexes():
    browser = _FakeBrowser([
        _FakeContext([_FakePage("a"), _FakePage("b")]),
        _FakeContext([_FakePage("c")]),
    ])
    assert select_cdp_page(browser, 0).name == "a"
    assert select_cdp_page(browser, 2).name == "c"


def test_select_cdp_page_out_of_range():
    browser = _FakeBrowser([_FakeContext([_FakePage("a")])])
    with pytest.raises(p.BridgeError) as exc:
        select_cdp_page(browser, 5)
    assert exc.value.code == p.INVALID_PARAMS


def test_select_cdp_page_no_pages():
    browser = _FakeBrowser([_FakeContext([])])
    with pytest.raises(p.BridgeError) as exc:
        select_cdp_page(browser, 0)
    assert exc.value.code == p.UNSUPPORTED


# --- capability + wiring --------------------------------------------------
@pytest.mark.asyncio
async def test_handshake_advertises_cdp_capability():
    server, _ = build_server()
    raw = await server.handle_message(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "handshake"})
    )
    caps = json.loads(raw)["result"]["capabilities"]
    assert "channel.web.cdp" in caps


@pytest.mark.asyncio
async def test_session_open_forwards_cdp_spec_to_factory():
    seen: dict[str, object] = {}

    async def factory(spec: OpenSpec) -> OpenedSession:
        seen["cdp_endpoint"] = spec.cdp_endpoint
        seen["page_index"] = spec.page_index

        async def aclose() -> None:
            return None

        return OpenedSession(session=object(), aclose=aclose)

    server, _ = build_server(factory=factory)
    raw = await server.handle_message(
        json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "session.open",
            "params": {"channel": "web", "cdp_endpoint": "http://localhost:9222", "page_index": 1},
        })
    )
    assert "session_id" in json.loads(raw)["result"]
    assert seen == {"cdp_endpoint": "http://localhost:9222", "page_index": 1}
