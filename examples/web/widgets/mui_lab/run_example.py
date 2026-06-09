"""Phase 22E-4: MUI lab — Material-UI styled widget scenarios.

Spins up the same daemon-thread HTTP server as widget_lab (via the shared
``bubblegum.testing.widget_lab`` helper, pointed at this lab's pages
directory) and drives 4 NL scenarios against a MUI-shaped DOM:

  - mui-select         Open MuiSelect, pick India, verify hidden input value
  - mui-checkbox       Check Newsletter, uncheck Marketing
  - mui-dialog         Open Edit Profile, type Name, click Save
  - mui-autocomplete   Type "In", filter list, pick India

The pages emit real MUI classnames and ARIA attributes so the
resolver path matches what a real React + MUI app produces.

Run:
    python examples/web/widgets/mui_lab/run_example.py            # headless
    python examples/web/widgets/mui_lab/run_example.py --headed   # visible
    python examples/web/widgets/mui_lab/run_example.py --strict   # NL-only
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from bubblegum.testing.widget_lab import start_widget_lab_server

PLAYWRIGHT_INSTALL_HINT = """Playwright is not installed.
Install with:
  pip install -e ".[web]"
Then install browser binaries:
  python -m playwright install chromium
"""

_PAGES_DIR = Path(__file__).resolve().parent / "pages"


def _start_server():
    return start_widget_lab_server(pages_dir=_PAGES_DIR)


def _result(name: str, passed: bool, **detail) -> dict:
    out = {"scenario": name, "passed": passed}
    out.update(detail)
    return out


def _safety_net(nl_only: bool, **strict_kwargs):
    return {} if nl_only else strict_kwargs


def _diag(nl_only: bool, label: str, step) -> None:
    if not nl_only:
        return
    if step.target is None:
        print(f"  [diag] {label}: status={step.status}  target=None")
        return
    ref = step.target.ref
    resolver = step.target.resolver_name
    conf = step.target.confidence
    print(f"  [diag] {label}: status={step.status}  ref={ref!r}  conf={conf:.2f}  resolver={resolver}")


async def run_select_scenario(page, base_url: str, *, nl_only: bool = False) -> dict:
    from bubblegum import act

    await page.goto(f"{base_url}/select.html")
    await page.wait_for_load_state("domcontentloaded")

    step_open = await act(
        "Click Country",
        page=page,
        channel="web",
        **_safety_net(nl_only, action_type="click", selector="#country-select"),
    )
    _diag(nl_only, "open-mui-select", step_open)
    await page.wait_for_selector("#country-menu", state="visible", timeout=3000)

    step_pick = await act(
        "Click India",
        page=page,
        channel="web",
        **_safety_net(nl_only, action_type="click", selector="#country-menu [data-value='IN']"),
    )
    _diag(nl_only, "pick-india", step_pick)

    selected_value = await page.locator("#country-value").input_value()
    display_text = (await page.locator("#country-display").inner_text()).strip()
    aria_expanded = await page.locator("#country-select").get_attribute("aria-expanded")
    result_text = await page.locator("#result").inner_text()

    state_ok = selected_value == "IN" and display_text == "India" and aria_expanded == "false"
    text_ok = "India" in result_text

    passed = step_open.status == "passed" and step_pick.status == "passed" and state_ok and text_ok
    return _result(
        "mui-select",
        passed,
        nl_only=nl_only,
        open_status=step_open.status,
        pick_status=step_pick.status,
        selected_value=selected_value,
        display_text=display_text,
        aria_expanded=aria_expanded,
        result_text=result_text,
    )


async def run_checkbox_scenario(page, base_url: str, *, nl_only: bool = False) -> dict:
    from bubblegum import act

    await page.goto(f"{base_url}/checkbox.html")
    await page.wait_for_load_state("domcontentloaded")

    step_check = await act(
        "Check Newsletter",
        page=page,
        channel="web",
        **_safety_net(nl_only, action_type="check", selector="#cb_newsletter"),
    )
    _diag(nl_only, "check-newsletter", step_check)
    newsletter_checked = await page.locator("#cb_newsletter").is_checked()

    step_uncheck = await act(
        "Uncheck Marketing emails",
        page=page,
        channel="web",
        **_safety_net(nl_only, action_type="uncheck", selector="#cb_marketing"),
    )
    _diag(nl_only, "uncheck-marketing", step_uncheck)
    marketing_unchecked = not await page.locator("#cb_marketing").is_checked()

    terms_untouched = not await page.locator("#cb_terms").is_checked()

    passed = (
        step_check.status == "passed"
        and step_uncheck.status == "passed"
        and newsletter_checked and marketing_unchecked and terms_untouched
    )
    return _result(
        "mui-checkbox",
        passed,
        nl_only=nl_only,
        check_status=step_check.status,
        uncheck_status=step_uncheck.status,
        newsletter_checked=newsletter_checked,
        marketing_unchecked=marketing_unchecked,
        terms_untouched=terms_untouched,
    )


async def run_dialog_scenario(page, base_url: str, *, nl_only: bool = False) -> dict:
    from bubblegum.session import BubblegumSession

    await page.goto(f"{base_url}/dialog.html")
    await page.wait_for_load_state("domcontentloaded")

    async with BubblegumSession.web(page) as s:
        step_open = await s.act(
            "Click Edit Profile",
            **_safety_net(nl_only, action_type="click", selector="#open-edit"),
        )
        _diag(nl_only, "open-edit", step_open)
        await page.wait_for_selector(
            "#edit-dialog[aria-modal='true']", state="visible", timeout=3000
        )

        step_type = await s.act(
            'Enter "Bishnu" into Name',
            **_safety_net(nl_only, action_type="type", selector="#edit-name", input_value="Bishnu"),
        )
        _diag(nl_only, "type-name", step_type)
        typed_value = await page.locator("#edit-name").input_value()

        step_save = await s.act(
            "Click Save",
            **_safety_net(nl_only, action_type="click", selector="#edit-save"),
        )
        _diag(nl_only, "click-save", step_save)
        await page.wait_for_selector("#edit-backdrop", state="detached", timeout=3000)
        result_text = await page.locator("#result").inner_text()

    open_ok = step_open.status == "passed"
    type_ok = step_type.status == "passed" and typed_value == "Bishnu"
    save_ok = step_save.status == "passed"
    text_ok = "Saved name: Bishnu" in result_text

    passed = open_ok and type_ok and save_ok and text_ok
    return _result(
        "mui-dialog",
        passed,
        nl_only=nl_only,
        open_status=step_open.status,
        type_status=step_type.status,
        save_status=step_save.status,
        typed_value=typed_value,
        result_text=result_text,
    )


async def run_autocomplete_scenario(page, base_url: str, *, nl_only: bool = False) -> dict:
    from bubblegum import act

    await page.goto(f"{base_url}/autocomplete.html")
    await page.wait_for_load_state("domcontentloaded")

    # Focus + type triggers the portal listbox; we type a partial "In" so
    # the filter narrows to India / Indonesia / etc.
    step_type = await act(
        'Enter "In" into Country',
        page=page,
        channel="web",
        **_safety_net(nl_only, action_type="type", selector="#country-input", input_value="In"),
    )
    _diag(nl_only, "type-In", step_type)
    await page.wait_for_selector("#country-listbox", state="visible", timeout=3000)

    # Wait for the filter to actually narrow the visible set.
    await page.wait_for_function(
        "() => { const lb = document.getElementById('country-listbox');"
        " if (!lb) return false;"
        " const visible = Array.from(lb.querySelectorAll('[role=option]'))"
        "   .filter(o => !o.hidden);"
        " return visible.length > 0 && visible.length < 8; }",
        timeout=3000,
    )

    step_pick = await act(
        "Click India",
        page=page,
        channel="web",
        **_safety_net(nl_only, action_type="click", selector="#country-listbox [data-value='India']"),
    )
    _diag(nl_only, "pick-india", step_pick)

    final_value = await page.locator("#country-input").input_value()
    aria_expanded = await page.locator("#country-input").get_attribute("aria-expanded")
    result_text = await page.locator("#result").inner_text()

    state_ok = final_value == "India" and aria_expanded == "false"
    text_ok = "India" in result_text

    passed = step_type.status == "passed" and step_pick.status == "passed" and state_ok and text_ok
    return _result(
        "mui-autocomplete",
        passed,
        nl_only=nl_only,
        type_status=step_type.status,
        pick_status=step_pick.status,
        final_value=final_value,
        aria_expanded=aria_expanded,
        result_text=result_text,
    )


async def run(headless: bool, nl_only: bool = False) -> int:
    from playwright.async_api import async_playwright

    server, base_url = _start_server()
    mode = "strict NL-only" if nl_only else "with selector safety net"
    print(f"Serving MUI lab at {base_url}  ({mode})")

    results: list[dict] = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                page.set_default_timeout(5_000)

                results.append(await run_select_scenario(page, base_url, nl_only=nl_only))
                results.append(await run_checkbox_scenario(page, base_url, nl_only=nl_only))
                results.append(await run_dialog_scenario(page, base_url, nl_only=nl_only))
                results.append(await run_autocomplete_scenario(page, base_url, nl_only=nl_only))
            finally:
                await browser.close()
    finally:
        server.shutdown()

    print("\nsummary:")
    failed = 0
    for r in results:
        status = "passed" if r["passed"] else "failed"
        print(f"  {r['scenario']:20s} {status}")
        for k, v in r.items():
            if k in {"scenario", "passed"}:
                continue
            print(f"    {k}: {v!r}")
        if not r["passed"]:
            failed += 1
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true", help="Run with a visible browser")
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Strict NL-only mode: drop selector= / action_type= / input_value= "
            "from every scenario and let the parser + resolver do the work."
        ),
    )
    args = parser.parse_args()

    try:
        return asyncio.run(run(headless=not args.headed, nl_only=args.strict))
    except ModuleNotFoundError as exc:
        if "playwright" in str(exc):
            print(PLAYWRIGHT_INSTALL_HINT)
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
