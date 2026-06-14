from __future__ import annotations

import pytest

from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter
from bubblegum.core import sdk
from bubblegum.core.network import (
    describe_matcher,
    extract_network_spec,
    find_matching_response,
    parse_network_matcher,
    response_matches,
)
from bubblegum.session import BubblegumSession


# ---------------------------------------------------------------------------
# Matcher parsing
# ---------------------------------------------------------------------------


def test_parse_full_spec():
    m = parse_network_matcher("POST /api/login 200")
    assert m == {"method": "POST", "url": "/api/login", "status": 200}


def test_parse_url_only():
    assert parse_network_matcher("/api/login") == {"method": None, "url": "/api/login", "status": None}


def test_parse_status_only():
    assert parse_network_matcher("500") == {"method": None, "url": None, "status": 500}


def test_parse_method_and_url():
    assert parse_network_matcher("DELETE /api/users/5") == {
        "method": "DELETE", "url": "/api/users/5", "status": None,
    }


def test_parse_bare_method_or_empty_is_none():
    assert parse_network_matcher("POST") is None
    assert parse_network_matcher("") is None
    assert parse_network_matcher(None) is None


def test_extract_spec_from_instruction():
    assert extract_network_spec("the login should POST /api/login 200") == "POST /api/login 200"
    assert extract_network_spec("nothing here") is None


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def test_response_matches_all_parts():
    rec = {"method": "POST", "url": "https://app.test/api/login?x=1", "status": 200}
    assert response_matches(rec, parse_network_matcher("POST /api/login 200"))
    assert response_matches(rec, parse_network_matcher("/api/login"))
    assert response_matches(rec, parse_network_matcher("200"))


def test_response_mismatch_on_each_part():
    rec = {"method": "GET", "url": "https://app.test/api/login", "status": 200}
    assert not response_matches(rec, parse_network_matcher("POST /api/login 200"))
    assert not response_matches(rec, parse_network_matcher("/api/logout"))
    assert not response_matches(rec, parse_network_matcher("500"))


def test_glob_url_matching():
    rec = {"method": "GET", "url": "https://app.test/api/users/42", "status": 200}
    assert response_matches(rec, parse_network_matcher("GET /api/users/* 200"))


def test_find_matching_returns_most_recent():
    records = [
        {"method": "GET", "url": "/api/login", "status": 500},
        {"method": "POST", "url": "/api/login", "status": 200},
        {"method": "GET", "url": "/api/me", "status": 200},
    ]
    found = find_matching_response(records, parse_network_matcher("/api/login 200"))
    assert found == {"method": "POST", "url": "/api/login", "status": 200}


def test_describe_matcher():
    assert describe_matcher(parse_network_matcher("POST /api/login 200")) == "POST /api/login 200"


# ---------------------------------------------------------------------------
# Adapter recorder + assert_network (fake page, no real browser)
# ---------------------------------------------------------------------------


class _FakeReq:
    def __init__(self, method):
        self.method = method


class _FakeResp:
    def __init__(self, method, url, status):
        self.request = _FakeReq(method)
        self.url = url
        self.status = status


class _FakeNetPage:
    def __init__(self):
        self._handlers = []

    def on(self, event, handler):
        if event == "response":
            self._handlers.append(handler)

    def emit(self, method, url, status):
        for h in self._handlers:
            h(_FakeResp(method, url, status))

    async def wait_for_response(self, predicate, timeout=None):
        raise RuntimeError("timed out waiting for response")


@pytest.mark.asyncio
async def test_adapter_records_and_matches_seen_response():
    page = _FakeNetPage()
    adapter = PlaywrightAdapter(page)  # __init__ wires the recorder
    page.emit("POST", "https://app.test/api/login", 200)

    ok, detail = await adapter.assert_network(parse_network_matcher("POST /api/login 200"))
    assert ok is True
    assert "200" in detail


@pytest.mark.asyncio
async def test_adapter_reports_miss_clearly():
    page = _FakeNetPage()
    adapter = PlaywrightAdapter(page)
    page.emit("GET", "https://app.test/api/other", 200)

    ok, detail = await adapter.assert_network(parse_network_matcher("POST /api/login 200"), timeout_ms=10)
    assert ok is False
    assert "no response matching" in detail


# ---------------------------------------------------------------------------
# sdk.verify / session network branch (fake adapter)
# ---------------------------------------------------------------------------


class _FakeNetAdapter:
    def __init__(self, result):
        self._result = result
        self.matcher = None
        self.timeout_ms = None

    async def assert_network(self, matcher, *, timeout_ms=5000):
        self.matcher = matcher
        self.timeout_ms = timeout_ms
        return self._result


@pytest.mark.asyncio
async def test_verify_network_passes(monkeypatch):
    adapter = _FakeNetAdapter((True, "matched POST https://app.test/api/login 200"))
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)
    s = BubblegumSession.web(object())

    result = await s.verify("login succeeded", assertion_type="network",
                            expected_value="POST /api/login 200")
    assert result.status == "passed"
    assert adapter.matcher == {"method": "POST", "url": "/api/login", "status": 200}
    assert result.target.metadata["network_assertion"]["passed"] is True


@pytest.mark.asyncio
async def test_verify_network_fails_clearly(monkeypatch):
    adapter = _FakeNetAdapter((False, "no response matching 'POST /api/login 200' (3 response(s) seen)"))
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)
    s = BubblegumSession.web(object())

    result = await s.verify("login succeeded", assertion_type="network",
                            expected_value="POST /api/login 200")
    assert result.status == "failed"
    assert result.error.error_type == "NetworkAssertionError"
    assert "no response matching" in result.error.message


@pytest.mark.asyncio
async def test_verify_network_requires_spec(monkeypatch):
    adapter = _FakeNetAdapter((True, "should not be called"))
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)
    s = BubblegumSession.web(object())

    result = await s.verify("login worked", assertion_type="network")
    assert result.status == "failed"
    assert result.error.error_type == "NetworkAssertionError"
    assert adapter.matcher is None  # never reached the adapter


@pytest.mark.asyncio
async def test_verify_network_is_web_only(monkeypatch):
    adapter = _FakeNetAdapter((True, "x"))
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)
    s = BubblegumSession.mobile(object())

    result = await s.verify("login succeeded", assertion_type="network",
                            expected_value="POST /api/login 200")
    assert result.status == "failed"
    assert result.error.error_type == "UnsupportedChannelError"
