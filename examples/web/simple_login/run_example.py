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

        await page.goto(login_url)

        step_open = await verify(
            "Open /login and confirm page is ready",
            page=page,
            channel="web",
            selector="body",
            assertion_type="visible",
        )
        print("open:", step_open.status)

        step_user = await act(
            'Type "tomsmith" into Username',
            page=page,
            channel="web",
            selector='input[name="username"]',
            value="tomsmith",
        )
        print("username:", step_user.status)

        step_pass = await act(
            'Type "SuperSecretPassword!" into Password',
            page=page,
            channel="web",
            selector='input[name="password"]',
            value="SuperSecretPassword!",
        )
        print("password:", step_pass.status)

        step_click = await act(
            "Click Login",
            page=page,
            channel="web",
            selector='button[type="submit"]',
        )
        print("click:", step_click.status)

        step_verify = await verify(
            'Verify success text: "You logged into a secure area!"',
            page=page,
            channel="web",
            selector='text="You logged into a secure area!"',
            assertion_type="text_visible",
            expected_value="You logged into a secure area!",
        )
        print("verify_text:", step_verify.status)

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
