"""
tests/integration/test_phase2_llm.py
======================================
Phase 2 LLM integration test — calls the real OpenAI API.

Skipped by default. Run with:
    pytest tests/integration/test_phase2_llm.py -m llm --llm -v

Requires OPENAI_API_KEY environment variable to be set.

Scenario: accessibility snapshot contains a "Sign In" button.
          Instruction says "Click Login".
          ExactTextResolver will miss (no "Login" in tree).
          LLMGroundingResolver should identify "Sign In" as the intent match.
"""

from __future__ import annotations

import os
import json

import pytest

from bubblegum.core.grounding.resolvers.llm_grounding import LLMGroundingResolver
from bubblegum.core.models.openai_provider import OpenAIProvider
from bubblegum.core.schemas import ExecutionOptions, StepIntent


# ---------------------------------------------------------------------------
# CLI flag for enabling live LLM tests
# ---------------------------------------------------------------------------

# def pytest_addoption(parser):
#     """Add --llm flag to enable live LLM integration tests."""
#     try:
#         parser.addoption(
#             "--llm",
#             action="store_true",
#             default=False,
#             help="Run live LLM integration tests (requires OPENAI_API_KEY).",
#         )
#     except Exception:
#         pass   # already added by another conftest
#
#
# def pytest_configure(config):
#     config.addinivalue_line("markers", "llm: mark test as requiring a live LLM API call")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def llm_enabled(request):
    """Skip this entire module unless --llm flag is passed."""
    if not request.config.getoption("--llm", default=False):
        pytest.skip("Pass --llm to run live LLM integration tests.")


@pytest.fixture(scope="module")
def api_key():
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        pytest.skip("OPENAI_API_KEY environment variable not set.")
    return key


# ---------------------------------------------------------------------------
# Snapshot used in all tests
# ---------------------------------------------------------------------------

_SNAPSHOT_SIGN_IN = """\
- banner
  - link "Home"
- main
  - heading "Welcome back"
  - textbox "Email address"
  - textbox "Password"
  - button "Sign In"
  - link "Forgot your password?"
  - link "Create account"
"""

_SNAPSHOT_SUBMIT_ORDER = """\
- main
  - heading "Your Order"
  - listitem "Product A — $9.99"
  - listitem "Product B — $4.99"
  - button "Place Order"
  - button "Go Back"
  - link "Terms and Conditions"
"""


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

@pytest.mark.llm
@pytest.mark.asyncio
class TestLLMGroundingResolverIntegration:

    async def test_login_intent_finds_sign_in_button(self, llm_enabled, api_key):
        """
        Instruction 'Click Login' — snapshot has 'Sign In' button.
        ExactTextResolver would miss. LLM should identify Sign In as correct match.
        """
        provider = OpenAIProvider(model="gpt-4o-mini", api_key=api_key)
        resolver = LLMGroundingResolver(provider=provider)

        intent = StepIntent(
            instruction="Click Login",
            channel="web",
            platform="web",
            action_type="click",
            context={"a11y_snapshot": _SNAPSHOT_SIGN_IN},
            options=ExecutionOptions(max_cost_level="high"),
        )

        targets = await resolver.resolve_async(intent)

        assert len(targets) >= 1, (
            "Expected at least one candidate. LLM should map 'Login' -> 'Sign In'."
        )

        top = targets[0]
        assert top.confidence >= 0.50, f"Confidence too low: {top.confidence}"
        assert top.ref, "ref must not be empty"
        # The ref should reference Sign In in some form
        assert any(
            term in top.ref.lower() for term in ["sign", "in", "button"]
        ), f"Unexpected ref: {top.ref}"

    async def test_submit_order_intent(self, llm_enabled, api_key):
        """
        Instruction 'Click Place Order' — direct match should yield high confidence.
        """
        provider = OpenAIProvider(model="gpt-4o-mini", api_key=api_key)
        resolver = LLMGroundingResolver(provider=provider)

        intent = StepIntent(
            instruction="Click Place Order",
            channel="web",
            platform="web",
            action_type="click",
            context={"a11y_snapshot": _SNAPSHOT_SUBMIT_ORDER},
            options=ExecutionOptions(max_cost_level="high"),
        )

        targets = await resolver.resolve_async(intent)

        assert len(targets) >= 1
        assert targets[0].confidence >= 0.70
        assert "place" in targets[0].ref.lower() or "order" in targets[0].ref.lower()

    async def test_no_match_returns_empty_or_low_confidence(self, llm_enabled, api_key):
        """
        Instruction 'Click Delete Account' against a snapshot with no delete action.
        Expect empty list (model returns confidence < 0.50) or very low confidence.
        """
        provider = OpenAIProvider(model="gpt-4o-mini", api_key=api_key)
        resolver = LLMGroundingResolver(provider=provider)

        intent = StepIntent(
            instruction="Click Delete Account",
            channel="web",
            platform="web",
            action_type="click",
            context={"a11y_snapshot": _SNAPSHOT_SIGN_IN},
            options=ExecutionOptions(max_cost_level="high"),
        )

        targets = await resolver.resolve_async(intent)

        # Either no result returned, or confidence is low
        if targets:
            assert targets[0].confidence < 0.75, (
                "Model should not be highly confident when no delete action exists."
            )

    async def test_response_is_valid_ref_format(self, llm_enabled, api_key):
        """
        Verify that the ref returned by the LLM is a recognisable Playwright locator.
        """
        provider = OpenAIProvider(model="gpt-4o-mini", api_key=api_key)
        resolver = LLMGroundingResolver(provider=provider)

        intent = StepIntent(
            instruction="Click Sign In",
            channel="web",
            platform="web",
            action_type="click",
            context={"a11y_snapshot": _SNAPSHOT_SIGN_IN},
            options=ExecutionOptions(max_cost_level="high"),
        )

        targets = await resolver.resolve_async(intent)

        if targets:
            ref = targets[0].ref
            # Must be a recognisable Playwright locator format.
            # LLM may return role=, text=, or bare CSS-style (button[name="..."])
            # — all are valid and handled by PlaywrightAdapter._resolve_locator().
            valid_prefix = (
                    ref.startswith("role=")
                    or ref.startswith("text=")
                    or ref.startswith("button")
                    or ref.startswith("link")
                    or ref.startswith("input")
                    or "[name=" in ref
                    or "[label=" in ref
            )
            assert valid_prefix, (
                f"Unexpected ref format — not a recognisable Playwright locator: {ref!r}"
            )

    async def test_metadata_contains_reasoning(self, llm_enabled, api_key):
        """Resolver must populate 'reasoning' in metadata."""
        provider = OpenAIProvider(model="gpt-4o-mini", api_key=api_key)
        resolver = LLMGroundingResolver(provider=provider)

        intent = StepIntent(
            instruction="Click Login",
            channel="web",
            platform="web",
            action_type="click",
            context={"a11y_snapshot": _SNAPSHOT_SIGN_IN},
            options=ExecutionOptions(max_cost_level="high"),
        )

        targets = await resolver.resolve_async(intent)

        if targets:
            assert "reasoning" in targets[0].metadata
            assert isinstance(targets[0].metadata["reasoning"], str)
