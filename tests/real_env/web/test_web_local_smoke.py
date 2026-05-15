from __future__ import annotations

import pytest

from bubblegum.adapters.web.playwright.sync_adapter import SyncPlaywrightAdapter
from bubblegum.core.grounding.engine import GroundingEngine
from bubblegum.core.grounding.registry import ResolverRegistry
from bubblegum.core.schemas import ActionPlan, ContextRequest, ExecutionOptions, StepIntent, ValidationPlan
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
                import asyncio

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
