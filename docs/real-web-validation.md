# Real-web validation runbook (pre-release)

Run this on a machine with a browser (your Mac) before releasing. It exercises
every feature added in this branch against real Chromium. CI proves the logic
with mocks; this proves it end-to-end.

## 0. Setup

```bash
pip install -e ".[web,test,anthropic,bdd]"
python -m playwright install chromium
```

## 1. Full unit + integration suite (no browser)

```bash
pytest -q
# expect: all passed, ~79 skipped (the --playwright/real_env gated tests)
```

## 2. Live widget + sample-app flows (real Chromium)

```bash
pytest tests/integration/ --playwright -q
```
This runs the production NL flow against real pages, including:
- `test_phase22e9_sample_app.py` — login → dashboard → settings round trip
- `test_phase22e5_tier2_widgets.py` — tabs / accordion / slider
- `test_nameless_combobox_web.py` — **PR6**: opens + selects from a combobox
  with no accessible name ("Open the fruit dropdown" → "Click Banana")

## 3. Self-healing advisory on a real page (PR2)

The sample login button says **"Sign in"**. Drive it with a step that says
**"login"** and confirm the step is marked `recovered` with a healing advisory.

```bash
python - <<'PY'
import asyncio
from playwright.async_api import async_playwright
from bubblegum.session import BubblegumSession
from bubblegum.testing.widget_lab import find_pages_dir, start_widget_lab_server

async def main():
    server, base = start_widget_lab_server(find_pages_dir(rel="examples/web/real_local/pages"))
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        s = BubblegumSession.web(page)
        await s.goto(f"{base}/login.html")
        await s.act('Enter "tester" into Username')
        await s.act('Enter "bubblegum!" into Password')
        r = await s.act("Click login")          # page only has "Sign in"
        print("status:", r.status)              # expect: recovered
        print("healing:", r.target.metadata.get("healing"))  # advisory dict
        await browser.close()
    server.shutdown()
asyncio.run(main())
PY
```
Expect `status: recovered` and a `healing` advisory naming requested `login` →
matched `Sign in`, severity `review`.

## 4. AI-first + Claude vision grounding (PR3) — needs an API key

This is the one paid path. It grounds an element from a **screenshot** via
Claude and resolves AI-first (AI tier before the deterministic tiers).

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python - <<'PY'
import asyncio
from playwright.async_api import async_playwright
from bubblegum.core import sdk
from bubblegum.core.config import BubblegumConfig
from bubblegum.core.vision import AnthropicVisionProvider
from bubblegum.session import BubblegumSession
from bubblegum.testing.widget_lab import find_pages_dir, start_widget_lab_server

async def main():
    # Enable vision + AI-first + screenshot privacy opt-ins.
    cfg = BubblegumConfig.load()
    cfg.grounding.enable_vision = True
    cfg.grounding.ai_first = True
    cfg.grounding.max_cost_level = "high"
    cfg.privacy.send_screenshots = True
    cfg.privacy.process_screenshots_for_vision = True
    sdk.configure_runtime(cfg)
    sdk.configure_vision_provider(AnthropicVisionProvider(create_client=True))  # claude-opus-4-8

    server, base = start_widget_lab_server(find_pages_dir(rel="examples/web/real_local/pages"))
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        s = BubblegumSession.web(page)
        await s.goto(f"{base}/login.html")
        r = await s.act("Click the Sign in button")
        print("status:", r.status, "resolver:", r.target.resolver_name if r.target else None)
        await browser.close()
    server.shutdown()
    sdk.clear_vision_provider()
asyncio.run(main())
PY
```
Expect a successful click. Note: AI-first only reorders when the AI tier can
run; if the deterministic tier already nails it, that's fine — the point is the
vision provider wiring works without error and the screenshot path is exercised.
Watch for any provider diagnostic (the backend is fail-safe and returns no
candidates on error, so check `AnthropicVisionProvider().get_last_diagnostic()`
if vision never contributes).

## 5. BDD (PR5) — plain-English Given/When/Then

```bash
pytest examples/web/bdd/ --playwright -q
```
Runs `login.feature` through the `bubblegum.bdd` When/Then steps.

## Sign-off

- [ ] §1 unit suite green
- [ ] §2 widget/sample-app + nameless combobox green
- [ ] §3 healing advisory observed (`recovered` + advisory)
- [ ] §4 Claude vision path runs without error
- [ ] §5 BDD scenarios pass

When all are checked, proceed to TestPyPI → PyPI (see `RELEASE_CHECKLIST.md`).
