"""Unit tests for the smart-tests TypeScript emitter (flow + test) and scaffold."""

from __future__ import annotations

from bubblegum.convert.emitters.ts_smart import (
    _fn_name,
    emit_flow_file,
    emit_test_file,
)
from bubblegum.convert.models import RawScenario
from bubblegum.convert.normalize import build_features
from bubblegum.convert.scaffold import scaffold_harness


def _feature(steps: str = None, **fields):
    raw = RawScenario(
        row=1,
        steps_text=steps
        or (
            'Given I am logged in as a "Shopper"\n'
            "And I open the Checkout page\n"
            'When I enter "SAVE10" into the Coupon code field\n'
            "And I click the Apply button\n"
            "Then I see the Discount applied message"
        ),
        fields={
            "feature": fields.get("feature", "[F][Web] Checkout"),
            "title": fields.get("title", "Verify a valid coupon applies a discount"),
            "persona": fields.get("persona", "Shopper"),
            "jira": fields.get("jira", "PROJ-1"),
        },
    )
    return build_features([raw])[0]


def _fns(feature):
    used = set()
    return [_fn_name(s.title, used) for s in feature.scenarios]


def test_fn_name_camelcase_drops_verify_and_unique():
    used = set()
    a = _fn_name("Verify a valid coupon applies a discount", used)
    b = _fn_name("Verify a valid coupon applies a discount", used)
    assert a == "aValidCouponAppliesADiscount"
    assert b == "aValidCouponAppliesADiscount2"  # disambiguated


def _no_data_profile():
    from dataclasses import replace
    from bubblegum.convert.profile import ConvertProfile

    p = ConvertProfile()
    p.output = replace(p.output, extract_data=False)
    return p


def test_flow_file_shape():
    feat = _feature()
    text = emit_flow_file(feat, _fns(feat), _no_data_profile())
    assert "import { act, verify, observe } from '../helpers/actions';" in text
    assert "export async function aValidCouponAppliesADiscount(engine: Bubblegum, page: Page)" in text
    # AUTO action step
    assert "await act(engine, 'Enter \"SAVE10\" into the Coupon code field');" in text
    # AUTO then step → verify with leading 'see' stripped
    assert "await verify(engine, 'The Discount applied message');" in text
    # login precondition is NOT repeated in the flow (handled in the test)
    assert "handled by loginFlow" in text
    # navigation step gets the wait pattern
    assert "await page.waitForLoadState('domcontentloaded');" in text


def test_data_extraction_lifts_static_literals():
    feat = _feature(
        steps=(
            "Given I open the Transfer page\n"
            'When I select "Savings" from the From account dropdown\n'
            'And I enter "150.00" into the Amount field\n'
            "And I click the Continue button\n"
            "Then I see Done"
        ),
        title="Transfer money",
    )
    from bubblegum.convert.emitters.ts_smart import emit_data_file

    fns = _fns(feat)
    flow = emit_flow_file(feat, fns)
    data = emit_data_file(feat, fns)
    # data file has one object with camelCase field keys
    assert "export const transferMoneyData = {" in data
    assert "fromAccount: 'Savings'," in data
    assert "amount: '150.00'," in data
    # flow interpolates via backticks and imports the object
    assert "from '../data/" in flow
    assert "await act(engine, `Select \"${transferMoneyData.fromAccount}\" from the From account dropdown`);" in flow
    # a button label is NOT extracted
    assert "await act(engine, 'Click the Continue button');" in flow


def test_template_value_not_extracted():
    feat = _feature(
        steps='When I enter "N-{{timestamp|%Y%m%d as v}}" into the Name field\nThen I see Done',
        title="Dyn",
    )
    from bubblegum.convert.emitters.ts_smart import emit_data_file

    fns = _fns(feat)
    assert emit_data_file(feat, fns) is None  # nothing static to extract
    assert "await engine.act('Enter \"N-{{timestamp|%Y%m%d as v}}\" into the Name field');" in emit_flow_file(feat, fns)


def test_flow_file_todo_for_needs_data():
    feat = _feature(
        steps="Given I open the Cart page\nAnd the cart has 2 items\nWhen I click Remove",
        title="Remove item",
    )
    text = emit_flow_file(feat, _fns(feat))
    assert "// TODO (NEEDS_DATA):" in text
    assert "// await act(engine, 'The cart has 2 items');" in text


def test_test_file_composes_flows_and_login():
    feat = _feature()
    fns = _fns(feat)
    text = emit_test_file(feat, fns)
    assert "import { initEngine, teardownEngine" in text
    assert "import { generateReports } from '../helpers/reporter';" in text
    assert "import { loginFlow } from '../flows/login.flow';" in text
    assert f"import {{ {fns[0]} }} from '../flows/checkout.flow';" in text
    assert "await loginFlow(engine, page, credentials);" in text
    # each scenario is registered as a labeled test method and run in a loop
    assert f"['Verify a valid coupon applies a discount', {fns[0]}]," in text
    assert "for (const [name, testFn] of tests)" in text
    assert "await testFn(engine, page);" in text
    assert "await generateReports(ctx.engine" in text
    assert "main();" in text


def test_test_file_has_one_method_per_scenario():
    # A two-scenario "workbook" bundle → one test file with two test methods.
    raws = [
        RawScenario(row=1, steps_text="Given I open A\nThen I see B",
                    fields={"feature": "[F][Web] Wb", "title": "First case"}),
        RawScenario(row=2, steps_text="Given I open C\nThen I see D",
                    fields={"feature": "[F][Web] Wb", "title": "Second case"}),
    ]
    feat = build_features(raws)[0]
    fns = _fns(feat)
    text = emit_test_file(feat, fns)
    assert "'First case'," in text
    assert "'Second case'," in text
    assert text.count("], ") + text.count("],\n") >= 2


def test_test_file_omits_login_when_no_precondition():
    feat = _feature(
        steps="Given I open the Home page\nThen I see the Welcome banner",
        title="Home banner",
    )
    text = emit_test_file(feat, _fns(feat))
    assert "loginFlow" not in text
    assert "credentials" not in text


def _profile(**convert):
    from bubblegum.convert.profile import ConvertProfile

    return ConvertProfile.from_dict({"convert": convert})


def test_navigation_mapping_menu_uses_observe_and_action():
    feat = _feature(steps="Given I open the Accounts page\nThen I see the Balance", title="Nav")
    profile = _profile(navigation={"Accounts": {"type": "menu", "action": "Click the Accounts menu"}})
    text = emit_flow_file(feat, _fns(feat), profile)
    assert "await observe(engine, 'the Accounts menu');" in text
    assert "await act(engine, 'Click the Accounts menu');" in text
    assert "await page.waitForLoadState('domcontentloaded');" in text


def test_navigation_mapping_url_uses_goto():
    feat = _feature(steps="Given I open the Bill payment page\nThen I see X", title="Nav url")
    profile = _profile(navigation={"Bill payment": {"type": "url", "path": "/bill-payment"}})
    text = emit_flow_file(feat, _fns(feat), profile)
    assert "await page.goto('/bill-payment');" in text


def test_template_expression_bypasses_wrapper():
    feat = _feature(
        steps='When I enter "N-{{timestamp|%Y%m%d as v}}" into the Name field\nThen in the row where Name is "{{$v}}" Status is "OK"',
        title="Dynamic",
    )
    text = emit_flow_file(feat, _fns(feat))
    # template act uses engine.act directly (wrapper can't process {{...}})
    assert "await engine.act('Enter \"N-{{timestamp|%Y%m%d as v}}\" into the Name field');" in text
    # template verify uses engine.verify directly
    assert "await engine.verify('In the row where Name is \"{{$v}}\" Status is \"OK\"');" in text


def test_plain_step_uses_wrapper_not_engine_direct():
    feat = _feature(steps="When I click the Save button\nThen I see Done", title="Plain")
    text = emit_flow_file(feat, _fns(feat))
    assert "await act(engine, 'Click the Save button');" in text
    assert "engine.act(" not in text


def test_custom_pattern_injects_literal_code():
    feat = _feature(steps="When I refresh the page\nThen I see X", title="Custom")
    profile = _profile(custom_patterns=[
        {"pattern": "I refresh the page", "code": "await page.reload({ waitUntil: 'networkidle' });"}
    ])
    text = emit_flow_file(feat, _fns(feat), profile)
    assert "await page.reload({ waitUntil: 'networkidle' });" in text


def test_test_file_wires_persona_credentials_and_base_url():
    feat = _feature()  # login precondition + persona "Shopper"
    profile = _profile(
        imports={"base_url": {"module": "@app/url", "export": "appUrl"}},
        personas={"Shopper": {"module": "@app/creds", "credential_function": "getShopperCreds"}},
    )
    text = emit_test_file(feat, _fns(feat), profile)
    assert "import { appUrl } from '@app/url';" in text
    assert "const APP_URL = appUrl;" in text
    assert "import { getShopperCreds } from '@app/creds';" in text
    assert "const credentials = getShopperCreds();" in text


def test_report_title_prefix_applied():
    feat = _feature()
    profile = _profile(reports={"title_prefix": "H365"})
    text = emit_test_file(feat, _fns(feat), profile)
    assert "title: 'H365 [F][Web] Checkout'" in text


def test_dependency_note_for_session_variable():
    raws = [
        RawScenario(row=1, steps_text='When I enter "O-{{timestamp|%Y as id}}" into Ref\nThen I see Done',
                    fields={"feature": "[F][Web] Orders", "title": "Create order"}),
        RawScenario(row=2, steps_text='Then in the row where Ref is "{{$id}}" Status is "New"',
                    fields={"feature": "[F][Web] Orders", "title": "Verify order"}),
    ]
    feat = build_features(raws)[0]
    text = emit_test_file(feat, _fns(feat))
    assert "// Depends on: scenario 1 (Create order) — sets {{$id}}" in text


def test_failure_screenshot_opt_in():
    feat = _feature()
    fns = _fns(feat)
    assert "page.screenshot(" not in emit_test_file(feat, fns)  # off by default
    profile = _profile()
    profile.project.on_failure_screenshot = True
    assert "page.screenshot(" in emit_test_file(feat, fns, profile)


def test_scaffold_writes_harness_once(tmp_path):
    written = scaffold_harness(tmp_path)
    assert (tmp_path / "helpers" / "engine.ts").exists()
    assert (tmp_path / "helpers" / "actions.ts").exists()
    assert (tmp_path / "helpers" / "reporter.ts").exists()
    assert (tmp_path / "flows" / "login.flow.ts").exists()
    assert (tmp_path / ".env.bubblegum.local.example").exists()
    assert (tmp_path / "SKILL.md").exists()
    # idempotent: a second call writes nothing (no overwrite)
    assert scaffold_harness(tmp_path) == []
    assert len(written) == 6
