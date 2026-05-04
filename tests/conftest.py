"""
tests/conftest.py
=================
Shared pytest configuration for all Bubblegum tests.

Flags:
  --llm     Enable integration tests that call a real LLM provider.
  --memory  Enable integration tests that write to SQLite on disk.
  --appium  Enable integration tests that require a real Appium server + device.
  --playwright  Enable tests that require a real Playwright/browser runtime.
  --e2e   Enable optional end-to-end tests.
"""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--llm",
        action="store_true",
        default=False,
        help="Run tests that call a real LLM provider (requires API key).",
    )
    parser.addoption(
        "--memory",
        action="store_true",
        default=False,
        help="Run tests that write to SQLite on disk.",
    )
    parser.addoption(
        "--appium",
        action="store_true",
        default=False,
        help="Run Appium integration tests (requires real Appium server + Android emulator).",
    )
    parser.addoption(
        "--playwright",
        action="store_true",
        default=False,
        help="Run tests that require Playwright/browser setup.",
    )
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="Run optional end-to-end tests.",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "llm: mark test as requiring a real LLM provider")
    config.addinivalue_line("markers", "memory: mark test as requiring SQLite on disk")
    config.addinivalue_line("markers", "appium: mark test as requiring a real Appium server")
    config.addinivalue_line("markers", "playwright: mark test as requiring Playwright/browser")
    config.addinivalue_line("markers", "e2e: mark optional end-to-end tests")


def pytest_collection_modifyitems(config, items):
    skip_llm    = pytest.mark.skip(reason="Pass --llm to run LLM integration tests")
    skip_memory = pytest.mark.skip(reason="Pass --memory to run memory integration tests")
    skip_appium = pytest.mark.skip(reason="Pass --appium to run Appium integration tests")
    skip_playwright = pytest.mark.skip(reason="Pass --playwright to run Playwright/browser tests")
    skip_e2e = pytest.mark.skip(reason="Pass --e2e to run e2e tests")

    for item in items:
        if "llm" in item.keywords and not config.getoption("--llm"):
            item.add_marker(skip_llm)
        if "memory" in item.keywords and not config.getoption("--memory"):
            item.add_marker(skip_memory)
        if "appium" in item.keywords and not config.getoption("--appium"):
            item.add_marker(skip_appium)
        if "playwright" in item.keywords and not config.getoption("--playwright"):
            item.add_marker(skip_playwright)
        if "e2e" in item.keywords and not config.getoption("--e2e"):
            item.add_marker(skip_e2e)
