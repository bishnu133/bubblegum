from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable


_WEBVIEW_TYPES = {"webview", "webview/chromium"}


@dataclass(repr=False)
class RealWebViewContextRef:
    safe_metadata: dict
    _raw_context_name: str | None = field(default=None, repr=False)


def _safe_context_type(value: str | None) -> str:
    normalized = str(value or "").strip().upper()
    if normalized == "NATIVE_APP":
        return "native"
    if normalized.startswith("WEBVIEW"):
        return "webview"
    if normalized == "CHROMIUM":
        return "webview/chromium"
    return "unknown"


def _base_switch_metadata(*, explicit_opt_in: bool, selected_context_type: str = "unknown") -> dict:
    return {
        "switch_enabled": bool(explicit_opt_in),
        "switch_attempted": False,
        "switch_status": "not_attempted",
        "restore_attempted": False,
        "restore_status": "not_needed",
        "original_context_type": "unknown",
        "selected_context_type": selected_context_type,
        "reason": "not_attempted",
        "evidence": [],
        "warnings": [],
        "safe_metadata_only": True,
    }


def execute_real_driver_switch_with_ref(
    *,
    context_ref: RealWebViewContextRef,
    get_current_context: Callable[[], str | None] | None,
    switch_context: Callable[[str], None] | None,
    restore_context: Callable[[str | None], None] | None,
    operation_callable: Callable[[], object] | None = None,
    explicit_opt_in: bool = False,
) -> dict:
    out = _base_switch_metadata(explicit_opt_in=explicit_opt_in, selected_context_type="webview")

    if not explicit_opt_in:
        out["switch_status"] = "blocked"
        out["reason"] = "opt_in_required"
        out["warnings"] = ["opt_in_required"]
        return out

    raw_name = context_ref._raw_context_name if isinstance(context_ref, RealWebViewContextRef) else None
    if not raw_name:
        out["switch_status"] = "blocked"
        out["reason"] = "internal_context_ref_missing"
        out["warnings"] = ["internal_context_ref_missing"]
        return out

    if not callable(switch_context):
        out["switch_status"] = "blocked"
        out["reason"] = "switch_callable_missing"
        out["warnings"] = ["switch_callable_missing"]
        return out

    original_context_value = None
    switched = False
    try:
        if callable(get_current_context):
            original_context_value = get_current_context()
            out["original_context_type"] = _safe_context_type(original_context_value)

        out["switch_attempted"] = True
        switch_context(raw_name)
        switched = True
        out["switch_status"] = "switched"
        out["reason"] = "switch_succeeded"
        if callable(operation_callable):
            operation_callable()
    except Exception:
        out["switch_status"] = "failed"
        out["reason"] = "execution_error"
        out["warnings"] = ["switch_failed"]
    finally:
        if switched:
            if callable(restore_context):
                out["restore_attempted"] = True
                try:
                    restore_context(original_context_value)
                    out["restore_status"] = "restored"
                except Exception:
                    out["restore_status"] = "failed"
                    out["warnings"] = [*out.get("warnings", []), "restore_failed"]
            else:
                out["restore_status"] = "unknown"

    return out



def _inventory_contexts(context_inventory: dict | None) -> list[str]:
    if not isinstance(context_inventory, dict):
        return []
    contexts = context_inventory.get("contexts")
    if not isinstance(contexts, list):
        return []
    return [str(v) for v in contexts]



def _webview_context_names(context_inventory: dict | None) -> list[str]:
    names = _inventory_contexts(context_inventory)
    return [name for name in names if str(name).strip().upper().startswith("WEBVIEW")]



def build_real_webview_context_map(*, context_inventory: dict | None = None) -> dict:
    out = {
        "status": "unknown",
        "reason": "context_inventory_missing",
        "webview_count": 0,
        "candidate_context_count": 0,
        "context_map_available": False,
        "safe_metadata_only": True,
        "evidence": [],
        "warnings": [],
    }

    if not isinstance(context_inventory, dict):
        return out

    webview_contexts = _webview_context_names(context_inventory)
    out["webview_count"] = len(webview_contexts)
    out["candidate_context_count"] = len(webview_contexts)

    if len(webview_contexts) <= 0:
        out["status"] = "blocked"
        out["reason"] = "webview_context_missing"
        out["warnings"] = ["webview_context_missing"]
        return out

    out["status"] = "ready"
    out["reason"] = "webview_context_map_ready"
    out["context_map_available"] = True
    return out



def resolve_real_webview_context_ref(
    *,
    context_inventory: dict | None = None,
    selected_context_index: int | None = None,
    selected_context_type: str | None = None,
) -> RealWebViewContextRef:
    safe_selected_type = str(selected_context_type or "").strip().lower()
    out = {
        "status": "unknown",
        "reason": "context_inventory_missing",
        "selected_context_type": "unknown",
        "selected_context_index": selected_context_index if isinstance(selected_context_index, int) else None,
        "internal_context_ref_available": False,
        "safe_metadata_only": True,
        "evidence": [],
        "warnings": [],
    }

    if safe_selected_type not in _WEBVIEW_TYPES:
        out["status"] = "blocked"
        out["reason"] = "selected_context_type_not_webview"
        out["warnings"] = ["selected_context_type_not_webview"]
        return RealWebViewContextRef(safe_metadata=out)

    out["selected_context_type"] = "webview"

    if not isinstance(context_inventory, dict):
        return RealWebViewContextRef(safe_metadata=out)

    if not isinstance(selected_context_index, int):
        out["status"] = "blocked"
        out["reason"] = "selected_context_index_missing"
        out["warnings"] = ["selected_context_index_missing"]
        return RealWebViewContextRef(safe_metadata=out)

    webview_contexts = _webview_context_names(context_inventory)
    if not webview_contexts:
        out["status"] = "blocked"
        out["reason"] = "webview_context_missing"
        out["warnings"] = ["webview_context_missing"]
        return RealWebViewContextRef(safe_metadata=out)

    if selected_context_index < 0 or selected_context_index >= len(webview_contexts):
        out["status"] = "blocked"
        out["reason"] = "selected_context_index_out_of_range"
        out["warnings"] = ["selected_context_index_out_of_range"]
        return RealWebViewContextRef(safe_metadata=out)

    out["status"] = "resolved"
    out["reason"] = "selected_context_resolved"
    out["internal_context_ref_available"] = True
    return RealWebViewContextRef(safe_metadata=out, _raw_context_name=webview_contexts[selected_context_index])
