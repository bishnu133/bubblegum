"""Unit tests for normalization + step classification."""

from __future__ import annotations

from bubblegum.convert.models import RawScenario, StepKind
from bubblegum.convert.normalize import (
    _strip_subject,
    build_features,
    normalize_scenario,
)


def _raw(steps: str, **fields) -> RawScenario:
    base = {
        "feature": "[F][Web] Demo",
        "title": "A scenario",
        "persona": "User",
        "jira": "PROJ-1",
    }
    base.update(fields)
    return RawScenario(row=1, steps_text=steps, fields=base)


def test_strip_subject_first_person():
    assert _strip_subject('I enter "x" into Username') == 'enter "x" into Username'
    assert _strip_subject("they will see the Dashboard") == "see the Dashboard"
    assert _strip_subject("the user clicks Save") == "clicks Save"


def test_action_steps_are_auto():
    sc = normalize_scenario(
        _raw(
            "Given I open the Login page\n"
            'When I enter "tom" into the Username field\n'
            "And I click the Sign in button\n"
            "Then I see the Dashboard heading"
        )
    )
    kinds = [s.kind for s in sc.steps]
    assert kinds == [StepKind.AUTO, StepKind.AUTO, StepKind.AUTO, StepKind.AUTO]
    # runtime instruction is subject-stripped, display text keeps first person
    assert sc.steps[0].text == "I open the Login page"
    assert sc.steps[0].instruction == "open the Login page"


def test_login_precondition_is_needs_data():
    sc = normalize_scenario(_raw('Given I am logged in as a "Shopper"'))
    assert sc.steps[0].kind is StepKind.NEEDS_DATA
    assert "fixture" in sc.steps[0].todo


def test_data_precondition_is_needs_data():
    sc = normalize_scenario(_raw("Given a user with 3 configured badges"))
    assert sc.steps[0].kind is StepKind.NEEDS_DATA


def test_vague_assertion_is_manual():
    sc = normalize_scenario(_raw("Then it will work as expected"))
    assert sc.steps[0].kind is StepKind.MANUAL


def test_backend_feature_marks_all_backend():
    sc = normalize_scenario(
        _raw(
            "Given a user\nWhen an order completes\nThen points accrue",
            feature="[F][Backend] Rewards",
        )
    )
    assert sc.is_backend
    assert all(s.kind is StepKind.BACKEND for s in sc.steps)
    assert "@backend" in sc.tags


def test_and_inherits_section():
    sc = normalize_scenario(
        _raw("Given I open a page\nWhen I click A\nAnd I click B\nThen I see C\nAnd I see D")
    )
    assert [s.keyword for s in sc.steps] == ["given", "when", "when", "then", "then"]


def test_build_features_groups_by_feature():
    raws = [
        _raw("Given I open X\nThen I see Y", feature="[F][Web] One"),
        _raw("Given I open Z\nThen I see W", feature="[F][Web] Two"),
        _raw("Given I open Q\nThen I see R", feature="[F][Web] One"),
    ]
    feats = build_features(raws)
    assert [f.name for f in feats] == ["[F][Web] One", "[F][Web] Two"]
    assert len(feats[0].scenarios) == 2


def test_feature_slugs_are_unique_across_tag_variants():
    # Two features differing only by a bracket tag must not collide (they would
    # otherwise overwrite each other's generated files).
    raws = [
        _raw("Given I open X\nThen I see Y", feature="[F][BAP] Streaks"),
        _raw("Given a user\nThen points accrue", feature="[F][Backend] Streaks"),
    ]
    feats = build_features(raws)
    slugs = [f.slug for f in feats]
    assert len(set(slugs)) == 2, slugs
    assert "streaks" in slugs
    assert any(s.startswith("streaks_") for s in slugs)


def test_glossary_rewrites_step():
    sc = normalize_scenario(
        _raw("Given the standard login"),
    )
    # without glossary the raw text is kept
    assert sc.steps[0].text == "the standard login"

    from bubblegum.convert.profile import ConvertProfile

    profile = ConvertProfile()
    profile.glossary = {"the standard login": "I open the Login page"}
    sc2 = normalize_scenario(_raw("Given the standard login"), profile)
    assert sc2.steps[0].text == "I open the Login page"
