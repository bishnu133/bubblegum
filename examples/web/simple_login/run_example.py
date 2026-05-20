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

        browser = await browser_launcher.launch(headless=bool(config["headless"]))
        page = await browser.new_page()
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

            # Phase 22C: navigation handled directly by Playwright.
            await page.goto(login_url)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_selector('input[name="username"]')
            print("open: passed")

            step_user = await act(
                'Type "tomsmith" into Username',
                page=page,
                channel="web",
                selector='input[name="username"]',
                value="tomsmith",
            )
            print("username:", step_user.status)

            step_pass = await act(
                f'Type "{password}" into Password',
                page=page,
                channel="web",
                selector='input[name="password"]',
                value=password,
            )
            print("password:", step_pass.status)

            step_click = await act(
                "Click Login",
                page=page,
                channel="web",
                selector='button[type="submit"]',
            )
            print("click:", step_click.status)

            await page.wait_for_selector("#flash")

            step_verify = await verify(
                f'Verify result text: "{expected_text}"',
                page=page,
                channel="web",
                selector="#flash",
                assertion_type="text_visible",
                expected_value=expected_text,
            )

            verify_status = step_verify.status
            if verify_status != "passed":
                flash_text = await page.locator("#flash").inner_text()
                if expected_text in flash_text:
                    verify_status = "passed"
                    print(
                        "verify_text: passed "
                        "(Phase 22C fallback: direct Playwright text check; Bubblegum verify mapping to be improved in Phase 22D)"
                    )
                else:
                    print("verify_text:", step_verify.status)
            else:
                print("verify_text:", verify_status)

            statuses = ["passed", step_user.status, step_pass.status, step_click.status, verify_status]
            scenario_results[name] = "passed" if all(s == "passed" for s in statuses) else "failed"

        print("summary:")
        print("valid-login:", scenario_results.get("valid-login", "failed"))
        print("invalid-login:", scenario_results.get("invalid-login", "failed"))
        print("report path:", config["report_path"])

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
