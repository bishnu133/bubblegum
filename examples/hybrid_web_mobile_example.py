"""Hybrid web + mobile usage example for Bubblegum (Phase 10K).

This file is intentionally illustrative:
- Web snippets show Playwright-style `page` usage.
- Mobile snippets show Appium-style `driver` usage.
- Hybrid mode idea: explicit selector first, natural-language fallback where useful.
- Includes `act(...)`, `verify(...)`, `extract(...)`, and `recover(...)` calls.
- Demonstrates OCR injected-block payload as optional input data only
  (no real OCR engine integration in this example).

This module is import-safe and does not require Playwright/Appium at import time.
Run snippets only in properly configured environments.
"""

from __future__ import annotations

from bubblegum import act, extract, recover, verify


async def web_flow(page) -> None:
    """Playwright-style web flow using deterministic-first selectors.

    The `page` parameter is expected to be a Playwright Page-like object.
    """
    await act(
        page=page,
        instruction="Type qa@example.com into the email input",
        selector="input[name='email']",  # explicit selector first
    )

    await act(
        page=page,
        instruction="Click Continue",
        # no selector -> natural-language fallback path when useful
    )

    await verify(
        page=page,
        assertion="A welcome message is visible",
    )

    result = await extract(
        page=page,
        instruction="Extract the logged-in user's display name",
    )
    print("[web] extracted:", result)


async def mobile_flow(driver) -> None:
    """Appium-style mobile flow using deterministic-first selectors.

    The `driver` parameter is expected to be an Appium WebDriver-like object.
    """
    await act(
        driver=driver,
        instruction="Tap Sign in",
        selector='//*[@content-desc="Sign in"]',  # explicit first
    )

    await verify(
        driver=driver,
        assertion="The home screen title is visible",
    )

    data = await extract(
        driver=driver,
        instruction="Extract the current cart count",
    )
    print("[mobile] extracted:", data)


async def hybrid_recovery_with_optional_ocr_context(page, driver) -> None:
    """Hybrid concept: recover in web and mobile with optional OCR context blocks.

    `ocr_blocks` below is *example injected data only* and does not imply a
    real OCR runtime in this example.
    """
    ocr_blocks = [
        {"text": "Continue", "bbox": [112, 420, 264, 478], "confidence": 0.98},
        {"text": "Cart (2)", "bbox": [310, 40, 392, 88], "confidence": 0.95},
    ]

    web_recovery = await recover(
        page=page,
        failed_selector="#continue-btn",
        intent="Click Continue",
        context={"ocr_blocks": ocr_blocks},
    )
    print("[hybrid:web] recover status:", web_recovery.status)

    mobile_recovery = await recover(
        driver=driver,
        failed_selector='//*[@content-desc="Proceed"]',
        intent="Tap Continue",
        context={"ocr_blocks": ocr_blocks},
    )
    print("[hybrid:mobile] recover status:", mobile_recovery.status)


async def main() -> None:
    """Pseudo-entrypoint showing where real framework objects would be passed.

    This function intentionally does not spin up Playwright or Appium to keep
    the example safe and infrastructure-free by default.
    """
    print(
        "This is an illustrative template. Integrate `web_flow`, `mobile_flow`, "
        "and `hybrid_recovery_with_optional_ocr_context` into your real "
        "Playwright/Appium test harness."
    )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
