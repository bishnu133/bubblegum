from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.mobile.webview_real_driver_switch import (
    RealWebViewContextRef,
    build_real_webview_context_map,
    resolve_real_webview_context_ref,
)


def test_build_real_webview_context_map_missing_inventory_unknown():
    out = build_real_webview_context_map(context_inventory=None)
    assert out["status"] == "unknown"
    assert out["reason"] == "context_inventory_missing"
    assert out["safe_metadata_only"] is True


def test_build_real_webview_context_map_no_webview_blocked():
    out = build_real_webview_context_map(context_inventory={"contexts": ["NATIVE_APP"]})
    assert out["status"] == "blocked"
    assert out["reason"] == "webview_context_missing"
    assert out["context_map_available"] is False


def test_build_real_webview_context_map_single_webview_ready():
    out = build_real_webview_context_map(context_inventory={"contexts": ["NATIVE_APP", "WEBVIEW_1"]})
    assert out["status"] == "ready"
    assert out["reason"] == "webview_context_map_ready"
    assert out["webview_count"] == 1
    assert out["context_map_available"] is True


def test_build_real_webview_context_map_multi_webview_hides_names():
    out = build_real_webview_context_map(context_inventory={"contexts": ["NATIVE_APP", "WEBVIEW_secret_1", "WEBVIEW_secret_2"]})
    assert out["status"] == "ready"
    assert out["webview_count"] == 2
    assert "WEBVIEW_secret_1" not in str(out)
    assert "WEBVIEW_secret_2" not in str(out)


def test_resolve_real_webview_context_ref_resolves_internal_ref_but_hides_raw_name():
    ref = resolve_real_webview_context_ref(
        context_inventory={"contexts": ["NATIVE_APP", "WEBVIEW_secret_1"]},
        selected_context_index=0,
        selected_context_type="webview",
    )
    assert isinstance(ref, RealWebViewContextRef)
    assert ref.safe_metadata["status"] == "resolved"
    assert ref.safe_metadata["internal_context_ref_available"] is True
    assert "WEBVIEW_secret_1" not in str(ref.safe_metadata)


def test_resolve_real_webview_context_ref_out_of_range_blocks():
    ref = resolve_real_webview_context_ref(
        context_inventory={"contexts": ["NATIVE_APP", "WEBVIEW_1"]},
        selected_context_index=3,
        selected_context_type="webview",
    )
    assert ref.safe_metadata["status"] == "blocked"
    assert ref.safe_metadata["reason"] == "selected_context_index_out_of_range"


def test_resolve_real_webview_context_ref_native_type_blocks():
    ref = resolve_real_webview_context_ref(
        context_inventory={"contexts": ["NATIVE_APP", "WEBVIEW_1"]},
        selected_context_index=0,
        selected_context_type="native",
    )
    assert ref.safe_metadata["status"] == "blocked"
    assert ref.safe_metadata["reason"] == "selected_context_type_not_webview"


def test_raw_context_name_not_in_repr_or_safe_output():
    ref = resolve_real_webview_context_ref(
        context_inventory={"contexts": ["NATIVE_APP", "WEBVIEW_secret_hidden"]},
        selected_context_index=0,
        selected_context_type="webview",
    )
    assert "WEBVIEW_secret_hidden" not in repr(ref)
    assert "WEBVIEW_secret_hidden" not in str(ref.safe_metadata)


def test_module_does_not_use_switch_to_context_text():
    import bubblegum.core.mobile.webview_real_driver_switch as mod

    source = open(mod.__file__, "r", encoding="utf-8").read()
    assert "switch_to.context" not in source


def test_helper_not_wired_into_appium_adapter_validate_extract_execute():
    source = open("bubblegum/adapters/mobile/appium/adapter.py", "r", encoding="utf-8").read()
    assert "webview_real_driver_switch" not in source
    assert "build_real_webview_context_map" not in source
    assert "resolve_real_webview_context_ref" not in source
    assert "driver.switch_to.context" not in source

    adapter = AppiumAdapter(type("_D", (), {})())
    assert not hasattr(adapter, "_real_webview_context_ref")
