# Phase 19M-L — Real Environment Smoke Harness Design (Design-Only)

## 1) Purpose

Bubblegum has strong local confidence for mobile metadata and dry-run decisioning, but real-environment behavior has not yet been exercised across emulator, simulator, physical devices, or cloud matrices. A dedicated smoke harness is needed before any runtime WebView switching work so we can:

- prove baseline stability of real-session orchestration and artifact/report safety,
- validate environment-specific setup/skip behavior without changing adapter execution policy,
- establish reproducible pass/skip/fail semantics for mobile and hybrid smoke runs,
- create gating evidence required before introducing real `driver.switch_to.context` implementation.

This harness design explicitly preserves the current policy: metadata-only intelligence, no runtime switching.

## 2) Scope

This phase defines **design only** for future real-environment smoke execution:

- future folder/test organization,
- pytest markers and opt-in behavior,
- config file shape and env-var mapping,
- command conventions for each environment class,
- artifact/report outputs and metadata-safety expectations,
- skip/fail categorization,
- minimal smoke scenario catalog,
- CI rollout strategy and readiness gates.

No executable smoke harness is introduced in this phase.

## 3) Non-goals

This phase does **not** include:

- real-device test implementation,
- cloud execution implementation,
- credential generation or storage,
- runtime WebView context switching,
- Appium adapter behavior changes,
- resolver routing/priority/ranker changes,
- public API/schema changes,
- package/dependency/version changes,
- benchmark default behavior changes.

## 4) Proposed folder structure

Recommended future structure (aligned with existing `tests/unit` + `tests/integration` style):

```text
tests/
  real_env/
    README.md
    conftest.py
    config.example.yaml
    fixtures/
      __init__.py
      env_config.py
      skip_policy.py
      artifact_policy.py
    web/
      test_web_smoke_click_text.py
      test_web_smoke_form_label.py
    android/
      test_android_native_smoke.py
      test_android_hybrid_metadata_smoke.py
      test_android_system_dialog_smoke.py
    ios/
      test_ios_native_smoke.py
      test_ios_hybrid_metadata_smoke.py
      test_ios_system_dialog_smoke.py
    cloud/
      test_cloud_android_smoke.py
      test_cloud_ios_smoke.py
      test_cloud_web_smoke.py
    sample_apps/
      README.md
```

Notes:
- `sample_apps/` contains requirements/docs only at first; no binary assets committed by default.
- `fixtures/` centralizes config loading, env validation, skip categorization, and artifact-safe defaults.

## 5) Pytest marker strategy

Introduce (future) markers:

- `real_env`: umbrella marker for all real-environment smoke tests.
- `web_smoke`: local/remote browser smoke group.
- `android_emulator`: Android emulator smoke.
- `ios_simulator`: iOS simulator smoke.
- `android_device`: physical Android device smoke.
- `ios_device`: physical iOS device smoke.
- `cloud_device`: cloud-hosted device/browser smoke.
- `hybrid_webview`: scenarios validating hybrid/WebView metadata behavior.
- `system_dialog`: permission/system dialog scenarios.
- `slow`: extended runtime scenarios.

Default behavior:
- real-env tests are skipped unless explicitly enabled.
- opt-in requires `BUBBLEGUM_REAL_ENV=1` and marker selection.
- missing required env/config for selected target yields **skip**, not failure.

Opt-in examples (future):
- `-m "real_env and web_smoke"`
- `-m "real_env and android_emulator"`

## 6) Configuration strategy

Define a future template file:

- `tests/real_env/config.example.yaml`

Proposed shape:

```yaml
run:
  enabled: false
  safe_metadata_only: true
  enable_screenshots: false
  artifact_path: artifacts/real_env

target:
  platform: android         # web | android | ios
  provider: local           # local | cloud
  browser: chromium         # for web runs

appium:
  server_url: ${BUBBLEGUM_APPIUM_SERVER_URL}
  device_name: emulator-5554
  platform_version: "16"

apps:
  android_app: ${BUBBLEGUM_ANDROID_APP}
  ios_app: ${BUBBLEGUM_IOS_APP}

cloud:
  provider: ${BUBBLEGUM_CLOUD_PROVIDER}
  username_env: BUBBLEGUM_CLOUD_USERNAME
  access_key_env: BUBBLEGUM_CLOUD_ACCESS_KEY

timeouts:
  session_start_s: 60
  step_timeout_ms: 8000
  context_inventory_timeout_ms: 3000
```

Rules:
- credentials are referenced via env-var names only.
- defaults keep screenshot collection off and metadata safety on.
- any config requesting unsafe payloads should be rejected by fixture policy.

## 7) Environment variable strategy

Use a dedicated namespace to avoid collisions:

- `BUBBLEGUM_REAL_ENV=1`
- `BUBBLEGUM_APPIUM_SERVER_URL`
- `BUBBLEGUM_ANDROID_APP`
- `BUBBLEGUM_IOS_APP`
- `BUBBLEGUM_CLOUD_PROVIDER`
- `BUBBLEGUM_CLOUD_USERNAME`
- `BUBBLEGUM_CLOUD_ACCESS_KEY`
- `BUBBLEGUM_REAL_ENV_CONFIG` (optional config path override)
- `BUBBLEGUM_REAL_ENV_ARTIFACT_DIR` (optional artifact override)

Policy:
- do not store credential values in repository files.
- log only presence/absence of required env-vars, never raw secret values.

## 8) Command strategy (examples only)

Future command conventions:

```bash
# Local web smoke
BUBBLEGUM_REAL_ENV=1 \
pytest tests/real_env -m "real_env and web_smoke" -q

# Android emulator smoke
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_ANDROID_APP=/path/to/sample.apk \
pytest tests/real_env -m "real_env and android_emulator" -q

# iOS simulator smoke
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_IOS_APP=/path/to/sample.app \
pytest tests/real_env -m "real_env and ios_simulator" -q

# Android real device smoke
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_ANDROID_APP=/path/to/sample.apk \
pytest tests/real_env -m "real_env and android_device" -q

# iOS real device smoke
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_IOS_APP=/path/to/sample.ipa \
pytest tests/real_env -m "real_env and ios_device" -q

# Cloud smoke
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_CLOUD_PROVIDER=<provider> \
BUBBLEGUM_CLOUD_USERNAME=<from-secret-store> \
BUBBLEGUM_CLOUD_ACCESS_KEY=<from-secret-store> \
pytest tests/real_env -m "real_env and cloud_device" -q
```

These are intentionally documentation-only and do not add scripts in this phase.

## 9) Smoke scenario catalog (minimum)

Define a minimal deterministic catalog for future harness implementation:

1. **Web click by text** (`web_smoke`)
2. **Web form field by label** (`web_smoke`)
3. **Android native target by text/content-desc/resource-id** (`android_emulator`, `android_device`)
4. **Android hybrid WebView detection metadata** (`hybrid_webview`)
5. **iOS native target by label/name/value** (`ios_simulator`, `ios_device`)
6. **System permission dialog detection** (`system_dialog`)
7. **Scroll + repeated list/card resolution** (`slow` optional)
8. **Report/analytics artifact validation** (all smoke classes)

Hybrid scenarios in this phase remain metadata-only validation (inventory/detection/diagnostics/guardrails), not runtime switching behavior.

## 10) Artifact and reporting expectations

Each smoke run should produce:

- JSON report (`--bubblegum-report-json`)
- HTML report (`--bubblegum-report`)
- optional screenshots **only** when explicitly enabled
- safe metadata fields only:
  - `framework_detection`
  - `context_inventory`
  - `webview_switch_diagnostics`
  - `webview_switch_guardrails`

Safety requirements:
- no raw XML or raw DOM in report payloads,
- no raw context names,
- no package/process identifiers,
- no plaintext credential leakage,
- no unsafe exception dumps in final published artifacts.

## 11) Skip/fail policy

Classification policy for future harness:

- **Skip**:
  - `BUBBLEGUM_REAL_ENV` not enabled,
  - required app path missing,
  - required device not connected,
  - cloud credentials/provider missing.
- **Fail**:
  - runtime test assertions fail,
  - metadata safety assertions fail,
  - required expected report artifacts absent.
- **Setup error (categorized clearly)**:
  - Appium session bootstrap failure,
  - simulator/emulator launch timeout,
  - iOS signing/WDA startup failure.

Recommended skip reason prefixes: `env_missing:*`, `device_missing:*`, `cloud_missing:*`, `setup_blocked:*`.

## 12) CI strategy

Future staged rollout:

- **PR CI:** do not run `real_env` by default.
- **Nightly CI (optional):** local web smoke + Android emulator smoke.
- **Release candidate CI:** web + Android emulator + iOS simulator + cloud smoke subset.
- **Alpha release gate:** required real device + cloud matrix with artifact safety checks.

All pipelines should publish sanitized reports/artifacts and preserve skip/fail categorization for triage.

## 13) Real WebView switching readiness gate

Before implementing runtime `driver.switch_to.context`, require smoke harness evidence that:

1. Emulator + simulator hybrid metadata smoke is stable over repeated runs.
2. Real-device hybrid metadata smoke passes threshold (>=90% target pass, bounded flakes).
3. Cloud hybrid metadata smoke is within defined parity delta from local baselines.
4. Artifact safety checks pass across all environments (no unsafe payload leaks).
5. Guardrail decisions remain deterministic (`allowed|blocked|deferred|unsupported`) with `switch_attempted=False`.

Only after gate satisfaction should runtime switching implementation be considered.

## 14) Risks and mitigations

- **Flaky Appium sessions**
  - Mitigation: retry session bootstrap once, isolate setup vs assertion failures, collect setup diagnostics.
- **Cloud quota/cost pressure**
  - Mitigation: minimal smoke subset, scheduled windows, capped matrix expansion.
- **Device availability drift**
  - Mitigation: explicit device pool labels + skip categorization instead of ambiguous failures.
- **iOS signing/WDA instability**
  - Mitigation: dedicated setup validation stage and clear `setup_blocked` classification.
- **WebView context not appearing**
  - Mitigation: treat as expected unsupported/deferred metadata outcome in smoke when policy indicates.
- **Artifact leakage risk**
  - Mitigation: enforce safe metadata assertions and block publication on safety violation.
- **Long execution time**
  - Mitigation: strict smoke/regression split and marker-based selective execution.

## 15) Recommended next phase

**Recommendation: GO for Phase 19M-M — Real Environment Smoke Harness Skeleton.**

Reasoning:
- This design now defines structure, markers, config, policy, and gates.
- The next safest increment is a harness skeleton (fixtures, markers, skip policy, docs/examples) without enabling real switching.
- It preserves current runtime behavior while preparing deterministic infrastructure for emulator/simulator/device/cloud smoke implementation.

---

## Explicit compliance statement

This phase is documentation-only and introduces **no runtime behavior change**, **no `driver.switch_to.context` usage**, **no adapter modification**, and **no package/dependency/version change**.
