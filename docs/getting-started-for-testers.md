# Getting Started for Testers

Bubblegum lets you write UI tests in plain language — no selectors, no
test IDs, no XPath. You say *what* a user does ("Click Sign in",
"Check Email notifications") and Bubblegum's grounding engine finds the
right element through the page's accessibility tree.

```python
await s.act('Enter "tester" into Username')
await s.act('Enter "bubblegum!" into Password')
await s.act("Click Sign in")
assert await s.is_visible("Dashboard")
```

That is a complete, working login test. This guide gets you from zero to
that test in about five minutes.

---

## 1. Install (60 seconds)

From the Bubblegum repo root:

```bash
pip install -e ".[web,test]"
python -m playwright install chromium
```

## 2. See it work (60 more seconds)

The repo ships **Acme Notes**, a small three-page app (login → dashboard
→ settings) made for exactly this moment:

```bash
python examples/web/real_local/run_example.py            # headless
python examples/web/real_local/run_example.py --headed   # watch the browser
```

You should see:

```
✅ Acme Notes flow complete: 7/7 steps passed in ...ms
```

Every one of those steps was natural language — open
`examples/web/real_local/run_example.py` and read it; it fits on one
screen.

## 3. Your first pytest test

Bubblegum ships a pytest plugin (auto-loaded — no conftest changes).
Create `test_acme.py`:

```python
import pytest

pytestmark = [pytest.mark.bubblegum, pytest.mark.asyncio]


async def test_login(bubblegum_web, sample_app):
    await bubblegum_web.goto(f"{sample_app}/login.html")

    await bubblegum_web.act('Enter "tester" into Username')
    await bubblegum_web.act('Enter "bubblegum!" into Password')
    await bubblegum_web.act("Click Sign in")

    assert await bubblegum_web.is_visible("Dashboard")
    bubblegum_web.assert_all_passed()
```

Run it:

```bash
pytest test_acme.py -v                       # headless
pytest test_acme.py -v --bubblegum-headed    # watch the browser
```

What the fixtures gave you:

- **`bubblegum_web`** — a launched Chromium page wrapped in a
  `BubblegumSession`. On failure it automatically saves a screenshot to
  `artifacts/<test>-final.png` (and one per failed step).
- **`sample_app`** — a local HTTP server for the Acme Notes pages;
  yields the base URL. (`widget_lab` does the same for the widget lab
  pages.)

Point your own tests at your own app by replacing `sample_app` with your
URL — everything else stays the same.

## 4. The session API you'll actually use

| Call | What it does |
|---|---|
| `await s.goto(url)` | Navigate and wait for the DOM |
| `await s.act("Click Sign in")` | Do a step described in plain language |
| `await s.act('Enter "x" into Field')` | Type into a labelled field |
| `await s.act("Check Email notifications")` | Check a checkbox (uncheck works too) |
| `await s.act("Select German from Language")` | Pick from a native select |
| `await s.act("Set Volume to 75")` | Drive a slider / range input |
| `await s.is_visible("Dashboard")` | Probe: is this text/element visible? |
| `await s.is_checked("Email notifications")` | Probe: checkbox/radio state |
| `await s.selected_value("Language")` | Probe: current select value |
| `s.assert_all_passed()` | Fail the test if any step failed |
| `s.summary()` | `{total, passed, failed, ...}` dict |

Phrasing tips: name elements by their **visible label** ("Username",
"Sign in", "Billing tab"). Add the widget word when two elements share a
label — "Click the Sign in **link**" vs "Click the Sign in **button**".

## 5. Faster suites: share the browser

`bubblegum_web` launches Chromium per test — simple, fully isolated,
fine for small suites. For bigger suites, switch to `bubblegum_page`:
the browser launches **once per session** and each test gets a fresh
incognito context (cookies/storage still isolated):

```python
import pytest

pytestmark = [
    pytest.mark.bubblegum,
    pytest.mark.asyncio(loop_scope="session"),   # required for bubblegum_page
]


async def test_login_fast(bubblegum_page, sample_app):
    await bubblegum_page.goto(f"{sample_app}/login.html")
    await bubblegum_page.act('Enter "tester" into Username')
    await bubblegum_page.act('Enter "bubblegum!" into Password')
    await bubblegum_page.act("Click Sign in")
    assert await bubblegum_page.is_visible("Dashboard")
    bubblegum_page.assert_all_passed()
```

The `loop_scope="session"` marker is required because Playwright objects
are bound to the event loop that created them, and the shared browser
lives on the session loop.

## 6. Mobile (Appium)

The same session API works against a real device or emulator through the
`bubblegum_mobile` fixture:

```python
import pytest

pytestmark = [pytest.mark.bubblegum, pytest.mark.asyncio]


async def test_tap_animation(bubblegum_mobile):
    result = await bubblegum_mobile.act("Tap Animation")
    assert result.status in ("passed", "recovered")
    bubblegum_mobile.assert_all_passed()
```

Run with an Appium server + device available:

```bash
pip install -e ".[mobile]"
pytest test_mobile.py --appium \
  --bubblegum-capabilities '{"platformName":"Android","appium:deviceName":"emulator-5554","appium:appPackage":"io.appium.android.apis","appium:appActivity":".ApiDemos","appium:automationName":"UiAutomator2"}'
```

The fixture skips (with the reason) when the server is unreachable or
capabilities are missing, so mobile tests never break a web-only run.

## 7. CLI options reference

| Option | Default | Purpose |
|---|---|---|
| `--bubblegum-headed` | off | Show the browser window |
| `--bubblegum-artifacts DIR` | `artifacts` | Where failure screenshots go |
| `--bubblegum-report PATH` | — | Write an HTML report at session end |
| `--bubblegum-report-json PATH` | — | Write a JSON report at session end |
| `--bubblegum-report-junit PATH` | — | Write a JUnit XML report at session end (Jenkins/GitLab/Azure/CircleCI) |
| `--bubblegum-report-allure DIR` | — | Write Allure result files at session end (view with `allure serve DIR`) |
| `--bubblegum-config PATH` | — | Bubblegum YAML config file |
| `--bubblegum-appium-url URL` | `http://localhost:4723` | Appium server for `bubblegum_mobile` |
| `--bubblegum-capabilities JSON_OR_PATH` | — | Appium caps (inline JSON or a .json file) |

Repo-checkout test flags: `--playwright` enables the browser-gated
integration tests, `--appium` the device-gated ones.

## 8. Troubleshooting

- **"Playwright is not installed"** — `pip install -e ".[web]"` then
  `python -m playwright install chromium`.
- **A step can't find its element** — phrase it by the visible label;
  add the widget word ("… link", "… button", "… tab") to break ties.
  Check the page exposes a label (`<label for=…>` or `aria-label`):
  Bubblegum grounds through the accessibility tree, so what a screen
  reader can't name, Bubblegum can't either — fixing it helps both.
- **Step failed and you can't tell why** — look in `artifacts/`: a
  screenshot is saved per failed step and at test teardown.
- **`bubblegum_page` errors about event loops** — add
  `pytest.mark.asyncio(loop_scope="session")` (see §5).
- **Mobile test skips** — read the skip reason (`pytest -rs`); it names
  the missing piece (server down, no capabilities, client not installed).
