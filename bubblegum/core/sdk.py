"""
bubblegum/core/sdk.py
=====================
Public SDK entry points: act(), verify(), extract(), recover().

These are the four primitives test authors call. Each one:
  1. Builds a StepIntent from the instruction + context
  2. Calls PlaywrightAdapter.collect_context() to get UIContext
  3. Merges UIContext into intent.context
  4. Calls GroundingEngine.ground() to resolve the target
  5. Calls the adapter to execute or validate
  6. Returns a StepResult

recover() is a special case:
  - Injects failed_selector into intent.context["explicit_selector"]
  - ExplicitSelectorResolver wins at 1.0 if the selector still works
  - If ExplicitSelectorResolver returns nothing (stale selector), the engine
    falls through to AccessibilityTreeResolver / ExactTextResolver
  - status = "recovered" when the original selector was stale but Bubblegum found it

extract() resolves the target element and reads its inner_text.
  - Returns StepResult with extracted value in target.metadata["extracted_value"]
  - action_type = "extract"

Screenshots (Phase 1B):
  - act() and recover() capture a screenshot after successful execution
  - Screenshot is appended to StepResult.artifacts as ArtifactRef(type="screenshot")
  - Screenshots are NOT captured on hard failures (no adapter available)

Phase 1A — act(), verify(), recover() implemented.
Phase 1B — extract() added; screenshot artifacts added to act() and recover().
Phase 3 — record_success() / record_failure() wired into act() and recover()
           so successful resolutions are persisted to SQLite for self-healing replay.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from bubblegum.core.config import BubblegumConfig
from bubblegum.core.grounding.engine import GroundingEngine
from bubblegum.core.grounding.errors import BubblegumError
from bubblegum.core.grounding.registry import ResolverRegistry
from bubblegum.core.grounding.resolvers.memory_cache import MemoryCacheResolver
from bubblegum.core.schemas import (
    ActionPlan,
    ArtifactRef,
    ContextRequest,
    ErrorInfo,
    ExecutionOptions,
    ResolvedTarget,
    StepIntent,
    StepResult,
    ValidationPlan,
    ValidationResult,
)

logger = logging.getLogger(__name__)

# Module-level runtime wiring — shared across SDK calls
_config: BubblegumConfig = BubblegumConfig.load()
_registry = ResolverRegistry()
_engine = GroundingEngine(
    registry=_registry,
    accept_threshold=_config.grounding.accept_threshold,
    review_threshold=_config.grounding.review_threshold,
    ambiguous_gap=_config.grounding.ambiguous_gap,
    reject_threshold=_config.grounding.reject_threshold,
)
_memory_cache = MemoryCacheResolver()  # Phase 3: single shared instance for record_*


def configure_runtime(config: BubblegumConfig | None = None, config_path: str | None = None) -> BubblegumConfig:
    """Configure SDK runtime from BubblegumConfig and rewire thresholds.

    Args:
        config: Pre-built BubblegumConfig instance.
        config_path: Optional YAML path loaded via BubblegumConfig.load().

    Returns:
        The active runtime BubblegumConfig.
    """
    global _config, _engine

    _config = config or BubblegumConfig.load(config_path)
    _engine = GroundingEngine(
        registry=_registry,
        accept_threshold=_config.grounding.accept_threshold,
        review_threshold=_config.grounding.review_threshold,
        ambiguous_gap=_config.grounding.ambiguous_gap,
        reject_threshold=_config.grounding.reject_threshold,
    )
    return _config


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def act(
    instruction: str,
    channel: str = "web",
    page=None,
    driver=None,
    **kwargs: Any,
) -> StepResult:
    """
    Execute a natural-language action step.

    Args:
        instruction: NL step, e.g. "Click Login"
        channel:     "web" (Phase 1A) | "mobile" (Phase 4)
        page:        Playwright Page object (required for web channel)
        **kwargs:    Forwarded to ExecutionOptions (timeout_ms, retry_count, etc.)

    Returns:
        StepResult with status "passed" on success, "failed" on error.
        On success, StepResult.artifacts includes a screenshot ArtifactRef.
    """
    t0 = time.monotonic()
    adapter = _get_adapter(channel, page=page, driver=driver)

    # 1. Build StepIntent
    options = _build_options(kwargs)
    intent  = StepIntent(
        instruction=instruction,
        channel=channel,
        platform=kwargs.get("platform", "web" if channel == "web" else "android"),
        action_type=_infer_action_type(instruction, kwargs),
        context={"explicit_selector": kwargs["selector"]} if kwargs.get("selector") else {},
        options=options,
    )

    # 2. Collect context
    ctx_request = ContextRequest(include_screenshot=False)
    ui_ctx = await adapter.collect_context(ctx_request)
    _merge_context(intent, ui_ctx)

    # 3. Ground
    try:
        target, traces = await _engine.ground(intent)
    except BubblegumError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return _failed_result(instruction, exc, duration_ms)

    # 4. Build ActionPlan and execute
    plan = ActionPlan(
        action_type=intent.action_type,
        target_hint=instruction,
        input_value=kwargs.get("input_value"),
        options=options,
    )
    exec_result = await adapter.execute(plan, target)
    duration_ms = int((time.monotonic() - t0) * 1000)

    if not exec_result.success:
        return StepResult(
            status="failed",
            action=instruction,
            target=target,
            confidence=target.confidence,
            duration_ms=duration_ms,
            traces=traces,
            error=ErrorInfo(
                error_type="ExecutionFailedError",
                message=exec_result.error or "Execution failed",
                resolver_name=target.resolver_name,
            ),
        )

    # Phase 3 — persist the winning resolution for self-healing replay
    _memory_cache.record_success(intent, target)

    # 5. Capture screenshot artifact after successful execution
    artifacts: list[ArtifactRef] = []
    try:
        artifact_ref = await adapter.screenshot()
        artifacts.append(artifact_ref)
    except Exception as exc:
        logger.warning("Screenshot capture failed after act(): %s", exc)

    return StepResult(
        status="passed",
        action=instruction,
        target=target,
        confidence=target.confidence,
        duration_ms=duration_ms,
        traces=traces,
        artifacts=artifacts,
    )


async def verify(
    instruction: str,
    channel: str = "web",
    page=None,
    driver=None,
    **kwargs: Any,
) -> StepResult:
    """
    Assert an expected state in natural language.

    Args:
        instruction: NL assertion, e.g. "Login button visible"
        channel:     "web" | "mobile"
        page:        Playwright Page object
        **kwargs:    assertion_type, expected_value, timeout_ms

    Returns:
        StepResult with status "passed" when assertion holds, "failed" otherwise.
    """
    t0 = time.monotonic()
    adapter = _get_adapter(channel, page=page, driver=driver)

    options = _build_options(kwargs)
    intent  = StepIntent(
        instruction=instruction,
        channel=channel,
        platform=kwargs.get("platform", "web" if channel == "web" else "android"),
        action_type="verify",
        context={"explicit_selector": kwargs["selector"]} if kwargs.get("selector") else {},
        options=options,
    )

    ctx_request = ContextRequest(include_screenshot=False)
    ui_ctx = await adapter.collect_context(ctx_request)
    _merge_context(intent, ui_ctx)

    try:
        target, traces = await _engine.ground(intent)
    except BubblegumError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return _failed_result(instruction, exc, duration_ms)

    assertion_type  = kwargs.get("assertion_type", "text_visible")
    expected_value  = kwargs.get("expected_value") or _extract_expected(instruction)
    timeout_ms      = kwargs.get("timeout_ms", options.timeout_ms)

    v_plan = ValidationPlan(
        assertion_type=assertion_type,
        expected_value=expected_value,
        timeout_ms=timeout_ms,
    )
    v_result = await adapter.validate(v_plan)
    duration_ms = int((time.monotonic() - t0) * 1000)

    status = "passed" if v_result.passed else "failed"
    return StepResult(
        status=status,
        action=instruction,
        target=target,
        confidence=target.confidence,
        validation=v_result,
        duration_ms=duration_ms,
        traces=traces,
        error=None if v_result.passed else ErrorInfo(
            error_type="ValidationFailedError",
            message=f"Validation failed: expected={expected_value!r}, actual={v_result.actual_value!r}",
        ),
    )


async def extract(
    instruction: str,
    channel: str = "web",
    page=None,
    driver=None,
    **kwargs: Any,
) -> StepResult:
    """
    Extract text content from a matched element.

    Grounds the target element using the same resolver chain as act(), then
    reads its inner text via page.locator(ref).inner_text().

    The extracted value is returned in StepResult.target.metadata["extracted_value"].

    Args:
        instruction: NL description of the element, e.g. "Get user email"
        channel:     "web" | "mobile"
        page:        Playwright Page object (required for web channel)
        **kwargs:    Forwarded to ExecutionOptions

    Returns:
        StepResult with status "passed" on success.
        target.metadata["extracted_value"] contains the extracted text string.
        Returns "failed" if the element cannot be resolved or text cannot be read.
    """
    t0 = time.monotonic()
    adapter = _get_adapter(channel, page=page, driver=driver)

    options = _build_options(kwargs)
    intent  = StepIntent(
        instruction=instruction,
        channel=channel,
        platform=kwargs.get("platform", "web" if channel == "web" else "android"),
        action_type="extract",
        context={"explicit_selector": kwargs["selector"]} if kwargs.get("selector") else {},
        options=options,
    )

    # Collect context (no screenshot needed for extract)
    ctx_request = ContextRequest(include_screenshot=False)
    ui_ctx = await adapter.collect_context(ctx_request)
    _merge_context(intent, ui_ctx)

    # Ground — find the target element
    try:
        target, traces = await _engine.ground(intent)
    except BubblegumError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return _failed_result(instruction, exc, duration_ms)

    # Extract text content from the resolved element ref
    timeout_ms = options.timeout_ms
    try:
        if channel == "mobile":
            if not hasattr(adapter, "extract_text"):
                raise NotImplementedError(
                    "Mobile extract is not supported by the active adapter."
                )
            extracted_value = await adapter.extract_text(target.ref, timeout_ms=timeout_ms)
        else:
            extracted_value = await _extract_inner_text(page, target.ref, timeout_ms)
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.error("inner_text() failed for ref=%r: %s", target.ref, exc)
        return StepResult(
            status="failed",
            action=instruction,
            target=target,
            confidence=target.confidence,
            duration_ms=duration_ms,
            traces=traces,
            error=ErrorInfo(
                error_type="ExecutionFailedError",
                message=f"Failed to extract text from {target.ref!r}: {exc}",
                resolver_name=target.resolver_name,
            ),
        )

    duration_ms = int((time.monotonic() - t0) * 1000)

    # Attach extracted value to target metadata (mutating a copy to avoid schema issues)
    enriched_metadata = dict(target.metadata)
    enriched_metadata["extracted_value"] = extracted_value
    enriched_target = target.model_copy(update={"metadata": enriched_metadata})

    logger.debug("extract(): ref=%r  value=%r", target.ref, extracted_value)

    return StepResult(
        status="passed",
        action=instruction,
        target=enriched_target,
        confidence=enriched_target.confidence,
        duration_ms=duration_ms,
        traces=traces,
    )


async def recover(
    page=None,
    failed_selector: str | None = None,
    intent: str | None = None,
    channel: str = "web",
    driver=None,
    **kwargs: Any,
) -> StepResult:
    """
    Fallback recovery for an existing Playwright test step whose selector is stale.

    Args:
        page:             Playwright Page object
        failed_selector:  The original selector that is now stale/broken
        intent:           NL description of the intended action, e.g. "Click Login"
        channel:          "web" (Phase 1A) | "mobile" (Phase 4)
        **kwargs:         Forwarded to ExecutionOptions

    Returns:
        StepResult with status "recovered" when Bubblegum found the element via
        a fallback resolver, or "failed" if all resolvers exhausted.
        On success or recovery, StepResult.artifacts includes a screenshot ArtifactRef.

    Behaviour:
        - failed_selector is injected into intent.context["explicit_selector"]
        - ExplicitSelectorResolver tries it first (confidence 1.0) — passes if selector still works
        - If the selector is truly stale, ExplicitSelectorResolver returns [] (because
          the PlaywrightAdapter will fail on execute); downstream resolvers take over
        - status = "recovered" whenever the original selector failed but Bubblegum succeeded
    """
    instruction = intent or failed_selector or "recover"
    t0 = time.monotonic()
    adapter = _get_adapter(channel, page=page, driver=driver)

    options = _build_options(kwargs)
    step_intent = StepIntent(
        instruction=instruction,
        channel=channel,
        platform=kwargs.get("platform", "web" if channel == "web" else "android"),
        action_type=_infer_action_type(instruction, kwargs),
        options=options,
        context={"explicit_selector": failed_selector} if failed_selector else {},
    )

    ctx_request = ContextRequest(include_screenshot=False)
    ui_ctx = await adapter.collect_context(ctx_request)
    _merge_context(step_intent, ui_ctx)

    # Ground — ExplicitSelectorResolver will win first if selector still works
    try:
        target, traces = await _engine.ground(step_intent)
    except BubblegumError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return _failed_result(instruction, exc, duration_ms)

    # Execute
    plan = ActionPlan(
        action_type=step_intent.action_type,
        target_hint=instruction,
        input_value=kwargs.get("input_value"),
        options=options,
    )

    exec_result = await adapter.execute(plan, target)

    # If the explicit selector worked on first try → "passed" (not "recovered")
    # If we had to fall through to another resolver → "recovered"
    used_explicit = (
        target.resolver_name == "explicit_selector"
        and failed_selector is not None
        and target.ref == failed_selector
    )

    duration_ms = int((time.monotonic() - t0) * 1000)

    if not exec_result.success:
        # Explicit selector executed but failed (element stale) — try fallback resolvers
        step_intent.context.pop("explicit_selector", None)
        try:
            target, traces = await _engine.ground(step_intent)
        except BubblegumError as exc:
            return _failed_result(instruction, exc, duration_ms)

        exec_result = await adapter.execute(plan, target)
        duration_ms = int((time.monotonic() - t0) * 1000)

        if not exec_result.success:
            return StepResult(
                status="failed",
                action=instruction,
                target=target,
                confidence=target.confidence,
                duration_ms=duration_ms,
                traces=traces,
                error=ErrorInfo(
                    error_type="ExecutionFailedError",
                    message=exec_result.error or "Recovery execution failed",
                    resolver_name=target.resolver_name,
                ),
            )

        # Fell back to another resolver → "recovered"
        # Phase 3 — persist the fallback resolution so next run replays from cache
        _memory_cache.record_success(step_intent, target)
        artifacts = await _capture_screenshot(adapter, instruction)
        return StepResult(
            status="recovered",
            action=instruction,
            target=target,
            confidence=target.confidence,
            duration_ms=duration_ms,
            traces=traces,
            artifacts=artifacts,
        )

    # Explicit selector succeeded without needing fallback
    # Phase 3 — persist so next run can replay from cache
    _memory_cache.record_success(step_intent, target)
    status = "passed" if used_explicit else "recovered"
    artifacts = await _capture_screenshot(adapter, instruction)
    return StepResult(
        status=status,
        action=instruction,
        target=target,
        confidence=target.confidence,
        duration_ms=duration_ms,
        traces=traces,
        artifacts=artifacts,
    )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _get_adapter(channel: str, page=None, driver=None):
    """Return the appropriate adapter for the channel.

    Web:    requires page= (Playwright Page object)
    Mobile: requires driver= (Appium WebDriver instance)
    """
    if channel == "web":
        from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter
        if page is None:
            raise ValueError("page= is required for channel='web'")
        return PlaywrightAdapter(page)

    if channel == "mobile":
        from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
        if driver is None:
            raise ValueError("driver= is required for channel='mobile'")
        return AppiumAdapter(driver)

    raise NotImplementedError(
        f"Channel '{channel}' not supported. Use 'web' or 'mobile'."
    )


def _build_options(kwargs: dict) -> ExecutionOptions:
    known = {
        "timeout_ms",
        "retry_count",
        "wait_for",
        "use_ai",
        "max_cost_level",
        "memory_ttl_days",
        "memory_max_failures",
    }
    opts = {k: v for k, v in kwargs.items() if k in known}
    opts.setdefault("use_ai", _config.ai_enabled)
    opts.setdefault("max_cost_level", _config.grounding.max_cost_level)
    opts.setdefault("memory_ttl_days", _config.grounding.memory_ttl_days)
    opts.setdefault("memory_max_failures", _config.grounding.memory_max_failures)
    return ExecutionOptions(**opts)


def _infer_action_type(instruction: str, kwargs: dict) -> str:
    """Infer action_type from kwargs or instruction text."""
    if "action_type" in kwargs:
        return kwargs["action_type"]
    lowered = instruction.lower()
    if any(w in lowered for w in ("type", "enter", "fill", "input")):
        return "type"
    if any(w in lowered for w in ("select", "choose", "pick")):
        return "select"
    if any(w in lowered for w in ("scroll",)):
        return "scroll"
    if any(w in lowered for w in ("verify", "check", "assert", "visible", "present")):
        return "verify"
    if any(w in lowered for w in ("extract", "get", "read", "fetch")):
        return "extract"
    return "click"  # default


def _extract_expected(instruction: str) -> str:
    """Pull the key noun phrase from a verify instruction as the expected value."""
    import re
    cleaned = re.sub(
        r"^(verify|check|assert|confirm|ensure|see|that)\s+",
        "",
        instruction,
        flags=re.IGNORECASE,
    ).strip()
    return cleaned


def _merge_context(intent: StepIntent, ui_ctx) -> None:
    """Merge UIContext fields into intent.context so resolvers can read them."""
    if ui_ctx.a11y_snapshot:
        intent.context["a11y_snapshot"] = ui_ctx.a11y_snapshot
    if ui_ctx.hierarchy_xml:
        intent.context["hierarchy_xml"] = ui_ctx.hierarchy_xml
    if ui_ctx.screenshot:
        intent.context["screenshot"] = ui_ctx.screenshot
    if ui_ctx.screen_signature:
        intent.context["screen_signature"] = ui_ctx.screen_signature

    # Runtime config flags exposed in context for resolver eligibility checks.
    intent.context.setdefault("config_ocr_enabled", _config.ocr_enabled)
    intent.context.setdefault("config_vision_enabled", _config.vision_enabled)


def _failed_result(instruction: str, exc: BubblegumError, duration_ms: int) -> StepResult:
    """Build a failed StepResult from a BubblegumError."""
    return StepResult(
        status="failed",
        action=instruction,
        confidence=0.0,
        duration_ms=duration_ms,
        error=ErrorInfo(
            error_type=type(exc).__name__,
            message=str(exc),
            resolver_name=exc.resolver_name,
            candidates=exc.candidates,
        ),
    )


async def _extract_inner_text(page, ref: str, timeout_ms: int) -> str:
    """
    Read the inner text of the element identified by ref.

    Uses _resolve_locator() logic inline (mirrors PlaywrightAdapter._resolve_locator)
    so we can call inner_text() without a full ActionPlan/execute cycle.
    """
    import re as _re

    _NAME_RE = _re.compile(r'\[name="([^"]+)"\]')

    if ref.startswith("role="):
        role_part  = ref[len("role="):]
        name_match = _NAME_RE.search(role_part)
        role       = _NAME_RE.sub("", role_part).strip()
        if name_match:
            locator = page.get_by_role(role, name=name_match.group(1))
        else:
            locator = page.get_by_role(role)
    elif ref.startswith('text="') and ref.endswith('"'):
        locator = page.get_by_text(ref[6:-1], exact=True)
    elif ref.startswith("text="):
        locator = page.get_by_text(ref[5:], exact=True)
    else:
        locator = page.locator(ref)

    return await locator.inner_text(timeout=timeout_ms)


async def _capture_screenshot(adapter, label: str) -> list[ArtifactRef]:
    """Capture a post-execution screenshot. Returns list with ArtifactRef, or [] on failure."""
    try:
        artifact_ref = await adapter.screenshot()
        return [artifact_ref]
    except Exception as exc:
        logger.warning("Screenshot capture failed after %r: %s", label, exc)
        return []
