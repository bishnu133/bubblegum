# How to Use Bubblegum — Mobile (Appium)

This is the **copy‑paste how‑to guide for the mobile channel**. Bubblegum is an
AI‑powered, natural‑language execution and self‑healing layer that sits on top of
your existing **Appium** tests (Android + iOS, native and hybrid). You describe a
step in plain English — `"Tap Login"`, `'Enter "tom" into Username'` — and
Bubblegum finds the element, performs the action, and heals the step when the UI
drifts.

> Looking for the web (Playwright) channel? See
> [`HOW_TO_USE_WEB.md`](HOW_TO_USE_WEB.md). The full combined reference is
> [`USER_GUIDE.md`](USER_GUIDE.md).

## Contents

- [Install & prerequisites](#install--prerequisites)
- [Hello, Bubblegum (mobile)](#hello-bubblegum-mobile)
- [The four primitives](#the-four-primitives)
- [`BubblegumSession.mobile`](#bubblegumsessionmobile--the-ergonomic-wrapper)
- [Natural‑language grammar](#naturallanguage-grammar)
- [Mobile actions](#mobile-actions)
- [Verify & extract](#verify--extract)
- [Icons, scroll discovery & repeated rows](#icons-scroll-discovery--repeated-rows)
- [System dialogs (permissions / alerts)](#system-dialogs-permissions--alerts)
- [Hybrid apps & WebView switching](#hybrid-apps--webview-switching)
- [Network‑condition simulation](#networkcondition-simulation)
- [Device cloud (BrowserStack / Sauce / LambdaTest / pCloudy)](#device-cloud)
- [`recover()` on mobile](#recover-on-mobile)
- [Skip the UI login (auth bootstrap)](#skip-the-ui-login-auth-bootstrap)
- [Self‑healing & memory](#selfhealing--memory)
- [pytest integration](#pytest-integration)
- [Configuration reference](#configuration-reference)
- [Quick recipes](#quick-recipes)

---

## Install & prerequisites

```bash
pip install "bubblegum-ai[mobile]"     # core + Appium-Python-Client

# Optional extras
pip install "bubblegum-ai[anthropic]"  # Claude LLM / vision grounding
pip install "bubblegum-ai[all]"        # everything
```

Python **3.11+** is required. Unlike the web channel, the mobile channel is **not
self‑contained** — you supply the real environment:

- a running **Appium server** (e.g. `appium` on `http://127.0.0.1:4723`),
- a running **emulator/simulator or physical device**,
- the **target app** installed (or an `.apk` / `.app` / `.ipa` path in caps),
- valid **Appium capabilities** (`platformName`, device, app, automation engine).

The mobile channel needs an Appium `WebDriver` instance. Element resolution uses
the Appium UI hierarchy (and, when enabled, OCR/vision over screenshots).

---

## Hello, Bubblegum (mobile)

```python
import asyncio
from appium import webdriver
from appium.options.android import UiAutomator2Options
from bubblegum import BubblegumSession

async def main():
    opts = UiAutomator2Options()
    opts.platform_name = "Android"
    opts.device_name = "emulator-5554"
    opts.app = "/path/to/app.apk"
    driver = webdriver.Remote("http://127.0.0.1:4723", options=opts)

    try:
        async with BubblegumSession.mobile(driver) as s:
            await s.act('Enter "tom" into Username')
            await s.act("Tap Login")
            await s.verify("Welcome")
            s.assert_all_passed()
    finally:
        driver.quit()

asyncio.run(main())
```

Or call the primitives directly with `channel="mobile", driver=driver`:

```python
from bubblegum import act
await act("Tap Login", channel="mobile", driver=driver)
```

iOS is the same shape with `XCUITestOptions` and `platform_name = "iOS"`.

---

## The four primitives

Every test is built from four `async` functions. All return a `StepResult`.

| Primitive | What it does | Example |
| --- | --- | --- |
| `act` | Perform an action (tap, type, scroll, swipe) | `await act("Tap Login", channel="mobile", driver=driver)` |
| `verify` | Assert a state holds | `await verify("Welcome", channel="mobile", driver=driver)` |
| `extract` | Read text from an element | `await extract("Get the balance", channel="mobile", driver=driver)` |
| `recover` | Heal an existing test's stale locator | `await recover(driver=driver, channel="mobile", failed_selector="//*[@id='old']", intent="Tap Login")` |

### `StepResult` — what you get back

```python
r = await act("Tap Login", channel="mobile", driver=driver)
r.status        # "passed" | "recovered" | "failed" | "dry_run" | "skipped"
r.target.ref    # the locator Bubblegum resolved
r.target.resolver_name   # which tier won: appium_hierarchy / fuzzy_text / memory_cache / ...
r.confidence    # 0.0–1.0
r.target.metadata.get("extracted_value")   # for extract()
r.target.metadata.get("healing")           # set when self-healing substituted a label
r.error.message # when status == "failed"
```

`"recovered"` means the original locator/label drifted but Bubblegum still found
the right element — surface it in CI so your team knows which steps to de‑brittle.

---

## `BubblegumSession.mobile` — the ergonomic wrapper

So you don't repeat `driver=`/`channel=` on every call, wrap the driver once:

```python
from bubblegum import BubblegumSession

async with BubblegumSession.mobile(driver) as s:
    await s.act('Enter "tom" into Username')
    await s.act("Tap Login")
    await s.verify("Welcome")
    s.assert_all_passed()
    print(s.summary())
```

Session extras: `s.results()`, `s.summary()`, `s.assert_all_passed()`,
`s.print_plan()` (dry‑run), `s.explain(step)` (why a step resolved the way it
did), and `s.is_visible(target)`.

---

## Natural‑language grammar

The same phrasing grammar works on web and mobile. Bubblegum parses the verb, the
target, and any value from your sentence.

| You write | Action | Target | Value |
| --- | --- | --- | --- |
| `Tap the Menu button` | tap | Menu | — |
| `Click Login` | tap | Login | — |
| `Enter "tom" into Username` | type | Username | tom |
| `Type "hello" in Search` | type | Search | hello |
| `Scroll to Settings` | scroll | Settings | — |
| `Swipe the banner` *(+ `action_type="swipe"`)* | swipe | banner | left/right/up/down |
| `Verify Welcome is visible` | verify | Welcome | — |
| `Get the account balance` | extract | account balance | — |

**Tips**

- Put values in quotes so they're never confused with the target:
  `'Enter "Submit" into Notes'`.
- Relational hints are understood: `'Tap Delete for "Groceries"'` (same row),
  `"in the confirmation dialog"`.

---

## Mobile actions

```python
await s.act("Tap Login")                      # tap (alias: click)
await s.act('Enter "tom" into Username')      # type into a field
await s.act("Scroll to Settings")             # scroll the target into view

# Swipe is driven explicitly — direction is the value (up/down/left/right):
await s.act("Swipe the banner", action_type="swipe", value="left")
```

> Web‑specific actions (`select`, `check/uncheck`, `upload`, `set` sliders) are
> **not** part of the mobile dispatch — use `tap` / `type` / `scroll` / `swipe`,
> which cover native controls. `tap`, `type` and `scroll` are inferred from plain
> English; `swipe` is requested with `action_type="swipe"` as shown above.

### Explicit locator / action overrides

```python
await s.act("Tap Submit", selector="//*[@text='Submit']")  # explicit XPath fallback
await s.act("Tap the row", action_type="tap")              # force the action
```

---

## Verify & extract

```python
await s.verify("Welcome", assertion_type="text_visible")     # page_source contains text
await s.verify("Home screen", assertion_type="activity", expected_value=".HomeActivity")
await s.verify("Save", assertion_type="element_state", expected_value="//*[@text='Save']")

r = await s.extract("Get the account balance")
print(r.target.metadata["extracted_value"])
```

`assertion_type` options (mobile): `text_visible` (default), `element_state`
(an XPath is displayed), `activity` (current activity / bundle id contains a
fragment).

Soft assertions work the same as web:

```python
with s.soft_assertions():
    await s.verify("Balance shown")
    await s.verify("Logout visible")
s.assert_all_passed()
```

---

## Icons, scroll discovery & repeated rows

Bubblegum's mobile resolution understands common native patterns without you
writing locators:

```python
await s.act("Tap the search icon")            # icon detection (no text label)
await s.act("Scroll down to Privacy Policy")  # scroll-discovery finds off-screen targets
await s.act('Tap Delete for "Groceries"')     # repeated rows: the Delete in the Groceries row
```

A UI **framework detector** (Compose / Flutter / React Native / SwiftUI) informs
resolution so the hierarchy is interpreted correctly per stack.

---

## System dialogs (permissions / alerts)

OS permission and alert dialogs are detected, and you act on their buttons by the
visible label — the same `act` you use everywhere:

```python
await s.act("Tap Allow")                       # accept a permission prompt
await s.act("Tap While using the app")
await s.act("Tap Cancel")                      # dismiss an alert
```

Detection is guard‑railed so Bubblegum only treats recognised, safe system
dialogs specially.

---

## Hybrid apps & WebView switching

For hybrid screens (a WebView embedded in a native app), Bubblegum can switch
into the WebView context to resolve web content, then restore the native context.
This is **opt‑in** and fail‑closed. Enable it in config:

```yaml
webview_switching:
  enable_webview_switching: true
  webview_switching_mode: opt_in          # off | dry_run | opt_in
  webview_switch_allowed_operations: ["extract_text", "validate"]
  require_restore_context: true
  webview_context_selection_policy: single_webview_only
```

Start with `validate` / `extract_text` (read‑only, lowest risk) before allowing
action routing. See [`mobile-frameworks.md`](mobile-frameworks.md) and the
WebView design docs for the full opt‑in model.

---

## Network‑condition simulation

You can drive flaky‑network scenarios (offline, 2G/3G, latency) against the device
during a test. See [`mobile-network-conditions.md`](mobile-network-conditions.md)
for the supported profiles and the per‑step API.

---

## Device cloud

Bubblegum runs against real‑device clouds — **BrowserStack**, **Sauce Labs**,
**LambdaTest**, and **pCloudy** — by pointing the Appium `WebDriver` at the
provider's hub URL and capabilities. The session/primitives are unchanged; only
driver construction differs. See [`mobile-cloud.md`](mobile-cloud.md) for the
per‑provider capability blocks and credentials handling.

---

## `recover()` on mobile

Drop Bubblegum into a legacy Appium test only where a locator breaks:

```python
from bubblegum import recover

# Your old line: driver.find_element(AppiumBy.XPATH, "//*[@id='login-btn']")  # now stale
r = await recover(
    driver=driver,
    channel="mobile",
    failed_selector="//*[@id='login-btn']",
    intent="Tap Login",
)
# r.status == "passed" if the locator still works, "recovered" if Bubblegum healed it
```

This is the lowest‑friction way to adopt Bubblegum — value before writing a single
new natural‑language step.

---

## Skip the UI login (auth bootstrap)

Pass a `bootstrap` callable that establishes authenticated state via API
(deep‑link or inject a token) so each test starts already authenticated. It runs
once on session entry and receives the `driver`:

```python
async def login(driver):
    token = await get_token_via_api("tester", "pw!")     # your API call
    driver.execute_script("mobile: deepLink", {"url": f"myapp://auth?token={token}"})

async with BubblegumSession.mobile(driver, bootstrap=login) as s:
    await s.verify("Dashboard")
```

Bubblegum stays provider‑agnostic — you supply the API/deep‑link call.

---

## Self‑healing & memory

Identical to web: a fuzzy/synonym substitution marks the step `recovered` with a
`healing` advisory, and successful resolutions are cached (keyed on a
mobile‑specific screen signature) so later runs replay instantly.

```python
r = await s.act("Tap Login")            # screen actually says "Sign In"
if r.status == "recovered":
    h = r.target.metadata["healing"]
    print(h["requested"], "→", h["matched"], f"({h['severity']})")
```

Late‑rendered elements benefit from the same re‑grounding retry. Memory persists
to `.bubblegum/memory.db`; delete it for a cold run. On mobile, the stability wait
treats the screen as "settled" when the Appium UI hierarchy stops changing for the
quiet window.

---

## pytest integration

Use the `bubblegum_mobile` fixture; pass the Appium server and capabilities on the
command line:

```python
import pytest

@pytest.mark.asyncio
@pytest.mark.bubblegum
async def test_mobile_login(bubblegum_mobile):
    await bubblegum_mobile.act('Enter "tom" into Username')
    await bubblegum_mobile.act("Tap Login")
    await bubblegum_mobile.verify("Welcome")
    bubblegum_mobile.assert_all_passed()
```

```bash
pytest --bubblegum-appium-url http://127.0.0.1:4723 \
       --bubblegum-capabilities caps.json \
       --bubblegum-report report.html
```

`caps.json` must include `platformName` (and your device/app fields). The fixture
**skips cleanly** when Appium isn't installed, no capabilities are given, or the
server is unreachable. A failure screenshot is captured via the driver.

See `examples/appium_quickstart.py` and the Appium onboarding notes in
`examples/README.md` for real‑environment prerequisites and common startup
failures.

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
  enable_vision: false            # AI vision tier (screenshot → model)
  enable_ocr: true                # OCR tier
  memory_ttl_days: 7
  memory_max_failures: 3
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

webview_switching:                # hybrid apps (see WebView section)
  enable_webview_switching: false
  webview_switching_mode: off     # off | dry_run | opt_in
```

### Per‑call options (kwargs on `act`/`verify`/`extract`)

| kwarg | Applies to | Meaning |
| --- | --- | --- |
| `selector` | all | Explicit XPath/accessibility id to use/fall back to |
| `action_type` | act | Force `tap`/`type`/`scroll`/`swipe` |
| `value` / `input_value` | act | Value to type, or swipe direction |
| `target_phrase` | all | Override the parsed target |
| `timeout_ms` | all | Per‑action timeout (default 10000) |
| `resolve_retries` | all | Re‑ground attempts for late renders (default 2) |
| `max_cost_level` | all | `low`/`medium`/`high` — gates the AI tier |
| `dry_run` | all | Resolve only, don't execute |
| `assertion_type` | verify | `text_visible` / `element_state` / `activity` |
| `expected_value` | verify | Expected text/fragment/XPath |

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
`max_cost_level: low`. All Tier‑1/2 features (hierarchy, text, fuzzy, synonyms,
memory, healing) still work.

**Cold run (ignore cache):** delete `.bubblegum/memory.db`.

**See what would happen:** wrap steps in `BubblegumSession.mobile(driver, dry_run=True)`
and call `s.print_plan()`.

**Explain a wrong pick:** `await s.explain("Tap Login")` prints the ranked
candidates, per‑signal score breakdown, the tier it stopped at, and the winner's
lead over the runner‑up.

**Real‑environment smoke harness:** opt‑in, skip‑by‑default smoke tests for
Android/iOS/cloud live under `tests/real_env/` — see `tests/real_env/README.md`.
