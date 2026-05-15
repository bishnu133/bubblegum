from __future__ import annotations

from typing import Any


_VALID_DECISIONS = {"allowed", "blocked", "deferred", "manual_review", "unknown"}
_VALID_REASONS = {
    "no_dialog",
    "opt_in_missing",
    "action_not_requested",
    "unsafe_action",
    "low_confidence",
    "ambiguous_dialog",
    "policy_allows",
    "policy_blocks",
    "manual_review_required",
    "insufficient_metadata",
}
_VALID_DIALOG_TYPES = {"permission", "confirm_cancel", "alert", "unknown"}
_VALID_ACTIONS = {"allow", "deny", "ok", "cancel", "dismiss", "unknown"}
_VALID_RECOMMENDED = {"allow", "deny", "dismiss", "defer", "manual_review", "unknown"}
_UNSAFE_ACTIONS = {"deny", "cancel"}


def _norm_choice(value: Any, allowed: set[str], fallback: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in allowed else fallback


def evaluate_system_dialog_guardrails(
    *,
    system_dialog_detection: dict | None = None,
    requested_action: str | None = None,
    explicit_opt_in: bool = False,
    policy: dict | None = None,
) -> dict:
    detection = system_dialog_detection if isinstance(system_dialog_detection, dict) else {}
    policy_dict = policy if isinstance(policy, dict) else {}

    dialog_detected = bool(detection.get("dialog_detected") is True)
    dialog_type = _norm_choice(detection.get("dialog_type"), _VALID_DIALOG_TYPES, "unknown")
    recommended_action = _norm_choice(detection.get("recommended_action"), _VALID_RECOMMENDED, "unknown")
    req_action = _norm_choice(requested_action, _VALID_ACTIONS, "unknown")

    confidence_raw = detection.get("confidence")
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = None

    warnings = detection.get("warnings") if isinstance(detection.get("warnings"), list) else []
    warning_tokens = [str(w).strip().lower() for w in warnings if str(w).strip()]

    evidence: list[str] = [f"dialog:{dialog_type}", f"action:{req_action}"]
    decision = "blocked"
    reason = "opt_in_missing"

    if not detection:
        decision = "unknown"
        reason = "insufficient_metadata"
        evidence.append("policy:metadata_missing")
    elif not dialog_detected:
        decision = "blocked"
        reason = "no_dialog"
        evidence.append("policy:no_dialog")
    elif req_action == "unknown":
        decision = "deferred"
        reason = "action_not_requested"
        evidence.append("policy:action_missing")
    elif not explicit_opt_in:
        decision = "blocked"
        reason = "opt_in_missing"
        evidence.append("policy:opt_in_missing")
    elif confidence is None:
        decision = "manual_review"
        reason = "insufficient_metadata"
        evidence.append("policy:confidence_missing")
    elif confidence < 0.7:
        decision = "blocked"
        reason = "low_confidence"
        evidence.append("policy:low_confidence")
    elif dialog_type == "unknown" or detection.get("owner") in {None, "", "unknown"}:
        decision = "manual_review"
        reason = "ambiguous_dialog"
        evidence.append("policy:ambiguous")
    elif any(t in {"ambiguous_dialog", "multiple_candidates", "ownership_unknown"} for t in warning_tokens):
        decision = "manual_review"
        reason = "ambiguous_dialog"
        evidence.append("policy:warning_ambiguous")
    elif policy_dict.get("block") is True:
        decision = "blocked"
        reason = "policy_blocks"
        evidence.append("policy:blocked")
    elif req_action != recommended_action and policy_dict.get("allow_mismatch") is not True:
        decision = "blocked"
        reason = "manual_review_required"
        evidence.append("policy:action_mismatch")
    elif req_action in _UNSAFE_ACTIONS and policy_dict.get("allow_destructive") is not True:
        decision = "blocked"
        reason = "unsafe_action"
        evidence.append("policy:unsafe_action")
    elif policy_dict.get("allow") is True or req_action == recommended_action:
        decision = "allowed"
        reason = "policy_allows"
        evidence.append("policy:allowed")
    else:
        decision = "deferred"
        reason = "manual_review_required"
        evidence.append("policy:defer")

    return {
        "decision": decision if decision in _VALID_DECISIONS else "unknown",
        "reason": reason if reason in _VALID_REASONS else "insufficient_metadata",
        "dialog_detected": dialog_detected,
        "dialog_type": dialog_type,
        "requested_action": req_action,
        "requires_opt_in": True,
        "opt_in_present": bool(explicit_opt_in),
        "action_attempted": False,
        "recommended_action": recommended_action,
        "evidence": sorted(set(evidence)),
        "warnings": warning_tokens,
        "safe_metadata_only": True,
    }
