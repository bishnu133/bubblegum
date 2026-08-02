"""Mobile screen readiness & resilience signals (M-D).

Real apps aren't always ready the instant a screen appears: a splash or a
spinner may still be up, the app may have thrown an "isn't responding" (ANR)
dialog, or it may have crashed. And on long device-farm runs the Appium session
itself can die. This module turns the current hierarchy (and driver errors) into
two safe, deterministic signals:

  * ``detect_mobile_readiness`` — is the screen *ready* to act on, or is a
    progress indicator / ANR / crash dialog blocking it?
  * ``classify_driver_error`` — is a driver exception a lost session (not
    recoverable by retrying in place), a transient blip (retryable), or other?

Pure and side-effect free (no Appium, no device), so every rule is unit-testable.
The adapter feeds readiness into ``app_state`` and its stability wait; the SDK
uses it to fail a step with an actionable message instead of a cryptic
grounding error when the app is wedged.
"""

from __future__ import annotations

from typing import Any

# Progress / loading indicators (substring match on lowercased hierarchy XML).
# Class names across native Android/iOS, Compose and Flutter spinners.
_PROGRESS_TOKENS: tuple[str, ...] = (
    "progressbar",                  # android.widget.ProgressBar
    "activityindicator",           # XCUIElementTypeActivityIndicator
    "progressindicator",           # Compose *ProgressIndicator
    "circularprogress",            # Compose CircularProgressIndicator
    "cupertinoactivityindicator",  # Flutter iOS-style spinner
    "loadingindicator",
    "loadingview",
)

# ANR ("App isn't responding") dialog signatures (text, lowercased). Specific
# phrases only — "unfortunately" alone is too broad and would false-positive on
# ordinary in-app copy.
_ANR_TEXT_TOKENS: tuple[str, ...] = (
    "isn't responding",
    "isnt responding",
    "is not responding",
    "application not responding",
)

# Crash / "has stopped" dialog signatures (text, lowercased).
_CRASH_TEXT_TOKENS: tuple[str, ...] = (
    "has stopped",
    "keeps stopping",
    "stopped working",
)

# Driver/session errors that mean the Appium session is gone — retrying the same
# call in place cannot help; the session must be surfaced as lost.
_SESSION_LOST_MARKERS: tuple[str, ...] = (
    "invalid session id",
    "session is either terminated",
    "session is either terminated or not started",
    "session deleted",
    "no such driver",
    "a session is either terminated",
    "instrumentation process is not running",
    "instrumentation process cannot be initialized",
    "session does not exist",
)

# Transient driver errors worth one retry (mirrors the adapter's own set).
_TRANSIENT_MARKERS: tuple[str, ...] = (
    "stale element reference",
    "no such element",
    "element not interactable",
    "timeout",
    "could not be located",
)


def _found(text: str, tokens: tuple[str, ...]) -> list[str]:
    return [t for t in tokens if t in text]


def detect_mobile_readiness(
    *,
    hierarchy_xml: str | None = None,
    platform: str | None = None,
    capabilities: dict | None = None,
) -> dict[str, Any]:
    """Classify whether the current screen is ready to act on.

    Returns a safe-metadata dict:
        ready          True when nothing blocks (no progress indicator, no ANR,
                       no crash dialog).
        blocker        "crash" | "anr" | "progress" | "none"  (hard blockers
                       first: a crash/ANR outranks a mere spinner).
        progress_active / anr_detected / crash_detected  the individual signals.
        evidence       matched tokens.
    Never raises; an empty/absent hierarchy is simply "ready" (nothing seen).
    """
    del platform, capabilities  # reserved; detection is hierarchy-text driven
    text = (hierarchy_xml or "").lower()

    anr_hits = _found(text, _ANR_TEXT_TOKENS)
    crash_hits = _found(text, _CRASH_TEXT_TOKENS)
    progress_hits = _found(text, _PROGRESS_TOKENS)

    anr_detected = bool(anr_hits)
    crash_detected = bool(crash_hits)
    progress_active = bool(progress_hits)

    if crash_detected:
        blocker = "crash"
    elif anr_detected:
        blocker = "anr"
    elif progress_active:
        blocker = "progress"
    else:
        blocker = "none"

    evidence: list[str] = []
    evidence += [f"crash:{t}" for t in crash_hits]
    evidence += [f"anr:{t}" for t in anr_hits]
    evidence += [f"progress:{t}" for t in progress_hits]

    return {
        "ready": blocker == "none",
        "blocker": blocker,
        "progress_active": progress_active,
        "anr_detected": anr_detected,
        "crash_detected": crash_detected,
        "evidence": sorted(set(evidence)),
        "safe_metadata_only": True,
    }


def classify_driver_error(error: Any) -> str:
    """Classify a driver exception/message as session/transient/other.

    Returns ``"session_lost"`` (surface as a lost session — retrying in place
    won't help), ``"transient"`` (one retry may help), or ``"other"``.
    """
    text = str(error or "").lower()
    if not text:
        return "other"
    if any(m in text for m in _SESSION_LOST_MARKERS):
        return "session_lost"
    if any(m in text for m in _TRANSIENT_MARKERS):
        return "transient"
    return "other"


def readiness_failure_message(readiness: dict[str, Any], *, instruction: str = "") -> str:
    """Build an actionable message for a hard readiness blocker (ANR/crash)."""
    blocker = str(readiness.get("blocker", "none"))
    suffix = f" while running {instruction!r}" if instruction else ""
    if blocker == "crash":
        return (
            f"The app appears to have crashed (a 'has stopped' dialog is on screen){suffix}. "
            "Relaunch the app / restart the session before continuing."
        )
    if blocker == "anr":
        return (
            f"The app is not responding (an ANR dialog is on screen){suffix}. "
            "Wait for it to recover or dismiss the ANR dialog before continuing."
        )
    return f"The screen is not ready ({blocker}){suffix}."
