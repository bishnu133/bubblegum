from __future__ import annotations

from bubblegum.core.config import BubblegumConfig


_ALLOWED_OPS = {"verify", "extract", "execute"}


def is_webview_switching_enabled_for_operation(*, config: BubblegumConfig, operation_type: str) -> dict:
    mode = str(config.webview_switching.webview_switching_mode or "unknown").strip().lower()
    operation = str(operation_type or "").strip().lower() or "unknown"

    out = {
        "enabled": False,
        "reason": "disabled_by_config",
        "operation_type": operation,
        "mode": mode if mode in {"off", "dry_run", "opt_in"} else "unknown",
        "safe_metadata_only": True,
    }

    if not config.webview_switching.enable_webview_switching:
        return out

    if out["mode"] == "off":
        out["reason"] = "mode_off"
        return out

    allowed_operations = [str(op).strip().lower() for op in config.webview_switching.webview_switch_allowed_operations]
    allowed_operations = [op for op in allowed_operations if op in _ALLOWED_OPS]

    if operation not in set(allowed_operations):
        out["reason"] = "operation_not_allowed"
        return out

    out["enabled"] = True
    out["reason"] = "enabled"
    return out
