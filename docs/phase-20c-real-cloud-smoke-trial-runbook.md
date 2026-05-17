# Phase 20C — Real Cloud Smoke Trial Runbook

## 1) Purpose

This runbook defines a **safe, documentation-only trial process** for executing real cloud smoke tests against supported Appium cloud providers.

It validates that:

- the existing real cloud harness can execute on real providers when explicitly enabled;
- collection, context, and reporting smoke checks behave as designed;
- generated artifacts remain privacy-safe.

This runbook does **not** introduce runtime behavior changes. It does not change cloud session behavior, capability construction, reporting logic, resolver/ranker/scoring behavior, or WebView switching behavior.

## 2) Supported providers

- pCloudy
- BrowserStack
- Sauce Labs
- LambdaTest
- generic Appium cloud

## 3) Safety rules

- Use credentials **only** through environment variables.
- Never commit credentials, tokens, or provider secrets.
- Keep screenshots disabled by default.
- Do not include raw hierarchy/page source/capability payloads in reports.
- Real-environment suites remain skip-by-default until explicitly enabled.
- Do not implement or invoke WebView switching.
- Do not add click/interaction behavior outside current context-collection/reporting smoke intent.

## 4) Provider setup matrix

| Provider | Required URL/env | Capability namespace | Android support | iOS support | Notes |
|---|---|---|---|---|---|
| pCloudy | Default URL available via provider mapping; optional override with `BUBBLEGUM_CLOUD_APPIUM_URL`/`BUBBLEGUM_APPIUM_SERVER_URL` | `pCloudy_Options` | Yes | Yes | Provider credentials mapped under provider namespace; use placeholder credentials in docs/commands. |
| BrowserStack | Default URL available via provider mapping; optional override with `BUBBLEGUM_CLOUD_APPIUM_URL`/`BUBBLEGUM_APPIUM_SERVER_URL` | `bstack:options` | Yes | Yes | Username key differs (`userName`) from some providers. |
| Sauce Labs | Default URL available via provider mapping; optional override with `BUBBLEGUM_CLOUD_APPIUM_URL`/`BUBBLEGUM_APPIUM_SERVER_URL` | `sauce:options` | Yes | Yes | Session naming uses provider conventions (`name`/`build`). |
| LambdaTest | Default URL available via provider mapping; optional override with `BUBBLEGUM_CLOUD_APPIUM_URL`/`BUBBLEGUM_APPIUM_SERVER_URL` | `LT:Options` | Yes | Yes | Username key uses `user` in provider namespace. |
| generic Appium cloud | **Explicit URL required** (`BUBBLEGUM_CLOUD_APPIUM_URL` or `BUBBLEGUM_APPIUM_SERVER_URL`) | `appium:options` | Yes | Yes | No provider-specific credential namespace injected by harness. |

## 5) Required env vars

Set these variables for trial execution:

- `BUBBLEGUM_REAL_ENV=1`
- `BUBBLEGUM_CLOUD_DEVICE=1`
- `BUBBLEGUM_CLOUD_PROVIDER`
- `BUBBLEGUM_CLOUD_USERNAME`
- `BUBBLEGUM_CLOUD_ACCESS_KEY`
- `BUBBLEGUM_CLOUD_PLATFORM` (`android` or `ios`)
- `BUBBLEGUM_CLOUD_DEVICE_NAME`
- one app launch selector:
  - `BUBBLEGUM_CLOUD_APP`, or
  - `BUBBLEGUM_CLOUD_APP_ID`, or
  - `BUBBLEGUM_CLOUD_ANDROID_PACKAGE` + `BUBBLEGUM_CLOUD_ANDROID_ACTIVITY`, or
  - `BUBBLEGUM_CLOUD_IOS_BUNDLE_ID`

Optional but commonly used:

- `BUBBLEGUM_CLOUD_APPIUM_URL`
- `BUBBLEGUM_APPIUM_SERVER_URL`
- `BUBBLEGUM_CLOUD_PLATFORM_VERSION`
- `BUBBLEGUM_CLOUD_AUTOMATION_NAME`
- `BUBBLEGUM_CLOUD_SESSION_NAME`
- `BUBBLEGUM_CLOUD_BUILD_NAME`

## 6) pCloudy example (placeholders only)

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_CLOUD_DEVICE=1 \
BUBBLEGUM_CLOUD_PROVIDER=pcloudy \
BUBBLEGUM_CLOUD_USERNAME="<PCLOUDY_USERNAME>" \
BUBBLEGUM_CLOUD_ACCESS_KEY="<PCLOUDY_ACCESS_KEY>" \
BUBBLEGUM_CLOUD_PLATFORM=android \
BUBBLEGUM_CLOUD_DEVICE_NAME="<ANDROID_DEVICE_NAME>" \
BUBBLEGUM_CLOUD_APP_ID="<PCLOUDY_APP_ID_OR_PUBLIC_LINK>" \
pytest tests/real_env/cloud/test_cloud_device_smoke.py -k collect_context -q
```

## 7) BrowserStack example (placeholders only)

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_CLOUD_DEVICE=1 \
BUBBLEGUM_CLOUD_PROVIDER=browserstack \
BUBBLEGUM_CLOUD_USERNAME="<BROWSERSTACK_USERNAME>" \
BUBBLEGUM_CLOUD_ACCESS_KEY="<BROWSERSTACK_ACCESS_KEY>" \
BUBBLEGUM_CLOUD_PLATFORM=android \
BUBBLEGUM_CLOUD_DEVICE_NAME="<ANDROID_DEVICE_NAME>" \
BUBBLEGUM_CLOUD_APP="bs://<BROWSERSTACK_APP_ID>" \
pytest tests/real_env/cloud/test_cloud_device_smoke.py -q
```

## 8) Sauce Labs example (placeholders only)

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_CLOUD_DEVICE=1 \
BUBBLEGUM_CLOUD_PROVIDER=saucelabs \
BUBBLEGUM_CLOUD_USERNAME="<SAUCE_USERNAME>" \
BUBBLEGUM_CLOUD_ACCESS_KEY="<SAUCE_ACCESS_KEY>" \
BUBBLEGUM_CLOUD_PLATFORM=ios \
BUBBLEGUM_CLOUD_DEVICE_NAME="<IOS_DEVICE_NAME>" \
BUBBLEGUM_CLOUD_APP="storage:filename=<APP_FILENAME.ipa>" \
pytest tests/real_env/cloud/test_cloud_device_smoke.py -k reporting -q
```

## 9) LambdaTest example (placeholders only)

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_CLOUD_DEVICE=1 \
BUBBLEGUM_CLOUD_PROVIDER=lambdatest \
BUBBLEGUM_CLOUD_USERNAME="<LAMBDATEST_USERNAME>" \
BUBBLEGUM_CLOUD_ACCESS_KEY="<LAMBDATEST_ACCESS_KEY>" \
BUBBLEGUM_CLOUD_PLATFORM=android \
BUBBLEGUM_CLOUD_DEVICE_NAME="<ANDROID_DEVICE_NAME>" \
BUBBLEGUM_CLOUD_APP="lt://<LAMBDATEST_APP_ID>" \
pytest tests/real_env/cloud/test_cloud_device_smoke.py -q
```

## 10) Generic Appium cloud example (placeholders only)

> Generic provider requires an explicit URL.

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_CLOUD_DEVICE=1 \
BUBBLEGUM_CLOUD_PROVIDER=generic \
BUBBLEGUM_CLOUD_APPIUM_URL="https://<YOUR-APPIUM-CLOUD>/wd/hub" \
BUBBLEGUM_CLOUD_USERNAME="<GENERIC_USERNAME>" \
BUBBLEGUM_CLOUD_ACCESS_KEY="<GENERIC_ACCESS_KEY>" \
BUBBLEGUM_CLOUD_PLATFORM=ios \
BUBBLEGUM_CLOUD_DEVICE_NAME="<IOS_DEVICE_NAME>" \
BUBBLEGUM_CLOUD_IOS_BUNDLE_ID="<IOS_BUNDLE_ID>" \
pytest tests/real_env/cloud/test_cloud_device_smoke.py -q
```

## 11) Commands to run

Primary commands:

```bash
pytest tests/real_env/cloud -q
pytest tests/real_env/cloud/test_cloud_device_smoke.py -q
```

Optional targeted selectors:

```bash
pytest tests/real_env/cloud/test_cloud_device_smoke.py -k collect_context -q
pytest tests/real_env/cloud/test_cloud_device_smoke.py -k reporting -q
```

## 12) Expected outputs

- Default behavior (no real-env enablement): cloud smoke tests are skipped.
- Explicit enablement with valid cloud environment: tests execute real cloud session attempts.
- Reporting tests generate JSON and HTML artifacts under pytest `tmp_path`.
- Report-safe metadata includes `cloud_provider_summary` only (no secret-bearing payloads).

## 13) Artifact inspection checklist

For each generated JSON/HTML pair:

- [ ] JSON parses successfully.
- [ ] HTML report exists.
- [ ] `cloud_provider_summary` is present.
- [ ] No username/access_key/token/secret values.
- [ ] No `raw_capabilities` content.
- [ ] No `raw_xml`, `hierarchy_xml`, `raw_dom`, `page_source`, or screenshot bytes.
- [ ] No raw package/process/context identifier leakage.

## 14) Failure triage

Common failure classes and first checks:

1. **Invalid cloud URL**
   - Verify provider default vs explicit URL vars.
   - For generic provider, verify explicit Appium hub URL is set.
2. **Invalid credentials**
   - Confirm username/access key env vars are set and current.
3. **App not uploaded / invalid app ID**
   - Validate provider-specific app reference format.
4. **Device unavailable**
   - Try a different device name or region-supported equivalent.
5. **automationName mismatch**
   - Use platform-correct automation defaults or explicit override.
6. **platformVersion mismatch**
   - Remove overly strict platform version first, then re-pin.
7. **Provider capability namespace issue**
   - Verify provider name and capability namespace mapping assumptions.
8. **Network timeout / transport issues**
   - Retry with increased patience and verify outbound connectivity.

## 15) Trial result template

```markdown
Provider:
Platform:
Device:
App reference type:
Command:
Result:
Artifacts generated:
Safety checks:
Issues found:
Follow-up:
```

## 16) GO/NO-GO after real trial

Use this gate before moving forward:

### GO criteria

- At least one real cloud smoke run succeeds on pCloudy with explicit opt-in env vars.
- At least one additional provider run (BrowserStack/Sauce Labs/LambdaTest/generic) is attempted and outcome documented.
- Reporting artifacts are generated and pass the safety checklist (no secret/raw payload leakage).
- No runtime behavior changes are required to execute baseline smoke flow.
- No WebView switching behavior is introduced.

### NO-GO criteria

- Repeated provider failures with unresolved URL/auth/app-reference issues.
- Artifact privacy checks fail.
- Any need is discovered to alter runtime behavior just to pass baseline smoke intent.

If GO criteria are met, proceed to design-oriented next phase planning or expanded trial execution per project priorities.
