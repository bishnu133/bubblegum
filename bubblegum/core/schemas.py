"""
bubblegum/core/schemas.py
=========================
All 13 Pydantic v2 schemas for Bubblegum.
These are the shared contract between every layer — lock before writing any adapter or resolver.

Phase 0 — contracts only. No logic here.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 1. ContextRequest
#    Controls what collect_context() captures from the adapter.
# ---------------------------------------------------------------------------

class ContextRequest(BaseModel):
    """Controls what UIContext data collect_context() should capture."""

    include_screenshot:    bool = True
    include_accessibility: bool = True    # a11y tree (web) / hierarchy XML (mobile)
    include_dom:           bool = False   # full raw DOM — expensive, off by default
    include_hierarchy:     bool = True
    redact_sensitive_data: bool = True    # always redact passwords/PII before capture


# ---------------------------------------------------------------------------
# 2. ExecutionOptions
#    Standalone reusable options — embedded in ActionPlan, StepIntent, and recover().
# ---------------------------------------------------------------------------

class ExecutionOptions(BaseModel):
    """Reusable execution options. Shared by ActionPlan, StepIntent, and recover()."""

    timeout_ms:     int       = 10_000
    retry_count:    int       = 2
    wait_for:       str | None = None    # e.g. 'networkidle', 'domcontentloaded'
    use_ai:         bool      = True
    max_cost_level: str       = "medium"  # "low" | "medium" | "high"
    memory_ttl_days: int      = 7
    memory_max_failures: int  = 3


# ---------------------------------------------------------------------------
# 3. StepIntent
#    Input to every resolver — produced by the parser/planner from a raw NL instruction.
# ---------------------------------------------------------------------------

class StepIntent(BaseModel):
    """Parsed and enriched intent passed into the GroundingEngine and every Resolver."""

    instruction:  str
    channel:      str                       # "web" | "mobile"
    platform:     str = "web"              # "web" | "android" | "ios"
    action_type:  str                       # "click" | "type" | "select" | "scroll" | "tap" | ...
    context:      dict[str, Any] = Field(default_factory=dict)
    options:      ExecutionOptions = Field(default_factory=ExecutionOptions)


# ---------------------------------------------------------------------------
# 4. UIContext
#    Snapshot of the current page/screen state — collected by the adapter.
# ---------------------------------------------------------------------------

class UIContext(BaseModel):
    """Collected page/screen state returned by BaseAdapter.collect_context()."""

    a11y_snapshot:   str | None = None    # YAML-format aria snapshot (web)
    hierarchy_xml:   str | None = None    # Appium XML hierarchy (mobile)
    screenshot:      bytes | None = None  # raw PNG bytes
    screen_signature: str | None = None   # fingerprint for memory matching
    app_state:       dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 5. ActionPlan
#    Derived from StepIntent by the Planner. Carries resolved execution parameters.
# ---------------------------------------------------------------------------

class ActionPlan(BaseModel):
    """
    Execution plan derived from StepIntent by the Planner layer.
    Does NOT carry the original StepIntent — only the resolved execution parameters.
    ResolvedTarget is added later by the GroundingEngine.
    """

    action_type:  Literal["click", "type", "select", "scroll", "tap", "swipe", "verify", "extract"]
    target_hint:  str | None = None   # natural language hint to the grounding engine
    input_value:  str | None = None   # value to type / select
    options:      ExecutionOptions = Field(default_factory=ExecutionOptions)


# ---------------------------------------------------------------------------
# 6. ResolvedTarget
#    Output from every Resolver — represents a single candidate element.
# ---------------------------------------------------------------------------

class ResolvedTarget(BaseModel):
    """A single candidate element returned by a Resolver."""

    ref:           str             # locator ref usable by the adapter (selector, xpath, aria-ref, etc.)
    confidence:    float           # 0.0 – 1.0
    resolver_name: str
    metadata:      dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 7. ExecutionResult
#    Returned by BaseAdapter.execute() after performing the action.
# ---------------------------------------------------------------------------

class ExecutionResult(BaseModel):
    """Result of the adapter executing an action against a ResolvedTarget."""

    success:     bool
    duration_ms: int
    element_ref: str | None = None
    error:       str | None = None    # raw error message from adapter, if any


# ---------------------------------------------------------------------------
# 8. ValidationPlan
#    Tells the ValidationEngine what to assert after an action.
# ---------------------------------------------------------------------------

class ValidationPlan(BaseModel):
    """Describes what post-action state the ValidationEngine should verify."""

    assertion_type: str           # "text_visible" | "element_state" | "page_transition" | ...
    expected_value: str | None = None
    timeout_ms:     int = 5_000


# ---------------------------------------------------------------------------
# 9. ValidationResult
#    Outcome of BaseAdapter.validate() — what was actually observed.
# ---------------------------------------------------------------------------

class ValidationResult(BaseModel):
    """Outcome returned by the ValidationEngine after asserting expected state."""

    passed:      bool
    actual_value: str | None = None
    screenshot:   bytes | None = None
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# 10. ArtifactRef
#     Reference to a file artifact produced during a step (screenshot, trace, report).
# ---------------------------------------------------------------------------

class ArtifactRef(BaseModel):
    """Reference to a file artifact saved to disk during execution."""

    type:      Literal["screenshot", "trace", "report", "json"]
    path:      str
    timestamp: str    # ISO-8601 string


# ---------------------------------------------------------------------------
# 11. ErrorInfo
#     Structured error attached to StepResult when something goes wrong.
# ---------------------------------------------------------------------------

class ErrorInfo(BaseModel):
    """Structured error information attached to a failed StepResult."""

    error_type:    str                              # matches error taxonomy class names
    message:       str
    resolver_name: str | None = None
    candidates:    list[ResolvedTarget] = Field(default_factory=list)
    screenshot:    ArtifactRef | None = None


# ---------------------------------------------------------------------------
# 12. ResolverTrace
#     Per-resolver debug log — one entry per resolver that ran during a step.
# ---------------------------------------------------------------------------

class ResolverTrace(BaseModel):
    """Debug trace for a single resolver invocation during a step."""

    resolver_name: str
    duration_ms:   int
    candidates:    list[ResolvedTarget] = Field(default_factory=list)
    can_run:       bool = True      # False if resolver was skipped (channel, cost, context)
    reason_skipped: str | None = None


# ---------------------------------------------------------------------------
# 13. StepResult
#     Top-level SDK return value from act(), verify(), extract(), and recover().
# ---------------------------------------------------------------------------

class StepResult(BaseModel):
    """
    Top-level result returned by act(), verify(), extract(), and recover().
    This is the contract with test frameworks.

    status:
      - "passed"    — original selector/intent succeeded
      - "recovered" — original selector failed, Bubblegum recovered it (CI flag)
      - "failed"    — could not resolve or execute
      - "skipped"   — step skipped per options
    """

    status:     Literal["passed", "failed", "recovered", "skipped"]
    action:     str
    target:     ResolvedTarget | None = None
    confidence: float = 0.0
    validation: ValidationResult | None = None
    artifacts:  list[ArtifactRef] = Field(default_factory=list)
    duration_ms: int = 0
    error:      ErrorInfo | None = None
    traces:     list[ResolverTrace] = Field(default_factory=list)   # one per resolver that ran
