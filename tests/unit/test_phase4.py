"""
tests/unit/test_phase4.py
=========================
Phase 4 unit tests — Android Appium adapter.

All tests use a mock Appium driver — no real device or Appium server required.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Shared XML fixture
# ---------------------------------------------------------------------------

_SIMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <android.widget.FrameLayout bounds="[0,0][1080,1920]">
    <android.widget.LinearLayout bounds="[0,0][1080,1920]">
      <android.widget.Button text="Login" content-desc="Login button"
          resource-id="com.example:id/login_btn" bounds="[240,800][840,960]"
          clickable="true" enabled="true"/>
      <android.widget.EditText text="" content-desc="Email input"
          resource-id="com.example:id/email_field" bounds="[60,600][1020,740]"
          clickable="true" enabled="true"/>
      <android.widget.TextView text="Welcome to MyApp"
          resource-id="com.example:id/welcome_text" bounds="[60,100][1020,200]"/>
    </android.widget.LinearLayout>
  </android.widget.FrameLayout>
</hierarchy>"""

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

# Canonical ref string used by AppiumHierarchyResolver
_LOGIN_REF = json.dumps({"by": "xpath", "value": "//android.widget.Button[@text='Login']"})


def _make_driver(activity=".MainActivity", page_source=_SIMPLE_XML):
    """Return a MagicMock resembling an Appium WebDriver."""
    driver = MagicMock()
    driver.current_activity = activity
    driver.page_source = page_source
    driver.get_screenshot_as_png.return_value = _PNG_BYTES
    driver.capabilities = {"platformName": "Android", "appPackage": "com.example"}

    element = MagicMock()
    element.id = "el1"
    element.location = {"x": 240, "y": 800}
    element.size = {"width": 600, "height": 160}
    element.is_displayed.return_value = True
    driver.find_element.return_value = element
    driver.find_elements.return_value = [element]
    return driver, element


def _run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ===========================================================================
# AppiumAdapter — collect_context
# ===========================================================================

class TestAppiumAdapterCollectContext:

    def test_collect_context_returns_hierarchy_xml(self):
        driver, _ = _make_driver()
        from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
        from bubblegum.core.schemas import ContextRequest
        adapter = AppiumAdapter(driver)
        ctx = _run_async(adapter.collect_context(ContextRequest(include_screenshot=False, include_hierarchy=True)))
        assert ctx.hierarchy_xml == _SIMPLE_XML

    def test_collect_context_screenshot_when_requested(self):
        driver, _ = _make_driver()
        from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
        from bubblegum.core.schemas import ContextRequest
        adapter = AppiumAdapter(driver)
        ctx = _run_async(adapter.collect_context(ContextRequest(include_screenshot=True)))
        assert ctx.screenshot == _PNG_BYTES
        driver.get_screenshot_as_png.assert_called_once()

    def test_collect_context_no_screenshot_when_not_requested(self):
        driver, _ = _make_driver()
        from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
        from bubblegum.core.schemas import ContextRequest
        adapter = AppiumAdapter(driver)
        ctx = _run_async(adapter.collect_context(ContextRequest(include_screenshot=False)))
        assert ctx.screenshot is None
        driver.get_screenshot_as_png.assert_not_called()

    def test_collect_context_screen_signature_is_32_char_hex(self):
        driver, _ = _make_driver()
        from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
        from bubblegum.core.schemas import ContextRequest
        adapter = AppiumAdapter(driver)
        ctx = _run_async(adapter.collect_context(ContextRequest(include_screenshot=False)))
        assert isinstance(ctx.screen_signature, str)
        assert len(ctx.screen_signature) == 32
        int(ctx.screen_signature, 16)  # must be valid hex

    def test_collect_context_signature_stable_for_same_inputs(self):
        driver, _ = _make_driver()
        from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
        from bubblegum.core.schemas import ContextRequest
        adapter = AppiumAdapter(driver)
        req = ContextRequest(include_screenshot=False)
        ctx1 = _run_async(adapter.collect_context(req))
        ctx2 = _run_async(adapter.collect_context(req))
        assert ctx1.screen_signature == ctx2.screen_signature

    def test_collect_context_handles_page_source_failure(self):
        driver, _ = _make_driver()
        type(driver).page_source = PropertyMock(side_effect=Exception("session lost"))
        from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
        from bubblegum.core.schemas import ContextRequest
        adapter = AppiumAdapter(driver)
        ctx = _run_async(adapter.collect_context(ContextRequest(include_screenshot=False)))
        assert ctx.hierarchy_xml is None


# ===========================================================================
# AppiumAdapter — execute
# ===========================================================================

class TestAppiumAdapterExecute:

    def _run(self, action_type, input_value=None, ref=None):
        driver, element = _make_driver()
        from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
        from bubblegum.core.schemas import ActionPlan, ExecutionOptions, ResolvedTarget

        if ref is None:
            ref = _LOGIN_REF

        adapter = AppiumAdapter(driver)
        plan = ActionPlan(
            action_type=action_type,
            target_hint="Login",
            input_value=input_value,
            options=ExecutionOptions(),
        )
        target = ResolvedTarget(ref=ref, confidence=0.92, resolver_name="appium_hierarchy")
        result = _run_async(adapter.execute(plan, target))
        return result, element, driver

    def test_execute_tap_calls_click(self):
        result, element, _ = self._run("tap")
        assert result.success is True
        element.click.assert_called_once()

    def test_execute_click_alias_calls_click(self):
        result, element, _ = self._run("click")
        assert result.success is True
        element.click.assert_called_once()

    def test_execute_type_calls_send_keys(self):
        result, element, _ = self._run("type", input_value="hello@example.com")
        assert result.success is True
        element.send_keys.assert_called_once_with("hello@example.com")

    def test_execute_type_empty_value(self):
        result, element, _ = self._run("type", input_value=None)
        assert result.success is True
        element.send_keys.assert_called_once_with("")

    def test_execute_scroll_does_not_raise(self):
        result, _, _ = self._run("scroll")
        assert result.success is True

    def test_execute_swipe_does_not_raise(self):
        result, _, _ = self._run("swipe", input_value="up")
        assert result.success is True

    def test_execute_unsupported_action_type_returns_success(self):
        driver, _ = _make_driver()
        from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
        from bubblegum.core.schemas import ActionPlan, ExecutionOptions, ResolvedTarget

        adapter = AppiumAdapter(driver)
        plan = ActionPlan(action_type="verify", target_hint="", options=ExecutionOptions())
        target = ResolvedTarget(ref=_LOGIN_REF, confidence=0.9, resolver_name="appium_hierarchy")
        result = _run_async(adapter.execute(plan, target))
        assert result.success is True

    def test_execute_returns_failure_on_driver_exception(self):
        driver, _ = _make_driver()
        driver.find_element.side_effect = Exception("NoSuchElementException")
        from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
        from bubblegum.core.schemas import ActionPlan, ExecutionOptions, ResolvedTarget

        bad_ref = json.dumps({"by": "xpath", "value": "//does.not.Exist"})
        adapter = AppiumAdapter(driver)
        plan = ActionPlan(action_type="tap", target_hint="X", options=ExecutionOptions())
        target = ResolvedTarget(ref=bad_ref, confidence=0.5, resolver_name="appium_hierarchy")
        result = _run_async(adapter.execute(plan, target))
        assert result.success is False
        assert result.error is not None  # driver raised, error captured

    def test_execute_duration_ms_is_non_negative_int(self):
        result, _, _ = self._run("tap")
        assert isinstance(result.duration_ms, int)
        assert result.duration_ms >= 0

    def test_execute_element_ref_in_result(self):
        result, _, _ = self._run("tap", ref=_LOGIN_REF)
        assert result.element_ref == _LOGIN_REF


# ===========================================================================
# AppiumAdapter — screenshot
# ===========================================================================

class TestAppiumAdapterScreenshot:

    def test_screenshot_saves_file_and_returns_artifact_ref(self, tmp_path, monkeypatch):
        driver, _ = _make_driver()
        monkeypatch.chdir(tmp_path)
        from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
        adapter = AppiumAdapter(driver)
        ref = _run_async(adapter.screenshot())
        assert ref.type == "screenshot"
        assert Path(ref.path).exists()
        assert Path(ref.path).read_bytes() == _PNG_BYTES


# ===========================================================================
# AppiumAdapter — validate
# ===========================================================================

class TestAppiumAdapterValidate:

    def _make_adapter(self, source=_SIMPLE_XML):
        driver, element = _make_driver(page_source=source)
        from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
        return AppiumAdapter(driver), driver, element

    def test_validate_text_visible_passes_when_text_in_source(self):
        adapter, _, _ = self._make_adapter()
        from bubblegum.core.schemas import ValidationPlan
        plan = ValidationPlan(assertion_type="text_visible", expected_value="Welcome to MyApp")
        result = _run_async(adapter.validate(plan))
        assert result.passed is True

    def test_validate_text_visible_fails_when_text_absent(self):
        adapter, _, _ = self._make_adapter()
        from bubblegum.core.schemas import ValidationPlan
        plan = ValidationPlan(assertion_type="text_visible", expected_value="NotPresentXYZ")
        result = _run_async(adapter.validate(plan))
        assert result.passed is False

    def test_validate_element_state_passes_when_displayed(self):
        adapter, driver, element = self._make_adapter()
        element.is_displayed.return_value = True
        # Patch the import inside validate so selenium isn't needed
        import sys
        from unittest.mock import patch, MagicMock
        mock_appium_by = MagicMock()
        mock_appium_by.AppiumBy.XPATH = "xpath"
        with patch.dict(sys.modules, {"appium.webdriver.common.appiumby": mock_appium_by}):
            from bubblegum.core.schemas import ValidationPlan
            plan = ValidationPlan(
                assertion_type="element_state",
                expected_value="//android.widget.Button[@text='Login']",
            )
            result = _run_async(adapter.validate(plan))
        assert result.passed is True

    def test_validate_element_state_fails_when_not_displayed(self):
        adapter, driver, element = self._make_adapter()
        element.is_displayed.return_value = False
        import sys
        from unittest.mock import patch, MagicMock
        mock_appium_by = MagicMock()
        mock_appium_by.AppiumBy.XPATH = "xpath"
        with patch.dict(sys.modules, {"appium.webdriver.common.appiumby": mock_appium_by}):
            from bubblegum.core.schemas import ValidationPlan
            plan = ValidationPlan(
                assertion_type="element_state",
                expected_value="//android.widget.Button[@text='Nonexistent']",
            )
            result = _run_async(adapter.validate(plan))
        assert result.passed is False

    def test_validate_activity_passes_when_activity_matches(self):
        adapter, _, _ = self._make_adapter()
        from bubblegum.core.schemas import ValidationPlan
        plan = ValidationPlan(assertion_type="activity", expected_value="MainActivity")
        result = _run_async(adapter.validate(plan))
        assert result.passed is True

    def test_validate_activity_fails_when_activity_differs(self):
        adapter, _, _ = self._make_adapter()
        from bubblegum.core.schemas import ValidationPlan
        plan = ValidationPlan(assertion_type="activity", expected_value="SettingsActivity")
        result = _run_async(adapter.validate(plan))
        assert result.passed is False

    def test_validate_unknown_assertion_type_returns_failed(self):
        adapter, _, _ = self._make_adapter()
        from bubblegum.core.schemas import ValidationPlan
        plan = ValidationPlan(assertion_type="page_transition", expected_value="something")
        result = _run_async(adapter.validate(plan))
        assert result.passed is False


# ===========================================================================
# AppiumAdapter — platform detection
# ===========================================================================

class TestAppiumAdapterPlatformDetection:

    def test_platform_set_to_android_from_capabilities(self):
        driver, _ = _make_driver()
        driver.capabilities = {"platformName": "Android"}
        from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
        assert AppiumAdapter(driver).platform == "android"

    def test_platform_set_to_ios_from_capabilities(self):
        driver, _ = _make_driver()
        driver.capabilities = {"platformName": "iOS"}
        from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
        assert AppiumAdapter(driver).platform == "ios"

    def test_platform_defaults_to_android_on_missing_caps(self):
        driver, _ = _make_driver()
        driver.capabilities = {}
        from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
        assert AppiumAdapter(driver).platform == "android"

    def test_channel_attribute_is_mobile(self):
        driver, _ = _make_driver()
        from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
        assert AppiumAdapter(driver).channel == "mobile"


# ===========================================================================
# AppiumHierarchyResolver — metadata
# ===========================================================================

class TestAppiumHierarchyResolverMetadata:

    def _r(self):
        from bubblegum.core.grounding.resolvers.appium_hierarchy import AppiumHierarchyResolver
        return AppiumHierarchyResolver()

    def test_resolver_name(self):
        assert self._r().name == "appium_hierarchy"

    def test_priority_is_20(self):
        assert self._r().priority == 20

    def test_channel_is_mobile_only(self):
        r = self._r()
        assert r.channels == ["mobile"]
        assert "web" not in r.channels

    def test_cost_level_is_low(self):
        assert self._r().cost_level == "low"

    def test_tier_is_1(self):
        assert self._r().tier == 1

    def test_required_context_is_empty(self):
        """required_context() is empty so can_run() succeeds for all mobile intents.
        Missing hierarchy_xml is handled gracefully inside resolve() instead."""
        assert self._r().required_context() == []


# ===========================================================================
# AppiumHierarchyResolver — can_run
# ===========================================================================

class TestAppiumHierarchyResolverCanRun:

    def _intent(self, channel="mobile", context_override=None, action_type="tap"):
        from bubblegum.core.schemas import ExecutionOptions, StepIntent
        ctx = {"hierarchy_xml": _SIMPLE_XML} if context_override is None else context_override
        return StepIntent(
            instruction="Login",
            channel=channel,
            action_type=action_type,
            context=ctx,
            options=ExecutionOptions(),
        )

    def test_can_run_true_for_mobile_with_hierarchy_xml(self):
        from bubblegum.core.grounding.resolvers.appium_hierarchy import AppiumHierarchyResolver
        assert AppiumHierarchyResolver().can_run(self._intent(channel="mobile")) is True

    def test_can_run_false_for_web_channel(self):
        from bubblegum.core.grounding.resolvers.appium_hierarchy import AppiumHierarchyResolver
        assert AppiumHierarchyResolver().can_run(self._intent(channel="web")) is False

    def test_can_run_true_even_without_hierarchy_xml(self):
        """resolve() handles missing xml gracefully; can_run() stays True so
        the resolver appears in the eligible list for all mobile intents."""
        from bubblegum.core.grounding.resolvers.appium_hierarchy import AppiumHierarchyResolver
        # Pass an empty dict — no hierarchy_xml key
        assert AppiumHierarchyResolver().can_run(self._intent(context_override={})) is True


# ===========================================================================
# AppiumHierarchyResolver — text match
# ===========================================================================

class TestAppiumHierarchyResolverTextMatch:

    def _resolve(self, instruction, xml=_SIMPLE_XML, action_type="tap"):
        from bubblegum.core.grounding.resolvers.appium_hierarchy import AppiumHierarchyResolver
        from bubblegum.core.schemas import ExecutionOptions, StepIntent
        r = AppiumHierarchyResolver()
        intent = StepIntent(
            instruction=instruction,
            channel="mobile",
            action_type=action_type,
            context={"hierarchy_xml": xml},
            options=ExecutionOptions(),
        )
        return r.resolve(intent)

    def test_text_match_returns_candidate(self):
        candidates = self._resolve("Login")
        text_matches = [c for c in candidates if c.metadata.get("matched_attr") == "text"]
        assert text_matches, "Expected at least one text-attr match"
        assert text_matches[0].confidence == 0.92

    def test_text_match_ref_is_xpath_json_string(self):
        candidates = self._resolve("Login")
        text_matches = [c for c in candidates if c.metadata.get("matched_attr") == "text"]
        ref_parsed = json.loads(text_matches[0].ref)
        assert ref_parsed["by"] == "xpath"
        assert "Login" in ref_parsed["value"]
        assert ref_parsed["value"].startswith("//")

    def test_text_match_resolver_name_is_appium_hierarchy(self):
        candidates = self._resolve("Login")
        text_matches = [c for c in candidates if c.metadata.get("matched_attr") == "text"]
        assert text_matches[0].resolver_name == "appium_hierarchy"

    def test_text_match_case_insensitive(self):
        candidates = self._resolve("login")
        text_matches = [c for c in candidates if c.metadata.get("matched_attr") == "text"]
        assert text_matches, "Case-insensitive match should find 'Login'"

    def test_no_match_returns_empty_list(self):
        assert self._resolve("ThisButtonDoesNotExistXYZ123") == []

    def test_unparseable_xml_returns_empty_list(self):
        assert self._resolve("Login", xml="<not valid xml <<") == []

    def test_empty_hierarchy_xml_returns_empty_list(self):
        assert self._resolve("Login", xml="") == []


# ===========================================================================
# AppiumHierarchyResolver — content-desc match
# ===========================================================================

class TestAppiumHierarchyResolverContentDescMatch:

    def _resolve(self, instruction, xml=_SIMPLE_XML):
        from bubblegum.core.grounding.resolvers.appium_hierarchy import AppiumHierarchyResolver
        from bubblegum.core.schemas import ExecutionOptions, StepIntent
        r = AppiumHierarchyResolver()
        intent = StepIntent(
            instruction=instruction,
            channel="mobile",
            action_type="tap",
            context={"hierarchy_xml": xml},
            options=ExecutionOptions(),
        )
        return r.resolve(intent)

    def test_content_desc_match_returns_confidence_0_85(self):
        # Strip text="" so the text branch is skipped and content-desc is matched instead.
        # content-desc="Login button" → "login button" in "login button" ✅
        xml_no_text = _SIMPLE_XML.replace('text="Login"', 'text=""')
        candidates = self._resolve("Login button", xml=xml_no_text)
        c_desc_matches = [c for c in candidates if c.metadata.get("matched_attr") == "content-desc"]
        assert c_desc_matches, f"Expected content-desc match. Got: {[c.metadata for c in candidates]}"
        assert c_desc_matches[0].confidence == 0.85

    def test_content_desc_match_ref_is_valid_xpath_json(self):
        xml_no_text = _SIMPLE_XML.replace('text="Login"', 'text=""')
        candidates = self._resolve("Login button", xml=xml_no_text)
        c_desc_matches = [c for c in candidates if c.metadata.get("matched_attr") == "content-desc"]
        if c_desc_matches:
            ref_parsed = json.loads(c_desc_matches[0].ref)
            assert ref_parsed["by"] == "xpath"
            assert "content-desc" in ref_parsed["value"]


# ===========================================================================
# AppiumHierarchyResolver — resource-id match
# ===========================================================================

class TestAppiumHierarchyResolverResourceIdMatch:

    def _resolve(self, instruction, xml=_SIMPLE_XML):
        from bubblegum.core.grounding.resolvers.appium_hierarchy import AppiumHierarchyResolver
        from bubblegum.core.schemas import ExecutionOptions, StepIntent
        r = AppiumHierarchyResolver()
        intent = StepIntent(
            instruction=instruction,
            channel="mobile",
            action_type="tap",
            context={"hierarchy_xml": xml},
            options=ExecutionOptions(),
        )
        return r.resolve(intent)

    def test_resource_id_partial_match_strips_package_prefix(self):
        # Strip content-desc so only resource-id matches "email_field"
        xml_stripped = _SIMPLE_XML.replace(
            'content-desc="Email input"', 'content-desc=""'
        ).replace('text="Welcome to MyApp"', 'text=""')
        candidates = self._resolve("email_field", xml=xml_stripped)
        id_matches = [c for c in candidates if c.metadata.get("matched_attr") == "resource-id"]
        assert id_matches, "Should match resource-id by stripped id part"
        assert id_matches[0].confidence == 0.75

    def test_resource_id_ref_contains_resource_id_attr_in_xpath(self):
        xml_stripped = _SIMPLE_XML.replace('content-desc="Email input"', 'content-desc=""')
        candidates = self._resolve("email_field", xml=xml_stripped)
        id_matches = [c for c in candidates if c.metadata.get("matched_attr") == "resource-id"]
        if id_matches:
            ref_parsed = json.loads(id_matches[0].ref)
            assert "resource-id" in ref_parsed["value"]


# ===========================================================================
# AppiumHierarchyResolver — multiple matches
# ===========================================================================

class TestAppiumHierarchyResolverMultipleMatches:

    def test_multiple_elements_with_same_text_return_multiple_candidates(self):
        xml_dupes = """<?xml version="1.0"?>
<hierarchy>
  <android.widget.LinearLayout>
    <android.widget.Button text="Save" resource-id="com.ex:id/save1"/>
    <android.widget.Button text="Save" resource-id="com.ex:id/save2"/>
  </android.widget.LinearLayout>
</hierarchy>"""
        from bubblegum.core.grounding.resolvers.appium_hierarchy import AppiumHierarchyResolver
        from bubblegum.core.schemas import ExecutionOptions, StepIntent

        r = AppiumHierarchyResolver()
        intent = StepIntent(
            instruction="Save",
            channel="mobile",
            action_type="tap",
            context={"hierarchy_xml": xml_dupes},
            options=ExecutionOptions(),
        )
        candidates = r.resolve(intent)
        text_matches = [c for c in candidates if c.metadata.get("matched_attr") == "text"]
        assert len(text_matches) == 2


# ===========================================================================
# AppiumHierarchyResolver — signal scoring (Phase 6G)
# ===========================================================================

class TestAppiumHierarchyResolverSignalsPhase6G:

    def _resolve(self, instruction, xml, action_type):
        from bubblegum.core.grounding.resolvers.appium_hierarchy import AppiumHierarchyResolver
        from bubblegum.core.schemas import ExecutionOptions, StepIntent
        r = AppiumHierarchyResolver()
        intent = StepIntent(
            instruction=instruction,
            channel="mobile",
            action_type=action_type,
            context={"hierarchy_xml": xml},
            options=ExecutionOptions(),
        )
        return r.resolve(intent)

    def test_role_match_uses_class_for_node_button_tap(self):
        xml = """<hierarchy>
  <node class="android.widget.Button" text="Sign In" content-desc="sign_in_button"/>
</hierarchy>"""
        candidates = self._resolve("Tap Sign In", xml, "tap")
        text_matches = [c for c in candidates if c.metadata.get("matched_attr") == "text"]
        assert text_matches
        assert text_matches[0].metadata["signals"]["role_match"] == 1.0

    def test_role_match_uses_class_for_node_edittext_type(self):
        xml = """<hierarchy>
  <node class="android.widget.EditText" text="" content-desc="Email input"/>
</hierarchy>"""
        candidates = self._resolve("Type into Email input", xml, "type")
        c_desc_matches = [c for c in candidates if c.metadata.get("matched_attr") == "content-desc"]
        assert c_desc_matches
        assert c_desc_matches[0].metadata["signals"]["role_match"] == 1.0

    def test_role_match_for_verify_textview_is_stronger_than_generic(self):
        xml = """<hierarchy>
  <node class="android.widget.TextView" text="Order Confirmed"/>
</hierarchy>"""
        candidates = self._resolve("Verify text Order Confirmed", xml, "verify")
        text_matches = [c for c in candidates if c.metadata.get("matched_attr") == "text"]
        assert text_matches
        assert text_matches[0].metadata["signals"]["role_match"] > 0.5

    def test_visibility_without_bounds_defaults_to_0_8_for_present_node(self):
        xml = """<hierarchy>
  <node class="android.widget.Button" text="Sign In"/>
</hierarchy>"""
        candidates = self._resolve("Tap Sign In", xml, "tap")
        text_matches = [c for c in candidates if c.metadata.get("matched_attr") == "text"]
        assert text_matches
        assert text_matches[0].metadata["signals"]["visibility"] == 0.8

    def test_visibility_reduced_when_explicitly_disabled(self):
        xml = """<hierarchy>
  <node class="android.widget.Button" text="Sign In" enabled="false"/>
</hierarchy>"""
        candidates = self._resolve("Tap Sign In", xml, "tap")
        text_matches = [c for c in candidates if c.metadata.get("matched_attr") == "text"]
        assert text_matches
        assert text_matches[0].metadata["signals"]["visibility"] == 0.2


# ===========================================================================
# XPath builder
# ===========================================================================

class TestXPathBuilder:

    def test_simple_value_no_quotes(self):
        from bubblegum.core.grounding.resolvers.appium_hierarchy import _build_xpath
        assert _build_xpath("android.widget.Button", "text", "Login") == \
               "//android.widget.Button[@text='Login']"

    def test_value_with_single_quote_uses_concat(self):
        from bubblegum.core.grounding.resolvers.appium_hierarchy import _build_xpath
        result = _build_xpath("android.widget.TextView", "text", "Don't press")
        assert "concat" in result
        assert "Don" in result

    def test_empty_tag_uses_wildcard(self):
        from bubblegum.core.grounding.resolvers.appium_hierarchy import _build_xpath
        assert _build_xpath("", "text", "Login").startswith("//*")


# ===========================================================================
# SDK mobile channel routing
# ===========================================================================

class TestSDKMobileChannelRouting:

    def test_get_adapter_mobile_returns_appium_adapter(self):
        driver, _ = _make_driver()
        from bubblegum.core.sdk import _get_adapter
        from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
        assert isinstance(_get_adapter("mobile", driver=driver), AppiumAdapter)

    def test_get_adapter_mobile_without_driver_raises_value_error(self):
        from bubblegum.core.sdk import _get_adapter
        with pytest.raises(ValueError, match="driver="):
            _get_adapter("mobile", driver=None)

    def test_get_adapter_web_still_works_with_mock_page(self):
        from bubblegum.core.sdk import _get_adapter
        from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter
        assert isinstance(_get_adapter("web", page=MagicMock()), PlaywrightAdapter)

    def test_get_adapter_unknown_channel_raises_not_implemented(self):
        from bubblegum.core.sdk import _get_adapter
        with pytest.raises(NotImplementedError):
            _get_adapter("fax", page=MagicMock())

    def test_act_accepts_driver_kwarg(self):
        import inspect
        from bubblegum.core import sdk as sdk_module
        assert "driver" in inspect.signature(sdk_module.act).parameters

    def test_recover_accepts_driver_kwarg(self):
        import inspect
        from bubblegum.core import sdk as sdk_module
        assert "driver" in inspect.signature(sdk_module.recover).parameters

    def test_verify_accepts_driver_kwarg(self):
        import inspect
        from bubblegum.core import sdk as sdk_module
        assert "driver" in inspect.signature(sdk_module.verify).parameters

    def test_extract_accepts_driver_kwarg(self):
        import inspect
        from bubblegum.core import sdk as sdk_module
        assert "driver" in inspect.signature(sdk_module.extract).parameters
