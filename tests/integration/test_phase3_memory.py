"""
tests/integration/test_phase3_memory.py
=========================================
Phase 3 integration test — Memory self-healing with a real Playwright page.

Run with:
    pytest tests/integration/test_phase3_memory.py --memory -v

Skipped by default (requires Playwright browser binary).
Pass --memory flag to opt in.

What this test proves
---------------------
test_run1_accessibility_tree_wins:
  - DB is empty → MemoryCacheResolver misses
  - AccessibilityTreeResolver or ExactTextResolver wins
  - record_success() writes the entry to a shared SQLite DB

test_run2_memory_cache_wins:
  - Same DB, same page state → MemoryCacheResolver (priority 10) wins first
  - LLMGroundingResolver is never called
  - StepResult.traces shows memory_cache as the winning resolver

Design: no module-scoped async fixtures (incompatible with pytest-asyncio 1.3.0).
Each test opens its own browser. State is shared between the two tests via a
module-level dict (_shared) that holds the DB path — a tempfile created once at
module import time so both tests point at the same SQLite file.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Shared state — one SQLite file across both tests in this module
# ---------------------------------------------------------------------------

_tmp    = tempfile.mkdtemp()
_shared: dict = {
    "db_path": Path(_tmp) / "phase3_memory.db",
}

# ---------------------------------------------------------------------------
# Inline HTML page used by both tests
# ---------------------------------------------------------------------------

_LOGIN_HTML = """
<!DOCTYPE html>
<html>
<body>
  <form>
    <label for="user">Username</label>
    <input id="user" type="text" placeholder="Username" />
    <label for="pass">Password</label>
    <input id="pass" type="password" placeholder="Password" />
    <button id="login-btn" type="button">Login</button>
  </form>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Helper — build a mini SDK (no LLM) backed by the shared DB
# ---------------------------------------------------------------------------

def _make_stack(db_path: Path):
    """
    Return (act_fn, memory_resolver).

    act_fn(instruction, page) -> StepResult
    Resolvers registered: MemoryCacheResolver -> AccessibilityTreeResolver -> ExactTextResolver
    No LLM resolver — Tier 3 is never reached so tests run without an API key.
    """
    from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter
    from bubblegum.core.grounding.engine import GroundingEngine
    from bubblegum.core.grounding.errors import BubblegumError
    from bubblegum.core.grounding.registry import ResolverRegistry
    from bubblegum.core.grounding.resolvers.accessibility_tree import AccessibilityTreeResolver
    from bubblegum.core.grounding.resolvers.exact_text import ExactTextResolver
    from bubblegum.core.grounding.resolvers.memory_cache import MemoryCacheResolver
    from bubblegum.core.schemas import (
        ActionPlan, ContextRequest, ErrorInfo, ExecutionOptions, StepIntent, StepResult,
    )

    memory_resolver = MemoryCacheResolver(db_path=db_path)
    registry = ResolverRegistry()
    registry.register(memory_resolver)
    registry.register(AccessibilityTreeResolver())
    registry.register(ExactTextResolver())
    engine = GroundingEngine(registry=registry)

    async def act_fn(instruction: str, page) -> StepResult:
        adapter = PlaywrightAdapter(page)
        options = ExecutionOptions()
        intent  = StepIntent(
            instruction=instruction,
            channel="web",
            action_type="click",
            options=options,
        )

        ui_ctx = await adapter.collect_context(ContextRequest(include_screenshot=False))
        if ui_ctx.a11y_snapshot:
            intent.context["a11y_snapshot"] = ui_ctx.a11y_snapshot
        if ui_ctx.screen_signature:
            intent.context["screen_signature"] = ui_ctx.screen_signature

        t0 = time.monotonic()
        try:
            target, traces = await engine.ground(intent)
        except BubblegumError as exc:
            return StepResult(
                status="failed",
                action=instruction,
                confidence=0.0,
                duration_ms=int((time.monotonic() - t0) * 1000),
                error=ErrorInfo(error_type=type(exc).__name__, message=str(exc)),
            )

        plan        = ActionPlan(action_type="click", target_hint=instruction, options=options)
        exec_res    = await adapter.execute(plan, target)
        duration_ms = int((time.monotonic() - t0) * 1000)

        if exec_res.success:
            memory_resolver.record_success(intent, target)

        return StepResult(
            status="passed" if exec_res.success else "failed",
            action=instruction,
            target=target,
            confidence=target.confidence,
            duration_ms=duration_ms,
            traces=traces,
        )

    return act_fn, memory_resolver


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.memory
@pytest.mark.asyncio
async def test_run1_accessibility_tree_wins(request):
    """
    Run 1: DB is empty — MemoryCacheResolver misses.
    AccessibilityTreeResolver or ExactTextResolver wins.
    Winning resolution is persisted to the shared SQLite DB.
    """
    if not request.config.getoption("--memory", default=False):
        pytest.skip("Pass --memory to run Playwright memory integration tests")

    from playwright.async_api import async_playwright
    from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter
    from bubblegum.core.grounding.resolvers.memory_cache import _step_hash
    from bubblegum.core.schemas import ContextRequest, ExecutionOptions, StepIntent

    db_path = _shared["db_path"]
    act_fn, memory_resolver = _make_stack(db_path)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page    = await browser.new_page()
        await page.set_content(_LOGIN_HTML)

        result = await act_fn("Click Login", page)

        assert result.status == "passed", f"Run 1 failed: {result.error}"
        assert result.target is not None
        assert result.confidence > 0
        assert result.target.resolver_name != "memory_cache", (
            "memory_cache won on Run 1 — DB should have been empty"
        )

        # Verify entry was written to SQLite
        adapter = PlaywrightAdapter(page)
        ui_ctx  = await adapter.collect_context(ContextRequest(include_screenshot=False))
        intent  = StepIntent(
            instruction="Click Login",
            channel="web",
            action_type="click",
            options=ExecutionOptions(),
            context={"screen_signature": ui_ctx.screen_signature},
        )
        entry = memory_resolver._layer.lookup(
            ui_ctx.screen_signature, _step_hash(intent), ttl_days=7, max_failures=3
        )
        assert entry is not None, "record_success() did not persist to SQLite after Run 1"

        await browser.close()

    memory_resolver.close()


@pytest.mark.memory
@pytest.mark.asyncio
async def test_run2_memory_cache_wins(request):
    """
    Run 2: Same DB, same page state.
    MemoryCacheResolver (priority 10) must win before any other resolver runs.
    LLMGroundingResolver must never be called.
    """
    if not request.config.getoption("--memory", default=False):
        pytest.skip("Pass --memory to run Playwright memory integration tests")

    from playwright.async_api import async_playwright

    db_path = _shared["db_path"]
    act_fn, memory_resolver = _make_stack(db_path)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page    = await browser.new_page()
        await page.set_content(_LOGIN_HTML)

        # Guard: seed the DB only if test_run1 hasn't already done it.
        # We check directly rather than calling act_fn again, because calling
        # act_fn when a cache entry already exists would produce two candidates
        # (memory_cache + another resolver) triggering AmbiguousTargetError.
        from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter
        from bubblegum.core.grounding.resolvers.memory_cache import _step_hash
        from bubblegum.core.schemas import ContextRequest, ExecutionOptions, StepIntent

        adapter  = PlaywrightAdapter(page)
        ui_ctx   = await adapter.collect_context(ContextRequest(include_screenshot=False))
        chk_intent = StepIntent(
            instruction="Click Login", channel="web", action_type="click",
            options=ExecutionOptions(),
            context={"screen_signature": ui_ctx.screen_signature},
        )
        existing = memory_resolver._layer.lookup(
            ui_ctx.screen_signature, _step_hash(chk_intent), ttl_days=7, max_failures=3
        )
        if existing is None:
            seed = await act_fn("Click Login", page)
            assert seed.status == "passed", f"Isolation seed failed: {seed.error}"

        # Run 2 — MemoryCacheResolver must now win at Tier 1 (priority 10),
        # stopping before any other resolver produces a candidate.
        result = await act_fn("Click Login", page)

        assert result.status == "passed", f"Run 2 failed: {result.error}"
        assert result.target is not None
        assert result.target.resolver_name == "memory_cache", (
            f"Expected memory_cache to win on Run 2, got: {result.target.resolver_name}"
        )

        # memory_cache trace must appear with exactly 1 candidate
        mem_traces = [t for t in result.traces if t.resolver_name == "memory_cache"]
        assert mem_traces, "No memory_cache trace in Run 2 StepResult"
        assert len(mem_traces[0].candidates) == 1

        # Tier 3 (LLM) must never have been reached
        llm_traces = [t for t in result.traces if t.resolver_name == "llm_grounding"]
        assert not llm_traces, (
            "LLMGroundingResolver was called — cache hit should have stopped at Tier 1"
        )

        await browser.close()

    memory_resolver.close()