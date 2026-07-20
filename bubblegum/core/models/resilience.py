"""
bubblegum/core/models/resilience.py
===================================
Bounded retry + hard timeout for model calls (Task #7).

Enterprise robustness: a slow or momentarily-overloaded model API must not hang
a suite or fail a whole run on a blip. call_with_resilience() wraps a single
async API call with a hard timeout and a bounded exponential backoff (with
jitter) that retries only *transient* errors — rate limits, 5xx, timeouts,
connection resets. Deterministic failures (bad request, auth) are re-raised
immediately so they surface fast instead of being retried pointlessly.
"""

from __future__ import annotations

import asyncio
import logging
import random

logger = logging.getLogger(__name__)

# Substrings that indicate a retryable, transient condition. Matched against the
# error text so we need not import each provider SDK's error classes.
_TRANSIENT_TOKENS = (
    "timeout", "timed out", "rate limit", "ratelimit", "too many requests",
    "overloaded", "temporarily", "connection", "reset by peer", "unavailable",
    "502", "503", "504", "529",
)


def is_transient_error(exc: Exception) -> bool:
    """Heuristic: is this error worth retrying?"""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if isinstance(status, int) and (status == 429 or 500 <= status < 600):
        return True
    msg = str(getattr(exc, "message", "") or exc).lower()
    return any(tok in msg for tok in _TRANSIENT_TOKENS)


async def call_with_resilience(
    factory,
    *,
    timeout_s: float,
    max_retries: int,
    backoff_ms: int,
    is_transient=is_transient_error,
):
    """Invoke ``factory()`` (a zero-arg coroutine factory) with timeout + retries.

    Args:
        factory:     called on each attempt to produce a fresh awaitable.
        timeout_s:   per-attempt hard timeout (<=0 disables the timeout).
        max_retries: max *additional* attempts after the first (0 = no retry).
        backoff_ms:  base backoff; delay grows as backoff * 2**attempt + jitter.

    Re-raises the last exception when retries are exhausted or the error is not
    transient.
    """
    attempt = 0
    while True:
        try:
            if timeout_s and timeout_s > 0:
                return await asyncio.wait_for(factory(), timeout=timeout_s)
            return await factory()
        except Exception as exc:  # noqa: BLE001 — classified below
            if attempt >= max_retries or not is_transient(exc):
                raise
            base = (backoff_ms / 1000.0) * (2 ** attempt)
            delay = base + random.uniform(0.0, base * 0.25)   # +/- jitter
            logger.warning(
                "Model call transient error (attempt %d/%d): %s — retrying in %.2fs",
                attempt + 1, max_retries + 1, exc, delay,
            )
            await asyncio.sleep(delay)
            attempt += 1
