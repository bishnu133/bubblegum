# Bubblegum BDD — Given/When/Then on the NL engine

Write tests in plain-English Gherkin. The **When** and **Then** steps are
provided by Bubblegum and routed through the natural-language engine, so manual
QA can author scenarios without selectors. You provide only the **Given**
(setup/navigation), because URLs are environment-specific.

## Install

```bash
pip install "bubblegum-ai[web,test,bdd]"
python -m playwright install chromium
```

## Run

```bash
pytest examples/web/bdd/
# watch it in a visible browser:
BUBBLEGUM_BDD_HEADED=1 pytest examples/web/bdd/ -s
```

No `--playwright` flag is needed — the BDD fixtures own their own headless
Chromium (`bubblegum.bdd.fixtures`), independent of pytest-playwright.

## How it works

- `from bubblegum.bdd.steps import *` registers catch-all **When** and **Then**
  steps. `import *` is required so pytest-bdd's generated step-definition
  fixtures are collected. Each step routes the full text through
  `bubblegum.bdd.dispatcher.execute_step`, which maps the phrasing onto
  `session.act / is_visible / is_checked / selected_value / extract`.
- pytest-bdd runs steps **synchronously**, so the bindings drive the async
  session on a dedicated event loop (`bubblegum_bdd_loop`); the `bubblegum_web`
  fixture creates the Playwright page on that same loop.
- You write the **Given** (navigation) with the `bubblegum_bdd_loop` +
  `sample_app` fixtures — see `test_login_bdd.py`.

## Supported step phrasings

A leading `I ` is optional; arguments are quoted; matching is case-insensitive.

| Step | Maps to |
|---|---|
| `When I click "Sign in"` | `act("Click Sign in")` |
| `When I enter "tester" into "Username"` | `act('Enter "tester" into Username')` |
| `When I fill "Password" with "secret"` | `act('Enter "secret" into Password')` |
| `When I select "German" from "Language"` | `act("Select German from Language")` |
| `When I check "Email notifications"` | `act("Check Email notifications")` |
| `When I uncheck "Email notifications"` | `act("Uncheck Email notifications")` |
| `When I run "Click the Settings link"` | `act("Click the Settings link")` (raw NL) |
| `When I go to "http://…/login.html"` | `goto(...)` |
| `Then I should see "Dashboard"` | assert `is_visible("Dashboard")` |
| `Then I should not see "Error"` | assert not visible |
| `Then "Email notifications" should be checked` | assert `is_checked(...)` |
| `Then "Language" should have value "de"` | assert `selected_value(...) == "de"` |
| `Then "Greeting" should contain "Welcome back"` | `extract(...)` then substring check |

Anything else fails with a helpful message. Use the raw passthrough
(`run "<plain English>"`) to reach any instruction the engine supports.

## Notes

- A step that the engine **self-heals** (status `recovered`) passes, and the
  healing advisory is surfaced in the Bubblegum report — so a "click login" that
  resolved to a "Sign In" button is flagged for review rather than silently
  passing or failing.
- Requires `pytest-bdd >= 7`. The step bindings are synchronous and drive the
  async session on the `bubblegum_bdd_loop` fixture (pytest-bdd does not await
  coroutine steps), so no pytest-asyncio is needed for the BDD run. Only
  **When** and **Then** are catch-alls, so your custom **Given** steps never
  collide. Use `from bubblegum.bdd.steps import *` (the `*` is required so
  pytest-bdd's generated step fixtures are collected).
- Programmatic use without pytest-bdd:

  ```python
  from bubblegum.bdd import execute_step
  await execute_step(session, 'click "Sign in"')
  await execute_step(session, 'I should see "Dashboard"')
  ```
