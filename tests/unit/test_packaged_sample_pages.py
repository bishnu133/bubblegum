"""
PR4 — packaged sample pages.

The widget_lab and sample_app pages ship *inside* the package so the quickstart
fixtures work for `pip install bubblegum-ai` users with no repository checkout.
These tests guard that:
  - the page sets are actually bundled (importable as package data), and
  - the bundled copies stay byte-for-byte in sync with the canonical example
    pages in the repo (a dev checkout serves the example copies; pip users get
    the bundled copies — they must not drift).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bubblegum.testing.widget_lab import packaged_pages_dir

REPO_ROOT = Path(__file__).resolve().parents[2]

_PAGE_SETS = {
    "widget_lab": REPO_ROOT / "examples" / "web" / "widgets" / "widget_lab" / "pages",
    "sample_app": REPO_ROOT / "examples" / "web" / "real_local" / "pages",
}


@pytest.mark.parametrize("name", sorted(_PAGE_SETS))
def test_page_set_is_bundled_in_package(name: str):
    packaged = packaged_pages_dir(name)
    assert packaged is not None, f"{name} pages are not bundled in the package"
    assert any(packaged.glob("*.html")), f"{name} bundled dir has no HTML pages"


@pytest.mark.parametrize("name", sorted(_PAGE_SETS))
def test_bundled_pages_match_example_sources(name: str):
    example_dir = _PAGE_SETS[name]
    if not example_dir.is_dir():
        pytest.skip("example sources only present in a repository checkout")

    packaged = packaged_pages_dir(name)
    assert packaged is not None

    example_pages = {p.name: p.read_bytes() for p in example_dir.glob("*.html")}
    packaged_pages = {p.name: p.read_bytes() for p in packaged.glob("*.html")}

    assert set(packaged_pages) == set(example_pages), (
        f"{name}: bundled page set differs from examples — re-sync "
        f"bubblegum/testing/pages/{name}/ with {example_dir}"
    )
    drifted = [n for n in example_pages if packaged_pages[n] != example_pages[n]]
    assert not drifted, (
        f"{name}: bundled pages drifted from examples: {drifted}. "
        f"Re-copy them into bubblegum/testing/pages/{name}/."
    )
