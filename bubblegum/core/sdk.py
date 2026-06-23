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

import asyncio
import difflib
import inspect
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from bubblegum.core.config import BubblegumConfig
from bubblegum.core.grounding.engine import GroundingEngine
from bubblegum.core.grounding.errors import (
    BubblegumError,
    LowConfidenceError,
    ResolutionFailedError,
)
from bubblegum.core.grounding.hydrator import VisualRefHydrator, is_visual_ref
from bubblegum.core.grounding.registry import ResolverRegistry
from bubblegum.core.grounding.resolvers.memory_cache import MemoryCacheResolver
from bubblegum.core.parser import decompose, extract_expected, infer_action_type, llm_decompose, substitute_dynamic_tokens
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
    ValidationResult,
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
    ai_first=_config.grounding.ai_first,
)
_memory_cache = MemoryCacheResolver()  # Phase 3: single shared instance for record_*
_vision_provider: VisionProvider | None = None
_visual_ref_hydrator = VisualRefHydrator()

# X2: apply the per-run Tier-3 cost budget from config to the global tracker.
from bubblegum.core import cost as _cost  # noqa: E402
_cost.configure_budget(_config.grounding.max_run_cost_usd)


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
        ai_first=_config.grounding.ai_first,
    )
    # X2: refresh the per-run Tier-3 cost budget from the (re)loaded config.
    _cost.configure_budget(_config.grounding.max_run_cost_usd)
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
# Self-healing advisory
# ---------------------------------------------------------------------------

# A fuzzy/synonym match whose label is this similar to the requested phrase is
# treated as a benign typo/case correction (e.g. "Logut" -> "Logout"). Below it,
# the substitution is semantic (e.g. "login" -> "Sign In") and is flagged for
# review as a possible defect.
_HEALING_REVIEW_SIMILARITY = 0.85


def _build_healing_advisory(intent: StepIntent, target: ResolvedTarget) -> dict | None:
    """
    Detect when self-healing substituted a different element label than the
    tester wrote, and build a report advisory.

    Returns None when the step matched cleanly (exact / substring), so clean
    steps keep status "passed". Only fuzzy/synonym matches are considered heals.
    """
    if target is None or target.resolver_name != "fuzzy_text":
        return None

    requested = (intent.target_phrase or intent.instruction or "").strip()
    matched = str(
        target.metadata.get("element_name")
        or target.metadata.get("matched_text")
        or ""
    ).strip()
    if not requested or not matched:
        return None

    req_n = requested.lower()
    matched_n = matched.lower()
    # Exact or substring containment is not drift worth flagging.
    if req_n == matched_n or req_n in matched_n or matched_n in req_n:
        return None

    fuzzy_ratio = float(target.metadata.get("fuzzy_ratio") or 0.0)
    direct = difflib.SequenceMatcher(None, req_n, matched_n).ratio()

    # A synonym substitution (the resolver's synonym table mapped the requested
    # phrase to a different word) is the clearest possible-defect signal — the
    # tester's literal label does not exist on the page at all.
    from bubblegum.core.grounding.resolvers.fuzzy_text import _expand_with_synonyms
    synonyms = {s for s in _expand_with_synonyms(req_n) if s != req_n}
    is_synonym = matched_n in synonyms

    if is_synonym:
        severity, match_kind = "review", "synonym"
    elif direct >= _HEALING_REVIEW_SIMILARITY:
        severity, match_kind = "info", "fuzzy"
    else:
        severity, match_kind = "review", "fuzzy"

    return {
        "applied": True,
        "requested": requested,
        "matched": matched,
        "resolver": target.resolver_name,
        "match_kind": match_kind,
        "similarity": round(fuzzy_ratio, 3),
        "severity": severity,
        # R3 suggested fix: the old→new diff a tester can apply to de-brittle
        # the step. old_ref is what the step says today; new_ref is the label
        # that actually matched; new_selector is the resolved technical ref.
        "old_ref": requested,
        "new_ref": matched,
        "new_selector": target.ref,
        "suggested_fix": f"Update the step label: {requested!r} → {matched!r}",
        "message": (
            f"Self-healing applied: your step referenced '{requested}', but the "
            f"closest element on the page was '{matched}'. If this substitution is "
            f"unexpected, it may be a real defect — please revisit your test step."
        ),
    }


def _resolve_healing_advisory(intent: StepIntent, target: ResolvedTarget) -> dict | None:
    """Return the healing advisory for this step, whether freshly healed or
    replayed from the memory cache.

    A live fuzzy/synonym win is detected by ``_build_healing_advisory``. On a
    subsequent run the same step resolves from the memory cache (resolver_name
    ``memory_cache``), so the live detector no longer fires — but the original
    advisory was persisted into the cached metadata, so we re-surface it and
    tag it as a replay.
    """
    advisory = _build_healing_advisory(intent, target)
    if advisory is not None:
        return advisory

    if target is not None and target.resolver_name == "memory_cache":
        cached = target.metadata.get("healing")
        if isinstance(cached, dict) and cached.get("applied"):
            replayed = dict(cached)
            replayed["replayed_from_cache"] = True
            return replayed
    return None


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

    # M2/M6: mobile system / hardware verbs (press back, rotate, hide keyboard,
    # deep link, background app, biometric, notification) and network-condition
    # verbs (go offline, airplane mode, throttle to 3G) act on the device, not a
    # UI element — route them before grounding. Caller overrides (explicit
    # selector / action_type) keep the normal element path.
    if channel == "mobile" and not kwargs.get("selector") and not kwargs.get("action_type"):
        from bubblegum.core.mobile.network_conditions import parse_network_condition
        from bubblegum.core.mobile.system_actions import parse_system_action

        system_action = parse_system_action(instruction) or parse_network_condition(instruction)
        if system_action is not None:
            return await _act_system(adapter, instruction, system_action, t0)

    # 1. Build StepIntent
    options = build_options(kwargs, ai_enabled=_config.ai_enabled, max_cost_level=_config.grounding.max_cost_level, memory_ttl_days=_config.grounding.memory_ttl_days, memory_max_failures=_config.grounding.memory_max_failures, resolve_retries=_config.grounding.resolve_retries, resolve_retry_interval_ms=_config.grounding.resolve_retry_interval_ms, stability_wait_enabled=_config.grounding.stability_wait_enabled, stability_quiet_ms=_config.grounding.stability_quiet_ms, stability_timeout_ms=_config.grounding.stability_timeout_ms, stability_spinner_selectors=_config.grounding.stability_spinner_selectors)
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
    await _maybe_wait_until_stable(adapter, options)
    ctx_request = context_request()
    ctx_request.include_screenshot = _should_request_vision_screenshot(intent)
    ui_ctx = await adapter.collect_context(ctx_request)
    _merge_context(intent, ui_ctx)
    _maybe_inject_vision_candidates(intent)

    # 3. Ground.
    # Table / link DOM actions first: "click the <col> value in the <row> row"
    # and "click the link <text>" address an element by table coordinates or
    # link text — resolved deterministically from the DOM rather than by name,
    # so they work when the visible text is dynamic (a UUID, a DB value, ...).
    table_target = await _maybe_resolve_table_or_link(adapter, channel, instruction, kwargs)
    if table_target is not None:
        target, traces = table_target, []
    else:
        try:
            target, traces = await _ground_with_wait(adapter, intent)
        except BubblegumError as exc:
            # DOM fallbacks when grounding can't pin a unique element from the
            # a11y snapshot (nameless/ambiguous custom widgets):
            #  - a dropdown/select trigger resolved by label/placeholder/value;
            #  - any interactive element resolved by accessible name + role
            #    (handles a button wrapping a same-text span, where the snapshot
            #    ties two candidates and refuses to auto-execute).
            fallback = await _maybe_resolve_select_trigger(adapter, channel, intent)
            if fallback is None:
                fallback = await _maybe_resolve_clickable(adapter, channel, instruction, intent)
            if fallback is None:
                fallback = await _maybe_resolve_input(adapter, channel, intent)
            if fallback is None:
                duration_ms = int((time.monotonic() - t0) * 1000)
                return _failed_result(instruction, exc, duration_ms)
            target, traces = fallback, []

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
    # M2: optionally hide the soft keyboard before a mobile tap/click so an
    # IME covering the target doesn't cause a flaky miss. Best-effort, opt-in.
    await _maybe_hide_keyboard(adapter, channel, intent.action_type)

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

    # Self-healing advisory: a fuzzy/synonym match means the literal step did
    # not match the page. Surface it so a tester can confirm the substitution
    # is intended and not masking a real defect. Built BEFORE record_success so
    # the advisory is persisted in the cached metadata and survives replays.
    advisory = _resolve_healing_advisory(intent, target)
    status = "passed"
    if advisory is not None:
        target.metadata["healing"] = advisory
        if advisory["severity"] == "review":
            status = "recovered"

    # Phase 3 — persist the winning resolution for self-healing replay. The
    # metadata now carries any healing advisory, so a future memory-cache replay
    # of this step keeps surfacing the substitution warning.
    _memory_cache.record_success(intent, target)

    # 5. Capture screenshot artifact after successful execution
    artifacts: list[ArtifactRef] = []
    try:
        artifact_ref = await adapter.screenshot()
        artifacts.append(artifact_ref)
    except Exception as exc:
        logger.warning("Screenshot capture failed after act(): %s", exc)

    return StepResult(
        status=status,
        action=instruction,
        target=target,
        confidence=target.confidence,
        duration_ms=duration_ms,
        traces=traces,
        artifacts=artifacts,
    )


_QUOTED_RE = re.compile(r'"([^"]+)"|“([^”]+)”|‘([^’]+)’|\'([^\']+)\'')


def _quoted_segments(instruction: str) -> list[str]:
    """Return non-empty quoted substrings (straight, smart, single) in order.

    Lets a verify name the literal text to look for inside a descriptive phrase,
    e.g. 'the page shows an "Update account status" button' -> ["Update account
    status"]. Paired quotes only, so apostrophes in contractions don't match.
    """
    out: list[str] = []
    for m in _QUOTED_RE.finditer(instruction or ""):
        seg = next((g for g in m.groups() if g), "").strip()
        if seg:
            out.append(seg)
    return out


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

    options = build_options(kwargs, ai_enabled=_config.ai_enabled, max_cost_level=_config.grounding.max_cost_level, memory_ttl_days=_config.grounding.memory_ttl_days, memory_max_failures=_config.grounding.memory_max_failures, resolve_retries=_config.grounding.resolve_retries, resolve_retry_interval_ms=_config.grounding.resolve_retry_interval_ms, stability_wait_enabled=_config.grounding.stability_wait_enabled, stability_quiet_ms=_config.grounding.stability_quiet_ms, stability_timeout_ms=_config.grounding.stability_timeout_ms, stability_spinner_selectors=_config.grounding.stability_spinner_selectors)

    # Accessibility assertions are page-scoped — there is no element to ground,
    # so they branch out before resolution and run an axe-core audit instead.
    if kwargs.get("assertion_type") == "a11y":
        return await _verify_a11y(adapter, channel, instruction, kwargs, t0)

    # Network assertions are also page-scoped: assert a backend call happened
    # (method + URL + status) rather than grounding a UI element.
    if kwargs.get("assertion_type") == "network":
        return await _verify_network(adapter, channel, instruction, kwargs, options, t0)

    # Visual-regression assertions are page-scoped too: capture a screenshot and
    # diff it against a stored baseline rather than grounding a UI element.
    if kwargs.get("assertion_type") == "visual":
        return await _verify_visual(adapter, channel, instruction, kwargs, t0)

    # Table assertions are page-scoped: read the table(s) and check columns /
    # cell values rather than grounding a single element. Routed explicitly via
    # assertion_type="table", or inferred when the phrase clearly describes a
    # table/column assertion (so plain-English verifies work too).
    if kwargs.get("assertion_type") == "table" or _looks_like_table_assertion(instruction, kwargs):
        return await _verify_table(adapter, channel, instruction, kwargs, options, t0)

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

    await _maybe_wait_until_stable(adapter, options)
    ctx_request = context_request()
    ctx_request.include_screenshot = _should_request_vision_screenshot(intent)
    ui_ctx = await adapter.collect_context(ctx_request)
    _merge_context(intent, ui_ctx)
    _maybe_inject_vision_candidates(intent)

    try:
        target, traces = await _ground_with_wait(adapter, intent)
    except BubblegumError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return _failed_result(instruction, exc, duration_ms)

    assertion_type  = kwargs.get("assertion_type", "text_visible")
    timeout_ms      = kwargs.get("timeout_ms", options.timeout_ms)
    explicit        = kwargs.get("expected_value")

    # Prefer quoted text as the literal thing to find. Testers naturally quote
    # the element/value they mean, e.g. verify('... an "Update account status"
    # button') or verify('account status is "Active"') — so check the quoted
    # text rather than the whole descriptive sentence (which isn't on the page).
    quoted = _quoted_segments(instruction) if explicit is None else []

    if assertion_type == "text_visible" and len(quoted) >= 2:
        # Several quoted phrases — all must be visible.
        results = []
        for seg in quoted:
            vp = build_validation_plan(assertion_type="text_visible", expected_value=seg, timeout_ms=timeout_ms)
            results.append((seg, await adapter.validate(vp)))
        passed = all(r.passed for _, r in results)
        actual = "; ".join(f"{s!r}={'ok' if r.passed else r.actual_value}" for s, r in results)
        duration_ms = int((time.monotonic() - t0) * 1000)
        v_result = ValidationResult(passed=passed, actual_value=actual, duration_ms=duration_ms)
        error = None if passed else ErrorInfo(error_type="ValidationFailedError", message=f"Validation failed: {actual}")
        return make_verification_result(status=verification_status(v_result), instruction=instruction,
                                        target=target, traces=traces, duration_ms=duration_ms, result=v_result, error=error)

    expected_value = explicit if explicit is not None else (quoted[0] if quoted else extract_expected(instruction))

    v_plan = build_validation_plan(assertion_type=assertion_type, expected_value=expected_value, timeout_ms=timeout_ms)
    v_result = await adapter.validate(v_plan)
    duration_ms = int((time.monotonic() - t0) * 1000)

    status = verification_status(v_result)
    error = verification_error(expected_value, v_result)
    return make_verification_result(status=status, instruction=instruction, target=target, traces=traces, duration_ms=duration_ms, result=v_result, error=error)


def _page_scoped_result(
    *, instruction: str, t0: float, passed: bool, message: str,
    error: ErrorInfo | None, metadata: dict[str, Any] | None = None,
    ref: str = "page", resolver_name: str = "page",
) -> StepResult:
    """Build a StepResult for a page-scoped check (synthetic target, no grounding)."""
    duration_ms = int((time.monotonic() - t0) * 1000)
    target = ResolvedTarget(
        ref=ref, confidence=1.0, resolver_name=resolver_name, metadata=metadata or {}
    )
    v_result = ValidationResult(passed=passed, actual_value=message, duration_ms=duration_ms)
    return make_verification_result(
        status="passed" if passed else "failed",
        instruction=instruction, target=target, traces=[],
        duration_ms=duration_ms, result=v_result, error=error,
    )


def _a11y_result(
    *, instruction: str, t0: float, passed: bool, message: str,
    error: ErrorInfo | None, metadata: dict[str, Any] | None = None,
) -> StepResult:
    """Build a StepResult for a page-scoped a11y check (synthetic 'page' target)."""
    return _page_scoped_result(
        instruction=instruction, t0=t0, passed=passed, message=message,
        error=error, metadata=metadata, ref="page", resolver_name="a11y",
    )


async def _verify_a11y(adapter, channel: str, instruction: str, kwargs: dict, t0: float) -> StepResult:
    """Run an axe-core accessibility audit and turn it into a StepResult.

    Page-scoped: skips element grounding entirely. axe-core is injected by the
    web adapter; result parsing/filtering lives in bubblegum.core.a11y.
    """
    from bubblegum.core import a11y as a11y_mod

    if channel != "web":
        return _a11y_result(
            instruction=instruction, t0=t0, passed=False,
            message="a11y assertions are web-only",
            error=ErrorInfo(error_type="UnsupportedChannelError",
                            message="assertion_type='a11y' is only supported on the web channel"),
        )

    cfg = _config.a11y
    axe_url = kwargs.get("axe_url") or cfg.axe_url
    axe_script_path = kwargs.get("axe_script_path") or cfg.axe_script_path
    threshold = kwargs.get("expected_value") or a11y_mod.impact_from_instruction(instruction, cfg.impact_threshold)

    try:
        if axe_url:
            raw = await adapter.run_axe(axe_url=axe_url)
        else:
            script = a11y_mod.load_axe_script(axe_script_path)
            raw = await adapter.run_axe(axe_script=script)
    except Exception as exc:  # noqa: BLE001 — surface any axe/browser failure as a failed step
        return _a11y_result(
            instruction=instruction, t0=t0, passed=False,
            message=f"axe-core run failed: {exc}",
            error=ErrorInfo(error_type="A11yCheckError", message=str(exc)),
        )

    passed, message, violations = a11y_mod.evaluate_axe_results(raw, threshold)
    metadata = {
        "a11y_violations": violations,
        "a11y_violation_count": len(violations),
        "a11y_impact_threshold": a11y_mod.normalize_impact(threshold),
    }
    error = None if passed else ErrorInfo(error_type="A11yViolationError", message=message)
    return _a11y_result(
        instruction=instruction, t0=t0, passed=passed, message=message,
        error=error, metadata=metadata,
    )


def _looks_like_table_assertion(instruction: str, kwargs: dict) -> bool:
    """True when the phrase clearly describes a table/column assertion.

    Conservative so it never hijacks ordinary text verifies: only fires when the
    caller hasn't asked for a different assertion_type and the rule-based table
    parser recognises the instruction.
    """
    at = kwargs.get("assertion_type")
    if at and at != "table":
        return False
    from bubblegum.core.table import parse_table_spec

    return parse_table_spec(instruction) is not None


async def _verify_table(adapter, channel: str, instruction: str, kwargs: dict, options, t0: float) -> StepResult:
    """Assert columns / cell values in a data table (page-scoped).

    Skips element grounding: reads every table on the page and checks the matcher
    (columns present, and/or a value under a column for a row matched by another
    column). Polls until the assertion holds or the timeout elapses, so it waits
    out async-loaded rows (e.g. results after a search click).
    """
    from bubblegum.core import table as tbl

    if channel != "web":
        return _page_scoped_result(
            instruction=instruction, t0=t0, passed=False,
            message="table assertions are web-only",
            error=ErrorInfo(error_type="UnsupportedChannelError",
                            message="assertion_type='table' is only supported on the web channel"),
            ref="table", resolver_name="table",
        )

    matcher = tbl.build_table_matcher(instruction, kwargs)
    if not matcher:
        return _page_scoped_result(
            instruction=instruction, t0=t0, passed=False,
            message=("could not understand the table assertion; pass columns / "
                     "row_match / cell, or phrase like 'the table has columns A, B' "
                     "or 'in the row where Name is \"X\", Status is \"Active\"'"),
            error=ErrorInfo(error_type="TableAssertionError",
                            message="no columns/row_match/cell and the phrase did not parse"),
            ref="table", resolver_name="table",
        )

    await _maybe_wait_until_stable(adapter, options)

    timeout_ms = kwargs.get("timeout_ms", options.timeout_ms)
    deadline = time.monotonic() + max(0, timeout_ms) / 1000.0
    passed, detail = False, "no tables found on the page"
    tables: list = []
    while True:
        try:
            tables = await adapter.extract_tables()
        except Exception as exc:  # noqa: BLE001 — surface adapter/browser errors as a failed step
            passed, detail = False, f"table extraction error: {exc}"
            break
        passed, detail = tbl.evaluate_table(matcher, tables)
        if passed or time.monotonic() >= deadline:
            break
        await asyncio.sleep(0.3)

    error = None if passed else ErrorInfo(error_type="TableAssertionError", message=detail)
    metadata = {
        "table_assertion": {
            "matcher": tbl.describe_table_matcher(matcher),
            "detail": detail,
            "passed": passed,
            "headers_seen": [t.get("headers", []) for t in tables][:5],
        }
    }
    return _page_scoped_result(
        instruction=instruction, t0=t0, passed=passed, message=detail,
        error=error, metadata=metadata, ref="table", resolver_name="table",
    )


async def _verify_network(adapter, channel: str, instruction: str, kwargs: dict, options, t0: float) -> StepResult:
    """Assert a backend call occurred (method + URL + status), not a UI element.

    Page-scoped: skips grounding. The web adapter records responses from the
    first Bubblegum step onward; matching/parsing lives in bubblegum.core.network.
    """
    from bubblegum.core import network as net

    if channel != "web":
        return _page_scoped_result(
            instruction=instruction, t0=t0, passed=False,
            message="network assertions are web-only",
            error=ErrorInfo(error_type="UnsupportedChannelError",
                            message="assertion_type='network' is only supported on the web channel"),
            ref="network", resolver_name="network",
        )

    expected = kwargs.get("expected_value") or net.extract_network_spec(instruction)
    matcher = net.parse_network_matcher(expected)
    if matcher is None:
        return _page_scoped_result(
            instruction=instruction, t0=t0, passed=False,
            message="network assertion needs expected_value like 'POST /api/login 200'",
            error=ErrorInfo(error_type="NetworkAssertionError",
                            message="provide expected_value, e.g. 'POST /api/login 200'"),
            ref="network", resolver_name="network",
        )

    timeout_ms = kwargs.get("timeout_ms", options.timeout_ms)
    try:
        passed, actual = await adapter.assert_network(matcher, timeout_ms=timeout_ms)
    except Exception as exc:  # noqa: BLE001 — surface adapter/browser errors as a failed step
        passed, actual = False, f"network assertion error: {exc}"

    error = None if passed else ErrorInfo(error_type="NetworkAssertionError", message=actual)
    metadata = {
        "network_assertion": {
            "matcher": net.describe_matcher(matcher),
            "actual": actual,
            "passed": passed,
        }
    }
    return _page_scoped_result(
        instruction=instruction, t0=t0, passed=passed, message=actual,
        error=error, metadata=metadata, ref="network", resolver_name="network",
    )


def _visual_result(
    *, instruction: str, t0: float, passed: bool, message: str,
    error: ErrorInfo | None, metadata: dict[str, Any] | None = None,
    artifacts: list[ArtifactRef] | None = None,
) -> StepResult:
    """Build a StepResult for a page-scoped visual check (synthetic 'visual' target)."""
    duration_ms = int((time.monotonic() - t0) * 1000)
    target = ResolvedTarget(
        ref="visual", confidence=1.0, resolver_name="visual", metadata=metadata or {}
    )
    return StepResult(
        status="passed" if passed else "failed",
        action=instruction,
        target=target,
        confidence=1.0,
        validation=ValidationResult(passed=passed, actual_value=message, duration_ms=duration_ms),
        artifacts=artifacts or [],
        duration_ms=duration_ms,
        error=error,
    )


async def _verify_visual(adapter, channel: str, instruction: str, kwargs: dict, t0: float) -> StepResult:
    """Compare a screenshot against a stored baseline (V1).

    Page-scoped: skips element grounding. First run (or ``--update-baselines``)
    captures the baseline and passes; later runs diff against it and, on
    failure, write a highlighted diff image plus the actual screenshot under the
    baseline directory and attach them to the result.
    """
    from datetime import datetime, timezone
    from pathlib import Path

    from bubblegum.core import visual as vmod
    from bubblegum.core import visual_image as vimg

    if channel != "web":
        return _visual_result(
            instruction=instruction, t0=t0, passed=False,
            message="visual assertions are web-only",
            error=ErrorInfo(error_type="UnsupportedChannelError",
                            message="assertion_type='visual' is only supported on the web channel"),
        )

    if not vimg.pillow_available():
        return _visual_result(
            instruction=instruction, t0=t0, passed=False, message=vimg.PILLOW_HINT,
            error=ErrorInfo(error_type="VisualDependencyError", message=vimg.PILLOW_HINT),
        )

    cfg = _config.visual
    full_page = bool(kwargs.get("full_page", cfg.full_page))
    tolerance = float(kwargs.get("tolerance", cfg.tolerance))
    channel_threshold = int(kwargs.get("channel_threshold", cfg.channel_threshold))
    update = kwargs.get("update_baseline")
    update = cfg.update_baselines if update is None else bool(update)

    name = kwargs.get("name") or vmod.baseline_name(instruction, kwargs.get("expected_value"))
    baseline_dir = Path(kwargs.get("baseline_dir") or cfg.baseline_dir)
    baseline_path = baseline_dir / f"{name}.png"

    try:
        actual_png = await adapter.screenshot_bytes(full_page=full_page)
    except Exception as exc:  # noqa: BLE001 — surface capture failures as a failed step
        return _visual_result(
            instruction=instruction, t0=t0, passed=False,
            message=f"screenshot capture failed: {exc}",
            error=ErrorInfo(error_type="VisualCaptureError", message=str(exc)),
        )

    base_meta = {"name": name, "baseline": str(baseline_path), "tolerance": tolerance}

    # First-run capture or explicit update: (re)write the baseline and pass.
    existed = baseline_path.exists()
    if update or not existed:
        baseline_dir.mkdir(parents=True, exist_ok=True)
        baseline_path.write_bytes(actual_png)
        action = "updated" if existed else "created"
        return _visual_result(
            instruction=instruction, t0=t0, passed=True,
            message=f"baseline {action}: {baseline_path}",
            error=None,
            metadata={"visual": {**base_meta, "baseline_action": action}},
        )

    try:
        base_rgba, bw, bh = vimg.load_png_rgba(baseline_path.read_bytes())
        act_rgba, aw, ah = vimg.load_png_rgba(actual_png)
    except Exception as exc:  # noqa: BLE001
        return _visual_result(
            instruction=instruction, t0=t0, passed=False,
            message=f"could not decode images: {exc}",
            error=ErrorInfo(error_type="VisualDecodeError", message=str(exc)),
            metadata={"visual": base_meta},
        )

    ts = datetime.now(tz=timezone.utc).isoformat()

    if (bw, bh) != (aw, ah):
        actual_path = baseline_dir / f"{name}.actual.png"
        actual_path.write_bytes(actual_png)
        msg = f"size changed: baseline {bw}x{bh} vs actual {aw}x{ah}"
        return _visual_result(
            instruction=instruction, t0=t0, passed=False, message=msg,
            error=ErrorInfo(error_type="VisualRegressionError", message=msg),
            metadata={"visual": {**base_meta, "baseline_size": [bw, bh], "actual_size": [aw, ah]}},
            artifacts=[ArtifactRef(type="screenshot", path=str(actual_path), timestamp=ts)],
        )

    diff_pixels, total, mask = vmod.compare_rgba(
        base_rgba, act_rgba, aw, ah, channel_threshold=channel_threshold
    )
    passed, ratio = vmod.evaluate_diff(diff_pixels, total, tolerance)
    meta = {**base_meta, "diff_pixels": diff_pixels, "total_pixels": total, "diff_ratio": ratio}

    if passed:
        return _visual_result(
            instruction=instruction, t0=t0, passed=True,
            message=f"{ratio:.4%} of pixels differ (tolerance {tolerance:.4%})",
            error=None, metadata={"visual": meta},
        )

    # Regression: write the highlighted diff + the actual screenshot as artifacts.
    diff_rgba = vmod.highlight_diff_rgba(act_rgba, mask, aw, ah)
    diff_path = vimg.save_png(diff_rgba, aw, ah, baseline_dir / f"{name}.diff.png")
    actual_path = baseline_dir / f"{name}.actual.png"
    actual_path.write_bytes(actual_png)
    msg = (
        f"{ratio:.4%} of pixels differ (tolerance {tolerance:.4%}); "
        f"diff image: {diff_path}"
    )
    return _visual_result(
        instruction=instruction, t0=t0, passed=False, message=msg,
        error=ErrorInfo(error_type="VisualRegressionError", message=msg),
        metadata={"visual": {**meta, "diff_image": str(diff_path), "actual_image": str(actual_path)}},
        artifacts=[
            ArtifactRef(type="screenshot", path=str(diff_path), timestamp=ts),
            ArtifactRef(type="screenshot", path=str(actual_path), timestamp=ts),
        ],
    )


async def _act_system(adapter, instruction: str, system_action, t0: float) -> StepResult:
    """Execute a mobile system/hardware action (M2) and build a StepResult.

    Device-level: no grounding. ``system_action`` is a SystemAction (kind +
    arg). Success → status "passed" with a synthetic ``system:<kind>`` target;
    any adapter/driver error → status "failed".
    """
    kind = system_action.kind
    arg = dict(system_action.arg or {})
    try:
        outcome = await adapter.execute_system_action(kind, arg)
    except Exception as exc:  # noqa: BLE001 — surface as a failed step
        duration_ms = int((time.monotonic() - t0) * 1000)
        return StepResult(
            status="failed",
            action=instruction,
            target=ResolvedTarget(ref=f"system:{kind}", confidence=1.0, resolver_name="mobile_system"),
            confidence=1.0,
            duration_ms=duration_ms,
            error=ErrorInfo(
                error_type="MobileSystemActionError",
                message=f"system action {kind!r} failed: {exc}",
                resolver_name="mobile_system",
            ),
        )

    duration_ms = int((time.monotonic() - t0) * 1000)
    metadata = {"system_action": {"kind": kind, **arg, **(outcome or {})}}
    return StepResult(
        status="passed",
        action=instruction,
        target=ResolvedTarget(
            ref=f"system:{kind}", confidence=1.0, resolver_name="mobile_system", metadata=metadata
        ),
        confidence=1.0,
        duration_ms=duration_ms,
    )


async def _maybe_hide_keyboard(adapter, channel: str, action_type: str) -> None:
    """Best-effort soft-keyboard hide before a mobile tap/click (M2 config flag).

    No-op unless ``mobile.auto_hide_keyboard`` is set, the channel is mobile, the
    action is a tap/click, and the adapter supports system actions. Never raises.
    """
    if channel != "mobile" or action_type not in ("tap", "click"):
        return
    if not _config.mobile.auto_hide_keyboard:
        return
    runner = getattr(adapter, "execute_system_action", None)
    if runner is None:
        return
    try:
        await runner("hide_keyboard")
    except Exception as exc:  # noqa: BLE001 — best-effort; never fail the step
        logger.debug("auto hide_keyboard skipped: %s", exc)


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

    options = build_options(kwargs, ai_enabled=_config.ai_enabled, max_cost_level=_config.grounding.max_cost_level, memory_ttl_days=_config.grounding.memory_ttl_days, memory_max_failures=_config.grounding.memory_max_failures, resolve_retries=_config.grounding.resolve_retries, resolve_retry_interval_ms=_config.grounding.resolve_retry_interval_ms, stability_wait_enabled=_config.grounding.stability_wait_enabled, stability_quiet_ms=_config.grounding.stability_quiet_ms, stability_timeout_ms=_config.grounding.stability_timeout_ms, stability_spinner_selectors=_config.grounding.stability_spinner_selectors)
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
    await _maybe_wait_until_stable(adapter, options)
    ctx_request = context_request()
    ctx_request.include_screenshot = _should_request_vision_screenshot(intent)
    ui_ctx = await adapter.collect_context(ctx_request)
    _merge_context(intent, ui_ctx)
    _maybe_inject_vision_candidates(intent)

    # Ground — find the target element
    try:
        target, traces = await _ground_with_wait(adapter, intent)
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
        if not hasattr(adapter, "extract_text"):
            raise NotImplementedError(
                "Text extraction is not supported by the active adapter."
            )
        extracted_value = await adapter.extract_text(target.ref, timeout_ms=timeout_ms)
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

    options = build_options(kwargs, ai_enabled=_config.ai_enabled, max_cost_level=_config.grounding.max_cost_level, memory_ttl_days=_config.grounding.memory_ttl_days, memory_max_failures=_config.grounding.memory_max_failures, resolve_retries=_config.grounding.resolve_retries, resolve_retry_interval_ms=_config.grounding.resolve_retry_interval_ms, stability_wait_enabled=_config.grounding.stability_wait_enabled, stability_quiet_ms=_config.grounding.stability_quiet_ms, stability_timeout_ms=_config.grounding.stability_timeout_ms, stability_spinner_selectors=_config.grounding.stability_spinner_selectors)
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

    await _maybe_wait_until_stable(adapter, options)
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
        resolve_retries=_config.grounding.resolve_retries,
        resolve_retry_interval_ms=_config.grounding.resolve_retry_interval_ms,
        stability_wait_enabled=_config.grounding.stability_wait_enabled,
        stability_quiet_ms=_config.grounding.stability_quiet_ms,
        stability_timeout_ms=_config.grounding.stability_timeout_ms,
        stability_spinner_selectors=_config.grounding.stability_spinner_selectors,
    )


async def _maybe_wait_until_stable(adapter, options) -> dict | None:
    """Settle the page/app before resolving (W2), when enabled.

    No-op when stability waiting is disabled, the adapter does not implement
    ``wait_until_stable``, or the wait raises (resolution then proceeds as
    before — the wait is best-effort and must never break a step). Returns the
    adapter's diagnostic dict, or None when skipped.
    """
    if not getattr(options, "stability_wait", True):
        return None
    wait = getattr(adapter, "wait_until_stable", None)
    if wait is None:
        return None
    spinner_selectors = getattr(options, "stability_spinner_selectors", None)
    if spinner_selectors is None:
        spinner_selectors = _config.grounding.stability_spinner_selectors
    try:
        return await wait(
            quiet_ms=options.stability_quiet_ms,
            timeout_ms=options.stability_timeout_ms,
            spinner_selectors=spinner_selectors,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort; never fail the step
        logger.debug("wait_until_stable skipped after error: %s", exc)
        return None


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

    # Expand dynamic-value tokens (e.g. {{today+7d|%d/%m/%Y}}) so a tester can
    # parameterise dates/times in the phrase. Token-free values pass through
    # untouched. Applied last so both parsed and explicit values are covered.
    input_value = substitute_dynamic_tokens(input_value)

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
    # X3: expose the coordinate-click fallback toggle so the visual-ref hydrator
    # can decide whether to emit a point:// ref when no element mapping exists.
    intent.context.setdefault(
        "coordinate_click_fallback", _config.grounding.coordinate_click_fallback
    )


# Resolution failures worth retrying: the element may simply not be in the DOM
# yet (SPA late render). Ambiguity / cost-policy blocks are NOT retried — more
# attempts cannot change those outcomes.
_RETRYABLE_GROUND_ERRORS = (ResolutionFailedError, LowConfidenceError)


async def _maybe_resolve_table_or_link(adapter, channel: str, instruction: str, kwargs: dict):
    """Resolve a table-cell click or link-by-text click from the DOM.

    Returns a ResolvedTarget for the cell's clickable element / matched link, or
    None when the step isn't a table/link action or nothing matches. Lets a
    tester address an element by table coordinates ("the PPHID value in the 1st
    row") or link text — robust when the visible text is dynamic.
    """
    if channel != "web":
        return None
    from bubblegum.core.table import parse_table_action

    spec = parse_table_action(instruction, kwargs)
    if not spec:
        return None

    try:
        if spec["kind"] == "link":
            finder = getattr(adapter, "find_link", None)
            ref = await finder(spec["text"], exact=spec.get("exact", False)) if finder else None
            resolver_name = "link_dom"
        else:
            finder = getattr(adapter, "find_table_cell", None)
            ref = await finder(
                column=spec["column"],
                row_index=spec.get("row_index"),
                row_match=spec.get("row_match"),
            ) if finder else None
            resolver_name = "table_cell_dom"
    except Exception as exc:  # noqa: BLE001 — fall through to normal grounding
        logger.debug("table/link DOM resolution errored: %s", exc)
        return None

    if not ref:
        return None
    logger.debug("Resolved '%s' via %s (%s)", instruction, resolver_name, ref)
    return ResolvedTarget(
        ref=ref, confidence=0.9, resolver_name=resolver_name,
        metadata={"table_or_link_dom": True, "spec": spec},
    )


async def _maybe_resolve_input(adapter, channel: str, intent: StepIntent):
    """DOM fallback for a `type` step whose field has no accessible name.

    Resolves a text input / textarea by its label / placeholder / nearby
    form-item label (the target phrase). Returns a ResolvedTarget or None.
    """
    if channel != "web" or getattr(intent, "action_type", None) not in ("type", "fill"):
        return None
    finder = getattr(adapter, "find_input", None)
    if finder is None:
        return None
    text = (intent.target_phrase or "").strip()
    if not text:
        return None
    try:
        ref = await finder(text)
    except Exception as exc:  # noqa: BLE001
        logger.debug("input DOM fallback errored: %s", exc)
        return None
    if not ref:
        return None
    logger.debug("Resolved type target via DOM input fallback (%s)", ref)
    return ResolvedTarget(
        ref=ref, confidence=0.7, resolver_name="input_dom",
        metadata={"role": "textbox", "input_dom": True},
    )


async def _maybe_resolve_clickable(adapter, channel: str, instruction: str, intent: StepIntent):
    """DOM fallback for an ambiguous/low-confidence click.

    Finds a single interactive element by accessible name + role (the quoted
    text in the step, else the target phrase). Returns a ResolvedTarget or None.
    """
    if channel != "web" or getattr(intent, "action_type", None) not in ("click", "tap"):
        return None
    finder = getattr(adapter, "find_clickable", None)
    if finder is None:
        return None
    quoted = _quoted_segments(instruction)
    text = quoted[0] if quoted else (intent.target_phrase or "")
    if not text.strip():
        return None
    try:
        ref = await finder(text)
    except Exception as exc:  # noqa: BLE001 — keep the original grounding error if this fails
        logger.debug("clickable DOM fallback errored: %s", exc)
        return None
    if not ref:
        return None
    logger.debug("Resolved click '%s' via DOM clickable fallback (%s)", instruction, ref)
    return ResolvedTarget(
        ref=ref, confidence=0.75, resolver_name="clickable_dom",
        metadata={"role": "button", "clickable_dom": True},
    )


async def _maybe_resolve_select_trigger(adapter, channel: str, intent: StepIntent):
    """DOM fallback for dropdown/select intents that failed to ground.

    Returns a ResolvedTarget pointing at the best select trigger (resolved by the
    adapter from label / placeholder / displayed value), or None when this isn't
    a web dropdown intent or no select-like control is found.
    """
    if channel != "web":
        return None
    from bubblegum.core.grounding.engine import _is_dropdown_select_intent

    if not _is_dropdown_select_intent(intent):
        return None
    finder = getattr(adapter, "find_select_trigger", None)
    if finder is None:
        return None
    try:
        ref = await finder(intent.target_phrase or "", intent.input_value or "")
    except Exception as exc:  # noqa: BLE001 — fallback must never mask the original error
        logger.debug("select-trigger DOM fallback errored: %s", exc)
        return None
    if not ref:
        return None
    logger.debug("Resolved dropdown '%s' via DOM select-trigger fallback (%s)", intent.instruction, ref)
    return ResolvedTarget(
        ref=ref,
        confidence=0.6,
        resolver_name="select_trigger_dom",
        metadata={"role": "combobox", "select_trigger_dom": True},
    )


async def _ground_with_wait(adapter, intent: StepIntent):
    """Ground the intent, re-collecting context and retrying when nothing
    resolves yet.

    Playwright auto-waits on a *known* locator, but Bubblegum resolves from a
    one-shot accessibility snapshot — so an element rendered a moment after the
    snapshot would otherwise fail immediately. Between attempts we sleep a short
    interval and re-collect context so the next snapshot can see it. Only
    retryable resolution errors trigger this; everything else propagates at
    once. Behaviour is unchanged whenever the first attempt succeeds.
    """
    retries = max(0, int(getattr(intent.options, "resolve_retries", 0)))
    interval_ms = max(0, int(getattr(intent.options, "resolve_retry_interval_ms", 0)))

    attempt = 0
    while True:
        try:
            return await _engine.ground(intent)
        except _RETRYABLE_GROUND_ERRORS:
            if attempt >= retries:
                raise
            attempt += 1
            if interval_ms:
                await asyncio.sleep(interval_ms / 1000.0)
            ctx_request = context_request()
            ctx_request.include_screenshot = _should_request_vision_screenshot(intent)
            ui_ctx = await adapter.collect_context(ctx_request)
            _merge_context(intent, ui_ctx)
            _maybe_inject_vision_candidates(intent)
            logger.debug(
                "Re-grounding '%s' after no/low-confidence match (attempt %d/%d)",
                intent.instruction, attempt, retries,
            )


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
