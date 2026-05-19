# Phase 21J — Cloud Provider WebView Trial Results Template

## 1) Purpose

This document records **cloud real-device WebView trial results** for Bubblegum's strict opt-in WebView switching path, limited to **validate/extract** operations.

Execution status for this phase: **prepared, not executed**.

## 2) Trial scope

- Provider-neutral cloud flow is the baseline.
- **pCloudy** is the first trial target for initial execution.
- **BrowserStack / Sauce Labs / LambdaTest / generic** remain supported and in-scope.
- Trial covers **validate/extract only**.
- **execute remains unsupported/unwired** and must not be expanded in this phase.

## 3) Provider priority

- First recommended provider: **pCloudy**.
- Also supported: **BrowserStack, Sauce Labs, LambdaTest, generic**.
- No provider-specific runtime behavior should be introduced unless isolated, minimal, and clearly justified.

## 4) Sample app / screen details (placeholders)

- App reference: `<app reference placeholder>`
- Platform: `<android|ios>`
- Device: `<device placeholder>`
- WebView screen: `<screen placeholder>`
- Validate target: `<validate text placeholder>`
- Extract ref: `<extract ref placeholder>`

## 5) Environment variables used (placeholders only)

### Required

- `BUBBLEGUM_REAL_ENV=1`
- `BUBBLEGUM_CLOUD_DEVICE=1`
- `BUBBLEGUM_CLOUD_PROVIDER=pcloudy|browserstack|saucelabs|lambdatest|generic`
- `BUBBLEGUM_CLOUD_USERNAME=<placeholder>`
- `BUBBLEGUM_CLOUD_ACCESS_KEY=<placeholder>`
- `BUBBLEGUM_CLOUD_PLATFORM=android|ios`
- `BUBBLEGUM_CLOUD_DEVICE_NAME=<placeholder>`
- `BUBBLEGUM_CLOUD_APP=<placeholder>` **or** `BUBBLEGUM_CLOUD_APP_ID=<placeholder>`
- `BUBBLEGUM_CLOUD_WEBVIEW_SWITCH_SMOKE=1`
- `BUBBLEGUM_CLOUD_WEBVIEW_VALIDATE_TEXT=<placeholder>`
- `BUBBLEGUM_CLOUD_WEBVIEW_EXTRACT_REF=<placeholder>`

### Optional

- `BUBBLEGUM_CLOUD_WEBVIEW_REQUIRE_SWITCH=1`
- `BUBBLEGUM_CLOUD_WEBVIEW_ALLOWED_OPERATION=validate|extract`
- `BUBBLEGUM_CLOUD_WEBVIEW_EXPECT_STATUS=<placeholder>`
- `BUBBLEGUM_CLOUD_APPIUM_URL=<placeholder>` **or** `BUBBLEGUM_APPIUM_SERVER_URL=<placeholder>` (generic/provider override)

## 6) Commands executed

Document and run (when credentials/device/app are available):

- `pytest tests/real_env/cloud/test_cloud_webview_switch_smoke.py::test_cloud_webview_switch_smoke_validate_extract_real_env -q`
- `pytest tests/real_env/cloud/test_cloud_webview_switch_smoke.py::test_cloud_webview_switch_reporting_artifacts_are_safe -q`

Current phase status: commands are documented for execution, but real cloud trial is **prepared, not executed**.

## 7) Expected success criteria

- Tests do not skip when all required cloud variables are set.
- Cloud session starts successfully.
- WebView context is detected.
- Validate/extract path runs.
- Switch is attempted when strict mode requires switching.
- Restore is attempted and restored after WebView access.
- `webview_switch_wiring_plan` is present.
- `webview_switch_execution` is present if a switch attempt occurs.
- JSON/HTML artifacts are safe/sanitized.
- Credentials and capabilities are not leaked.
- Execute path remains unwired.

## 8) Actual result template (copy/paste)

| date (UTC) | provider | platform | device | app reference | command | validate target | extract ref | result summary | skip/pass/fail | switch status | restore status | artifact paths | provider logs reviewed? | leakage check | issues found | GO/NO-GO decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `<YYYY-MM-DD>` | `<pcloudy|browserstack|saucelabs|lambdatest|generic>` | `<android|ios>` | `<device>` | `<app ref>` | `<pytest command>` | `<validate text>` | `<extract ref>` | `<short summary>` | `<skip|pass|fail>` | `<not-required|attempted-ok|attempted-failed|not-attempted>` | `<restored|restore-failed|not-attempted>` | `<json/html paths>` | `<yes|no>` | `<pass|fail>` | `<none or issue list>` | `<GO|NO-GO>` |

## 9) Artifact safety checklist

- [ ] No username/access key in JSON/HTML/logs.
- [ ] No raw capabilities in JSON/HTML/logs.
- [ ] No raw WebView/native context names.
- [ ] No page source/XML/screenshots included.
- [ ] No exception internals leaked.
- [ ] Provider-safe summary only.

## 10) Failure triage matrix

| failure mode | likely signal | primary checks | action |
|---|---|---|---|
| skipped because env missing | pytest skip with env gating | verify required env vars are set | populate env and rerun |
| cloud auth failed | session creation/auth error | verify username/access key and provider URL | correct credentials/endpoint |
| app reference invalid | app not found/install failure | verify `BUBBLEGUM_CLOUD_APP` / `BUBBLEGUM_CLOUD_APP_ID` | update app reference |
| provider capability rejected | capability validation error | inspect provider capability mapping | adjust provider-compatible capabilities (no runtime hack) |
| no WebView context found | no switch candidate context | confirm app screen truly opens WebView | adjust test flow/screen timing |
| switch not attempted | strict switch preconditions unmet | verify require-switch/operation configuration | correct env and rerun |
| switch failed | context switch exception/timeout | inspect sanitized execution summary and provider logs | triage context readiness/capabilities |
| restore failed | did not return to original context | inspect restore step and provider behavior | treat as NO-GO and investigate |
| validate target not found | validate step failed | verify target text and screen state | correct validate target / navigation |
| extract ref invalid | extraction key/ref mismatch | verify extract reference format/content | correct extract ref |
| artifact leakage failed | safety test reports leak | inspect artifacts for sensitive/raw fields | block rollout, patch sanitization |

## 11) GO/NO-GO criteria

### GO

- Session runs.
- Switch/restore works, or non-switch outcome is understood and acceptable for the scenario.
- Artifacts are safe.
- No execute wiring changed.
- Provider-neutral behavior preserved.

### NO-GO

- Credential leak.
- Raw capability leak.
- Restore failure.
- Provider-specific runtime hack is required.
- Execute path changed.
- Repeated unstable cloud session creation.

## 12) Next action recommendation

- If **pCloudy passes**: run **BrowserStack / Sauce Labs / LambdaTest / generic** as optional follow-up coverage.
- If **pCloudy fails**: document provider issue and triage capability mapping, while preserving provider-neutral runtime behavior.
- Then proceed to **Phase 21K — WebView Timing/Readiness Stabilization**.

---

## Phase 21J execution record

- Trial execution state: **prepared, not executed**.
- Reason: real provider credentials, device allocation, and app reference are not embedded in repository docs/templates.
- Next step: execute the two cloud pytest commands above once credentials/device/app are available.
