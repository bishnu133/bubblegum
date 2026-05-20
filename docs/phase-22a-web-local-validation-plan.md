# Phase 22A — Web Local Validation Plan

## Purpose
Validate Bubblegum against a real web application locally before running mobile/WebView/cloud real trials.
This reduces risk and helps confirm tester onboarding flow.

## Why PyPI is not needed yet
- Phase 22A is validation-focused, not distribution-focused.
- Editable local install is faster for iteration.
- We avoid release overhead while behavior is still being validated in real usage.

## Local validation approach
1. Install Bubblegum locally in editable mode.
2. Create or copy a small web login test.
3. Point config to a real, stable web application.
4. Run baseline checks and test collection.
5. Run benchmark and diagnostics scripts.
6. Capture evidence and decide GO/NO-GO.

## Editable install steps
From repo root:

```bash
python -m pip install -e .
```

Then verify collection and scripts run with the required commands.

## Suggested real web app selection criteria
Choose an app that is:
- Stable (UI does not change daily)
- Non-production or safe test environment
- Has dedicated test accounts
- Has predictable login flow
- Allows legal/compliant automation usage

## Required test scenarios
Minimum set:
1. Successful login (happy path)
2. Invalid login (error message path)
3. Logout path
4. Simple authenticated navigation check

Nice-to-have:
- Session timeout handling
- Basic form submission

## Evidence to capture
For each scenario/run, capture:
- Command used
- Timestamp
- Pass/fail result
- Logs
- Screenshots (where useful)
- Environment details (OS, browser, Bubblegum version from local source)

## GO/NO-GO criteria
**GO** if all are true:
- Editable install works cleanly
- Baseline validation scripts run successfully
- Test collection baseline remains expected (or intentional delta documented)
- Required scenarios are automated and run locally with reproducible outcomes
- Evidence package is complete

**NO-GO** if any are true:
- Local install is unstable
- Required checks fail without understood workaround
- Scenario failures are due to framework instability (not app/test data)
- Evidence is incomplete

## Next steps after web validation
If GO:
1. Proceed to Phase 22B: run Bubblegum against a real web app locally at broader scenario depth.
2. Finalize execution notes for mobile/WebView switching trial.
3. Move to real Android/iOS/cloud trial execution plan.

If NO-GO:
1. Log blockers with reproduction steps.
2. Apply minimal, focused fixes.
3. Re-run Phase 22A checks before expanding scope.
