from __future__ import annotations

import json

from bubblegum.core.schemas import ResolvedTarget, StepResult
from bubblegum.reporting.html_report import build_report_analytics
from bubblegum.reporting.suggested_fixes import build_suggested_fixes, write_suggested_fixes


def _healed(action: str, requested: str, matched: str, *, selector: str | None = None,
            severity: str = "review", match_kind: str = "synonym") -> StepResult:
    selector = selector or f'role=button[name="{matched}"]'
    target = ResolvedTarget(
        ref=selector,
        confidence=0.78,
        resolver_name="fuzzy_text",
        metadata={
            "healing": {
                "applied": True,
                "requested": requested,
                "matched": matched,
                "resolver": "fuzzy_text",
                "match_kind": match_kind,
                "similarity": 0.6,
                "severity": severity,
                "old_ref": requested,
                "new_ref": matched,
                "new_selector": selector,
                "suggested_fix": f"Update the step label: {requested!r} → {matched!r}",
            }
        },
    )
    return StepResult(status="recovered", action=action, target=target, confidence=0.78)


def _clean() -> StepResult:
    return StepResult(status="passed", action="Open page", confidence=1.0,
                      target=ResolvedTarget(ref="x", confidence=1.0, resolver_name="exact_text"))


# ---------------------------------------------------------------------------
# build_suggested_fixes
# ---------------------------------------------------------------------------


def test_collects_one_fix_per_healed_step():
    results = [_healed("Click Login", "Login", "Sign In"), _clean()]
    payload = build_suggested_fixes(results)

    assert payload["total_healed_steps"] == 1
    fix = payload["fixes"][0]
    assert fix["old_ref"] == "Login"
    assert fix["new_ref"] == "Sign In"
    assert fix["new_selector"] == 'role=button[name="Sign In"]'
    assert "Login" in fix["suggested_fix"] and "Sign In" in fix["suggested_fix"]
    assert fix["action"] == "Click Login"


def test_brittleness_ranks_most_healed_first():
    results = [
        _healed("Click Login", "Login", "Sign In"),
        _healed("Click Login again", "Login", "Sign In"),
        _healed("Click Login once more", "Login", "Sign In"),
        _healed("Tap Delete", "Delete", "Remove"),
    ]
    payload = build_suggested_fixes(results)
    brittle = payload["brittleness"]
    assert brittle[0] == {"ref": "Login", "heals": 3}
    assert {"ref": "Delete", "heals": 1} in brittle


def test_top_n_caps_brittleness_list():
    results = [_healed(f"step {i}", f"label{i}", f"match{i}") for i in range(8)]
    payload = build_suggested_fixes(results, top_n=3)
    assert len(payload["brittleness"]) == 3


def test_no_heals_yields_empty_payload():
    payload = build_suggested_fixes([_clean()])
    assert payload["total_healed_steps"] == 0
    assert payload["fixes"] == []
    assert payload["brittleness"] == []


def test_write_suggested_fixes_round_trips(tmp_path):
    path = tmp_path / "fixes.json"
    out = write_suggested_fixes([_healed("Click Login", "Login", "Sign In")], path=path)
    assert out == path.resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == "1"
    assert payload["fixes"][0]["new_ref"] == "Sign In"
    assert payload["brittleness"][0]["ref"] == "Login"


# ---------------------------------------------------------------------------
# brittleness surfaces in the shared report analytics too
# ---------------------------------------------------------------------------


def test_report_analytics_includes_brittleness():
    results = [
        _healed("a", "Login", "Sign In"),
        _healed("b", "Login", "Sign In"),
        _healed("c", "Delete", "Remove"),
    ]
    analytics = build_report_analytics(results)
    brittle = analytics["healing_summary"]["brittleness"]
    assert brittle[0] == {"ref": "Login", "heals": 2}
