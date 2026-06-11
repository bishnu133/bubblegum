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
        # Observe whether the vision tier actually ran and what it returned:
        for t in r.traces:
            print(f"  trace: {t.resolver_name} -> {len(t.candidates)} candidate(s)")
        await browser.close()
    server.shutdown()
    sdk.clear_vision_provider()
asyncio.run(main())
PY
```
Expect a successful click. The `trace:` lines show which resolvers ran — with
AI-first you should see `vision_model` run first. On a page where the target has
a clean accessible name ("Sign in"), the deterministic tier may still win even
though vision ran; that's expected. The bar for this check is: **the vision
provider wiring runs without error and `vision_model` appears in the traces**.
To see the vision tier actually *win*, point it at a deterministic-hard target
(an icon/image button with no text). If vision never returns candidates, the
backend is fail-safe — inspect `provider.get_last_diagnostic()` for the reason.

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
