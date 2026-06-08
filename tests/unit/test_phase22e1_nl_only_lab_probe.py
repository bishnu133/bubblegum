"""Phase 22E-1 probe: which widget-lab scenarios already resolve NL-only?

Feeds synthetic ARIA snapshots (mirroring what each lab page produces) directly
to AccessibilityTreeResolver.resolve(), bypassing the browser. Each test asserts
that the resolver's top candidate matches the element the lab scenario would
need to click / type / select against, without any `selector=` safety net.

Status assertions are organized as PASS / NEEDS_FIX. The PASS cases are the
ones where 22E-1 can immediately drop `selector=` from the lab runner. The
NEEDS_FIX cases pin the gaps that 22E-1 still has to close before the lab can
run in strict NL-only mode.
"""

from __future__ import annotations

from typing import Optional

import pytest

from bubblegum.core.grounding.ranker import CandidateRanker
from bubblegum.core.grounding.resolvers.accessibility_tree import (
    AccessibilityTreeResolver,
)
from bubblegum.core.grounding.resolvers.fuzzy_text import FuzzyTextResolver
from bubblegum.core.parser.instruction import (
    decompose,
    infer_action_type,
    parse_relational_intent,
)
from bubblegum.core.schemas import StepIntent


# ---------------------------------------------------------------------------
# Helpers: build a StepIntent the same way the SDK does, then run the full
# Tier 1 + Tier 2 candidate pipeline through the ranker. Using the ranker
# (not raw resolver.confidence) is critical: the engine's early-exit and
# tie-breaking use the ranker's weighted score, so a probe that only looks
# at raw confidence can miss the real production ordering (which is what
# the 22E-1c lab strict run exposed).
# ---------------------------------------------------------------------------


def _intent(instruction: str, snapshot: str) -> StepIntent:
    action = infer_action_type(instruction, {})
    parsed = decompose(instruction, {})
    relational = parse_relational_intent(instruction, action_type=action)
    return StepIntent(
        instruction=instruction,
        channel="web",
        platform="web",
        action_type=action,
        target_phrase=parsed.target_phrase,
        input_value=parsed.input_value,
        context={
            "a11y_snapshot": snapshot,
            "relational_intent": relational,
        },
    )


def _resolve_all(snapshot: str, instruction: str):
    intent = _intent(instruction, snapshot)
    candidates = []
    for resolver in (AccessibilityTreeResolver(), FuzzyTextResolver()):
        candidates.extend(resolver.resolve(intent))
    return candidates


def _top_ref(snapshot: str, instruction: str) -> Optional[str]:
    candidates = _resolve_all(snapshot, instruction)
    if not candidates:
        return None
    return CandidateRanker().best(candidates).ref


def _all_refs(snapshot: str, instruction: str) -> list[str]:
    return [c.ref for c in _resolve_all(snapshot, instruction)]


# ---------------------------------------------------------------------------
# Synthetic snapshots mirroring the lab pages
# ---------------------------------------------------------------------------

# Native <select> Country — pages/select.html
SNAPSHOT_SELECT = """\
- heading "Native <select>" [level=1]
- paragraph: Labeled native dropdown.
- text: Country
- combobox "Country"
  - option "-- Pick one --"
  - option "United States"
  - option "India"
  - option "United Kingdom"
  - option "Singapore"
- paragraph
"""

# File upload — pages/upload.html
SNAPSHOT_UPLOAD = """\
- heading "File upload" [level=1]
- paragraph
- text: Resume
- button "Choose File"
- paragraph
"""

# Checkbox group — pages/checkboxes.html
SNAPSHOT_CHECKBOXES = """\
- heading "Checkboxes" [level=1]
- group "Preferences"
  - checkbox "Newsletter"
  - checkbox "Terms and Conditions"
  - checkbox "Marketing emails" [checked]
"""

# Radio group — pages/radios.html
SNAPSHOT_RADIOS = """\
- heading "Radio group" [level=1]
- group "Color"
  - radio "Red"
  - radio "Blue"
  - radio "Green"
- paragraph
"""

# Link vs Button — pages/link_vs_button.html
SNAPSHOT_LINK_VS_BUTTON = """\
- heading "Link vs Button" [level=1]
- paragraph
- list
  - listitem
- button "Sign in"
- link "Sign in"
- paragraph
"""

# Custom combobox — pages/combobox.html (BEFORE opening: listbox is in a
# <template>, not in the live DOM)
SNAPSHOT_COMBOBOX_CLOSED = """\
- heading "Custom combobox" [level=1]
- paragraph
- combobox "Select country"
- paragraph
"""

# Same page AFTER opening: portal listbox is now appended to document.body
SNAPSHOT_COMBOBOX_OPEN = """\
- heading "Custom combobox" [level=1]
- paragraph
- combobox "Select country"
- paragraph
- listbox "Country"
  - option "United States"
  - option "India"
  - option "United Kingdom"
  - option "Singapore"
"""

# Phase 22E-1c surfaced this: Playwright's real aria_snapshot uses an
# inline-value form for the combobox trigger ("role: name", not "role
# \"name\""). The 22E-1d regex update accepts both forms; this snapshot
# pins the new behaviour.
SNAPSHOT_COMBOBOX_REAL_CLOSED = """\
- heading "Custom combobox (portal-rendered listbox)" [level=1]
- paragraph:
  - text: The trigger lives inline; the listbox is appended to
  - code: document.body
- combobox: Select country
- paragraph
"""

# Real link-vs-button snapshot the user captured: contains both `button
# "Sign in"` and `link "Sign in":` (with children for the href). Tier-1
# regression: the link must win when the NL says "link" even when the
# button appears earlier in DOM order.
SNAPSHOT_LINK_VS_BUTTON_REAL = """\
- heading "Link vs Button — same label" [level=1]
- paragraph: "Both controls have the accessible name \\"Sign in\\". The expected disambiguation:"
- list:
  - listitem:
    - text: "\\"Click the Sign in"
    - strong: link
    - text: "\\" → navigates to"
    - code: /link-clicked.html
  - listitem:
    - text: "\\"Click the Sign in"
    - strong: button
- button "Sign in"
- link "Sign in":
  - /url: /link-clicked.html
- paragraph: Button clicked!
"""

# Modal — pages/modal.html (after opening the dialog)
SNAPSHOT_MODAL_OPEN = """\
- heading "Modal dialog" [level=1]
- paragraph
- button "Open Settings"
- dialog "Settings"
  - heading "Settings" [level=2]
  - text: Name
  - textbox "Name"
  - button "Cancel"
  - button "Close"
- paragraph
"""


# ---------------------------------------------------------------------------
# PASS — NL-only resolution works today
# ---------------------------------------------------------------------------


def test_native_select_resolves_country_combobox():
    assert _top_ref(SNAPSHOT_SELECT, "Select India from Country") == \
        'role=combobox[name="Country"]'


def test_checkbox_resolves_by_label():
    assert _top_ref(SNAPSHOT_CHECKBOXES, "Check Newsletter") == \
        'role=checkbox[name="Newsletter"]'


def test_checkbox_uncheck_resolves_by_label():
    assert _top_ref(SNAPSHOT_CHECKBOXES, "Uncheck Marketing emails") == \
        'role=checkbox[name="Marketing emails"]'


def test_radio_resolves_by_option_label():
    assert _top_ref(SNAPSHOT_RADIOS, "Click Red radio") == \
        'role=radio[name="Red"]'


def test_modal_open_trigger_resolves():
    assert _top_ref(SNAPSHOT_MODAL_OPEN, "Click Open Settings") == \
        'role=button[name="Open Settings"]'


def test_modal_name_input_resolves_inside_dialog():
    assert _top_ref(SNAPSHOT_MODAL_OPEN, 'Enter "Bishnu" into Name') == \
        'role=textbox[name="Name"]'


def test_combobox_trigger_resolves_by_accessible_name():
    assert _top_ref(SNAPSHOT_COMBOBOX_CLOSED, "Click Select country") == \
        'role=combobox[name="Select country"]'


def test_combobox_option_resolves_when_listbox_is_in_dom():
    # After the combobox is opened, the portal listbox is in document.body,
    # so a fresh snapshot includes role=option entries.
    assert _top_ref(SNAPSHOT_COMBOBOX_OPEN, "Click India") == \
        'role=option[name="India"]'


# ---------------------------------------------------------------------------
# NEEDS_FIX — pin the gaps 22E-1 has to close
# ---------------------------------------------------------------------------


def test_link_vs_button_link_wins_when_kind_hint_is_link():
    """Phase 22E-1: control_kind_hint=link biases the resolver toward role=link.

    Without the bias, 'Click the Sign in link' scored both candidates at 0.96
    and max() returned the button (it appears first in snapshot order). The
    _KIND_BIAS nudge breaks the tie in favour of the role the NL explicitly
    asked for.
    """
    refs = _all_refs(SNAPSHOT_LINK_VS_BUTTON, "Click the Sign in link")
    # Both candidates are present (resolver does not narrow them out).
    assert 'role=button[name="Sign in"]' in refs
    assert 'role=link[name="Sign in"]' in refs
    # The link explicitly named in the NL must win the tie.
    top = _top_ref(SNAPSHOT_LINK_VS_BUTTON, "Click the Sign in link")
    assert top == 'role=link[name="Sign in"]'


def test_link_vs_button_button_default_when_no_kind_hint():
    """No 'link' suffix => no control_kind_hint => button wins by default.

    'Click Sign in' carries no kind hint; the resolver returns both
    candidates at equal confidence and iteration order picks the button
    (first in snapshot order), which matches the ambiguity policy: button
    wins by default, link wins only when the NL says 'link'.
    """
    top = _top_ref(SNAPSHOT_LINK_VS_BUTTON, "Click Sign in")
    assert top == 'role=button[name="Sign in"]'


def test_link_vs_button_button_resolves_to_button_when_button_in_phrase():
    """When the NL says 'button', the result is still the button."""
    top = _top_ref(SNAPSHOT_LINK_VS_BUTTON, "Click the Sign in button")
    assert top == 'role=button[name="Sign in"]'


# ---------------------------------------------------------------------------
# 22E-1d real-snapshot regressions (from the lab strict run user pasted)
# ---------------------------------------------------------------------------


def test_real_combobox_inline_value_form_resolves():
    """`combobox: Select country` (no quotes around the name) must parse
    correctly with the 22E-1d regex update. Pre-22E-1d this dropped the
    name and the resolver returned target=None.
    """
    top = _top_ref(SNAPSHOT_COMBOBOX_REAL_CLOSED, "Click Select country")
    assert top == 'role=combobox[name="Select country"]'


def test_real_link_vs_button_link_wins_against_noisy_snapshot():
    """Real Playwright snapshot includes paragraph/listitem text that also
    mentions 'Sign in' (from the page's instructional copy). The kind-hint
    bias must still pick the role=link element, not noise.
    """
    top = _top_ref(SNAPSHOT_LINK_VS_BUTTON_REAL, "Click the Sign in link")
    assert top == 'role=link[name="Sign in"]'


def test_real_link_vs_button_button_wins_when_no_kind_hint():
    top = _top_ref(SNAPSHOT_LINK_VS_BUTTON_REAL, "Click Sign in")
    assert top == 'role=button[name="Sign in"]'


def test_combobox_option_passes_review_threshold():
    """Phase 22E-1g: a role=option click target must score above the
    review_threshold (0.70). Pre-fix role_fit_score(option, click)=0.5
    gave option a weighted score of 0.67, so the engine dropped it.
    The fix bumps option to the 0.8 tier (same as menuitem/tab/etc).
    """
    snapshot = (
        '- combobox "Country"\n'
        '- listbox "Country"\n'
        '  - option "India"\n'
        '  - option "Singapore"\n'
    )
    assert _top_ref(snapshot, "Click India") == 'role=option[name="India"]'


def test_real_combobox_with_name_and_value_resolves_by_name():
    """Phase 22E-1f: when the combobox has BOTH an accessible name AND an
    inline value (`combobox "Select country": Select country`), the
    resolver must extract the quoted name and ignore the value, so the
    Playwright role-name selector matches the trigger.
    """
    snapshot = (
        '- heading "Custom combobox" [level=1]\n'
        '- combobox "Select country": Select country\n'
        '- paragraph\n'
    )
    assert _top_ref(snapshot, "Click Select country") == \
        'role=combobox[name="Select country"]'


# ---------------------------------------------------------------------------
# Summary marker — fail loudly if a PASS case starts regressing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "snapshot,instruction,expected_ref",
    [
        (SNAPSHOT_SELECT, "Select India from Country", 'role=combobox[name="Country"]'),
        (SNAPSHOT_CHECKBOXES, "Check Newsletter", 'role=checkbox[name="Newsletter"]'),
        (SNAPSHOT_CHECKBOXES, "Uncheck Marketing emails", 'role=checkbox[name="Marketing emails"]'),
        (SNAPSHOT_RADIOS, "Click Red radio", 'role=radio[name="Red"]'),
        (SNAPSHOT_MODAL_OPEN, "Click Open Settings", 'role=button[name="Open Settings"]'),
        (SNAPSHOT_MODAL_OPEN, 'Enter "Bishnu" into Name', 'role=textbox[name="Name"]'),
        (SNAPSHOT_COMBOBOX_CLOSED, "Click Select country", 'role=combobox[name="Select country"]'),
        (SNAPSHOT_COMBOBOX_OPEN, "Click India", 'role=option[name="India"]'),
    ],
    ids=[
        "select-country",
        "check-newsletter",
        "uncheck-marketing",
        "click-red-radio",
        "click-open-settings",
        "enter-name-in-dialog",
        "open-combobox",
        "click-india-option",
    ],
)
def test_pass_matrix_top_candidate(snapshot: str, instruction: str, expected_ref: str) -> None:
    assert _top_ref(snapshot, instruction) == expected_ref
