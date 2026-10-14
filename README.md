<h1 align="center">Bubblegum</h1>

<p align="center">
  <strong>Write UI tests in plain English. Bubblegum finds the elements, heals broken locators, and uses AI only when it has to.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/bubblegum-ai/"><img src="https://img.shields.io/pypi/v/bubblegum-ai?label=bubblegum-ai&color=ff69b4" alt="PyPI"/></a>
  <a href="https://www.npmjs.com/package/@bubblegum-ai/node"><img src="https://img.shields.io/npm/v/@bubblegum-ai/node?label=%40bubblegum-ai%2Fnode&color=cb3837" alt="npm"/></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+"/>
  <img src="https://img.shields.io/badge/node-18%2B-339933.svg" alt="Node 18+"/>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-lightgrey.svg" alt="MIT License"/></a>
</p>

---

Bubblegum is a test-automation library that sits on top of **Playwright** (web) and
**Appium** (Android / iOS). Instead of writing selectors, you write steps the way you
would describe them to a colleague:

```python
await s.act('Enter "tomsmith" into Username')
await s.act("Click Login")
await s.verify('the status tag shows "Active"')
```

Bubblegum works out which element you mean, performs the action, and records *why* it
chose that element. When the UI changes and a label or locator drifts, it heals the
step instead of failing the run.

- **No selectors in your tests** — plain-English steps for clicks, typing, dropdowns, tables, modals, uploads and assertions.
- **Self-healing** — remembers what worked and adapts when the UI changes; healed steps are flagged as `recovered` so nothing is hidden.
- **Deterministic first, AI last** — fast, free resolvers run first; an LLM or vision model is used only when they can't decide.
- **Works with any web stack** — Ant Design, MUI, Bootstrap, plain HTML, React, Angular and more.
- **Python and TypeScript** — use it from pytest, or from any Node test runner via `@bubblegum-ai/node`.
- **Clear reports** — HTML/JSON/JUnit/Allure plus a combined summary dashboard with screenshots on every failure.

Bubblegum is not a replacement for Playwright or Appium — it plugs into your existing
tests and you can mix plain-English steps with regular Playwright/Appium code.

---

## Contents

- [Versions](#versions)
- [Install](#install)
- [Quick start](#quick-start)
- [Writing steps](#writing-steps)
- [Dynamic values](#dynamic-values)
- [How Bubblegum finds elements](#how-bubblegum-finds-elements)
- [Configuration](#configuration)
- [Reports and console output](#reports-and-console-output)
- [Mobile](#mobile)
- [pytest plugin](#pytest-plugin)
- [Command-line tools](#command-line-tools)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)
- [Release history](#release-history)

---

## Versions

| Package | Latest | Install |
|---|---|---|
| Engine (Python) — `bubblegum-ai` | **0.0.18** | `pip install "bubblegum-ai[web]"` |
| Node / TypeScript client — `@bubblegum-ai/node` | **0.0.6-alpha.17** | `npm install @bubblegum-ai/node` |

Requirements: **Python 3.11+**. The Node client needs **Node 18+** *and* the Python engine
installed on the same machine (the client runs the engine for you).

---

## Install

### Python

```bash
# Web (Playwright)
pip install "bubblegum-ai[web]"
python -m playwright install chromium

# Mobile (Appium) — also needs a running Appium server and a device/emulator
pip install "bubblegum-ai[mobile]"

# Everything
pip install "bubblegum-ai[all]"
```

Optional extras:

| Extra | Adds |
|---|---|
| `web` | Playwright |
| `mobile` | Appium Python client |
| `anthropic` / `openai` | SDK for the AI fallback tier |
| `localvision` | Offline on-device OCR (RapidOCR) — read text from screenshots without any cloud call |
| `allure` | Allure report output |
| `a11y` | Accessibility audits (axe-core) |
| `visual` | Visual (screenshot) regression checks |
| `bdd` | pytest-bdd step library |
| `convert` | Spreadsheet-of-scenarios → test scaffold converter |

### Node / TypeScript

```bash
pip install "bubblegum-ai[web]"          # the engine the client drives
python -m playwright install chromium
npm install @bubblegum-ai/node
```

If you keep the engine in a dedicated virtualenv, point the client at it:

```bash
export BUBBLEGUM_PYTHON=/path/to/.venv/bin/python
```

---

## Quick start

### Python

```python
import asyncio
from playwright.async_api import async_playwright
from bubblegum import BubblegumSession

async def main():
    async with async_playwright() as p:
        page = await (await p.chromium.launch()).new_page()
        await page.goto("https://the-internet.herokuapp.com/login")

        async with BubblegumSession.web(page) as s:
            await s.act('Enter "tomsmith" into Username')
            await s.act('Enter "SuperSecretPassword!" into Password')
            await s.act("Click Login")
            result = await s.verify("You logged into a secure area")
            print(result.status)   # passed | recovered | failed

asyncio.run(main())
```

Prefer plain functions? The same primitives are available directly:

```python
from bubblegum import act, verify, extract, recover

await act("Click Login", channel="web", page=page)
await verify("Dashboard is visible", channel="web", page=page)
```

### TypeScript / JavaScript

```ts
import { Bubblegum } from "@bubblegum-ai/node";

const bg = await Bubblegum.launch({ url: "https://the-internet.herokuapp.com/login" });
try {
  await bg.act('Enter "tomsmith" into Username');
  await bg.act('Enter "SuperSecretPassword!" into Password');
  await bg.act("Click Login");
  const r = await bg.verify("You logged into a secure area");
  console.log(r.status);   // "passed" | "recovered" | "failed"
} finally {
  await bg.close();
}
```

Already have a Playwright browser open in your test? Attach to it instead of launching a
new one: `Bubblegum.attach({ cdpEndpoint: "http://localhost:9222" })`. ESM and CommonJS
are both supported.

### Heal a broken selector in an existing test

You don't have to rewrite anything to get value — wrap a step whose selector broke:

```python
from bubblegum import recover

result = await recover(page=page, failed_selector="#login-btn", intent="Click Login")
# result.status == "recovered" → the old selector failed but Bubblegum clicked the right element
```

### Every call returns a `StepResult`

| Field | Meaning |
|---|---|
| `status` | `passed`, `recovered` (healed — worth reviewing), `failed`, or `skipped` |
| `target` | The element that was used, which resolver found it, and its confidence |
| `confidence` | 0.0 – 1.0 |
| `error` | Error type and message when the step failed |
| `artifacts` | Screenshots (always captured on failure) |
| `traces` | Every resolver that ran and what it found |

---

## Writing steps

Steps are ordinary sentences. Put **values you type or look for in quotes**; refer to
fields and buttons by the label a user sees on screen.

### Clicking and navigating

```text
Click Login
Click the Save as draft button
Click the Reports menu                      # also finds items collapsed into a "…"/More menu
Hover over the Settings menu
Click the link "View details"
Click "Record-2026-001"                     # a clickable table row or any element by its text
Click the RecordID value in the 1st row     # a cell by column + row
In the row where Date is "10/08/2026", click the "Edit" link
In the row where Date is "10/08/2026", select the checkbox
Click on the Search icon of Title column    # a filter/search/sort icon inside a column header
Click the filter icon in the Status column
Expand the Billing section                  # accordion panels
```

When a modal or confirm dialog is open, clicks, typing, uploads, radios and checkboxes
automatically target the controls **inside the dialog**, not same-named ones behind it.

### Entering data

```text
Enter "Jane Doe" into Full Name
Enter "This is a description" into Description          # text areas and rich-text editors too
Enter "10/08/2026" into Start date                       # date / time / range pickers
Select "Premium" from Plan dropdown
Select "Email, SMS" from Notification channels dropdown   # multi-select
Enter "urgent" into Tags and press Enter               # tags / token inputs (Enter or Tab)
Upload "assets/cover.png" into Cover image
Select "Monthly" radio
Select the Remember me checkbox
```

Tags/token inputs (where each typed value becomes a chip) are committed automatically,
so repeating `Enter "…" into Tags` adds one item per step. Add `and press Tab` /
`and press Enter` when the field needs a specific key.

Searchable dropdowns whose stored value differs from the label you see (e.g. options keyed
by an ID) can be picked without typing to filter: pass the option `select_no_filter: true`.

### Verifying

```text
You logged into a secure area                             # text is visible
the page shows a "Update account status" button
the page header is "General Information"
the "Save" button is present
the "Saving..." message is no longer visible             # absence checks wait for removal
the status tag shows "In Draft"                          # status pills / badges / chips
in the row where Name is "Item A", Status is "Live", Division is "North"
the "Country" dropdown contains "India", "Singapore"
the alert says "Saved"
the "Dashboard" menu is highlighted
Monthly radio is selected
```

Specialised checks are available with an explicit `assertion_type`:

```python
await s.verify("login request", assertion_type="network", expected_value="POST /api/login 200")
await s.verify("page has no critical a11y violations", assertion_type="a11y")
await s.verify("dashboard looks unchanged", assertion_type="visual")
```

### Reading values

```python
email = (await s.extract("Get the user email")).target.metadata["extracted_value"]
```

### Mixing with your own code

Every step accepts options — keyword arguments in Python (`timeout_ms=20000`), an options
object in TypeScript (`{ timeout_ms: 20000 }`). You can always drop down to
Playwright/Appium for anything custom.

---

## Dynamic values

Generate unique or date-based values inside any step, and reuse them later:

| Token | Example result |
|---|---|
| `{{today}}`, `{{today+7d}}`, `{{today+1mo\|%d/%m/%Y}}` | Dates with offsets (`d`, `w`, `mo`, `y`) and a format |
| `{{now+2h\|%d/%m/%Y %H:%M}}`, `{{today+2d@07:00\|%d/%m/%Y %H:%M}}` | Date-times (`h`, `min`, `s`) and a fixed time of day |
| `{{timestamp}}`, `{{timestamp\|%Y%m%d%H%M%S}}` | Unique timestamps |
| `{{uuid:8}}`, `{{random:6}}` | Short random IDs |

Capture a generated value with `as <name>` and recall it with `{{$name}}` in any later step
of the same session:

```text
Enter "Order_{{timestamp|%Y%m%d%H%M%S as orderRef}}" into Reference
Enter "Order_{{$orderRef}}" into Search
Click "Order_{{$orderRef}}"
in the row where Reference is "Order_{{$orderRef}}", Status is "Live"
```

From Python you can also use `remember(name, value)`, `recall(name)`, `variables()` and
`clear_variables()`.

---

## How Bubblegum finds elements

Each step goes through a tiered resolver chain and stops at the first confident answer:

| Tier | Resolvers | Cost |
|---|---|---|
| 1 — Deterministic | Learned memory cache, accessibility tree, exact label / placeholder / aria text, built-in handlers for dropdowns, tables, modals, pickers, uploads, radios, checkboxes | Free, fast |
| 2 — Fuzzy / semantic | Edit-distance and synonyms ("Login" ≈ "Sign in"), optional embeddings | Free, local |
| 3 — AI | LLM grounding, OCR, vision model | Only when tiers 1–2 can't decide; can be disabled |

Safety rules:

- **No silent wrong clicks.** If two candidates are equally likely, the step fails with
  `AmbiguousTargetError` instead of guessing.
- **Self-healing is visible.** Healed steps are reported as `recovered`, so you can update
  the test intentionally.
- **Learned locators are re-checked** before reuse (screen fingerprint, element still
  present, success history, 7-day TTL by default).

### Last-resort selector (optional)

For a business-critical step you can supply a selector that is used **only if every
natural-language and AI approach fails**:

```ts
await bg.act("Click Save", { fallbackSelector: '[data-testid="save-btn"]' });
```

The step still passes, but it is flagged with a ⚠ *Fallback* marker in the report (and
never cached), so you can see which steps need attention. To force a specific element
first instead, pass `selector`.

---

## Configuration

Bubblegum works with no configuration. To tune it, add `bubblegum.yaml` to your project root:

```yaml
grounding:
  max_cost_level: medium        # low = never call AI | medium | high
  ai_mode: live                 # replay = only learned cache + deterministic tiers (zero-cost CI)
  enable_vision: false
  vision_backend: none          # none | rapidocr (offline) | anthropic | openai | http | callable

ai:
  enabled: true
  provider: anthropic           # anthropic | openai | gemini | local
  model: <model-id>             # required to use the AI tier — no default, so no surprise costs
  # fast_model: <cheaper-model-id>
  # strong_model: <stronger-model-id>

privacy:
  redact_pii: true
  send_screenshots: false       # set true only to send screenshots to a hosted vision model
```

### AI provider keys

| Provider | Environment variable |
|---|---|
| Anthropic (default) | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |

Use any current model ID from your provider for `model`. For element grounding a fast,
low-cost model is usually enough.

### Running without AI

```yaml
ai:
  enabled: false
```

All deterministic and fuzzy resolution keeps working; no API key or network access is
needed. For screens whose text isn't in the DOM/hierarchy (canvas, Flutter), use the
offline OCR backend: `pip install "bubblegum-ai[localvision]"` and set
`vision_backend: rapidocr` with `enable_vision: true` — screenshots never leave the machine.

### Privacy

- Only a filtered accessibility tree / hierarchy is sent to an AI provider — never the raw DOM.
- Password fields are never captured; fields named like secrets/tokens are redacted.
- Screenshots go to a hosted model only when you explicitly enable it.

---

## Reports and console output

### From TypeScript

```ts
await bg.report({
  html: "report/{run_id}/",                    // a folder → one file per test: <suiteName>.html
  json: "report/{run_id}/",
  junit: "report/{run_id}/",
  allure: "report/{run_id}/allure-results",
  summary: "report/{run_id}/summary.html",     // one dashboard for every test in the run
  suiteName: "checkout",
  title: "Checkout",
  summaryTitle: "Web Automation Summary Report",
});
```

- `{run_id}` creates one timestamped folder per execution. To gather **several test files**
  into the same folder and summary, set one ID for the whole run before starting them:
  `export BUBBLEGUM_RUN_ID="Report_$(date +%d%m%Y_%H%M%S)"`.
- Several tests in one file: call `report({ scope: "sinceLast", suiteName: "…", … })` after
  each test — each gets its own report and its own row in the summary.
- The summary dashboard shows pass rate, step outcomes (passed / self-healed / fallback /
  failed / skipped), a per-test breakdown, and each test's full step-by-step detail.
- Every failed step includes a screenshot. Set `BUBBLEGUM_RECORD_VIDEO=1` to also record
  a video per session.

### Console output (TypeScript)

```ts
import { RunConsole } from "@bubblegum-ai/node";

const out = new RunConsole("Checkout flow");
out.section("General info");
out.step(await bg.act("Click Save"));
out.step(await bg.verify('the status tag shows "In Draft"'));
out.summary();   // ✔ 5   ✚ 1   ✖ 1   ○ 0   · 86% pass · 12.4s
```

`logStep(result)` and `formatStepLine(result)` are available for one-off lines. Colours turn
off automatically in CI logs or when `NO_COLOR` is set.

### From pytest

```bash
pytest --bubblegum-report artifacts/report.html \
       --bubblegum-report-json artifacts/report.json \
       --bubblegum-report-junit artifacts/junit.xml \
       --bubblegum-report-allure artifacts/allure-results
```

---

## Mobile

```python
async with BubblegumSession.mobile(driver) as s:   # an Appium driver
    await s.act("Tap Continue")
    await s.act('Enter "jane@example.com" into "Email address"')
    await s.verify('the screen shows "Welcome"')
```

- **Android and iOS** (UiAutomator2 / XCUITest), native, hybrid and React Native apps.
- **Attach to a running session** — reuse the Appium session your test already owns
  (needed on device farms that allow one session per device):
  `Bubblegum.attachMobile({ appiumUrl, existingSessionId })`.
- **Scroll-to-find** — steps naming an off-screen control scroll until it appears.
- **System alerts** — permission dialogs can be accepted or dismissed automatically
  (`grounding.system_alert_handling: accept | dismiss`).
- **Flutter / canvas / game screens** — detected automatically and resolved by on-device OCR.
- **App health** — waits out spinners and fails fast with a clear message on a crash or ANR.
- Cloud device providers (BrowserStack, Sauce Labs, LambdaTest, pCloudy) via
  `--bubblegum-cloud-provider`.

See [How to Use — Mobile](docs/HOW_TO_USE_MOBILE.md) for setup.

---

## pytest plugin

The plugin is registered automatically when Bubblegum is installed.

```python
async def test_login(bubblegum_web):
    await bubblegum_web.act('Enter "tomsmith" into Username')
    await bubblegum_web.act("Click Login")
    assert (await bubblegum_web.verify("Secure Area")).status in ("passed", "recovered")
```

Fixtures: `bubblegum_web`, `bubblegum_page`, `bubblegum_browser`, `bubblegum_mobile`,
`bubblegum_reporter`, `bubblegum_config`.

Useful flags: `--bubblegum-config`, `--bubblegum-headed`, `--bubblegum-ai`,
`--bubblegum-artifacts`, `--bubblegum-report*`, `--bubblegum-update-baselines`,
`--bubblegum-flaky-report`, `--bubblegum-quarantine`, `--bubblegum-appium-url`,
`--bubblegum-capabilities`. See [pytest plugin](docs/pytest-plugin.md).

---

## Command-line tools

| Command | Purpose |
|---|---|
| `bubblegum repl` | Try plain-English steps live against a running page or app |
| `bubblegum bridge` | Run the engine for non-Python clients (used by `@bubblegum-ai/node`) |
| `bubblegum record` | Record a manual click-through as plain-English steps |
| `bubblegum convert` | Turn a spreadsheet of manual scenarios into test scaffolds |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| A fix you upgraded to doesn't seem to apply | Check which engine actually ran — in TypeScript, `bg.bridge.handshakeInfo?.engine_version`. If it's old, upgrade the interpreter the client uses (the one in `BUBBLEGUM_PYTHON`, if set): `<that-python> -m pip install -U bubblegum-ai`. |
| `AmbiguousTargetError` | Two elements match equally. Add context: a quoted label, the section, the dialog, the row, or the column (`… of Title column`). |
| Step resolves to a similar but wrong field | Use the exact on-screen label in quotes, or name the section it belongs to. |
| `LowConfidenceError` / `ResolutionFailedError` | The element may not be rendered yet (raise `timeout_ms`), may be off-screen, or the label differs — check the screenshot attached to the failed step. |
| Steps pass locally but fail in headless CI | Make sure the CI viewport is wide enough that menus don't collapse, and that CI uses the same engine version. |
| AI tier never runs | Set `ai.model` and the provider's API key, and keep `max_cost_level` at `medium` or higher. |
| Playwright says the browser isn't installed | Run `python -m playwright install chromium`. |

---

## Documentation

- [How to Use — Web](docs/HOW_TO_USE_WEB.md)
- [How to Use — Mobile](docs/HOW_TO_USE_MOBILE.md)
- [How to Use — TypeScript / JavaScript](docs/HOW_TO_USE_TYPESCRIPT.md)
- [User Guide](docs/USER_GUIDE.md) — full reference
- [Getting started for testers](docs/getting-started-for-testers.md)
- [Writing good steps](docs/authoring-scenarios-style-guide.md)
- [AI grounding setup](docs/ai-grounding-enhancements.md)
- [pytest plugin](docs/pytest-plugin.md) · [CI usage](docs/ci.md)
- [Mobile cloud providers](docs/mobile-cloud.md) · [Attach to an existing session](docs/mobile-attach-existing-session.md)
- [Node client](clients/node/README.md)
- [Examples](examples/README.md)

---

## Release history

Full details for every release are in the [CHANGELOG](CHANGELOG.md).

| Version | Highlights |
|---|---|
| **0.0.18** | Buttons inside an open **pop-up panel** (e.g. a column filter's `Search` / `Reset`) win over same-named page buttons. |
| **0.0.17** | Click a filter / search / sort icon inside a **named column header** (`Click on the Search icon of Title column`). |
| **0.0.16** | **Tags / token inputs** — add multiple items; `… and press Enter` / `… and press Tab` supported. |
| **0.0.15** | **Absence checks** — `… is not present`, `… is no longer visible`, waiting for removal. |
| **0.0.14** | Click nav items hidden in a responsive **"…" / More** overflow menu. |
| **0.0.13** | Clicks go through **sticky headers/overlays**; screenshot attached to every failed step. |
| **0.0.12** | More reliable menu clicks; failure screenshots; optional **session video** recording. |
| **0.0.11** | Reliable **date / time picker** entry in headless CI. |
| **0.0.10** | Page-header checks find styled (non-`<h1>`) titles. |
| **0.0.9** | **UI validations** — element presence, highlighted nav, dropdown options, alerts, page header — and **row-scoped table actions**. |
| **0.0.8** | Radios, checkboxes and time pickers resolved **inside modals**; exact-label radio matching. |
| **0.0.7** | **iOS / Android system alerts** handled automatically. |
| **0.0.6** | First stable release. Includes: status-tag assertions, the summary dashboard and console renderer, last-resort `fallbackSelector`, several tests per file with timestamped report folders, modal-aware typing and uploads, offline OCR, Flutter/canvas support, mobile scroll-to-find, iOS support and session attach, app-health checks, and the TypeScript client. |

---

## License

[MIT](LICENSE)
