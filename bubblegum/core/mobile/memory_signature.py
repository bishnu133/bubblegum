from __future__ import annotations

from typing import Any

_ALLOWED_SURFACES = {"android_native", "ios_native", "webview", "hybrid", "system_dialog", "unknown"}
_ALLOWED_CONTEXT_MODES = {"native_only", "webview_only", "hybrid", "unknown"}
_ALLOWED_DIALOG = {"none", "system_dialog", "app_modal", "unknown"}
_ALLOWED_SCROLL = {"not_needed", "candidate", "unknown"}
_ALLOWED_REPEATED = {"resolved", "ambiguous", "none", "unknown"}



def _norm(value: Any, allowed: set[str], default: str = "unknown") -> str:
    v = str(value or "").strip().lower()
    return v if v in allowed else default


def build_mobile_memory_signature(*, ui_context, target_metadata: dict | None = None) -> dict:
    state = getattr(ui_context, "app_state", None)
    app_state = state if isinstance(state, dict) else {}
    metadata = target_metadata if isinstance(target_metadata, dict) else {}

    framework = app_state.get("framework_detection") if isinstance(app_state.get("framework_detection"), dict) else {}
    inventory = app_state.get("context_inventory") if isinstance(app_state.get("context_inventory"), dict) else {}
    dialog = app_state.get("system_dialog_detection") if isinstance(app_state.get("system_dialog_detection"), dict) else {}
    scroll = app_state.get("scroll_discovery") if isinstance(app_state.get("scroll_discovery"), dict) else {}

    platform = _norm(framework.get("platform") or inventory.get("platform"), {"android", "ios", "unknown"})
    surface = _norm(framework.get("surface_type"), _ALLOWED_SURFACES)
    context_mode = _norm(inventory.get("inferred_context_mode"), _ALLOWED_CONTEXT_MODES)

    dialog_state = "unknown"
    if dialog.get("dialog_detected") is False:
        dialog_state = "none"
    elif dialog.get("dialog_detected") is True:
        owner = str(dialog.get("owner") or "").strip().lower()
        dialog_state = "system_dialog" if owner == "system" else "app_modal"

    scroll_state = _norm(scroll.get("status"), _ALLOWED_SCROLL)

    repeated_diag = metadata.get("repeated_region_diagnostics") if isinstance(metadata.get("repeated_region_diagnostics"), dict) else {}
    repeated_raw = str(repeated_diag.get("status") or "").strip().lower()
    repeated_state = "resolved" if repeated_raw == "resolved" else "ambiguous" if repeated_raw == "ambiguous" else "none" if repeated_raw in {"no_repeated_region", "no_anchor", "unsupported"} else "unknown"

    icon_diag = metadata.get("icon_detection") if isinstance(metadata.get("icon_detection"), dict) else {}
    icon_target = str(icon_diag.get("target_icon") or "none").strip().lower()
    if not icon_target:
        icon_target = "none"
    if icon_target not in {"search", "delete", "profile", "unknown", "none", "cart", "back", "close", "more", "settings", "edit", "add", "calendar", "filter", "favorite"}:
        icon_target = "unknown"

    parts = [
        f"platform:{platform}",
        f"surface:{surface}",
        f"context:{context_mode}",
        f"dialog:{dialog_state}",
        f"scroll:{scroll_state}",
        f"repeated:{repeated_state}",
        f"icon:{icon_target}",
    ]

    return {
        "enabled": True,
        "platform": platform,
        "surface_type": surface,
        "context_mode": context_mode,
        "dialog_state": dialog_state,
        "scroll_state": scroll_state,
        "repeated_region_status": repeated_state,
        "icon_target": icon_target,
        "signature_parts": parts,
        "warnings": [],
        "safe_metadata_only": True,
    }
