# Phase 20D — Real pCloudy Smoke Trial Execution Results

## 1) Purpose

This phase validates that the **existing** cloud-device smoke harness executes safely against a **real pCloudy session** for context collection and reporting artifacts, without altering resolver/ranker behavior or runtime interaction logic.

## 2) Scope

- pCloudy-first trial flow.
- Cloud context collection smoke.
- Cloud reporting artifact smoke.
- No app interaction beyond context collection/reporting smoke tests.
- No WebView switching.

## 3) Required local setup checklist

- [ ] Python virtual environment is active.
- [ ] Bubblegum package is installed in editable mode.
- [ ] Appium + pCloudy account access are available.
- [ ] Application is uploaded or a valid app reference is available.
- [ ] A pCloudy device target is selected.
- [ ] Credentials are provided only via environment variables.

## 4) Required environment variables

Use placeholders only (never commit real values):

- `BUBBLEGUM_REAL_ENV=1`
- `BUBBLEGUM_CLOUD_DEVICE=1`
- `BUBBLEGUM_CLOUD_PROVIDER=pcloudy`
- `BUBBLEGUM_CLOUD_USERNAME=<placeholder>`
- `BUBBLEGUM_CLOUD_ACCESS_KEY=<placeholder>`
- `BUBBLEGUM_CLOUD_PLATFORM=android` or `ios`
- `BUBBLEGUM_CLOUD_DEVICE_NAME=<placeholder>`
- `BUBBLEGUM_CLOUD_APP=<placeholder>` or `BUBBLEGUM_CLOUD_APP_ID=<placeholder>`
- Optional: `BUBBLEGUM_CLOUD_PLATFORM_VERSION`
- Optional: `BUBBLEGUM_CLOUD_AUTOMATION_NAME`
- Optional: `BUBBLEGUM_CLOUD_SESSION_NAME`
- Optional: `BUBBLEGUM_CLOUD_BUILD_NAME`

## 5) Commands to run

```bash
pytest tests/real_env/cloud/test_cloud_device_smoke.py::test_cloud_device_smoke_collect_context_mvp -q
pytest tests/real_env/cloud/test_cloud_device_smoke.py::test_cloud_device_reporting_artifacts_are_safe -q
pytest tests/real_env/cloud -q
```

## 6) Expected successful result

- Tests execute (not skipped) when required real-env/cloud flags and credentials are set.
- Context collection smoke passes.
- Reporting artifact smoke generates expected report outputs.
- `cloud_provider_summary` appears in produced report artifacts.
- No credentials/raw capabilities/raw hierarchy leakage in artifacts.
- No `switch_to.context` usage.

## 7) Expected failure / triage matrix

| Symptom | Likely cause | Triage action |
|---|---|---|
| Auth/session creation fails | Invalid credentials | Re-check `BUBBLEGUM_CLOUD_USERNAME` / `BUBBLEGUM_CLOUD_ACCESS_KEY` env vars and account status. |
| Session init fails before app launch | Invalid app ID or upload reference | Validate `BUBBLEGUM_CLOUD_APP` / `BUBBLEGUM_CLOUD_APP_ID` format and ownership. |
| Device allocation fails | Unsupported/invalid device name | Correct `BUBBLEGUM_CLOUD_DEVICE_NAME` to provider-supported value. |
| Session create rejects capability | Wrong platform version | Align `BUBBLEGUM_CLOUD_PLATFORM_VERSION` to device/provider support. |
| Driver init or command failure | `automationName` mismatch | Set/remove `BUBBLEGUM_CLOUD_AUTOMATION_NAME` to match provider/device requirements. |
| Cannot connect to server/hub | Hub URL issue | Validate endpoint/region config and network reachability. |
| Session created but test times out on app readiness | App launch timeout | Confirm app package integrity, launchability, and provider-side startup timing. |
| Session created but source collection fails | Page source timeout | Re-run with stable device and inspect provider/Appium logs for transient failures. |
| Capability mapping appears ignored or rejected | Provider namespace mismatch | Verify expected pCloudy namespacing and capability key handling in harness config. |

## 8) Actual trial result template

Date:
Provider:
Region/Hub:
Platform:
Device:
Platform version:
App reference type:
Command:
Result:
Failure/skip/pass:
Artifacts:
Safety check:
Issue found:
Fix required:
Decision:

## 9) GO / NO-GO criteria

**GO** if all are true:

- pCloudy context smoke passes.
- Reporting artifact smoke passes.
- No unsafe leakage is observed in generated artifacts.
- No runtime behavior changes are required.

**NO-GO** if any are true:

- Provider capability mapping is incorrect.
- Credential leakage risk is detected.
- Reports include raw capabilities or raw hierarchy/source payloads.
- Appium session setup is unstable for repeated smoke execution.

## 10) Next action recommendation

- If trial passes: **Phase 20E — Cloud Trial Result Audit and Provider Matrix Update**.
- If trial fails: **Phase 20E — pCloudy Capability Fix / Trial Stabilization**.

---

## Validation checklist for this phase

Run:

```bash
pytest --collect-only -q
git diff --check
# repo-wide context-switch usage check
rg "switch_to\.context" . || true
```

Expected:

- Docs-only change unless a small documented fix is required.
- `pytest --collect-only -q` remains **866 collected**.
- No runtime behavior changes.
