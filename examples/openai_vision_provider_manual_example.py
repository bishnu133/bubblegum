"""Manual/optional OpenAI Vision provider setup example (Phase 11V).

This example is intentionally import-safe and does not execute any network calls on
module import. It demonstrates how adopters can manually enable the optional
OpenAIVisionProvider using public lifecycle APIs.

Requirements (user-installed, not bundled by Bubblegum base install):
    python -m pip install openai

Environment:
    OPENAI_API_KEY must be set for real provider calls (read by the OpenAI SDK/environment).

Privacy/safety notes:
    - Vision remains opt-in and privacy-gated.
    - All gates must be enabled before screenshot-to-vision processing can run:
      grounding.enable_vision=true
      privacy.send_screenshots=true
      privacy.process_screenshots_for_vision=true
    - Do not log/store raw screenshot bytes.
    - vision:// refs are synthetic ranking metadata, not adapter-executable selectors.
"""

from __future__ import annotations

import os

from bubblegum import clear_vision_provider, configure_runtime, configure_vision_provider
from bubblegum.core.config import BubblegumConfig
from bubblegum.core.vision.backends.openai import OpenAIVisionProvider


def manual_openai_vision_setup_example() -> None:
    """Demonstrate manual runtime/provider setup and teardown.

    This function intentionally does not run a real SDK call by default.
    Replace the placeholder action/verify call section in your own environment.
    """
    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set; skipping manual OpenAI vision demo.")
        return

    # Required privacy/config gates for screenshot-to-vision provider execution.
    # Cost gate reminder: invoke SDK steps with max_cost_level="high".
    configure_runtime(
        config=BubblegumConfig.model_validate(
            {
                "grounding": {"enable_vision": True},
                "privacy": {
                    "send_screenshots": True,
                    "process_screenshots_for_vision": True,
                },
            }
        )
    )

    provider = OpenAIVisionProvider(
        model="gpt-4.1-mini",
        timeout=20.0,
        create_client=True,
    )

    configure_vision_provider(provider)

    try:
        # Placeholder only: run your SDK flow (act/verify/recover/extract) in a real
        # app session with screenshot capture available and gates enabled.
        #
        # Example (pseudo):
        #   result = await act("Click the Sign in button", channel="web", page=page, max_cost_level="high")
        #   assert result.status in {"passed", "recovered"}
        #
        # Keep raw screenshot bytes out of logs/persistent metadata.
        print("Manual OpenAI vision provider configured. Run this inside your test/app flow.")
    finally:
        # Always tear down provider registration to avoid state leakage.
        clear_vision_provider()


if __name__ == "__main__":
    manual_openai_vision_setup_example()
