"""Phase 22E-3: state probes + auto-screenshot on failure.

Covers:
  - is_checked / selected_value / is_visible route NL targets through the
    SDK with action_type=verify, dry_run=True, then convert ref to a
    Playwright locator via the adapter and read state.
  - Probes raise BubblegumProbeError when the resolver returns no target.
  - Probes are web-only.
  - Auto-screenshot fires on failed act/verify/extract steps when a label
    is set, and the path follows <artifacts>/<label>-stepN.png.
  - No screenshot when label is unset, when the result passed, or for
    non-web channels.
  - capture_failure_screenshot writes a -final.png and is a no-op without
    a label / page.
  - _sanitize_label rejects path-unsafe characters.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from bubblegum.core import sdk
from bubblegum.core.schemas import (
    ArtifactRef,
    ErrorInfo,
    ExecutionResult,
    ResolvedTarget,
    StepResult,
    UIContext,
    ValidationResult,
)
from bubblegum.session import (
    BubblegumProbeError,
    BubblegumSession,
    _sanitize_label,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

_A11Y = "\n".join([
    '- checkbox "Newsletter"',
    '- combobox "Country"',
    '- heading "Dashboard"',
])


class _FakeLocator:
    def __init__(self, *, checked: bool = False, value: str = "", visible: bool = True):
        self._checked = checked
        self._value = value
        self._visible = visible

    @property
    def first(self) -> "_FakeLocator":
        return self

    async def is_checked(self) -> bool:
        return self._checked

    async def input_value(self) -> str:
        return self._value

    async def is_visible(self) -> bool:
        return self._visible


class _FakePage:
    def __init__(self, locators: dict[str, _FakeLocator] | None = None):
        self._locators = locators or {}
        self.screenshots: list[str] = []

    def get_by_role(self, role: str, name: str | None = None) -> _FakeLocator:
        key = f"role={role}" + (f'[name="{name}"]' if name else "")
        return self._locators.get(key, _FakeLocator(visible=False))

    def get_by_text(self, text: str, exact: bool = True) -> _FakeLocator:
        return self._locators.get(f'text="{text}"', _FakeLocator(visible=False))

    def locator(self, selector: str) -> _FakeLocator:
        return self._locators.get(selector, _FakeLocator(visible=False))

    async def screenshot(self, *, path: str | None = None, **_: Any) -> bytes:
        # Mirror the Playwright contract: writing happens if path= is passed.
        if path is not None:
            Path(path).write_bytes(b"\x89PNG\r\n\x1a\nfake")
            self.screenshots.append(path)
        return b"\x89PNG\r\n\x1a\nfake"


class _FakeAdapter:
    def __init__(self, page: _FakePage):
        self._page = page

    async def collect_context(self, _req):
        return UIContext(a11y_snapshot=_A11Y, screen_signature="sig")

    async def execute(self, plan, target):
        return ExecutionResult(success=True, duration_ms=1)

    async def validate(self, _plan):
        return ValidationResult(passed=True)

    async def screenshot(self):
        return ArtifactRef(type="screenshot", path="/tmp/x.png", timestamp="2026-01-01T00:00:00+00:00")

    def _resolve_locator(self, ref: str):
        # Mirror PlaywrightAdapter._resolve_locator just enough for tests.
        if ref.startswith("role="):
            import re
            name_match = re.search(r'\[name="([^"]+)"\]', ref)
            role = re.sub(r'\[name="[^"]+"\]', "", ref[len("role="):]).strip()
            if name_match:
                return self._page.get_by_role(role, name=name_match.group(1))
            return self._page.get_by_role(role)
        if ref.startswith('text="') and ref.endswith('"'):
            return self._page.get_by_text(ref[6:-1], exact=True)
        return self._page.locator(ref)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def patched_adapter(monkeypatch):
    """Pin a single _FakeAdapter instance for the duration of the test."""
    holder: dict[str, _FakeAdapter] = {}

    def _factory(channel: str, page=None, driver=None):
        if "adapter" not in holder:
            holder["adapter"] = _FakeAdapter(page)
        return holder["adapter"]

    monkeypatch.setattr(sdk, "_get_adapter", _factory)
    return holder


# ---------------------------------------------------------------------------
# Label sanitization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("tests/integration/test_foo.py::test_bar", "tests_integration_test_foo.py_test_bar"),
        ("simple_name", "simple_name"),
        ("with spaces and / slashes", "with_spaces_and_slashes"),
        ("___", "bubblegum"),
        ("", "bubblegum"),
    ],
)
def test_sanitize_label_strips_unsafe_chars(raw, expected):
    assert _sanitize_label(raw) == expected


# ---------------------------------------------------------------------------
# Probes — resolution path
# ---------------------------------------------------------------------------


def test_is_checked_uses_resolver_then_reads_locator(patched_adapter, monkeypatch):
    page = _FakePage({
        'role=checkbox[name="Newsletter"]': _FakeLocator(checked=True),
    })
    session = BubblegumSession.web(page)

    # Force grounding to return a known ref so the probe path is deterministic.
    async def fake_act(instruction, **kwargs):
        assert kwargs.get("dry_run") is True
        assert kwargs.get("action_type") == "verify"
        return StepResult(
            status="dry_run",
            action=instruction,
            target=ResolvedTarget(
                ref='role=checkbox[name="Newsletter"]',
                confidence=0.9,
                resolver_name="fake",
            ),
            confidence=0.9,
            duration_ms=0,
        )

    monkeypatch.setattr(sdk, "act", fake_act)

    assert _run(session.is_checked("Newsletter")) is True


def test_selected_value_reads_input_value(patched_adapter, monkeypatch):
    page = _FakePage({
        'role=combobox[name="Country"]': _FakeLocator(value="IN"),
    })
    session = BubblegumSession.web(page)

    async def fake_act(instruction, **kwargs):
        return StepResult(
            status="dry_run",
            action=instruction,
            target=ResolvedTarget(
                ref='role=combobox[name="Country"]',
                confidence=0.9,
                resolver_name="fake",
            ),
            confidence=0.9,
            duration_ms=0,
        )

    monkeypatch.setattr(sdk, "act", fake_act)

    assert _run(session.selected_value("Country")) == "IN"


def test_is_visible_reads_visibility(patched_adapter, monkeypatch):
    page = _FakePage({
        'role=heading[name="Dashboard"]': _FakeLocator(visible=True),
    })
    session = BubblegumSession.web(page)

    async def fake_act(instruction, **kwargs):
        return StepResult(
            status="dry_run",
            action=instruction,
            target=ResolvedTarget(
                ref='role=heading[name="Dashboard"]',
                confidence=0.9,
                resolver_name="fake",
            ),
            confidence=0.9,
            duration_ms=0,
        )

    monkeypatch.setattr(sdk, "act", fake_act)

    assert _run(session.is_visible("Dashboard")) is True


def test_probe_raises_when_target_unresolved(patched_adapter, monkeypatch):
    page = _FakePage({})
    session = BubblegumSession.web(page)

    async def fake_act(instruction, **kwargs):
        return StepResult(
            status="failed",
            action=instruction,
            target=None,
            confidence=0.0,
            duration_ms=0,
            error=ErrorInfo(error_type="x", message="no candidates"),
        )

    monkeypatch.setattr(sdk, "act", fake_act)

    with pytest.raises(BubblegumProbeError, match="no candidates"):
        _run(session.is_checked("Phantom"))


def test_probes_are_web_only():
    session = BubblegumSession.mobile(driver=object())
    with pytest.raises(NotImplementedError, match="web-only"):
        _run(session.is_checked("Newsletter"))


# ---------------------------------------------------------------------------
# Auto-screenshot on failed step
# ---------------------------------------------------------------------------


def test_auto_screenshot_writes_on_failed_act(monkeypatch, tmp_path):
    page = _FakePage()
    session = BubblegumSession.web(page)
    session.label = "tests::test_foo"
    session.artifacts_dir = tmp_path

    async def fake_act(instruction, **kwargs):
        return StepResult(
            status="failed",
            action=instruction,
            target=None,
            confidence=0.0,
            duration_ms=0,
            error=ErrorInfo(error_type="x", message="boom"),
        )

    monkeypatch.setattr(sdk, "act", fake_act)

    _run(session.act("Click Phantom"))

    expected = tmp_path / "tests_test_foo-step1.png"
    assert expected.exists(), f"expected {expected} to be written; got {list(tmp_path.iterdir())}"
    assert page.screenshots == [str(expected)]
    assert session.failure_screenshots == [expected]


def test_auto_screenshot_indexes_steps_across_calls(monkeypatch, tmp_path):
    page = _FakePage()
    session = BubblegumSession.web(page)
    session.label = "foo"
    session.artifacts_dir = tmp_path

    async def fake_passed(instruction, **kwargs):
        return StepResult(
            status="passed", action=instruction, target=None,
            confidence=0.0, duration_ms=0,
        )

    async def fake_failed(instruction, **kwargs):
        return StepResult(
            status="failed", action=instruction, target=None,
            confidence=0.0, duration_ms=0,
            error=ErrorInfo(error_type="x", message="bad"),
        )

    # First step passes (no screenshot), second fails (step2 written).
    monkeypatch.setattr(sdk, "act", fake_passed)
    _run(session.act("Click A"))
    assert page.screenshots == []

    monkeypatch.setattr(sdk, "act", fake_failed)
    _run(session.act("Click B"))
    assert page.screenshots == [str(tmp_path / "foo-step2.png")]


def test_auto_screenshot_skipped_when_no_label(monkeypatch, tmp_path):
    page = _FakePage()
    session = BubblegumSession.web(page)
    session.artifacts_dir = tmp_path

    async def fake_act(instruction, **kwargs):
        return StepResult(
            status="failed", action=instruction, target=None,
            confidence=0.0, duration_ms=0,
            error=ErrorInfo(error_type="x", message="boom"),
        )

    monkeypatch.setattr(sdk, "act", fake_act)
    _run(session.act("Click X"))
    assert page.screenshots == []
    assert session.failure_screenshots == []


def test_auto_screenshot_skipped_on_passed_step(monkeypatch, tmp_path):
    page = _FakePage()
    session = BubblegumSession.web(page)
    session.label = "foo"
    session.artifacts_dir = tmp_path

    async def fake_act(instruction, **kwargs):
        return StepResult(
            status="passed", action=instruction, target=None,
            confidence=0.0, duration_ms=0,
        )

    monkeypatch.setattr(sdk, "act", fake_act)
    _run(session.act("Click ok"))
    assert page.screenshots == []


# ---------------------------------------------------------------------------
# capture_failure_screenshot (test-level fixture finalizer path)
# ---------------------------------------------------------------------------


def test_capture_failure_screenshot_writes_final_png(tmp_path):
    page = _FakePage()
    session = BubblegumSession.web(page)
    session.label = "tests::test_demo"
    session.artifacts_dir = tmp_path

    path = _run(session.capture_failure_screenshot(suffix="final"))

    assert path is not None
    assert path.exists()
    assert path.name == "tests_test_demo-final.png"


def test_capture_failure_screenshot_noop_without_label(tmp_path):
    page = _FakePage()
    session = BubblegumSession.web(page)
    session.artifacts_dir = tmp_path

    path = _run(session.capture_failure_screenshot())
    assert path is None
    assert page.screenshots == []


def test_capture_failure_screenshot_noop_on_mobile():
    session = BubblegumSession.mobile(driver=object())
    session.label = "x"
    assert _run(session.capture_failure_screenshot()) is None
