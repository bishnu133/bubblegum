from bubblegum.core.mobile.memory_signature import build_mobile_memory_signature
from bubblegum.core.schemas import UIContext


def _ctx(app_state: dict):
    return UIContext(app_state=app_state)


def test_android_native_signature_safe():
    sig = build_mobile_memory_signature(
        ui_context=_ctx({
            "framework_detection": {"platform": "android", "surface_type": "android_native"},
            "context_inventory": {"inferred_context_mode": "native_only"},
            "system_dialog_detection": {"dialog_detected": False},
            "scroll_discovery": {"status": "not_needed"},
        })
    )
    assert sig["platform"] == "android"
    assert sig["surface_type"] == "android_native"
    assert sig["context_mode"] == "native_only"
    assert sig["dialog_state"] == "none"
    assert sig["scroll_state"] == "not_needed"
    assert sig["safe_metadata_only"] is True


def test_hybrid_signature_differs():
    sig = build_mobile_memory_signature(
        ui_context=_ctx({
            "framework_detection": {"platform": "android", "surface_type": "hybrid"},
            "context_inventory": {"inferred_context_mode": "hybrid"},
            "system_dialog_detection": {"dialog_detected": False},
            "scroll_discovery": {"status": "candidate"},
        })
    )
    assert "surface:hybrid" in sig["signature_parts"]
    assert "context:hybrid" in sig["signature_parts"]
    assert sig["scroll_state"] == "candidate"


def test_system_dialog_reflected():
    sig = build_mobile_memory_signature(
        ui_context=_ctx({
            "framework_detection": {"platform": "android", "surface_type": "system_dialog"},
            "context_inventory": {"inferred_context_mode": "native_only"},
            "system_dialog_detection": {"dialog_detected": True, "owner": "system"},
        })
    )
    assert sig["dialog_state"] == "system_dialog"


def test_repeated_and_icon_compact_metadata():
    sig = build_mobile_memory_signature(
        ui_context=_ctx({"framework_detection": {"platform": "android", "surface_type": "android_native"}}),
        target_metadata={
            "repeated_region_diagnostics": {"status": "resolved", "selected_candidate_ref": "//raw"},
            "icon_detection": {"status": "resolved", "target_icon": "search", "selected_candidate_ref": "//raw"},
        },
    )
    assert sig["repeated_region_status"] == "resolved"
    assert sig["icon_target"] == "search"
    blob = str(sig)
    assert "selected_candidate_ref" not in blob
    assert "hierarchy_xml" not in blob
    assert "page_source" not in blob
