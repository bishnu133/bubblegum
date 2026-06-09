"""Phase 22D-4..5: widget lab — native widget E2E scenarios.

Spins up a tiny static HTTP server serving pages/ and drives Bubblegum NL
instructions through Playwright against it. Each scenario verifies widget
*state* (selected value, is_checked, URL transition, etc.) in addition to
any result text — text-only verification is intentionally insufficient.

Scenarios:
  22D-4
    native-select   Select India from Country  (state: input_value == "IN")
    file-upload     Upload <tmp> to Resume      (state: input.files non-empty)
  22D-5
    checkbox-group  Check / uncheck across three checkboxes
                    (state: is_checked() per box)
    radio-group     Click Red radio
                    (state: red is_checked, others unchecked)
    link-vs-button  Disambiguate same-label "Sign in" <a> vs <button>
                    (state: link navigates, button does not + result text)
  22D-8
    combobox-select ARIA combobox + portal-rendered listbox
                    (state: trigger text/data-value, aria-expanded=false)
    modal-flow      Open dialog, type into Name, session.close_dialog()
                    (state: aria-modal cleared, scope popped, result text)

Run:
    python examples/web/widgets/widget_lab/run_example.py            # headless
    python examples/web/widgets/widget_lab/run_example.py --headed   # visible
"""

from __future__ import annotations

import argparse
import asyncio
import tempfile
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
    """Return strict_kwargs unless we are in NL-only mode.

    When `nl_only=True` we drop every selector / action_type / input_value
    safety net so the resolver chain and the parser have to do the work end
    to end. Anything the parser cannot extract from the NL string (e.g. a
    file path the test generates at runtime) is passed via `keep_value=`.
    """
    return {} if nl_only else strict_kwargs


def _diag(nl_only: bool, label: str, step) -> None:
    """Print the resolver outcome for a strict-mode step.

    Strict NL-only runs are where we learn whether the synthetic-snapshot
    probe matches real-browser behaviour. When something fails, this diag
    line tells us which element the resolver actually picked so we can
    target the fix instead of guessing.
    """
    if not nl_only:
        return
    if step.target is None:
        print(f"  [diag] {label}: status={step.status}  target=None  (resolver returned no candidates)")
        return
    ref = step.target.ref
    resolver = step.target.resolver_name
    conf = step.target.confidence
    print(f"  [diag] {label}: status={step.status}  ref={ref!r}  conf={conf:.2f}  resolver={resolver}")


async def run_select_scenario(page, base_url: str, *, nl_only: bool = False) -> dict:
    from bubblegum import act

    await page.goto(f"{base_url}/select.html")
    await page.wait_for_load_state("domcontentloaded")

    # In safety-net mode we pass selector + value so the adapter dispatch is
    # exercised independently of the resolver. In strict NL-only mode the
    # parser extracts target="Country" + value="India" from the instruction,
    # and the accessibility-tree resolver finds the labeled <select>.
    # select_option() accepts an option's visible label, so "India" works
    # for a <select> whose option value is "IN".
    step = await act(
        "Select India from Country",
        page=page,
        channel="web",
        **_safety_net(nl_only, action_type="select", selector="#country", input_value="IN"),
    )
    _diag(nl_only, "select-country", step)

    selected_value = await page.locator("#country").input_value()
    state_ok = selected_value == "IN"
    result_text = await page.locator("#result").inner_text()
    text_ok = "India" in result_text

    passed = step.status == "passed" and state_ok and text_ok
    return _result(
        "native-select",
        passed,
        nl_only=nl_only,
        action_status=step.status,
        selected_value=selected_value,
        result_text=result_text,
        state_ok=state_ok,
        text_ok=text_ok,
    )


async def run_upload_scenario(page, base_url: str, *, nl_only: bool = False) -> dict:
    from bubblegum import act

    await page.goto(f"{base_url}/upload.html")
    await page.wait_for_load_state("domcontentloaded")

    tmp = tempfile.NamedTemporaryFile(prefix="widget_lab_resume_", suffix=".pdf", delete=False)
    try:
        tmp.write(b"%PDF-1.4 widget_lab sample resume\n")
        tmp.flush()
        upload_path = tmp.name
    finally:
        tmp.close()

    # The parser extracts the path from "Upload <path> to Resume", so we can
    # drop input_value too in NL-only mode. The accessibility-tree resolver
    # finds the file input by its associated <label for="resume">Resume.
    step = await act(
        f"Upload {upload_path} to Resume",
        page=page,
        channel="web",
        **_safety_net(nl_only, action_type="upload", selector="#resume", input_value=upload_path),
    )
    _diag(nl_only, "upload-resume", step)

    has_files = await page.evaluate(
        "() => { const i = document.querySelector('#resume');"
        " return !!(i && i.files && i.files.length); }"
    )
    result_text = await page.locator("#result").inner_text()
    basename = Path(upload_path).name
    text_ok = basename in result_text

    passed = step.status == "passed" and bool(has_files) and text_ok
    return _result(
        "file-upload",
        passed,
        nl_only=nl_only,
        action_status=step.status,
        upload_path=upload_path,
        has_files=bool(has_files),
        result_text=result_text,
        text_ok=text_ok,
    )


async def run_checkbox_scenario(page, base_url: str, *, nl_only: bool = False) -> dict:
    from bubblegum import act

    await page.goto(f"{base_url}/checkboxes.html")
    await page.wait_for_load_state("domcontentloaded")

    # 1) Check Newsletter (starts unchecked) -> should be checked
    step_check = await act(
        "Check Newsletter",
        page=page,
        channel="web",
        **_safety_net(nl_only, action_type="check", selector="#cb_newsletter"),
    )
    _diag(nl_only, "check-newsletter", step_check)
    newsletter_checked = await page.locator("#cb_newsletter").is_checked()

    # 2) Uncheck Marketing emails (starts checked) -> should be unchecked
    step_uncheck = await act(
        "Uncheck Marketing emails",
        page=page,
        channel="web",
        **_safety_net(nl_only, action_type="uncheck", selector="#cb_marketing"),
    )
    _diag(nl_only, "uncheck-marketing", step_uncheck)
    marketing_unchecked = not await page.locator("#cb_marketing").is_checked()

    # 3) Terms left untouched -> should stay unchecked
    terms_untouched = not await page.locator("#cb_terms").is_checked()

    passed = (
        step_check.status == "passed"
        and step_uncheck.status == "passed"
        and newsletter_checked
        and marketing_unchecked
        and terms_untouched
    )
    return _result(
        "checkbox-group",
        passed,
        nl_only=nl_only,
        check_status=step_check.status,
        uncheck_status=step_uncheck.status,
        newsletter_checked=newsletter_checked,
        marketing_unchecked=marketing_unchecked,
        terms_untouched=terms_untouched,
    )


async def run_radio_scenario(page, base_url: str, *, nl_only: bool = False) -> dict:
    from bubblegum import act

    await page.goto(f"{base_url}/radios.html")
    await page.wait_for_load_state("domcontentloaded")

    # NL "Click Red radio" -> Red selected, Blue/Green unselected. In NL-only
    # mode the parser infers action_type=click and target=Red (the "radio"
    # suffix is stripped); the resolver finds role=radio[name="Red"] and the
    # adapter dispatches click(), which selects the native input[type=radio].
    step = await act(
        "Click Red radio",
        page=page,
        channel="web",
        **_safety_net(nl_only, action_type="check", selector="#r_red"),
    )
    _diag(nl_only, "click-red-radio", step)

    red_checked = await page.locator("#r_red").is_checked()
    blue_checked = await page.locator("#r_blue").is_checked()
    green_checked = await page.locator("#r_green").is_checked()
    result_text = await page.locator("#result").inner_text()
    text_ok = "red" in result_text.lower()

    passed = (
        step.status == "passed"
        and red_checked
        and not blue_checked
        and not green_checked
        and text_ok
    )
    return _result(
        "radio-group",
        passed,
        nl_only=nl_only,
        action_status=step.status,
        red_checked=red_checked,
        blue_checked=blue_checked,
        green_checked=green_checked,
        result_text=result_text,
        text_ok=text_ok,
    )


async def run_combobox_scenario(page, base_url: str, *, nl_only: bool = False) -> dict:
    """ARIA combobox with a portal-rendered listbox.

    Step 1 clicks the combobox trigger so the listbox is appended to
    document.body and shown. Step 2 clicks the "India" option inside the
    portal. In NL-only mode both steps rely on the resolver finding the
    combobox by accessible name and the option by visible label after the
    listbox is appended to the live DOM. State check: trigger label and
    data-value reflect the choice, listbox is collapsed (aria-expanded=false)
    after selection.
    """
    from bubblegum import act

    await page.goto(f"{base_url}/combobox.html")
    await page.wait_for_load_state("domcontentloaded")

    step_open = await act(
        "Click Select country",
        page=page,
        channel="web",
        **_safety_net(nl_only, action_type="click", selector="#country-trigger"),
    )
    _diag(nl_only, "open-combobox", step_open)
    # Wait for the portal listbox to be visible (it is created at first open).
    try:
        await page.wait_for_selector("#country-listbox", state="visible", timeout=3000)
    except Exception as exc:
        # Strict-mode diagnostic: if the trigger click did not open the
        # listbox, capture the live aria_snapshot so we can see what the
        # resolver actually saw.
        if nl_only:
            snap = await page.locator("body").aria_snapshot()
            print(f"  [diag] open-combobox: listbox never opened; aria_snapshot follows:")
            for line in snap.splitlines()[:40]:
                print(f"    {line}")
        raise

    step_pick = await act(
        "Click India",
        page=page,
        channel="web",
        **_safety_net(
            nl_only,
            action_type="click",
            selector="#country-listbox [role='option'][data-value='IN']",
        ),
    )
    _diag(nl_only, "pick-india", step_pick)
    if nl_only and step_pick.status != "passed":
        # Listbox is open; dump the snapshot so we can see exactly which
        # option entries Playwright surfaced.
        snap = await page.locator("body").aria_snapshot()
        print(f"  [diag] pick-india: dump aria_snapshot (option entries):")
        for line in snap.splitlines():
            if "option" in line.lower() or "listbox" in line.lower() or "combobox" in line.lower():
                print(f"    {line}")

    trigger_text = (await page.locator("#country-trigger").inner_text()).strip()
    trigger_value = await page.locator("#country-trigger").get_attribute("data-value")
    aria_expanded = await page.locator("#country-trigger").get_attribute("aria-expanded")
    result_text = await page.locator("#result").inner_text()

    trigger_ok = trigger_text == "India" and trigger_value == "IN"
    collapsed_ok = aria_expanded == "false"
    text_ok = "India" in result_text

    passed = (
        step_open.status == "passed"
        and step_pick.status == "passed"
        and trigger_ok
        and collapsed_ok
        and text_ok
    )
    return _result(
        "combobox-select",
        passed,
        nl_only=nl_only,
        open_status=step_open.status,
        pick_status=step_pick.status,
        trigger_text=trigger_text,
        trigger_value=trigger_value,
        aria_expanded=aria_expanded,
        result_text=result_text,
    )


async def run_modal_scenario(page, base_url: str, *, nl_only: bool = False) -> dict:
    """Open dialog → type into Name → close via session.close_dialog().

    Drives a BubblegumSession so close_dialog() is on the public API path,
    not just the internal helper. The scope is pushed manually with a
    root_locator (the dialog element); 22D-6's close_dialog_web uses that
    pinned root and bypasses the page-level dialog scan.
    """
    from bubblegum.session import BubblegumSession

    await page.goto(f"{base_url}/modal.html")
    await page.wait_for_load_state("domcontentloaded")

    async with BubblegumSession.web(page) as s:
        step_open = await s.act(
            "Click Open Settings",
            **_safety_net(nl_only, action_type="click", selector="#open-settings"),
        )
        _diag(nl_only, "open-settings", step_open)
        await page.wait_for_selector(
            "#settings-dialog[aria-modal='true']", state="visible", timeout=3000
        )

        # Push dialog scope with the dialog element as root_locator so
        # close_dialog uses the scope path (skips page-level dialog scan).
        dialog_locator = page.locator("#settings-dialog")
        s.push_scope("dialog", label="Settings", root_locator=dialog_locator)

        step_type = await s.act(
            'Enter "Bishnu" into Name',
            **_safety_net(nl_only, action_type="type", selector="#dialog-name", input_value="Bishnu"),
        )
        _diag(nl_only, "type-name", step_type)

        # Verify the value landed inside the dialog before we close it.
        typed_value = await page.locator("#dialog-name").input_value()

        close_report = await s.close_dialog()

        # Wait for the dialog backdrop to be hidden.
        await page.wait_for_selector("#backdrop", state="hidden", timeout=3000)
        dialog_modal_attr = await page.locator("#settings-dialog").get_attribute("aria-modal")
        result_text = await page.locator("#result").inner_text()
        scope_after = s.current_scope.type

    open_ok = step_open.status == "passed"
    type_ok = step_type.status == "passed" and typed_value == "Bishnu"
    close_ok = close_report["closed_by"] == "close_button"
    scope_ok = scope_after == "page" and close_report["popped_scope"] == {
        "type": "dialog",
        "label": "Settings",
    }
    dom_ok = dialog_modal_attr is None and "Saved name: Bishnu" in result_text

    passed = open_ok and type_ok and close_ok and scope_ok and dom_ok
    return _result(
        "modal-flow",
        passed,
        nl_only=nl_only,
        open_status=step_open.status,
        type_status=step_type.status,
        typed_value=typed_value,
        close_report=close_report,
        dialog_modal_after=dialog_modal_attr,
        result_text=result_text,
        scope_after=scope_after,
    )


async def run_link_vs_button_scenario(page, base_url: str, *, nl_only: bool = False) -> dict:
    """Disambiguation: NL "Click the Sign in link" picks the <a>, not the <button>.

    Verifies the link branch by URL transition AND the button branch by result
    text on a separate visit so both code paths run. In NL-only mode the 22E-1a
    kind-hint bias is what makes "link" win the tie over "button" with the
    same accessible name.
    """
    from bubblegum import act

    # --- Link branch ---
    await page.goto(f"{base_url}/link_vs_button.html")
    await page.wait_for_load_state("domcontentloaded")
    url_before = page.url

    step_link = await act(
        "Click the Sign in link",
        page=page,
        channel="web",
        **_safety_net(nl_only, action_type="click", selector="#lnk_signin"),
    )
    _diag(nl_only, "click-sign-in-link", step_link)
    await page.wait_for_load_state("domcontentloaded")
    try:
        heading_text = await page.locator("#heading").inner_text(timeout=3000)
    except Exception:
        # Strict-mode diagnostic: if the link click did not navigate, dump
        # the aria_snapshot so we can see which element actually got clicked.
        if nl_only:
            snap = await page.locator("body").aria_snapshot()
            print(f"  [diag] click-sign-in-link: did not navigate; aria_snapshot follows:")
            for line in snap.splitlines()[:30]:
                print(f"    {line}")
        raise
    url_after = page.url
    link_navigated = url_after != url_before and url_after.endswith("/link-clicked.html")
    link_heading_ok = heading_text.strip() == "Link clicked!"

    # --- Button branch (fresh load) ---
    await page.goto(f"{base_url}/link_vs_button.html")
    await page.wait_for_load_state("domcontentloaded")
    url_before_btn = page.url

    step_btn = await act(
        "Click the Sign in button",
        page=page,
        channel="web",
        **_safety_net(nl_only, action_type="click", selector="#btn_signin"),
    )
    _diag(nl_only, "click-sign-in-button", step_btn)
    # The button does not navigate; wait briefly for the onclick handler.
    await page.wait_for_function(
        "() => document.getElementById('result') && "
        "document.getElementById('result').textContent.length > 0",
        timeout=3000,
    )
    button_result_text = await page.locator("#result").inner_text()
    button_did_not_navigate = page.url == url_before_btn
    button_text_ok = "Button clicked!" in button_result_text

    passed = (
        step_link.status == "passed"
        and step_btn.status == "passed"
        and link_navigated
        and link_heading_ok
        and button_did_not_navigate
        and button_text_ok
    )
    return _result(
        "link-vs-button",
        passed,
        nl_only=nl_only,
        link_status=step_link.status,
        button_status=step_btn.status,
        link_navigated=link_navigated,
        link_heading=heading_text,
        button_did_not_navigate=button_did_not_navigate,
        button_result_text=button_result_text,
    )


async def run(headless: bool, nl_only: bool = False) -> int:
    from playwright.async_api import async_playwright

    server, base_url = _start_server()
    mode = "strict NL-only" if nl_only else "with selector safety net"
    print(f"Serving widget lab at {base_url}  ({mode})")

    results: list[dict] = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                page.set_default_timeout(5_000)

                results.append(await run_select_scenario(page, base_url, nl_only=nl_only))
                results.append(await run_upload_scenario(page, base_url, nl_only=nl_only))
                results.append(await run_checkbox_scenario(page, base_url, nl_only=nl_only))
                results.append(await run_radio_scenario(page, base_url, nl_only=nl_only))
                results.append(await run_link_vs_button_scenario(page, base_url, nl_only=nl_only))
                results.append(await run_combobox_scenario(page, base_url, nl_only=nl_only))
                results.append(await run_modal_scenario(page, base_url, nl_only=nl_only))
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
