"""
bubblegum/adapters/base.py
============================
BaseAdapter — abstract interface that every channel adapter must implement.

This keeps web (Playwright) and mobile (Appium) execution interchangeable
at the orchestration layer. The core never changes when a new platform is added;
only a new adapter subclass is required.

Phase 0 — interface definition only.
  PlaywrightAdapter lives in adapters/web/playwright/ (Phase 1A)
  AppiumAdapter     lives in adapters/mobile/appium/  (Phase 4)
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from bubblegum.core.schemas import (
    ActionPlan,
    ArtifactRef,
    ContextRequest,
    ExecutionResult,
    ResolvedTarget,
    UIContext,
    ValidationPlan,
    ValidationResult,
)


class BaseAdapter(ABC):
    """
    Abstract base for all Bubblegum channel adapters.

    Subclasses implement the four async methods below. The orchestration layer
    (GroundingEngine, ValidationEngine, RecoveryEngine) calls these methods
    without knowing which adapter is active — web or mobile.

    Channel / platform metadata:
        Adapters should expose `channel` ("web" | "mobile") and
        `platform` ("web" | "android" | "ios") as class-level attributes
        so the registry and engine can match them to StepIntent.
    """

    channel:  str = "base"
    platform: str = "base"

    # ------------------------------------------------------------------
    # Context collection
    # ------------------------------------------------------------------

    @abstractmethod
    async def collect_context(self, request: ContextRequest) -> UIContext:
        """
        Capture the current page/screen state as a UIContext snapshot.

        Only capture what request flags indicate — avoids unnecessary cost:
          request.include_screenshot    → capture PNG bytes
          request.include_accessibility → capture a11y tree / hierarchy XML
          request.include_dom           → capture full raw DOM (expensive, off by default)
          request.include_hierarchy     → capture element hierarchy
          request.redact_sensitive_data → strip passwords and PII before returning

        Returns:
            UIContext with populated fields matching the request flags.

        Raises:
            ContextCollectionError if the browser/app session is unavailable.
        """
        ...

    # ------------------------------------------------------------------
    # Action execution
    # ------------------------------------------------------------------

    @abstractmethod
    async def execute(self, plan: ActionPlan, target: ResolvedTarget) -> ExecutionResult:
        """
        Perform the action described in plan against the resolved target element.

        The GroundingEngine has already selected target — the adapter should not
        re-run any element discovery. It should use target.ref directly
        (Playwright locator string, Appium element ID, etc.).

        Returns:
            ExecutionResult with success=True on completion, or success=False with
            error message on adapter-level failure.

        Raises:
            ExecutionFailedError if the action cannot be completed and the adapter
            wants to surface a structured error rather than returning success=False.
        """
        ...

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @abstractmethod
    async def validate(self, plan: ValidationPlan) -> ValidationResult:
        """
        Assert expected post-action state — separate from grounding.

        Validation is intentionally decoupled from execution:
          - The adapter checks the expected state described in plan.
          - It does NOT re-execute any action.
          - It returns what was actually observed so the caller can compare.

        Returns:
            ValidationResult with passed=True if assertion holds within plan.timeout_ms.

        Raises:
            ValidationFailedError if the assertion framework raises unexpectedly.
        """
        ...

    # ------------------------------------------------------------------
    # Screenshot utility
    # ------------------------------------------------------------------

    @abstractmethod
    async def screenshot(self) -> ArtifactRef:
        """
        Capture the current screen state as a PNG artifact.

        The returned ArtifactRef.path must point to a real file on disk.
        Called by the engine before raising errors — ensures every failure
        has a screenshot attached.

        Returns:
            ArtifactRef(type="screenshot", path=..., timestamp=...)
        """
        ...
