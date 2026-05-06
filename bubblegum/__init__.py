"""bubblegum — AI-powered recovery and NL execution layer for Playwright and Appium.

Public MVP API re-exports:
- act
- verify
- extract
- recover
- configure_runtime
"""

from bubblegum.core.sdk import act, configure_runtime, extract, recover, verify

__all__ = [
    "act",
    "verify",
    "extract",
    "recover",
    "configure_runtime",
    "__version__",
]

__version__ = "0.0.2a0"
