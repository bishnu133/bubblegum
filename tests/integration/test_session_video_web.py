"""Engine-owned web sessions optionally record a video, toggled by env.

BUBBLEGUM_RECORD_VIDEO=1 makes default_session_factory create the context with
record_video_dir, so a .webm is written when the session closes. Off by default.
CDP-attach sessions never record (the caller's Playwright owns its context).

Runs against a real browser; skips when none is available.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.asyncio]

from bubblegum.bridge.sessions import OpenSpec, default_session_factory


async def _open(spec):
    try:
        return await default_session_factory(spec)
    except Exception as exc:  # pragma: no cover — no browser in this env
        pytest.skip(f"No usable browser for session factory: {exc}")


async def test_video_recorded_when_enabled(tmp_path, monkeypatch):
    pytest.importorskip("playwright.async_api")
    monkeypatch.setenv("BUBBLEGUM_RECORD_VIDEO", "1")
    monkeypatch.setenv("BUBBLEGUM_VIDEO_DIR", str(tmp_path / "vids"))
    opened = await _open(OpenSpec(channel="web", headless=True))
    try:
        await opened.session.act('nothing', dry_run=True) if hasattr(opened.session, "act") else None
    except Exception:
        pass
    await opened.aclose()   # flushes the video to disk
    videos = list((tmp_path / "vids").glob("*.webm"))
    assert videos, "no video file written when recording enabled"


async def test_no_video_by_default(tmp_path, monkeypatch):
    pytest.importorskip("playwright.async_api")
    monkeypatch.delenv("BUBBLEGUM_RECORD_VIDEO", raising=False)
    monkeypatch.setenv("BUBBLEGUM_VIDEO_DIR", str(tmp_path / "vids"))
    opened = await _open(OpenSpec(channel="web", headless=True))
    await opened.aclose()
    assert not (tmp_path / "vids").exists() or not list((tmp_path / "vids").glob("*.webm"))
