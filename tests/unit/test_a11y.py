from __future__ import annotations

import pytest

from bubblegum.core import a11y, sdk
from bubblegum.core.a11y import (
    DEFAULT_AXE_PATH,
    evaluate_axe_results,
    filter_violations,
    impact_from_instruction,
    load_axe_script,
    normalize_impact,
    safe_violation_summary,
)
from bubblegum.session import BubblegumSession


_AXE_RESULTS = {
    "violations": [
        {
            "id": "color-contrast",
            "impact": "serious",
            "help": "Elements must have sufficient color contrast",
            "helpUrl": "https://dequeuniversity.com/rules/axe/4.11/color-contrast",
            "nodes": [{"target": ["#a"]}, {"target": ["#b"]}],
        },
        {
            "id": "image-alt",
            "impact": "critical",
            "help": "Images must have alternate text",
            "helpUrl": "https://dequeuniversity.com/rules/axe/4.11/image-alt",
            "nodes": [{"target": ["img.logo"]}],
        },
        {
            "id": "landmark-unique",
            "impact": None,  # axe sometimes reports null impact — never fails
            "help": "Landmarks should be unique",
            "nodes": [{"target": ["nav"]}],
        },
    ]
}


# ---------------------------------------------------------------------------
# Vendored axe + script loading
# ---------------------------------------------------------------------------


def test_vendored_axe_is_present_and_pinned():
    assert DEFAULT_AXE_PATH.is_file()
    head = DEFAULT_AXE_PATH.read_text(encoding="utf-8")[:600]
    assert "axe v4.11.0" in head
    # MPL attribution header retained (wraps across lines in the minified file).
    assert "Mozilla Public" in head and "MPL" in head


def test_load_axe_script_default():
    script = load_axe_script()
    assert "axe.version" in script or "axe v4.11.0" in script


def test_load_axe_script_custom_path(tmp_path):
    custom = tmp_path / "myaxe.js"
    custom.write_text("window.axe = {};", encoding="utf-8")
    assert load_axe_script(custom) == "window.axe = {};"


def test_load_axe_script_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_axe_script(tmp_path / "nope.js")


# ---------------------------------------------------------------------------
# Severity inference + filtering
# ---------------------------------------------------------------------------


def test_impact_from_instruction():
    assert impact_from_instruction("page has no critical a11y violations") == "critical"
    assert impact_from_instruction("no serious a11y issues") == "serious"
    assert impact_from_instruction("accessible page", default="moderate") == "moderate"
    # several named → strictest (lowest) threshold wins
    assert impact_from_instruction("no serious or critical violations") == "serious"


def test_normalize_impact_defaults_invalid_to_critical():
    assert normalize_impact("bogus") == "critical"
    assert normalize_impact(None) == "critical"
    assert normalize_impact("Serious") == "serious"


def test_filter_violations_threshold_critical():
    failing = filter_violations(_AXE_RESULTS, "critical")
    assert [v["id"] for v in failing] == ["image-alt"]


def test_filter_violations_threshold_serious_includes_more():
    failing = filter_violations(_AXE_RESULTS, "serious")
    assert {v["id"] for v in failing} == {"color-contrast", "image-alt"}


def test_filter_violations_ignores_null_impact():
    failing = filter_violations(_AXE_RESULTS, "minor")
    assert "landmark-unique" not in {v["id"] for v in failing}


# ---------------------------------------------------------------------------
# Evaluate + safe summary
# ---------------------------------------------------------------------------


def test_evaluate_axe_results_pass_when_below_threshold():
    clean = {"violations": [{"id": "x", "impact": "minor", "help": "h", "nodes": []}]}
    passed, message, violations = evaluate_axe_results(clean, "critical")
    assert passed is True
    assert violations == []
    assert "no a11y violations" in message


def test_evaluate_axe_results_fail_lists_rules():
    passed, message, violations = evaluate_axe_results(_AXE_RESULTS, "critical")
    assert passed is False
    assert len(violations) == 1
    assert violations[0]["id"] == "image-alt"
    assert "image-alt" in message


def test_safe_violation_summary_shape():
    summary = safe_violation_summary(filter_violations(_AXE_RESULTS, "serious"))
    cc = next(v for v in summary if v["id"] == "color-contrast")
    assert cc["impact"] == "serious"
    assert cc["node_count"] == 2
    assert cc["sample_targets"] == ["#a", "#b"]
    assert cc["help_url"].startswith("https://")


# ---------------------------------------------------------------------------
# Adapter injection wiring (fake page — no real browser)
# ---------------------------------------------------------------------------


class _FakePage:
    def __init__(self, results):
        self._results = results
        self.script_tag_calls = []
        self.evaluated = []

    async def add_script_tag(self, *, content=None, url=None):
        self.script_tag_calls.append({"content": content is not None, "url": url})

    async def evaluate(self, expr):
        self.evaluated.append(expr)
        return self._results


@pytest.mark.asyncio
async def test_run_axe_injects_inline_script():
    from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter

    page = _FakePage(_AXE_RESULTS)
    adapter = PlaywrightAdapter(page)
    out = await adapter.run_axe(axe_script="window.axe={run:()=>{}}")
    assert out == _AXE_RESULTS
    assert page.script_tag_calls == [{"content": True, "url": None}]
    assert "axe.run" in page.evaluated[0]


@pytest.mark.asyncio
async def test_run_axe_uses_url_when_given():
    from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter

    page = _FakePage(_AXE_RESULTS)
    adapter = PlaywrightAdapter(page)
    await adapter.run_axe(axe_url="https://example.com/axe.min.js")
    assert page.script_tag_calls == [{"content": False, "url": "https://example.com/axe.min.js"}]


@pytest.mark.asyncio
async def test_run_axe_requires_a_source():
    from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter

    adapter = PlaywrightAdapter(_FakePage(_AXE_RESULTS))
    with pytest.raises(ValueError):
        await adapter.run_axe()


# ---------------------------------------------------------------------------
# End-to-end through sdk.verify / session (fake adapter exposing run_axe)
# ---------------------------------------------------------------------------


class _FakeA11yAdapter:
    def __init__(self, results):
        self._results = results
        self.run_axe_kwargs = None

    async def run_axe(self, *, axe_script=None, axe_url=None):
        self.run_axe_kwargs = {"has_script": axe_script is not None, "axe_url": axe_url}
        if isinstance(self._results, Exception):
            raise self._results
        return self._results


@pytest.mark.asyncio
async def test_verify_a11y_fails_on_critical_violation(monkeypatch):
    adapter = _FakeA11yAdapter(_AXE_RESULTS)
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)
    s = BubblegumSession.web(object())

    result = await s.verify("page has no critical a11y violations", assertion_type="a11y")

    assert result.status == "failed"
    assert result.error.error_type == "A11yViolationError"
    assert result.target.metadata["a11y_violation_count"] == 1
    assert result.target.metadata["a11y_impact_threshold"] == "critical"
    # default injection uses the vendored inline script, not a URL
    assert adapter.run_axe_kwargs == {"has_script": True, "axe_url": None}


@pytest.mark.asyncio
async def test_verify_a11y_passes_when_clean(monkeypatch):
    adapter = _FakeA11yAdapter({"violations": [{"id": "x", "impact": "moderate", "help": "h", "nodes": []}]})
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)
    s = BubblegumSession.web(object())

    result = await s.verify("page has no critical a11y violations", assertion_type="a11y")
    assert result.status == "passed"
    assert result.target.metadata["a11y_violation_count"] == 0


@pytest.mark.asyncio
async def test_verify_a11y_threshold_override_via_expected_value(monkeypatch):
    adapter = _FakeA11yAdapter(_AXE_RESULTS)
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)
    s = BubblegumSession.web(object())

    result = await s.verify("a11y check", assertion_type="a11y", expected_value="serious")
    # serious threshold catches both serious + critical
    assert result.status == "failed"
    assert result.target.metadata["a11y_violation_count"] == 2


@pytest.mark.asyncio
async def test_verify_a11y_is_web_only(monkeypatch):
    adapter = _FakeA11yAdapter(_AXE_RESULTS)
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)
    s = BubblegumSession.mobile(object())

    result = await s.verify("page has no critical a11y violations", assertion_type="a11y")
    assert result.status == "failed"
    assert result.error.error_type == "UnsupportedChannelError"


@pytest.mark.asyncio
async def test_verify_a11y_surfaces_axe_run_error(monkeypatch):
    adapter = _FakeA11yAdapter(RuntimeError("boom"))
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)
    s = BubblegumSession.web(object())

    result = await s.verify("page has no critical a11y violations", assertion_type="a11y")
    assert result.status == "failed"
    assert result.error.error_type == "A11yCheckError"
    assert "boom" in result.error.message
