# How to Use Bubblegum — Web (Playwright)

This is the **copy‑paste how‑to guide for the web channel**. Bubblegum is an
AI‑powered, natural‑language execution and self‑healing layer that sits on top of
your existing **Playwright** tests. You describe a step in plain English —
`"Click Login"`, `'Enter "tom" into Username'` — and Bubblegum finds the element,
performs the action, and heals the step when the UI drifts.

> Looking for the mobile (Appium) channel? See
> [`HOW_TO_USE_MOBILE.md`](HOW_TO_USE_MOBILE.md). The full combined reference is
> [`USER_GUIDE.md`](USER_GUIDE.md).

## Contents

- [Install](#install)
- [Hello, Bubblegum](#hello-bubblegum)
- [The four primitives](#the-four-primitives)
- [`BubblegumSession`](#bubblegumsession--the-ergonomic-wrapper)
- [Natural‑language grammar](#naturallanguage-grammar)
- [Web actions — every type](#web-actions--every-type)
- [Verify (assertions)](#verify-assertions)
- [Extract & state probes](#extract--state-probes)
- [iframes, nav‑wait, re‑grounding](#iframes-navwait-regrounding)
- [Dialogs & scopes](#dialogs--scopes)
- [`recover()` — heal an existing test](#recover--heal-an-existing-playwright-test)
- [Skip the UI login (auth bootstrap)](#skip-the-ui-login-auth-bootstrap)
- [Self‑healing & memory](#selfhealing--memory)
- [Vision / OCR (icon‑only targets)](#vision--ocr-icononly-targets)
- [pytest integration](#pytest-integration)
- [BDD (Gherkin)](#bdd-gherkin)
- [Configuration reference](#configuration-reference)
- [Quick recipes](#quick-recipes)

---

## Install

```bash
pip install "bubblegum-ai[web]"        # core + Playwright
python -m playwright install chromium  # one-time browser download

# Optional extras
pip install "bubblegum-ai[anthropic]"  # Claude LLM / vision grounding
pip install "bubblegum-ai[a11y]"       # accessibility assertions
pip install "bubblegum-ai[visual]"     # visual-regression assertions
pip install "bubblegum-ai[bdd]"        # pytest-bdd Gherkin steps
pip install "bubblegum-ai[all]"        # everything
```

Python **3.11+** is required. The web channel needs a Playwright **async** `Page`.

> **Using a TypeScript / JavaScript Playwright project?** Use the
> **`@bubblegum-ai/node`** client to call the same primitives from Node — see
> [`HOW_TO_USE_TYPESCRIPT.md`](HOW_TO_USE_TYPESCRIPT.md).

---

## Hello, Bubblegum

```python
import asyncio
from playwright.async_api import async_playwright
from bubblegum import act, verify

async def main():
    async with async_playwright() as p:
        page = await (await p.chromium.launch()).new_page()
        await page.goto("https://the-internet.herokuapp.com/login")

        await act('Enter "tomsmith" into Username', page=page)
        await act('Enter "SuperSecretPassword!" into Password', page=page)
        await act("Click Login", page=page)
        await verify("You logged into a secure area", page=page)

asyncio.run(main())
```

`channel` defaults to `"web"`, so you only pass `page=page`.

---

## The four primitives

Every test is built from four `async` functions. All return a `StepResult`.

| Primitive | What it does | Example |
| --- | --- | --- |
| `act` | Perform an action (click, type, select, …) | `await act("Click Login", page=page)` |
| `verify` | Assert a state holds | `await verify("Welcome is visible", page=page)` |
| `extract` | Read text from an element | `await extract("Get the order total", page=page)` |
| `recover` | Heal an existing test's stale selector | `await recover(page=page, failed_selector="#old", intent="Click Login")` |

### `StepResult` — what you get back

```python
r = await act("Click Login", page=page)
r.status        # "passed" | "recovered" | "failed" | "dry_run" | "skipped"
r.target.ref    # the locator Bubblegum resolved, e.g. role=button[name="Login"]
r.target.resolver_name   # which tier won: accessibility_tree / fuzzy_text / memory_cache / ...
r.confidence    # 0.0–1.0
r.target.metadata.get("extracted_value")   # for extract()
r.target.metadata.get("healing")           # set when self-healing substituted a label
r.error.message # when status == "failed"
```

`"recovered"` means the original locator/label drifted but Bubblegum still found
the right element — important for CI reporting so your team knows which steps to
de‑brittle.

---

## `BubblegumSession` — the ergonomic wrapper

So you don't repeat `page=` on every call, wrap the page once:

```python
from bubblegum import BubblegumSession

async with BubblegumSession.web(page) as s:
    await s.goto("https://your-app.test/login")
    await s.act('Enter "tom" into Username')
    await s.act("Click Login")
    await s.verify("You are logged in")
    s.assert_all_passed()      # raises if any step failed
    print(s.summary())         # {'total': 3, 'passed': 3, 'failed': 0, ...}
```

Session extras: `s.goto(url)`, `s.results()`, `s.summary()`,
`s.assert_all_passed()`, `s.print_plan()` (dry‑run), `s.explain(step)` (why a
step resolved the way it did), and state probes (`s.is_checked`,
`s.selected_value`, `s.is_visible`).

---

## Natural‑language grammar

Bubblegum parses the verb, the target, and any value from your sentence.

| You write | Action | Target | Value |
| --- | --- | --- | --- |
| `Click Login` | click | Login | — |
| `Enter "tom" into Username` | type | Username | tom |
| `Type "hello" in Search` | type | Search | hello |
| `Fill Email with "a@b.com"` *(BDD)* | type | Email | a@b.com |
| `Select "France" from Country` | select | Country | France |
| `Choose Blue radio button` | select | Blue | — |
| `Check Newsletter` | check | Newsletter | — |
| `Uncheck Remember me` | uncheck | Remember me | — |
| `Toggle Dark mode` | check (switch) | Dark mode | — |
| `Set Volume to 75` | set | Volume | 75 |
| `Upload "/tmp/cv.pdf" into Resume` | upload | Resume | /tmp/cv.pdf |
| `Scroll to Footer` | scroll | Footer | — |
| `Open the Settings tab` | click (tab) | Settings | — |
| `Verify Welcome is visible` | verify | Welcome | — |
| `Get the order total` | extract | order total | — |

**Tips**

- Put values in quotes so they're never confused with the target:
  `'Enter "Select All" into Notes'`.
- Add a widget word to disambiguate: `"Click the Sign in link"` prefers a link
  over a button; `"Choose Blue radio"` prefers a radio.
- Relational hints are understood: `"from the Country dropdown"`,
  `"in the confirmation modal"`, `"... for Acme Corp"` (same row).

---

## Web actions — every type

```python
await s.act("Click Login")                          # click / link / button
await s.act('Enter "tomsmith" into Username')       # type into a field
await s.act('Select "France" from Country')         # native <select> by visible label
await s.act("Check Newsletter")                     # tick a checkbox
await s.act("Uncheck Remember me")                  # untick a checkbox
await s.act("Toggle Dark mode")                     # ARIA switch
await s.act("Click Blue radio")                     # radio button
await s.act("Set Volume to 75")                     # slider / <input type=range>
await s.act('Upload "/tmp/resume.pdf" into Resume') # file input
await s.act("Scroll to Footer")                     # scroll element into view
await s.act("Open the Billing tab")                 # tabs
await s.act("Expand Shipping section")              # accordion
```

**Select by label (not value).** `Select "France" from Country` works even when
the option is `<option value="FR">France</option>` — Bubblegum matches the
visible label, falling back from the value automatically.

### Explicit selector / action overrides

Natural language is the default, but you can always be explicit:

```python
await s.act("Click first checkbox", selector="input[type=checkbox]:first-of-type")
await s.act("Submit", action_type="click")           # force the action
await s.act("Set quantity", action_type="type", value="5", selector="#qty")
```

---

## Verify (assertions)

```python
await s.verify("Welcome back is visible")                                  # default: text on page
await s.verify("Dashboard", assertion_type="text_visible", expected_value="Dashboard")
await s.verify("URL changed", assertion_type="page_transition", expected_value="/home")
await s.verify("Save button", assertion_type="element_state", expected_value="#save")
```

`assertion_type` options (web): `text_visible` (default), `element_state` (a CSS
selector is visible), `page_transition` (URL contains a fragment), `a11y`
(accessibility audit), `network` (a backend call happened).

### Network assertions

UI text alone can't prove the backend did the thing. Assert on the network call —
method + URL + status (any part may be omitted):

```python
await s.act("Click Sign in")
await s.verify("login call succeeded",
               assertion_type="network", expected_value="POST /api/login 200")
```

The URL part is a substring or glob (`/api/users/*`).

### Accessibility (a11y) assertions

```python
await s.verify("page has no critical a11y violations", assertion_type="a11y")
```

Bubblegum injects [axe-core](https://github.com/dequelabs/axe-core) (vendored,
offline) and audits the whole page. The failing severity is read from the
instruction (`critical`/`serious`/`moderate`/`minor`) or set with
`expected_value="serious"`. Install with `pip install "bubblegum-ai[a11y]"`.

### Soft assertions

A failing `verify` is recorded and surfaced together at `assert_all_passed()` —
it does not stop the test on the spot:

```python
with s.soft_assertions():
    await s.verify("Total is $42")
    await s.verify("Cart shows 3 items")
    await s.verify("Discount applied")
s.assert_all_passed()   # raises once, listing all soft failures
```

---

## Extract & state probes

```python
r = await s.extract("Get the flash message")
print(r.target.metadata["extracted_value"])
# Works across iframes. Need a non-semantic element? Pass a selector:
r = await s.extract("Get the banner", selector="#flash")
```

Read widget state directly, by natural language:

```python
await s.is_checked("Newsletter")        # True/False
await s.selected_value("Country")       # current <select>/<input> value, e.g. "FR"
await s.is_visible("Welcome banner")    # True/False
```

---

## iframes, nav‑wait, re‑grounding

**iframes (same‑origin)** are discovered automatically — Bubblegum merges each
child frame's accessibility tree and routes the action into the owning frame. No
special syntax:

```python
await page.goto(".../checkout.html")     # has a payment <iframe>
await s.act("Click Pay Now")             # button lives inside the iframe
```

**Bounded navigation wait.** After a click, Bubblegum briefly waits to see if a
navigation commits, then moves on, so a plain AJAX/SPA button no longer burns a
fixed 5 s:

```python
await s.act("Add to cart", nav_wait_ms=1500)   # default 1000ms; 0 = skip the probe
```

**Re‑grounding for late‑rendered (SPA) elements.** If a target renders a beat
after the page settles, Bubblegum re‑collects and retries instead of failing:

```python
await s.act("Click the lazy-loaded Continue", resolve_retries=4)
```

**Stability wait (anti‑flake)** is on by default — before each step Bubblegum
waits for no in‑flight network, a DOM quiet window, and no visible spinner. Tune
it in `bubblegum.yaml` (`stability_wait_enabled`, `stability_quiet_ms`,
`stability_timeout_ms`) or per call: `await s.act("Click Continue", stability_wait=False)`.

---

## Dialogs & scopes

When a modal is open, scope steps to it and close it cleanly:

```python
s.push_scope("dialog", label="Confirm delete")
await s.act("Click Delete")          # resolved within the dialog
await s.close_dialog()               # clicks close/cancel/×, or presses Escape
```

---

## `recover()` — heal an existing Playwright test

Drop Bubblegum into a legacy test only where a selector breaks:

```python
from bubblegum import recover

# Your old line: await page.click("#login-btn")   # selector now stale
r = await recover(page=page, failed_selector="#login-btn", intent="Click Login")
# r.status == "passed" if the selector still works, "recovered" if Bubblegum healed it
```

This is the lowest‑friction way to adopt Bubblegum — you get value before writing
a single new natural‑language step.

---

## Skip the UI login (auth bootstrap)

Logging in through the UI on every test is the biggest source of slowness and
flakiness. Pass a `bootstrap` callable that establishes authenticated state via
API (inject cookies / `localStorage` / token) and start each test already
authenticated:

```python
async def login(page):
    token = await get_token_via_api("tester", "pw!")     # your API call
    await page.context.add_cookies(
        [{"name": "session", "value": token, "url": "https://your-app.test"}]
    )

async with BubblegumSession.web(page, bootstrap=login) as s:
    await s.goto("https://your-app.test/dashboard")       # already authed
    await s.verify("Dashboard is visible")
```

See `examples/web/auth_bootstrap/`.

---

## Self‑healing & memory

If your step says `"Login"` but the page now says `"Sign In"`, the fuzzy tier
heals it: the step still passes but is marked **`recovered`** and carries a
`healing` advisory:

```python
r = await s.act("Click Login")          # page actually says "Sign In"
if r.status == "recovered":
    h = r.target.metadata["healing"]
    print(h["requested"], "→", h["matched"], f"({h['severity']})")
    # login → Sign In (review)
```

`severity` is `info` for a benign typo/case fix, `review` for a semantic
substitution worth a human glance. Each heal also includes a **suggested fix**
(old→new label/selector). Export them and a brittleness ranking with
`--bubblegum-suggest-fixes fixes.json`.

**Memory cache.** Successful resolutions persist to `.bubblegum/memory.db`. On
the next run the memory cache replays the same element instantly (you'll see
`resolver=memory_cache`). Entries expire by TTL (default 7 days) and
self‑invalidate after repeated failures. Delete the file for a cold run.

---

## Vision / OCR (icon‑only targets)

When a control has **no accessible name** (an icon‑only button), the
deterministic tiers can't match it. Register a vision provider and Bubblegum's AI
tier reads the screenshot:

```python
from bubblegum import configure_vision_provider
from bubblegum.core.vision.engine import FakeVisionProvider  # or a Claude-backed provider

configure_vision_provider(FakeVisionProvider())
await s.act("Click the settings icon", max_cost_level="high")
```

Vision is opt‑in (it sends a screenshot to a model):

```yaml
grounding:
  enable_vision: true
  max_cost_level: high
privacy:
  send_screenshots: true
  process_screenshots_for_vision: true
```

Anthropic (Claude) and OpenAI backends ship in `bubblegum.core.vision.backends`.

---

## pytest integration

Use the `bubblegum_web` fixture (auto‑launches Chromium) and the bundled
`widget_lab` / `sample_app` demo servers:

```python
import pytest

@pytest.mark.asyncio
@pytest.mark.bubblegum
async def test_login(bubblegum_web, sample_app):
    await bubblegum_web.goto(f"{sample_app}/login.html")
    await bubblegum_web.act('Enter "admin" into Username')
    await bubblegum_web.act('Enter "admin" into Password')
    await bubblegum_web.act("Click Login")
    await bubblegum_web.verify("Dashboard is visible")
    bubblegum_web.assert_all_passed()
```

Run with reports and a visible browser:

```bash
pytest --bubblegum-headed \
       --bubblegum-report report.html \
       --bubblegum-report-json report.json \
       --bubblegum-config bubblegum.yaml
```

A screenshot is written to `artifacts/<test>-final.png` automatically on failure.

---

## BDD (Gherkin)

`pip install "bubblegum-ai[bdd]"`, then write plain‑English `.feature` files:

```gherkin
# login.feature
Feature: Login
  Scenario: Valid login
    Given I am on the login page
    When I enter "tom" into "Username"
    And I click "Login"
    Then I should see "Dashboard"
```

```python
# test_login_bdd.py
from pytest_bdd import scenarios, given
from bubblegum.bdd.steps import *                       # When/Then bindings
from bubblegum.bdd.fixtures import bubblegum_web, bubblegum_bdd_loop  # noqa: F401

scenarios("login.feature")

@given("I am on the login page")
def _open(bubblegum_web, bubblegum_bdd_loop, sample_app):
    bubblegum_bdd_loop.run_until_complete(bubblegum_web.goto(f"{sample_app}/login.html"))
```

---

## Configuration reference

Place `bubblegum.yaml` in your project root (auto‑loaded), or pass
`--bubblegum-config PATH` / `configure_runtime(config_path=...)`. Everything has a
sensible default — zero config works out of the box.

```yaml
grounding:
  accept_threshold: 0.85          # Tier-1 auto-accept score
  review_threshold: 0.70          # "proceed with warning" band
  ambiguous_gap: 0.05             # min lead before two candidates are "ambiguous"
  max_cost_level: medium          # low | medium | high  (high enables vision/LLM)
  enable_vision: false            # AI vision tier
  enable_ocr: true                # OCR tier
  ai_first: false                 # try the AI tier *before* deterministic tiers
  memory_ttl_days: 7              # cache entry lifetime
  memory_max_failures: 3          # auto-invalidate after N failures
  resolve_retries: 2              # re-ground attempts for late-rendered elements
  resolve_retry_interval_ms: 300

ai:
  enabled: true
  provider: anthropic             # anthropic | openai | gemini | local
  model: <your-model-name>        # set explicitly; no surprise API costs

privacy:
  redact_pii: true
  send_screenshots: false         # must be true for the vision tier
  process_screenshots_for_vision: false
  process_screenshots_for_ocr: false
```

### Per‑call options (kwargs on `act`/`verify`/`extract`)

| kwarg | Applies to | Meaning |
| --- | --- | --- |
| `selector` | all | Explicit CSS/XPath to use/fall back to |
| `action_type` | act | Force `click`/`type`/`select`/… |
| `value` / `input_value` | act | Value to type/select |
| `target_phrase` | all | Override the parsed target |
| `timeout_ms` | all | Per‑action timeout (default 10000) |
| `nav_wait_ms` | act | Post‑click navigation probe budget (default 1000; 0 = skip) |
| `resolve_retries` | all | Re‑ground attempts for late renders (default 2) |
| `max_cost_level` | all | `low`/`medium`/`high` — gates the AI tier |
| `dry_run` | all | Resolve only, don't execute |
| `assertion_type` | verify | `text_visible` / `element_state` / `page_transition` / `a11y` / `network` |
| `expected_value` | verify | Expected text/fragment/selector |
| `wait_for` | act | Wait for `visible` / `attached` / `enabled` before acting |

### Runtime configuration in code

```python
from bubblegum import configure_runtime
from bubblegum.core.config import BubblegumConfig

cfg = BubblegumConfig.load()       # or BubblegumConfig() for all-defaults
cfg.ai.enabled = False             # deterministic-only, no API key needed
configure_runtime(config=cfg)
```

---

## Quick recipes

**Deterministic‑only (no API key, fastest):** set `ai.enabled: false` or
`max_cost_level: low`. All Tier‑1/2 features (text, fuzzy, synonyms, memory,
healing) still work.

**Cold run (ignore cache):** delete `.bubblegum/memory.db`.

**See what would happen:** wrap steps in `BubblegumSession.web(page, dry_run=True)`
and call `s.print_plan()`.

**Explain a wrong pick:** `await s.explain("Click Login")` prints the ranked
candidates, per‑signal score breakdown, the tier it stopped at, and the winner's
lead over the runner‑up.
