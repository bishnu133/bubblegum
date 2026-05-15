from __future__ import annotations

import asyncio
import json

import pytest

from bubblegum.adapters.web.playwright.sync_adapter import SyncPlaywrightAdapter
from bubblegum.core.grounding.engine import GroundingEngine
from bubblegum.core.grounding.registry import ResolverRegistry
from bubblegum.core.schemas import ActionPlan, ContextRequest, ExecutionOptions, StepIntent, StepResult, ValidationPlan
from bubblegum.reporting.html_report import write_html_report
from bubblegum.reporting.json_report import write_json_report
from tests.real_env.conftest import require_target_env


@pytest.mark.real_env
@pytest.mark.web_smoke
@pytest.mark.playwright
def test_web_local_smoke_sign_in_flow() -> None:
    require_target_env("web")

    playwright_sync = pytest.importorskip("playwright.sync_api")

    try:
        with playwright_sync.sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            try:
                page.set_content(
                    """
                    <main>
                      <h1>Welcome</h1>
                      <label for=\"email\">Email</label>
                      <input id=\"email\" type=\"email\" />
                      <button id=\"signin\">Sign In</button>
                      <p id=\"status\" aria-live=\"polite\"></p>
                    </main>
                    <script>
                      const status = document.getElementById('status');
                      document.getElementById('signin').addEventListener('click', () => {
                        status.textContent = 'Signed in locally';
                      });
                    </script>
                    """
                )

                adapter = SyncPlaywrightAdapter(page)
                ui_context = adapter.collect_context(ContextRequest(include_screenshot=False))
                assert ui_context.a11y_snapshot

                engine = GroundingEngine(registry=ResolverRegistry())
                intent = StepIntent(
                    instruction="Click Sign In",
                    channel="web",
                    platform="web",
                    action_type="click",
                    options=ExecutionOptions(),
                    context={"a11y_snapshot": ui_context.a11y_snapshot},
                )

                target, _traces = asyncio.run(engine.ground(intent))
                execution = adapter.execute(ActionPlan(action_type="click"), target)
                assert execution.success is True

                validation = adapter.validate(
                    ValidationPlan(assertion_type="text_visible", expected_value="Signed in locally", timeout_ms=2000)
                )
                assert validation.passed is True
            finally:
                browser.close()
    except Exception as exc:  # pragma: no cover - runtime-dependent skip path
        message = str(exc).lower()
        if "executable" in message or "browser" in message or "install" in message:
            pytest.skip(f"Playwright browser runtime is unavailable: {exc}")
        raise


@pytest.mark.real_env
@pytest.mark.web_smoke
@pytest.mark.playwright
def test_web_local_smoke_reporting_artifacts_are_safe(tmp_path) -> None:
    require_target_env("web")

    playwright_sync = pytest.importorskip("playwright.sync_api")

    try:
        with playwright_sync.sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            try:
                page.set_content(
                    """
                    <main>
                      <h1>Welcome</h1>
                      <label for=\"email\">Email</label>
                      <input id=\"email\" type=\"email\" value=\"redact.me@example.com\" />
                      <button id=\"signin\">Sign In</button>
                      <p id=\"status\" aria-live=\"polite\"></p>
                    </main>
                    <script>
                      const status = document.getElementById('status');
                      document.getElementById('signin').addEventListener('click', () => {
                        status.textContent = 'Signed in locally';
                      });
                    </script>
                    """
                )

                adapter = SyncPlaywrightAdapter(page)
                ui_context = adapter.collect_context(ContextRequest(include_screenshot=False))
                assert ui_context.a11y_snapshot

                engine = GroundingEngine(registry=ResolverRegistry())
                target, _traces = asyncio.run(
                    engine.ground(
                        StepIntent(
                            instruction="Click Sign In",
                            channel="web",
                            platform="web",
                            action_type="click",
                            options=ExecutionOptions(),
                            context={"a11y_snapshot": ui_context.a11y_snapshot},
                        )
                    )
                )

                execution = adapter.execute(ActionPlan(action_type="click"), target)
                assert execution.success is True

                validation = adapter.validate(
                    ValidationPlan(assertion_type="text_visible", expected_value="Signed in locally", timeout_ms=2000)
                )
                assert validation.passed is True

                assert target.metadata is not None
                target.metadata.update(
                    {
                        "provider_payload": "secret-provider-payload",
                        "raw_dom": page.content(),
                        "screenshot_bytes": "raw-image-bytes",
                        "raw_context_name": "WEBVIEW_com.example.secret",
                        "password": "super-secret-password",
                        "username": "user@example.com",
                    }
                )

                result = StepResult(
                    status="passed",
                    action="Click Sign In",
                    target=target,
                    confidence=target.confidence,
                    duration_ms=1,
                )

                json_path = tmp_path / "web_smoke_report.json"
                html_path = tmp_path / "web_smoke_report.html"
                write_json_report([result], path=json_path, title="Web Smoke Reporting")
                write_html_report([result], path=html_path, title="Web Smoke Reporting")

                assert json_path.exists()
                assert html_path.exists()

                payload = json.loads(json_path.read_text(encoding="utf-8"))
                assert payload["title"] == "Web Smoke Reporting"
                assert payload["analytics"]["total"] == 1

                html_text = html_path.read_text(encoding="utf-8")
                assert "Web Smoke Reporting" in html_text
                assert "Passed" in html_text

                serialized = json.dumps(payload)
                forbidden_markers = (
                    "secret-provider-payload",
                    "raw-image-bytes",
                    "WEBVIEW_com.example.secret",
                    "super-secret-password",
                    "user@example.com",
                    "redact.me@example.com",
                    "<main>",
                    "<input",
                )
                for marker in forbidden_markers:
                    assert marker not in serialized
                    assert marker not in html_text
            finally:
                browser.close()
    except Exception as exc:  # pragma: no cover - runtime-dependent skip path
        message = str(exc).lower()
        if "executable" in message or "browser" in message or "install" in message:
            pytest.skip(f"Playwright browser runtime is unavailable: {exc}")
        raise
