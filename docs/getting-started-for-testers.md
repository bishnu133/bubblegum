# Getting Started for Testers

## What is Bubblegum?
Bubblegum is a test automation tool that lets you write simple, behavior-driven tests.
It is made to help QA teams describe user actions in plain language and run them consistently.

## Who should use it?
Use Bubblegum if you are:
- A manual tester starting automation
- A QA engineer who wants simple test setup
- A team that needs readable test scenarios

## What problem does it solve?
Bubblegum helps you:
- Turn repeatable manual checks into automated tests
- Keep test steps readable for non-developers
- Run local validation before bigger mobile/cloud trials

## Install locally (editable install)
From the Bubblegum repo root:

```bash
pip install -e .
```

Why editable install?
- You test the local code directly
- You can update docs/examples and re-run immediately
- You do **not** need PyPI for this phase

## Create a test folder
Create a simple folder structure:

```text
my-web-tests/
  bubblegum.yaml
  test_login.feature
```

Tip: You can copy the sample from `examples/web/simple_login/` and edit it.

## Write a simple web test
Create `test_login.feature` with steps like:
- Open login page
- Enter username
- Enter password
- Click login
- Verify dashboard or welcome text

Start small with one happy-path login scenario.

## Configure browser and base URL
In `bubblegum.yaml`, set:
- `app_type: web`
- `base_url: "https://your-app-url"`
- `browser: "chromium"` (or your preferred browser)
- `headless: true` for CI-like runs, `false` to watch browser
- `timeout` for slow pages
- `report_path` for output artifacts

## Run tests locally
Common commands:

```bash
pytest -q
```

Or run a specific feature folder:

```bash
pytest -q path/to/your/tests
```

## View reports
After the run, open your report folder configured in `report_path`.
Capture and keep:
- Pass/fail summary
- Logs
- Screenshots (if enabled)

Use these as evidence for GO/NO-GO decisions.

## Supported features (current)
| Area | Status | Notes |
|---|---|---|
| Local editable install | Supported | Recommended for current validation |
| Web test authoring (feature files) | Supported | Good for starter scenarios |
| Local test execution | Supported | Use local browser setup |
| Mobile/WebView real switching | Prepared, not fully executed | Planned for next phases |
| Cloud provider real trials | Prepared, not fully executed | Planned after local web validation |
| PyPI distribution | Not required now | Keep local install for this phase |

## Current limitations
- This phase is focused on local web validation only.
- Real Android/iOS/cloud execution is prepared but not the first validation step.
- Keep scenarios simple (login, navigation, basic assertions) before scaling.

## Troubleshooting
- **Import/module errors**: Re-run `pip install -e .` from repo root.
- **Browser not launching**: Check local browser/runtime setup and headless mode.
- **Timeouts**: Increase `timeout` in `bubblegum.yaml`.
- **Selectors not found**: Re-check page locators in your feature steps.
- **No report output**: Verify `report_path` exists or can be created.

## Best practices for testers
- Start with 1 critical scenario (login).
- Keep test data simple and stable.
- Avoid too many assertions in one scenario.
- Use clear scenario names.
- Save evidence on each run.
- Review failures quickly and update selectors when UI changes.
