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


def test_flow_file_shape():
    feat = _feature()
    text = emit_flow_file(feat, _fns(feat))
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
    assert f"await {fns[0]}(engine, page);" in text
    assert "await generateReports(ctx.engine" in text
    assert "main();" in text


def test_test_file_omits_login_when_no_precondition():
    feat = _feature(
        steps="Given I open the Home page\nThen I see the Welcome banner",
        title="Home banner",
    )
    text = emit_test_file(feat, _fns(feat))
    assert "loginFlow" not in text
    assert "credentials" not in text


def test_scaffold_writes_harness_once(tmp_path):
    written = scaffold_harness(tmp_path)
    assert (tmp_path / "helpers" / "engine.ts").exists()
    assert (tmp_path / "helpers" / "actions.ts").exists()
    assert (tmp_path / "helpers" / "reporter.ts").exists()
    assert (tmp_path / "flows" / "login.flow.ts").exists()
    assert (tmp_path / ".env.bubblegum.local.example").exists()
    # idempotent: a second call writes nothing (no overwrite)
    assert scaffold_harness(tmp_path) == []
    assert len(written) == 5
