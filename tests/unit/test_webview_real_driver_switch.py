from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.mobile.webview_real_driver_switch import (
    RealWebViewContextRef,
    build_real_webview_context_map,
    execute_real_driver_switch_with_ref,
    resolve_real_webview_context_ref,
)


class _FakeSwitchTo:
    def __init__(self, driver):
        self._driver = driver

    def context(self, name: str):
        self._driver.calls.append(("switch", name))
        if self._driver.fail_switch:
            raise RuntimeError("switch failed WEBVIEW_secret")
        if name not in self._driver.contexts:
            raise RuntimeError("stale context")
        self._driver.current_context = name


class _FakeDriver:
    def __init__(self, *, contexts=None, current_context="NATIVE_APP", fail_switch=False, fail_restore=False):
        self.contexts = list(contexts or ["NATIVE_APP", "WEBVIEW_1"])
        self.current_context = current_context
        self.fail_switch = fail_switch
        self.fail_restore = fail_restore
        self.calls = []
        self.switch_to = _FakeSwitchTo(self)

    def restore(self, name: str | None):
        self.calls.append(("restore", name))
        if self.fail_restore:
            raise RuntimeError("restore failed NATIVE_APP")
        self.current_context = name or self.current_context


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


def test_execute_real_driver_switch_fake_success_and_restore_sequence():
    ref = resolve_real_webview_context_ref(
        context_inventory={"contexts": ["NATIVE_APP", "WEBVIEW_1"]}, selected_context_index=0, selected_context_type="webview"
    )
    driver = _FakeDriver()
    out = execute_real_driver_switch_with_ref(
        context_ref=ref,
        get_current_context=lambda: driver.current_context,
        switch_context=driver.switch_to.context,
        restore_context=driver.restore,
        explicit_opt_in=True,
    )
    assert out["switch_status"] == "switched"
    assert out["restore_status"] == "restored"
    assert driver.calls == [("switch", "WEBVIEW_1"), ("restore", "NATIVE_APP")]


def test_execute_real_driver_switch_fake_switch_failure_sanitized():
    ref = resolve_real_webview_context_ref(
        context_inventory={"contexts": ["NATIVE_APP", "WEBVIEW_secret"]}, selected_context_index=0, selected_context_type="webview"
    )
    driver = _FakeDriver(contexts=["NATIVE_APP", "WEBVIEW_secret"], fail_switch=True)
    out = execute_real_driver_switch_with_ref(
        context_ref=ref,
        get_current_context=lambda: driver.current_context,
        switch_context=driver.switch_to.context,
        restore_context=driver.restore,
        explicit_opt_in=True,
    )
    assert out["switch_status"] == "failed"
    assert out["restore_attempted"] is False
    assert "WEBVIEW_secret" not in str(out)


def test_execute_real_driver_switch_fake_restore_failure_fail_closed():
    ref = resolve_real_webview_context_ref(
        context_inventory={"contexts": ["NATIVE_APP", "WEBVIEW_1"]}, selected_context_index=0, selected_context_type="webview"
    )
    driver = _FakeDriver(fail_restore=True)
    out = execute_real_driver_switch_with_ref(
        context_ref=ref,
        get_current_context=lambda: driver.current_context,
        switch_context=driver.switch_to.context,
        restore_context=driver.restore,
        explicit_opt_in=True,
    )
    assert out["switch_status"] == "switched"
    assert out["restore_status"] == "failed"


def test_execute_real_driver_switch_operation_failure_still_restores():
    ref = resolve_real_webview_context_ref(
        context_inventory={"contexts": ["NATIVE_APP", "WEBVIEW_1"]}, selected_context_index=0, selected_context_type="webview"
    )
    driver = _FakeDriver()
    out = execute_real_driver_switch_with_ref(
        context_ref=ref,
        get_current_context=lambda: driver.current_context,
        switch_context=driver.switch_to.context,
        restore_context=driver.restore,
        operation_callable=lambda: (_ for _ in ()).throw(RuntimeError("boom WEBVIEW_secret")),
        explicit_opt_in=True,
    )
    assert out["switch_status"] == "failed"
    assert out["restore_status"] == "restored"
    assert driver.calls == [("switch", "WEBVIEW_1"), ("restore", "NATIVE_APP")]


def test_execute_real_driver_switch_operation_success_runs_after_switch():
    ref = resolve_real_webview_context_ref(
        context_inventory={"contexts": ["NATIVE_APP", "WEBVIEW_1"]}, selected_context_index=0, selected_context_type="webview"
    )
    driver = _FakeDriver()
    flag = {"ran": False}
    out = execute_real_driver_switch_with_ref(
        context_ref=ref,
        get_current_context=lambda: driver.current_context,
        switch_context=driver.switch_to.context,
        restore_context=driver.restore,
        operation_callable=lambda: flag.__setitem__("ran", True),
        explicit_opt_in=True,
    )
    assert out["switch_status"] == "switched"
    assert flag["ran"] is True


def test_execute_real_driver_switch_stale_context_ref_fails_safely():
    ref = RealWebViewContextRef(safe_metadata={"status": "resolved"}, _raw_context_name="WEBVIEW_gone")
    driver = _FakeDriver(contexts=["NATIVE_APP", "WEBVIEW_1"])
    out = execute_real_driver_switch_with_ref(
        context_ref=ref,
        get_current_context=lambda: driver.current_context,
        switch_context=driver.switch_to.context,
        restore_context=driver.restore,
        explicit_opt_in=True,
    )
    assert out["switch_status"] == "failed"
    assert out["reason"] == "execution_error"


def test_execute_real_driver_switch_missing_raw_ref_blocks():
    ref = RealWebViewContextRef(safe_metadata={"status": "blocked"})
    out = execute_real_driver_switch_with_ref(
        context_ref=ref,
        get_current_context=lambda: "NATIVE_APP",
        switch_context=lambda _name: None,
        restore_context=lambda _name: None,
        explicit_opt_in=True,
    )
    assert out["switch_status"] == "blocked"
    assert out["reason"] == "internal_context_ref_missing"


def test_execute_real_driver_switch_opt_in_false_blocks():
    ref = RealWebViewContextRef(safe_metadata={"status": "resolved"}, _raw_context_name="WEBVIEW_1")
    out = execute_real_driver_switch_with_ref(
        context_ref=ref,
        get_current_context=lambda: "NATIVE_APP",
        switch_context=lambda _name: None,
        restore_context=lambda _name: None,
        explicit_opt_in=False,
    )
    assert out["switch_enabled"] is False
    assert out["switch_status"] == "blocked"
    assert out["reason"] == "opt_in_required"
