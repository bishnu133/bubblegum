# Bubblegum — User Guide

Bubblegum is an **AI‑powered, natural‑language execution and self‑healing layer**
for Playwright (web) and Appium (mobile) tests. You describe a step in plain
English — `"Click Login"`, `'Enter "tom" into Username'` — and Bubblegum finds
the element, performs the action, and heals the step when the UI drifts, so you
write far fewer brittle selectors.

This guide is split into:

- [Shared concepts](#shared-concepts) — the four primitives, the session, config
- [Natural‑language reference](#natural-language-reference) — the phrasing grammar
- [**Web**](#web) — Playwright channel, every web feature with examples
- [**Mobile**](#mobile) — Appium channel, every mobile feature with examples
- [Self‑healing & reports](#self-healing--reports)
- [Configuration reference](#configuration-reference)

---

## Installation

```bash
pip install bubblegum-ai            # core
pip install "bubblegum-ai[web]"     # + Playwright (web)
pip install "bubblegum-ai[mobile]"  # + Appium-Python-Client (mobile)
pip install "bubblegum-ai[anthropic]"  # + Claude vision/LLM grounding
pip install "bubblegum-ai[bdd]"     # + pytest-bdd (Gherkin steps)
pip install "bubblegum-ai[all]"     # everything

# Web only — install the browser once:
python -m playwright install chromium
```

Python 3.11+ is required. The web channel needs a Playwright `Page`; the mobile
channel needs an Appium `WebDriver`.

---

## Shared concepts

### The four primitives

Every test is built from four `async` functions (all return a `StepResult`):

| Primitive | What it does | Example |
| --- | --- | --- |
| `act` | Perform an action (click, type, select, …) | `await act("Click Login", page=page)` |
| `verify` | Assert a state holds | `await verify("Welcome is visible", page=page)` |
| `extract` | Read text from an element | `await extract("Get the order total", page=page)` |
| `recover` | Heal an existing test's stale selector | `await recover(page=page, failed_selector="#old", intent="Click Login")` |

```python
import asyncio
from bubblegum import act, verify, extract
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        page = await (await p.chromium.launch()).new_page()
        await page.goto("https://example.com/login")

        await act('Enter "tom" into Username', page=page)
        await act('Enter "secret" into Password', page=page)
        await act("Click Login", page=page)
        await verify("You are logged in", page=page)

asyncio.run(main())
```

`channel` defaults to `"web"`. For mobile, pass `channel="mobile", driver=driver`.

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

### `BubblegumSession` — the ergonomic wrapper

So you don't repeat `page=`/`channel=` on every call, wrap them once:

```python
from bubblegum import BubblegumSession

async with BubblegumSession.web(page) as s:
    await s.act('Enter "tom" into Username')
    await s.act("Click Login")
    await s.verify("You are logged in")
    s.assert_all_passed()          # raises if any step failed
    print(s.summary())             # {'total': 3, 'passed': 3, 'failed': 0, ...}
```

```python
async with BubblegumSession.mobile(driver) as s:
    await s.act("Tap Login")
```

Session extras: `s.goto(url)` (web), `s.results()`, `s.summary()`,
`s.assert_all_passed()`, `s.print_plan()` (dry‑run), `s.explain(step)`
(why a step resolved the way it did), and state probes
(`s.is_checked`, `s.selected_value`, `s.is_visible`) — see the Web section.

### Skip the UI login (API auth bootstrap)

Logging in through the UI on every test is the single biggest source of both
slowness and flakiness. Pass an async (or sync) `bootstrap` callable that
establishes authenticated state via API — inject cookies/`localStorage`/token on
web, or deep‑link/inject a token on mobile — and start each test already
authenticated, with zero UI login steps. It runs once on session entry and
receives the wrapped handle (`page` for web, `driver` for mobile):

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

Bubblegum stays provider‑agnostic — you supply the API call. See
`examples/web/auth_bootstrap/`.

### How resolution works (the grounding tiers)

Bubblegum tries resolvers in cost order and stops as soon as one is confident:

1. **Tier 1 — deterministic** (free, fast): explicit selector → memory cache →
   accessibility tree → exact text.
2. **Tier 2 — fuzzy/semantic** (free): fuzzy text + a synonym table
   (`login`↔`sign in`, `delete`↔`remove`, …).
3. **Tier 3 — AI** (costs a model call, opt‑in): LLM grounding, OCR, vision.

You normally never think about tiers — but `r.target.resolver_name` tells you
which one won, and the `max_cost_level` setting controls whether Tier 3 may run.

When Bubblegum picks the *wrong* element, `s.explain(step)` shows the full
rationale — the ranked candidates, each one's per‑signal score breakdown
(text/role/visibility/uniqueness/proximity/memory) against the confidence‑formula
weights, the tier it stopped at, and how far the winner beat the runner‑up. It
runs a dry‑run resolution (no execution) and prints the report:

```python
await s.explain("Click Login")
```

### Stability wait (anti‑flake, built in)

Before resolving each step, Bubblegum waits for the page to **settle** — no
in‑flight network, no DOM mutations for a short quiet window, and no visible
loading spinner — so it never acts mid‑render. This is on by default and bounded
by a timeout (it proceeds anyway if the page never settles). A 1.5 s
spinner‑gated button resolves without any `sleep()` in your test. Tune or disable
it in `bubblegum.yaml`:

```yaml
grounding:
  stability_wait_enabled: true   # set false to restore old timing
  stability_quiet_ms: 400        # required quiet window
  stability_timeout_ms: 5000     # give up settling after this long
  # stability_spinner_selectors: ["[role='progressbar']", ".spinner"]
```

Per call: `await s.act("Click Continue", stability_wait=False)` or
`stability_quiet_ms=200`. On mobile, "settled" means the Appium UI hierarchy
stopped changing for the quiet window.

### Self‑healing (built in)

If your step says `"Login"` but the page now says `"Sign In"`, the fuzzy tier
heals it: the step still passes but is marked **`recovered`** and carries a
`healing` advisory so you can confirm the substitution wasn't a real bug. This
survives across runs — once healed, the resolution is cached and the advisory
keeps showing on replays.

Each heal also includes a **suggested fix** — the old→new label/selector change
to de‑brittle the step (`healing.suggested_fix`, plus `old_ref`/`new_ref`/
`new_selector`), which the HTML report renders as a copy‑pasteable block. To
export the fixes and a **brittleness ranking** (the most‑healed labels — which
selectors are rotting), pass `--bubblegum-suggest-fixes fixes.json`. The same
ranking appears under `analytics.healing_summary.brittleness` in the HTML/JSON
reports.

### Memory cache (faster, stickier runs)

Successful resolutions are persisted to a small SQLite file
(`.bubblegum/memory.db`). On the next run the **memory cache** replays the same
element instantly (you'll see `resolver=memory_cache`). Entries expire by TTL
(default 7 days) and self‑invalidate after repeated failures. Delete the file
for a cold run.

---

## Natural‑language reference

The same phrasing grammar works on web and mobile. Bubblegum parses the verb,
the target, and any value from your sentence.

| You write | Action | Target | Value |
| --- | --- | --- | --- |
| `Click Login` | click | Login | — |
| `Tap the Menu button` | tap | Menu | — |
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
| `Expand Billing section` | click | Billing | — |
| `Open the Settings tab` | click (tab) | Settings | — |
| `Verify Welcome is visible` | verify | Welcome | — |
| `Get the order total` / `Extract email` | extract | order total / email | — |

**Tips**

- Put values in quotes so they're never confused with the target:
  `'Enter "Select All" into Notes'`.
- Add a widget word to disambiguate: `"Click the Sign in link"` prefers a link
  over a button; `"Choose Blue radio"` prefers a radio.
- Relational hints are understood: `"from the Country dropdown"`,
  `"in the confirmation modal"`, `"... for Acme Corp"` (same row).

---

## Dynamic values (dates, times & uniqueness)

Any value you type can be **computed at run time** with a `{{ ... }}` token
instead of hard‑coding a literal that goes stale or collides. Works on web and
mobile, in the Python SDK and the Node client, in any step that carries a value
(`act`, and the `value=`/`input_value=` overrides). Tokens are expanded
engine‑side just before the value is used.

```python
# Relative dates — for date pickers and any date field:
await act('Enter "{{today+7d|%d/%m/%Y}}" into Start date', page=page)   # -> 23/06/2026
await act('Enter "{{now+2h|%d/%m/%Y %H:%M}}" into Appointment', page=page)

# Relative date + an ABSOLUTE time of day (use "@") — "2 days out at 7:00am":
await act('Enter "{{today+2d@07:00|%d/%m/%Y %H:%M}}" into Start', page=page)  # -> 05/07/2026 07:00
await act('Enter "{{tomorrow@9am|%d/%m/%Y %H:%M}}" into Visible from', page=page)  # -> ... 09:00

# Uniqueness — for a field whose value must differ every run
# (a badge name, an email, any create‑form field with a unique constraint):
await act('Enter "Badge_{{timestamp}}" into Display Name', page=page)           # -> Badge_1751558400
await act('Enter "Badge_{{timestamp|%Y%m%d%H%M%S}}" into Display Name', page=page)  # -> Badge_20260703153012
await act('Enter "user_{{uuid:8}}@test.com" into Email', page=page)            # -> user_3f9a1c02@test.com
await act('Enter "SKU-{{random:6}}" into Code', page=page)                     # -> SKU-402913
```

**Relative dates/times**

| Part | Values |
| --- | --- |
| Base | `today`, `now`, `tomorrow`, `yesterday` |
| Offset (chainable, signed) | `+7d` `-3d` `+2w` `+1mo` `-1y` `+2h` `+30min` `+45s` |
| Absolute time (`@`, after offsets) | `@07:00` `@7am` `@9:30pm` `@23:59` `@07:00:00` |
| Format | anything after `\|` is a `strftime` pattern |

The `@` pins a **specific clock time** (after any date offset) — use it when you
want "N days from today at exactly 7:00am" rather than midnight or the current
time. If `@` is present and you give no `|` format, the default output includes
the time (`%Y-%m-%d %H:%M`).

**Date range pickers (start/end).** For a two-input range picker (e.g. Ant
`RangePicker`) whose inputs are nameless, just say **"Start date"** / **"End
date"** and Bubblegum pins the correct sub-input deterministically:

```python
await act('Enter "{{today+2d@07:00|%d/%m/%Y %H:%M}}" into Start date', page=page)
await act('Enter "{{today+12d@23:59|%d/%m/%Y %H:%M}}" into End date', page=page)
```

If a page has more than one range picker, add the field's label to disambiguate
(`"into the Visibility Period Start date"`). As a last resort you can always pin
the input explicitly with `selector='input[date-range="start"]'`.

Bubblegum also **commits** the value the way pickers expect — for a date/time
picker input it clicks to activate the field, types, then presses Enter — so a
range picker's start and end values land in their own fields instead of both
piling into "Start date". Ordinary text fields are typed normally (no Enter).

Units: `d` days, `w` weeks, `mo` months, `y` years, `h` hours, `min` minutes,
`s` seconds (`mo`/`min` are spelled out so a bare `m` is never ambiguous).
Default formats are `%Y-%m-%d` for date bases and `%Y-%m-%d %H:%M` for `now`.

**Uniqueness tokens**

| Token | Produces | Notes |
| --- | --- | --- |
| `{{timestamp}}` | Unix epoch **seconds** (e.g. `1751558400`) | `{{timestamp:ms}}` for milliseconds (tighter uniqueness in fast loops); `{{timestamp\|%Y%m%d%H%M%S}}` for a readable stamp |
| `{{uuid}}` | random uuid4 hex, 32 chars | `{{uuid:8}}` keeps the first 8 chars — unique regardless of the clock |
| `{{random}}` | 6 random digits | `{{random:N}}` for `N` digits |

**Remember a value and reuse it later (`as name` / `{{$name}}`).** Append
`as <name>` to a token to store its value, then recall the *same* value later in
the session with `{{$name}}` — e.g. generate a unique Display Name, then search
for the record you just created:

```python
await act('Enter "Badge_{{timestamp|%Y%m%d%H%M%S as badgeName}}" into Display Name', page=page)
# ...later step / another page...
await act('Enter "Badge_{{$badgeName}}" into Search', page=page)
await verify('{{$badgeName}} is visible', page=page)
```

`as name` captures the **token's** value (here `20260704153012`); rebuild the full
string with the same literal prefix (`Badge_{{$badgeName}}`). The store lives for
the engine session, so recall works across steps (and through the Node client).
Read it from code with `bubblegum.variables()` / `recall("badgeName")`; reset
between runs with `clear_variables()`. An unknown `{{$name}}` is left verbatim.

Token‑free values (and any `{{...}}` that isn't a recognised expression) are
passed through unchanged, so existing literal steps are never altered.

---

## Web

The web channel drives a Playwright **async** `Page`.

### Setup

```python
import asyncio
from playwright.async_api import async_playwright
from bubblegum import BubblegumSession

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://the-internet.herokuapp.com/login")

        async with BubblegumSession.web(page) as s:
            await s.act('Enter "tomsmith" into Username')
            await s.act('Enter "SuperSecretPassword!" into Password')
            await s.act("Click Login")
            await s.verify("You logged into a secure area")
            s.assert_all_passed()

        await browser.close()

asyncio.run(main())
```

### Web actions — every type with an example

```python
await s.act("Click Login")                              # click / link / button
await s.act('Enter "tomsmith" into Username')           # type into a field
await s.act('Select "France" from Country')             # native <select> by visible label
await s.act("Check Newsletter")                         # tick a checkbox
await s.act("Uncheck Remember me")                      # untick a checkbox
await s.act("Toggle Dark mode")                         # ARIA switch
await s.act("Click Blue radio")                         # radio button
await s.act("Set Volume to 75")                         # slider / <input type=range>
await s.act('Upload "/tmp/resume.pdf" into Resume')     # file input
await s.act("Scroll to Footer")                         # scroll element into view
await s.act("Open the Billing tab")                     # tabs
await s.act("Expand Shipping section")                  # accordion
```

**Select by label (not value).** `Select "France" from Country` works even when
the option is `<option value="FR">France</option>` — Bubblegum matches the
visible label, falling back from the value automatically.

**Radio buttons.** `Select "<label>" radio` (or `Choose … radio` / `Click …
radio`) selects a radio by its visible label — including Ant/MUI radios whose
real `<input type=radio>` is hidden behind a styled wrapper. Verify the choice
with `verify("<label> radio is selected")` (see below).

```python
await s.act('Select "Create cumulative milestone(s)" radio')
await s.verify("Create cumulative milestone(s) radio is selected")
```

**File upload (hidden inputs, multiple sections).** `Upload "<path>" into
<field>` finds the real `<input type=file>` even when it's hidden behind a styled
"+ Upload" button (Ant/MUI `Upload`). When a page has **several uploaders with
repeating labels**, name the section to disambiguate — the nearest section
heading is part of the match:

```python
await s.act('Upload "/tmp/album.png" into Awarded Album View')
await s.act('Upload "/tmp/front.png" into Awarded Front View')
await s.act('Upload "/tmp/back.png" into Upcoming Back View')
# or spell out the section: '... into the Album View under Upcoming Badge Details'
```

Pass a list to attach multiple files: `value=["/a.png", "/b.png"]`. As a last
resort you can pin the input explicitly, e.g.
`selector='#alreadyEarnedThumbnailImageUploadInput'`.

### Verify (assertions)

```python
await s.verify("Welcome back is visible")               # default: text on page
await s.verify("Dashboard", assertion_type="text_visible", expected_value="Dashboard")
await s.verify("URL changed", assertion_type="page_transition", expected_value="/home")
await s.verify("Save button", assertion_type="element_state", expected_value="#save")
# Radio / checkbox checked state (reads the real state, not just visibility):
await s.verify("Create cumulative milestone(s) radio is selected")
await s.verify("None radio is not selected")
await s.verify("Newsletter checkbox is checked")
# A "page appeared" assertion checks the visible heading text:
await s.verify("the Create Badge page appear")     # -> looks for "Create Badge"
# Validate specific columns of the row matched by a key column (quote the values):
await s.verify('in the row where Badge Internal Name is "{{$badgeName}}", '
               'Status is "Submitted", Badge Type is "Proficiency"')
```

> **Row validation tips.** Quote each value; the first `<col> is <val>` pair is the
> row key and the rest are the cells checked in that row. `{{$name}}` recalls a
> value you captured earlier (e.g. the unique name you generated on the create
> page). If you captured only a token (`... as badgeName` stored the timestamp),
> rebuild the full key with its literal prefix:
> `Badge Internal Name is "BadgeInternalName-{{$badgeName}}"`.

`assertion_type` options (web): `text_visible` (default), `element_state`
(a CSS selector is visible), `page_transition` (URL contains a fragment),
`a11y` (accessibility audit — see below), `network` (a backend call happened —
see below).

#### Network assertions

UI text alone can't prove the backend actually did the thing. Assert on the
network call instead — method + URL + status (any part may be omitted):

```python
await s.act("Click Sign in")
await s.verify("login call succeeded",
               assertion_type="network", expected_value="POST /api/login 200")
```

Bubblegum records responses from the first step onward, so this matches a call
that already happened during the action (and waits up to `timeout_ms` for one
still in flight). The URL part is a substring or glob (`/api/users/*`); it fails
with a clear message listing how many responses were seen.

#### Accessibility (a11y) assertions

```python
await s.verify("page has no critical a11y violations", assertion_type="a11y")
```

Bubblegum injects [axe-core](https://github.com/dequelabs/axe-core) and audits
the whole page (no element grounding needed). The failing severity is read from
the instruction (`critical`/`serious`/`moderate`/`minor`) or set explicitly with
`expected_value="serious"`; any violation at or above it fails the step, and the
error message lists each rule. The failed step carries the structured
violations under `result.target.metadata["a11y_violations"]`.

axe-core ships **vendored** with Bubblegum (offline, zero-config). Override the
source in `bubblegum.yaml` if needed:

```yaml
a11y:
  impact_threshold: critical      # default failing severity
  # axe_script_path: path/to/axe.min.js   # use your own pinned build
  # axe_url: https://cdn.example.com/axe.min.js   # load from a URL instead
```

Install with the `[a11y]` extra (it pulls the web/browser stack):
`pip install "bubblegum-ai[a11y]"`.

#### Soft assertions

A failing `verify` is recorded and surfaced together at
`assert_all_passed()` — it does not stop the test on the spot. To check a
batch of expectations and report **every** failure in one run, wrap them in a
soft-assertions block (or pass `soft=True` per call):

```python
with s.soft_assertions():
    await s.verify("Total is $42")
    await s.verify("Cart shows 3 items")
    await s.verify("Discount applied")
s.assert_all_passed()   # raises once, listing all soft failures
```

Soft failures are tagged `target.metadata["soft"] = True`, so they are
distinguishable in the JSON/HTML/JUnit reports. `s.soft_failures()` returns
just the soft-failed steps.

### Extract (read text)

```python
r = await s.extract("Get the flash message")
print(r.target.metadata["extracted_value"])
# Works across iframes too. Need a non-semantic element? Pass a selector:
r = await s.extract("Get the banner", selector="#flash")
```

### State probes (web)

Read widget state directly, by natural language:

```python
await s.is_checked("Newsletter")        # True/False
await s.selected_value("Country")       # current <select>/<input> value, e.g. "FR"
await s.is_visible("Welcome banner")    # True/False
```

### iframes (same‑origin)

Elements inside `<iframe>`s are discovered automatically — Bubblegum merges each
child frame's accessibility tree and routes the click/type/extract into the
owning frame. No special syntax:

```python
await page.goto(".../checkout.html")     # has a payment <iframe>
await s.act("Click Pay Now")             # button lives inside the iframe
```

Frame scanning is on by default and is a no‑op on pages without iframes.

### Bounded navigation wait (faster suites)

After a click, Bubblegum briefly waits to see if a navigation commits, then
moves on. A plain AJAX/SPA button no longer burns a fixed 5 s. Tune it:

```python
await s.act("Add to cart", nav_wait_ms=1500)   # default 1000ms; 0 = skip the probe
```

Toggle‑style controls (radio, checkbox, switch, tab, …) skip the wait entirely.

### Re‑grounding for late‑rendered (SPA) elements

If a target renders a beat after the page settles, Bubblegum re‑collects the
page and retries resolution instead of failing immediately. Controlled by
`resolve_retries` (default 2) and `resolve_retry_interval_ms` (default 300):

```python
await s.act("Click the lazy-loaded Continue", resolve_retries=4)
```

### Dialogs and scopes

When a **confirmation modal** is open, a click automatically prefers the button
*inside* the dialog — so the same-named button on the page behind the mask
(a common cause of "click times out / intercepts pointer events") is avoided:

```python
await s.act("Click Submit")                    # opens a "Submit Badge?" confirm
await s.act("Click Submit on Submit Badge? dialog")  # clicks the modal's Submit
# or just: await s.act("Click Submit")   # with the modal open, the modal wins
await s.act("Click No, cancel")                # the modal's cancel button
```

This works for Ant `Modal.confirm`, `[role=dialog]`, native `<dialog>`, and
common modal classes. You can still scope explicitly and close cleanly:

```python
s.push_scope("dialog", label="Confirm delete")
await s.act("Click Delete")          # resolved within the dialog
await s.close_dialog()               # clicks close/cancel/×, or presses Escape
```

### `recover()` — heal an existing Playwright test

Drop Bubblegum into a legacy test only where a selector breaks:

```python
from bubblegum import recover

# Your old line: await page.click("#login-btn")   # selector now stale
r = await recover(page=page, failed_selector="#login-btn", intent="Click Login")
# r.status == "passed" if the selector still works, "recovered" if Bubblegum healed it
```

### Explicit selector / action overrides

Natural language is the default, but you can always be explicit:

```python
await s.act("Click first checkbox", selector="input[type=checkbox]:first-of-type")
await s.act("Submit", action_type="click")           # force the action
await s.act("Set quantity", action_type="type", value="5", selector="#qty")
```

### Dry‑run (resolve without acting)

```python
async with BubblegumSession.web(page, dry_run=True) as s:
    await s.act("Click Login")
    await s.act('Enter "tom" into Username')
    s.print_plan()      # prints what each step *would* target, no clicks performed
```

### pytest integration

Bubblegum ships a pytest plugin. Use the `bubblegum_web` fixture (auto‑launches
Chromium) and the bundled `widget_lab` / `sample_app` demo servers:

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

### BDD (Gherkin)

`pip install "bubblegum-ai[bdd]"`, then write plain‑English `.feature` files:

```gherkin
# login.feature
Feature: Login
  Scenario: Valid login
    Given I am on the login page
    When I enter "tom" into "Username"
    And I enter "secret" into "Password"
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

Supported step phrasings include: `click/tap/press "X"`, `enter/type "v" into "f"`,
`fill "f" with "v"`, `select "v" from "f"`, `check/uncheck "X"`,
`run "<any NL instruction>"`, `should see "X"`, `"X" should be visible/checked`,
`"f" should have value "v"`, `"X" should contain "v"`.

### Vision / OCR grounding (icon‑only targets)

When a control has **no accessible name** (an icon‑only button), the deterministic
tiers can't match it. Register a vision provider and Bubblegum's AI tier reads
the screenshot to find it:

```python
from bubblegum import configure_vision_provider
from bubblegum.core.vision.engine import FakeVisionProvider  # or your Claude-backed provider

configure_vision_provider(FakeVisionProvider())
await s.act("Click the settings icon", max_cost_level="high")
```

Vision requires opting in via config (it sends a screenshot to a model):

```yaml
grounding:
  enable_vision: true
  max_cost_level: high
privacy:
  send_screenshots: true
  process_screenshots_for_vision: true
```

A provider implements `detect_targets(image_bytes, instruction, context=None)`
and returns candidates (`label`, `bbox`, `confidence`, optional `role`/`text`).
Anthropic (Claude) and OpenAI backends ship in `bubblegum.core.vision.backends`.

> Note: on web, vision *wins the decision* and then maps the match back to a DOM
> element by its role/label to click it — so the control must be locatable by the
> label the model returns. Clicking purely by pixel coordinates is on the roadmap,
> not yet supported. The deterministic tiers remain best for named controls.

---

## Mobile

The mobile channel drives an Appium `WebDriver`. The same primitives and NL
grammar apply; element resolution uses the Appium UI hierarchy (and, when
enabled, OCR/vision over screenshots).

### Setup

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
    finally:
        driver.quit()

asyncio.run(main())
```

Or call the primitives directly with `channel="mobile", driver=driver`:

```python
from bubblegum import act
await act("Tap Login", channel="mobile", driver=driver)
```

### Mobile actions

```python
await s.act("Tap Login")                      # tap (alias: click)
await s.act('Enter "tom" into Username')      # type into a field
await s.act("Scroll to Settings")             # scroll the target into view

# Swipe is driven explicitly — direction is the value (up/down/left/right):
await s.act("Swipe the banner", action_type="swipe", value="left")
```

> Web‑specific actions (`select`, `check/uncheck`, `upload`, `set` sliders) are
> not part of the mobile dispatch — use `tap`/`type`/`scroll`/`swipe`, which
> cover native controls. `tap`, `type` and `scroll` are inferred from plain
> English; `swipe` is requested with `action_type="swipe"` as shown above.

### Verify and extract (mobile)

```python
await s.verify("Welcome", assertion_type="text_visible")     # page_source contains text
await s.verify("Home screen", assertion_type="activity", expected_value=".HomeActivity")
await s.verify("Save", assertion_type="element_state", expected_value="//*[@text='Save']")

r = await s.extract("Get the account balance")
print(r.target.metadata["extracted_value"])
```

`assertion_type` options (mobile): `text_visible`, `element_state` (XPath is
displayed), `activity` (current activity/bundle id contains a fragment).

### Self‑healing & memory (mobile)

Identical to web: a fuzzy/synonym substitution marks the step `recovered` with a
`healing` advisory, and successful resolutions are cached (keyed on a
mobile‑specific screen signature) so later runs replay instantly. Late‑rendered
elements benefit from the same re‑grounding retry.

### Icon, scroll discovery & repeated rows (natural language)

Bubblegum's mobile resolution understands common native patterns without you
writing locators:

```python
await s.act("Tap the search icon")            # icon detection (no text label)
await s.act("Scroll down to Privacy Policy")  # scroll-discovery finds off-screen targets
await s.act('Tap Delete for "Groceries"')     # repeated rows: the Delete in the Groceries row
```

### System dialogs (permissions / alerts)

OS permission and alert dialogs are detected, and you act on their buttons by
the visible label — the same `act` you use everywhere:

```python
await s.act("Tap Allow")                       # accept a permission prompt
await s.act("Tap While using the app")
await s.act("Tap Cancel")                      # dismiss an alert
```

Detection is guard‑railed so Bubblegum only treats recognised, safe system
dialogs specially.

### Hybrid apps & WebView switching

For hybrid screens (a WebView embedded in a native app), Bubblegum can switch
into the WebView context to resolve web content, then restore the native
context. This is **opt‑in** and fail‑closed. Enable it in config:

```yaml
webview_switching:
  enable_webview_switching: true
  webview_switching_mode: opt_in          # off | dry_run | opt_in
  webview_switch_allowed_operations: ["extract_text", "validate"]
  require_restore_context: true
  webview_context_selection_policy: single_webview_only
```

Start with `validate`/`extract_text` (read‑only, lowest risk) before allowing
action routing.

### pytest integration (mobile)

Use the `bubblegum_mobile` fixture; pass the Appium server and capabilities on
the command line:

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
skips cleanly when Appium isn't installed, no capabilities are given, or the
server is unreachable. A failure screenshot is captured via the driver.

---

## Self‑healing & reports

### Reading the healing advisory

```python
r = await s.act("Click Login")          # page actually says "Sign In"
if r.status == "recovered":
    h = r.target.metadata["healing"]
    print(h["requested"], "→", h["matched"], f"({h['severity']})")
    # login → Sign In (review)
```

`severity` is `info` for a benign typo/case fix and `review` for a semantic
substitution worth a human glance. `assert_all_passed()` treats `recovered` as a
pass, so healed steps don't block the run but still surface in reports.

### HTML / JSON reports

```python
from bubblegum.reporting.html_report import write_html_report
from bubblegum.reporting.json_report import write_json_report

results = s.results()
write_html_report(results, "report.html", title="My Suite")
write_json_report(results, "report.json", title="My Suite")
```

Reports highlight healed steps and include per‑step resolver, confidence, and
screenshots. With the pytest plugin, pass `--bubblegum-report` /
`--bubblegum-report-json` to generate them at session end automatically.

---

## Configuration reference

### `bubblegum.yaml`

Place this in your project root (auto‑loaded), or pass `--bubblegum-config PATH`
/ `configure_runtime(config_path=...)`. Everything has a sensible default — zero
config works out of the box.

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

webview_switching:                # mobile hybrid apps (see Mobile section)
  enable_webview_switching: false
  webview_switching_mode: off     # off | dry_run | opt_in
```

### Per‑call options (kwargs on `act`/`verify`/`extract`)

| kwarg | Applies to | Meaning |
| --- | --- | --- |
| `selector` | all | Explicit CSS/XPath to use/fall back to |
| `action_type` | act | Force `click`/`type`/`select`/… |
| `value` / `input_value` | act | Value to type/select |
| `target_phrase` | all | Override the parsed target |
| `timeout_ms` | all | Per‑action timeout (default 10000) |
| `retry_count` | act | Transient‑error retries |
| `nav_wait_ms` | act (web) | Post‑click navigation probe budget (default 1000; 0 = skip) |
| `resolve_retries` | all | Re‑ground attempts for late renders (default 2) |
| `max_cost_level` | all | `low`/`medium`/`high` — gates the AI tier |
| `dry_run` | all | Resolve only, don't execute |
| `assertion_type` | verify | `text_visible` / `element_state` / `page_transition` / `activity` |
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

**Validate everything locally:** see `docs/web-improvements-validation.md` for the
exact unit / `--playwright` / Appium commands.
