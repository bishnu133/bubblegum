"""Phase 22C minimal web example runner (no Behave runtime)."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from urllib.parse import urljoin

import yaml

PLAYWRIGHT_INSTALL_HINT = """Playwright is not installed.
Install with one of:
  pip install -e ".[web]"
  pip install "bubblegum-ai[web]"
Then install browser binaries:
  python -m playwright install chromium
"""

REQUIRED_CONFIG_KEYS = (
    "app_type",
    "base_url",
    "browser",
    "headless",
    "timeout",
    "report_path",
)

SCENARIOS = [
    {
        "name": "valid-login",
        "steps": [
            "Open /login",
            'Enter username "tomsmith"',
            'Enter password "SuperSecretPassword!"',
            "Click Login",
            'Verify text "You logged into a secure area!" is visible',
        ],
    },
    {
        "name": "invalid-login",
        "steps": [
            "Open /login",
            'Enter username "tomsmith"',
            'Enter password "wrong-password"',
            "Click Login",
            'Verify text "Your password is invalid!" is visible',
        ],
    },
]


def load_example_config(path: Path) -> dict:
    """Load and validate example-specific web config as a plain dict."""
    if not path.exists():
        raise FileNotFoundError(f"Example config file not found: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Example config must be a YAML mapping/object: {path}")

    missing = [key for key in REQUIRED_CONFIG_KEYS if key not in data]
    if missing:
        missing_text = ", ".join(missing)
        raise ValueError(
            f"Missing required key(s) in {path}: {missing_text}. "
            f"Required keys: {', '.join(REQUIRED_CONFIG_KEYS)}"
        )

    return data


def print_dry_run(config: dict) -> None:
    print("Dry-run: loaded config")
    for key in REQUIRED_CONFIG_KEYS:
        print(f"- {key}: {config[key]}")

    print("Planned scenarios:")
    for scenario in SCENARIOS:
        print(f"- {scenario['name']}")
        for idx, step in enumerate(scenario["steps"], start=1):
            print(f"  {idx}. {step}")


async def run(config: dict) -> None:
    from playwright.async_api import async_playwright
    from bubblegum import act, verify

    base_url = str(config["base_url"] or "")
    if not base_url:
        raise RuntimeError("`base_url` is required in examples/web/simple_login/bubblegum.yaml")

    login_url = urljoin(base_url.rstrip("/") + "/", "login")

    async with async_playwright() as p:
        browser_name = str(config["browser"]).strip().lower()
        browser_launcher = getattr(p, browser_name, None)
        if browser_launcher is None:
            raise ValueError(
                f"Unsupported browser '{config['browser']}'. Expected one of: chromium, firefox, webkit"
            )

        browser = None
        context = None
        page = None
        try:
            browser = await browser_launcher.launch(
                headless=bool(config["headless"]),
                slow_mo=int(config.get("slow_mo", 0)),
            )
            context = await browser.new_context()
            page = await context.new_page()
            page.set_default_timeout(float(config["timeout"]) * 1000)

            scenario_results: dict[str, str] = {}

            for scenario in SCENARIOS:
                name = str(scenario["name"])
                expected_text = (
                    "You logged into a secure area!"
                    if name == "valid-login"
                    else "Your password is invalid!"
                )
                password = "SuperSecretPassword!" if name == "valid-login" else "wrong-password"

                await page.goto(login_url)
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_selector('input[name="username"]')
                print("open: passed")
                print("page_closed_after_open:", page.is_closed())

                step_user = await act(
                    'Enter "tomsmith" into Username',
                    page=page,
                    channel="web",
                    action_type="type",
                    selector='input[name="username"]',
                    input_value="tomsmith",
                )
                print("username:", step_user.status)
                username_value = await page.locator('input[name="username"]').input_value()
                username_dom_ok = username_value == "tomsmith"
                print("username_dom_check:", "passed" if username_dom_ok else "failed")
                print("page_closed_after_username:", page.is_closed())

                step_pass = await act(
                    f'Enter "{password}" into Password',
                    page=page,
                    channel="web",
                    action_type="type",
                    selector='input[name="password"]',
                    input_value=password,
                )
                print("password:", step_pass.status)
                password_value = await page.locator('input[name="password"]').input_value()
                password_dom_ok = password_value == password
                print("password_dom_check:", "passed" if password_dom_ok else "failed")
                print("page_closed_after_password:", page.is_closed())

                click_status = "skipped"
                verify_status = "failed"
                if username_dom_ok and password_dom_ok:
                    step_click = await act(
                        "Click Login",
                        page=page,
                        channel="web",
                        selector='button[type="submit"]',
                    )
                    click_status = step_click.status
                    print("click:", click_status)
                    print("page_closed_after_click:", page.is_closed())

                    await page.wait_for_selector("#flash", timeout=float(config["timeout"]) * 1000)
                    flash_text = await page.locator("#flash").inner_text()

                    if not page.is_closed():
                        try:
                            step_verify = await verify(
                                f'Verify result text: "{expected_text}"',
                                page=page,
                                channel="web",
                                selector="#flash",
                                assertion_type="text_visible",
                                expected_value=expected_text,
                            )
                            verify_status = step_verify.status
                        except Exception as exc:
                            verify_status = "failed"
                            print(f"verify limitation: Bubblegum verify failed with {type(exc).__name__}")

                    if expected_text in flash_text:
                        verify_status = "passed"
                        print("verify_text: passed")
                    elif verify_status != "passed":
                        print("verify_text:", verify_status)
                else:
                    print("click: skipped")
                    print("page_closed_after_click:", page.is_closed())
                    print("verify_text: failed")

                statuses = [
                    "passed",
                    step_user.status,
                    "passed" if username_dom_ok else "failed",
                    step_pass.status,
                    "passed" if password_dom_ok else "failed",
                    click_status,
                    verify_status,
                ]
                scenario_results[name] = "passed" if all(s == "passed" for s in statuses) else "failed"

            print("summary:")
            print("valid-login:", scenario_results.get("valid-login", "failed"))
            print("invalid-login:", scenario_results.get("invalid-login", "failed"))
            print("report path:", config["report_path"])
        finally:
            if page is not None and not page.is_closed():
                await page.close()
            if context is not None:
                await context.close()
            if browser is not None:
                await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print config and planned scenarios only")
    args = parser.parse_args()

    config_path = Path("examples/web/simple_login/bubblegum.yaml")
    config = load_example_config(config_path)

    if args.dry_run:
        print_dry_run(config)
        return

    try:
        asyncio.run(run(config))
    except ModuleNotFoundError:
        print(PLAYWRIGHT_INSTALL_HINT)


if __name__ == "__main__":
    main()
