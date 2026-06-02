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

extract() resolves the target element and reads text via channel-specific extraction paths.
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

import inspect
import logging
import time
from datetime import datetime, timezone
from typing import Any

from bubblegum.core.config import BubblegumConfig
from bubblegum.core.grounding.engine import GroundingEngine
from bubblegum.core.grounding.errors import BubblegumError
from bubblegum.core.grounding.hydrator import VisualRefHydrator, is_visual_ref
from bubblegum.core.grounding.registry import ResolverRegistry
from bubblegum.core.grounding.resolvers.memory_cache import MemoryCacheResolver
from bubblegum.core.parser import decompose, extract_expected, infer_action_type, llm_decompose
from bubblegum.core.planner import build_options, build_validation_plan, context_request, make_intent
from bubblegum.core.recovery import remove_explicit_selector, used_explicit_selector
from bubblegum.core.mobile.memory_signature import build_mobile_memory_signature
from bubblegum.core.schemas import (
    ActionPlan,
    ArtifactRef,
    ErrorInfo,
    ResolvedTarget,
    StepIntent,
    StepResult,
)
from bubblegum.core.validation import make_verification_result, verification_error, verification_status
from bubblegum.core.vision.engine import VisionProvider, build_vision_candidates_from_screenshot

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
_vision_provider: VisionProvider | None = None
_visual_ref_hydrator = VisualRefHydrator()


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


def _set_vision_provider_for_testing(provider: VisionProvider | None) -> None:
    """Internal test hook for wiring an optional runtime vision provider."""
    global _vision_provider
    _vision_provider = provider


def _validate_vision_provider(provider: VisionProvider) -> None:
    detect_targets = getattr(provider, "detect_targets", None)
    if not callable(detect_targets):
        raise TypeError("Vision provider must define callable detect_targets(image_bytes, instruction, context=None).")

    signature = inspect.signature(detect_targets)
    params = list(signature.parameters.values())
    positional = [
        p
        for p in params
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    has_varargs = any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in params)

    if len(positional) < 2 and not has_varargs:
        raise ValueError("Vision provider detect_targets must accept image_bytes and instruction parameters.")


def configure_vision_provider(provider: VisionProvider) -> None:
    """Register a runtime vision provider used by optional screenshot-to-vision wiring."""
    _validate_vision_provider(provider)
    global _vision_provider
    _vision_provider = provider


def clear_vision_provider() -> None:
    """Clear the registered runtime vision provider. Safe to call repeatedly."""
    global _vision_provider
    _vision_provider = None


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
    options = build_options(kwargs, ai_enabled=_config.ai_enabled, max_cost_level=_config.grounding.max_cost_level, memory_ttl_days=_config.grounding.memory_ttl_days, memory_max_failures=_config.grounding.memory_max_failures)
    action_type, target_phrase, input_value = await _decompose_for(instruction, kwargs)
    intent  = make_intent(
        instruction=instruction,
        channel=channel,
        platform=kwargs.get("platform", "web" if channel == "web" else "android"),
        action_type=action_type,
        selector=kwargs.get("selector"),
        target_phrase=target_phrase,
        input_value=input_value,
        options=options,
    )

    # 2. Collect context
    ctx_request = context_request()
    ctx_request.include_screenshot = _should_request_vision_screenshot(intent)
    ui_ctx = await adapter.collect_context(ctx_request)
    _merge_context(intent, ui_ctx)
    _maybe_inject_vision_candidates(intent)

    # 3. Ground
    try:
        target, traces = await _engine.ground(intent)
    except BubblegumError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return _failed_result(instruction, exc, duration_ms)

    target, hydration_error, _hydration_meta = _maybe_hydrate_visual_target(intent=intent, target=target)
    if hydration_error is not None:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return StepResult(
            status="failed",
            action=instruction,
            target=None,
            confidence=0.0,
            duration_ms=duration_ms,
            traces=traces,
            error=hydration_error,
        )

    # 4. Dry-run short-circuit — resolve only, do not execute
    if options.dry_run:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return StepResult(
            status="dry_run",
            action=instruction,
            target=target,
            confidence=target.confidence,
            duration_ms=duration_ms,
            traces=traces,
        )

    # 5. Build ActionPlan and execute
    plan = ActionPlan(
        action_type=intent.action_type,
        target_hint=intent.target_phrase or instruction,
        input_value=intent.input_value,
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

    options = build_options(kwargs, ai_enabled=_config.ai_enabled, max_cost_level=_config.grounding.max_cost_level, memory_ttl_days=_config.grounding.memory_ttl_days, memory_max_failures=_config.grounding.memory_max_failures)
    _, target_phrase, _ = await _decompose_for(instruction, kwargs, force_action="verify")
    intent  = make_intent(
        instruction=instruction,
        channel=channel,
        platform=kwargs.get("platform", "web" if channel == "web" else "android"),
        action_type="verify",
        selector=kwargs.get("selector"),
        target_phrase=target_phrase,
        options=options,
    )

    ctx_request = context_request()
    ctx_request.include_screenshot = _should_request_vision_screenshot(intent)
    ui_ctx = await adapter.collect_context(ctx_request)
    _merge_context(intent, ui_ctx)
    _maybe_inject_vision_candidates(intent)

    try:
        target, traces = await _engine.ground(intent)
    except BubblegumError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return _failed_result(instruction, exc, duration_ms)

    assertion_type  = kwargs.get("assertion_type", "text_visible")
    expected_value  = kwargs.get("expected_value") or extract_expected(instruction)
    timeout_ms      = kwargs.get("timeout_ms", options.timeout_ms)

    v_plan = build_validation_plan(assertion_type=assertion_type, expected_value=expected_value, timeout_ms=timeout_ms)
    v_result = await adapter.validate(v_plan)
    duration_ms = int((time.monotonic() - t0) * 1000)

    status = verification_status(v_result)
    error = verification_error(expected_value, v_result)
    return make_verification_result(status=status, instruction=instruction, target=target, traces=traces, duration_ms=duration_ms, result=v_result, error=error)


async def extract(
    instruction: str,
    channel: str = "web",
    page=None,
    driver=None,
    **kwargs: Any,
) -> StepResult:
    """
    Extract text content from a matched element.

    Grounds the target element using the same resolver chain as act().

    Web channel reads text via Playwright locator inner_text() path.
    Mobile channel delegates to the adapter extraction path (e.g., AppiumAdapter.extract_text()).

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

    options = build_options(kwargs, ai_enabled=_config.ai_enabled, max_cost_level=_config.grounding.max_cost_level, memory_ttl_days=_config.grounding.memory_ttl_days, memory_max_failures=_config.grounding.memory_max_failures)
    _, target_phrase, _ = await _decompose_for(instruction, kwargs, force_action="extract")
    intent  = make_intent(
        instruction=instruction,
        channel=channel,
        platform=kwargs.get("platform", "web" if channel == "web" else "android"),
        action_type="extract",
        selector=kwargs.get("selector"),
        target_phrase=target_phrase,
        options=options,
    )

    # Collect context (no screenshot needed for extract)
    ctx_request = context_request()
    ctx_request.include_screenshot = _should_request_vision_screenshot(intent)
    ui_ctx = await adapter.collect_context(ctx_request)
    _merge_context(intent, ui_ctx)
    _maybe_inject_vision_candidates(intent)

    # Ground — find the target element
    try:
        target, traces = await _engine.ground(intent)
    except BubblegumError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return _failed_result(instruction, exc, duration_ms)

    target, hydration_error, _hydration_meta = _maybe_hydrate_visual_target(intent=intent, target=target)
    if hydration_error is not None:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return StepResult(
            status="failed",
            action=instruction,
            target=None,
            confidence=0.0,
            duration_ms=duration_ms,
            traces=traces,
            error=hydration_error,
        )

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

    options = build_options(kwargs, ai_enabled=_config.ai_enabled, max_cost_level=_config.grounding.max_cost_level, memory_ttl_days=_config.grounding.memory_ttl_days, memory_max_failures=_config.grounding.memory_max_failures)
    action_type, target_phrase, input_value = await _decompose_for(instruction, kwargs)
    step_intent = make_intent(
        instruction=instruction,
        channel=channel,
        platform=kwargs.get("platform", "web" if channel == "web" else "android"),
        action_type=action_type,
        selector=failed_selector,
        target_phrase=target_phrase,
        input_value=input_value,
        options=options,
    )

    ctx_request = context_request()
    ctx_request.include_screenshot = _should_request_vision_screenshot(step_intent)
    ui_ctx = await adapter.collect_context(ctx_request)
    _merge_context(step_intent, ui_ctx)
    _maybe_inject_vision_candidates(step_intent)

    # Ground — ExplicitSelectorResolver will win first if selector still works
    try:
        target, traces = await _engine.ground(step_intent)
    except BubblegumError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return _failed_result(instruction, exc, duration_ms)

    # Execute
    plan = ActionPlan(
        action_type=step_intent.action_type,
        target_hint=step_intent.target_phrase or instruction,
        input_value=step_intent.input_value,
        options=options,
    )

    exec_result = await adapter.execute(plan, target)

    # If the explicit selector worked on first try → "passed" (not "recovered")
    # If we had to fall through to another resolver → "recovered"
    used_explicit = used_explicit_selector(resolver_name=target.resolver_name, failed_selector=failed_selector, ref=target.ref)

    duration_ms = int((time.monotonic() - t0) * 1000)

    if not exec_result.success:
        # Explicit selector executed but failed (element stale) — try fallback resolvers
        remove_explicit_selector(step_intent.context)
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


def _build_options(kwargs: dict):
    return build_options(
        kwargs,
        ai_enabled=_config.ai_enabled,
        max_cost_level=_config.grounding.max_cost_level,
        memory_ttl_days=_config.grounding.memory_ttl_days,
        memory_max_failures=_config.grounding.memory_max_failures,
    )


def _infer_action_type(instruction: str, kwargs: dict) -> str:
    return infer_action_type(instruction, kwargs)


def _llm_parse_allowed() -> bool:
    """Whether the LLM parse fallback may run (fallback-first + cost gate)."""
    if not _config.ai_enabled:
        return False
    return str(_config.grounding.max_cost_level).lower() != "low"


def _get_parse_provider():
    """Return a configured ModelProvider, or None if AI parsing is unavailable."""
    try:
        from bubblegum.core.models.factory import get_provider
        return get_provider(_config)
    except Exception as exc:  # noqa: BLE001 - parsing must degrade gracefully
        logger.warning("LLM parse provider unavailable; using deterministic parse: %s", exc)
        return None


async def _decompose_for(
    instruction: str,
    kwargs: dict,
    *,
    force_action: str | None = None,
) -> tuple[str, str | None, str | None]:
    """Decompose an instruction into (action_type, target_phrase, input_value).

    Deterministic grammar first. If that is not confident and AI parsing is
    enabled (and the cost policy allows it), escalate to the LLM parser. Caller
    kwargs always win — backward-compatible with explicit selector/value usage.
    """
    parsed = decompose(instruction, kwargs)

    action_type = force_action or kwargs.get("action_type") or parsed.action_type
    target_phrase = kwargs.get("target_phrase") or parsed.target_phrase
    explicit_value = kwargs.get("input_value", kwargs.get("value"))
    input_value = explicit_value if explicit_value is not None else parsed.input_value

    if not parsed.confident and _llm_parse_allowed():
        llm = await llm_decompose(instruction, _get_parse_provider())
        if llm is not None:
            if force_action is None and not kwargs.get("action_type") and llm.action_type:
                action_type = llm.action_type
            if target_phrase is None:
                target_phrase = llm.target_phrase
            if input_value is None:
                input_value = llm.input_value

    return action_type, target_phrase, input_value


def _extract_expected(instruction: str) -> str:
    return extract_expected(instruction)

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
    if ui_ctx.app_state:
        intent.context["app_state"] = dict(ui_ctx.app_state)

    if intent.channel == "mobile":
        intent.context["mobile_memory_signature"] = build_mobile_memory_signature(
            ui_context=ui_ctx,
            target_metadata=None,
        )

    # Runtime config flags exposed in context for resolver eligibility checks.
    intent.context.setdefault("config_ocr_enabled", _config.ocr_enabled)
    intent.context.setdefault("config_vision_enabled", _config.vision_enabled)


def _should_request_vision_screenshot(intent: StepIntent) -> bool:
    if "vision_candidates" in intent.context:
        return False
    if not _allows_provider_vision_cost(intent):
        return False
    return bool(
        _config.grounding.enable_vision
        and _config.privacy.send_screenshots
        and _config.privacy.process_screenshots_for_vision
        and _vision_provider is not None
    )


def _allows_provider_vision_cost(intent: StepIntent) -> bool:
    return str(intent.options.max_cost_level).lower() == "high"


def _maybe_build_vision_candidates(intent: StepIntent) -> list:
    if "vision_candidates" in intent.context:
        return []
    if not _allows_provider_vision_cost(intent):
        return []
    screenshot = intent.context.get("screenshot")
    if not isinstance(screenshot, (bytes, bytearray)):
        return []
    return build_vision_candidates_from_screenshot(
        bytes(screenshot),
        instruction=intent.instruction,
        provider=_vision_provider,
        enabled=bool(_config.grounding.enable_vision),
        privacy_gate=bool(
            _config.privacy.send_screenshots
            and _config.privacy.process_screenshots_for_vision
        ),
        context={"channel": intent.channel, "platform": intent.platform},
    )


def _maybe_inject_vision_candidates(intent: StepIntent) -> None:
    candidates = _maybe_build_vision_candidates(intent)
    if candidates:
        intent.context["vision_candidates"] = candidates


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


def _hydration_surface_metadata(*, intent: StepIntent, hydration) -> dict[str, Any]:
    diagnostics = dict(getattr(hydration, "diagnostics", {}) or {})
    blocked = {
        "hierarchy_xml",
        "a11y_snapshot",
        "screenshot",
        "screenshot_bytes",
        "image_bytes",
        "base64",
        "raw_payload",
        "provider_request",
        "provider_response",
        "api_key",
        "secret",
        "secrets",
        "candidates",
        "candidate_dump",
    }
    diagnostics = {k: v for k, v in diagnostics.items() if k not in blocked}
    out: dict[str, Any] = {
        "hydration_status": hydration.status,
        "hydration_reason": hydration.reason,
        "hydration_original_ref": hydration.original_ref,
        "hydration_hydrated_ref": hydration.hydrated_ref,
        "hydration_channel": intent.channel,
    }
    if isinstance(diagnostics.get("strategy"), str):
        out["hydration_strategy"] = diagnostics["strategy"]
    if isinstance(diagnostics.get("source"), str):
        out["hydration_source"] = diagnostics["source"]
    if isinstance(diagnostics.get("match_field"), str):
        out["match_field"] = diagnostics["match_field"]
    if hydration.reason in {"mobile_visual_hydration_ambiguous_match", "mobile_visual_hydration_no_match"}:
        if isinstance(diagnostics.get("match_count"), int):
            out["match_count"] = diagnostics["match_count"]
    return out


def _maybe_hydrate_visual_target(*, intent: StepIntent, target: ResolvedTarget) -> tuple[ResolvedTarget, ErrorInfo | None, dict[str, Any] | None]:
    if not is_visual_ref(target.ref):
        return target, None, None

    hydration = _visual_ref_hydrator.hydrate(target=target, intent=intent)
    hydration_meta = _hydration_surface_metadata(intent=intent, hydration=hydration)
    if hydration.status == "hydrated" and hydration.target is not None:
        enriched_target = hydration.target.model_copy(update={"metadata": {**hydration.target.metadata, **hydration_meta}})
        return enriched_target, None, hydration_meta

    return target, ErrorInfo(
        error_type="VisualRefHydrationError",
        message=(
            f"Visual ref hydration failed ({hydration.reason}) for ref {hydration.original_ref!r}. "
            "Synthetic visual refs are non-executable until deterministically hydrated. "
            f"hydration={hydration_meta}"
        ),
        resolver_name=target.resolver_name,
    ), hydration_meta
