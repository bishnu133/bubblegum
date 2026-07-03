"""bubblegum — AI-powered recovery and NL execution layer for Playwright and Appium.

Public MVP API re-exports:
- act
- verify
- extract
- recover
- configure_runtime
"""

from bubblegum.core.sdk import (
    act,
    clear_vision_provider,
    configure_runtime,
    configure_vision_provider,
    extract,
    recover,
    verify,
)
from bubblegum.session import BubblegumSession

__all__ = [
    "act",
    "verify",
    "extract",
    "recover",
    "configure_runtime",
    "configure_vision_provider",
    "clear_vision_provider",
    "BubblegumSession",
    "__version__",
]

__version__ = "0.0.6a19"
