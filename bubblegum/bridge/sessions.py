"""
bubblegum/bridge/sessions.py
============================
Server-side session registry for the bridge.

The wire protocol cannot ship a live Playwright ``Page`` or Appium ``WebDriver``
to a non-Python client, so the **engine owns the runtime handle**: the client
calls ``session.open`` to get a string ``session_id`` and then passes that id on
every subsequent call. :class:`SessionManager` maps ids to opened
:class:`~bubblegum.session.BubblegumSession` instances plus a teardown.

Session construction goes through an injectable ``factory`` so unit tests can
register fake sessions with no browser/device. The default factory
(:func:`default_session_factory`) lazily launches Playwright (web) or builds an
Appium driver (mobile), mirroring the ``bubblegum repl`` launchers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from bubblegum.bridge import protocol as p


@dataclass
class OpenSpec:
    """Normalized arguments for ``session.open``."""

    channel: str = "web"
    url: str | None = None
    headless: bool = True
    dry_run: bool = False
    appium_url: str | None = None
    capabilities: dict[str, Any] | None = None

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> "OpenSpec":
        channel = params.get("channel", "web")
        if channel not in ("web", "mobile"):
            raise p.BridgeError(p.INVALID_PARAMS, f"unknown channel: {channel!r}")
        return cls(
            channel=channel,
            url=params.get("url"),
            headless=bool(params.get("headless", True)),
            dry_run=bool(params.get("dry_run", False)),
            appium_url=params.get("appium_url"),
            capabilities=params.get("capabilities"),
        )


@dataclass
class OpenedSession:
    """A live session plus the coroutine that releases its runtime handle."""

    session: Any                      # a BubblegumSession (entered)
    aclose: Callable[[], Awaitable[None]]


# A factory turns an OpenSpec into an entered OpenedSession.
SessionFactory = Callable[[OpenSpec], Awaitable[OpenedSession]]


class SessionManager:
    """Owns the set of open sessions, keyed by id."""

    def __init__(self, factory: SessionFactory | None = None) -> None:
        self._factory = factory or default_session_factory
        self._sessions: dict[str, OpenedSession] = {}

    async def open(self, spec: OpenSpec) -> str:
        opened = await self._factory(spec)
        session_id = uuid.uuid4().hex
        self._sessions[session_id] = opened
        return session_id

    def get(self, session_id: str | None):
        """Return the live BubblegumSession for ``session_id`` or raise."""
        if not session_id or session_id not in self._sessions:
            raise p.BridgeError(
                p.SESSION_NOT_FOUND, f"no open session: {session_id!r}"
            )
        return self._sessions[session_id].session

    async def close(self, session_id: str | None) -> None:
        if not session_id or session_id not in self._sessions:
            raise p.BridgeError(
                p.SESSION_NOT_FOUND, f"no open session: {session_id!r}"
            )
        opened = self._sessions.pop(session_id)
        await opened.aclose()

    async def close_all(self) -> None:
        """Tear down every open session (best-effort; used on shutdown)."""
        for session_id in list(self._sessions):
            opened = self._sessions.pop(session_id)
            try:
                await opened.aclose()
            except Exception:  # noqa: BLE001 — shutdown is best-effort
                pass


async def default_session_factory(spec: OpenSpec) -> OpenedSession:
    """Launch a real web/mobile session, mirroring the ``repl`` launchers.

    Imports of Playwright/Appium are deferred so merely importing the bridge
    never requires the optional channel dependencies.
    """
    from bubblegum.session import BubblegumSession

    if spec.channel == "web":
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise p.BridgeError(
                p.UNSUPPORTED,
                'web channel needs Playwright — install "bubblegum-ai[web]" '
                "and run `python -m playwright install chromium`",
            ) from exc

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=spec.headless)
        context = await browser.new_context()
        page = await context.new_page()
        if spec.url:
            await page.goto(spec.url)
        session = await BubblegumSession.web(page, dry_run=spec.dry_run).__aenter__()

        async def aclose() -> None:
            try:
                await session.__aexit__(None, None, None)
            finally:
                await browser.close()
                await pw.stop()

        return OpenedSession(session=session, aclose=aclose)

    # mobile
    try:
        from bubblegum.testing.appium_driver import create_appium_driver
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise p.BridgeError(
            p.UNSUPPORTED,
            'mobile channel needs the Appium client — install "bubblegum-ai[mobile]"',
        ) from exc

    if not spec.appium_url:
        raise p.BridgeError(p.INVALID_PARAMS, "mobile session needs 'appium_url'")
    driver = create_appium_driver(spec.appium_url, spec.capabilities or {})
    session = await BubblegumSession.mobile(driver, dry_run=spec.dry_run).__aenter__()

    async def aclose() -> None:
        try:
            await session.__aexit__(None, None, None)
        finally:
            try:
                driver.quit()
            except Exception:  # noqa: BLE001
                pass

    return OpenedSession(session=session, aclose=aclose)
