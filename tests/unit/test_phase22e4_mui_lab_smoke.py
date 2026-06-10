"""Phase 22E-4: MUI lab — page server + runner module smoke.

Does not launch Chromium; just verifies:
  - The 4 MUI lab pages exist and are servable through
    ``start_widget_lab_server(pages_dir=...)``.
  - The runner module imports cleanly and exposes the 4 scenario
    functions the regression script depends on.
  - The regression script imports the lab module via its private helper
    (catches path-resolution regressions).

Live browser coverage lives in tests/integration/test_phase22e4_mui_lab.py
behind --playwright.
"""

from __future__ import annotations

import importlib.util
import urllib.request
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MUI_PAGES = _REPO_ROOT / "examples" / "web" / "widgets" / "mui_lab" / "pages"
_MUI_RUNNER = _REPO_ROOT / "examples" / "web" / "widgets" / "mui_lab" / "run_example.py"
_REGRESSION = _REPO_ROOT / "scripts" / "run_mui_lab_regression.py"


def _import_path(label: str, path: Path):
    spec = importlib.util.spec_from_file_location(label, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "page,marker",
    [
        ("select.html", b"MuiOutlinedInput-root"),
        ("checkbox.html", b"MuiCheckbox-root"),
        ("dialog.html", b'role="dialog"'),
        ("autocomplete.html", b"MuiAutocomplete-root"),
    ],
)
def test_mui_lab_pages_serve_with_mui_markers(page, marker):
    from bubblegum.testing.widget_lab import start_widget_lab_server

    server, base_url = start_widget_lab_server(pages_dir=_MUI_PAGES)
    try:
        with urllib.request.urlopen(f"{base_url}/{page}", timeout=5) as resp:
            assert resp.status == 200
            body = resp.read()
        assert marker in body, f"{page} missing MUI marker {marker!r}"
    finally:
        server.shutdown()


def test_mui_lab_runner_exposes_scenarios():
    runner = _import_path("mui_lab_runner_smoke", _MUI_RUNNER)
    expected = {
        "run_select_scenario",
        "run_checkbox_scenario",
        "run_dialog_scenario",
        "run_autocomplete_scenario",
    }
    missing = expected - set(dir(runner))
    assert not missing, f"runner missing scenarios: {missing}"


def test_regression_script_can_import_lab():
    reg = _import_path("mui_lab_regression_smoke", _REGRESSION)
    lab = reg._import_lab_module()
    assert hasattr(lab, "run_select_scenario")
    assert hasattr(lab, "run_autocomplete_scenario")


def test_mui_checkbox_svg_is_pointer_event_transparent():
    """Regression for the 22E-4 dogfooding round: when MUI's `.Mui-checked`
    adds `position: relative` to the SVG icon, the SVG ends up in the same
    stacking context as the absolutely-positioned hidden input but later in
    DOM order, so it intercepts clicks meant for the input. Real MUI sets
    `pointer-events: none` on the decorative icon to fix this — assert our
    sample does the same so the lab doesn't go red whenever the checked
    state changes the stacking context.
    """
    body = (_MUI_PAGES / "checkbox.html").read_text(encoding="utf-8")
    assert ".MuiSvgIcon-root" in body
    # Look for the rule block on .MuiSvgIcon-root containing pointer-events: none.
    icon_block_start = body.index(".MuiSvgIcon-root {")
    icon_block_end = body.index("}", icon_block_start)
    block = body[icon_block_start:icon_block_end]
    assert "pointer-events: none" in block, (
        "MuiSvgIcon-root must be pointer-event-transparent so clicks reach the input"
    )
