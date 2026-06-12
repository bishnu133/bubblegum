# Validating the Web reliability improvements locally

This guide lists the exact commands to validate everything implemented in the
`claude/practical-turing-rxomfi` branch:

- iframe support, bounded post-click nav-wait, `<select>` by visible label,
  strict-mode retry, SPA re-grounding
- self-healing advisory surviving memory-cache replays
- vision tier winning on deterministic-hard targets
- mobile re-grounding parity

## 0. Setup

```bash
python -m pip install -e ".[dev,bdd]"
```

Everything in **Sections 1–4** runs with **no browser and no API key**.
**Section 5** needs a real browser; **Section 6** needs an Appium device.

## 1. Fast path — the whole unit suite

```bash
python -m pytest tests/unit -q
```

Expected: `1309 passed, 3 skipped`. This includes every browser-free check below.

## 2. Web reliability (browser-free, fakes)

```bash
python -m pytest tests/unit/test_web_resilience.py -v
```

Covers, each as a named test:

| Feature | Test |
| --- | --- |
| Bounded nav-wait uses `nav_wait_ms`, skips load-state with no nav | `test_nav_wait_uses_configured_timeout_and_skips_load_state_when_no_nav` |
| Nav-wait waits for the document only when navigation commits | `test_nav_wait_waits_for_load_state_when_navigation_commits` |
| `nav_wait_ms=0` skips the probe entirely | `test_nav_wait_zero_skips_probe_entirely` |
| `<select>` falls back from value to visible label | `test_select_falls_back_to_label_when_value_match_fails` |
| Strict-mode violation retries on `.first` | `test_strict_mode_violation_retries_on_first_match` |
| `collect_context()` merges child-frame snapshots | `test_collect_context_merges_child_frame_snapshots` |
| Execution routes into the owning iframe | `test_execution_routes_into_child_frame_when_main_has_no_match` |
| Text extraction reads from an iframe | `test_extract_text_reads_from_child_frame` |
| SPA re-grounding retries + re-collects context | `test_ground_with_wait_retries_and_recollects_context` |

## 3. Self-healing advisory across cache replays

```bash
python -m pytest tests/unit/test_self_healing_advisory.py -v
```

Key tests: `test_healing_advisory_is_persisted_and_replays_from_cache` (drives
`act()` twice and asserts the second, cache-replayed run stays `recovered` and
keeps the advisory) and the `TestResolveHealingAdvisory` class.

## 4. Vision tier on deterministic-hard targets + mobile re-grounding

```bash
python -m pytest tests/unit/test_vision_deterministic_hard.py tests/unit/test_mobile_reground.py -v
```

- `test_vision_tier_wins_on_nameless_icon_target` — vision wins when no text/role
  resolver can match a nameless icon button.
- `test_deterministic_wins_when_target_has_a_clean_name` — vision does **not**
  displace a clean deterministic/fuzzy match.
- `test_deterministic_hard_target_fails_without_vision_candidates` /
  `test_vision_tier_blocked_under_low_cost_policy` — the contrast cases.
- `test_mobile_reground_recollects_and_retries` — re-grounding works on mobile.

## 5. Live browser e2e (real Chromium)

```bash
python -m pip install -e ".[web]"
python -m playwright install chromium

# iframe routing + select-by-label, driven through the public NL flow:
python -m pytest tests/integration/test_phase22e10_web_resilience_e2e.py -v --playwright

# Existing widget-lab regression (tabs/accordion/slider/select/combobox):
python -m pytest tests/integration -v --playwright
```

You can also watch the broader smoke run against a public site:

```bash
python examples/test_real_web.py --headed
```

## 6. Mobile e2e (real device / emulator)

Full mobile e2e needs an Appium server + device. The harness is env-gated and
skips cleanly when the variables are unset:

```bash
export BUBBLEGUM_REAL_ENV=1
export BUBBLEGUM_APPIUM_SERVER_URL="http://127.0.0.1:4723"
export BUBBLEGUM_ANDROID_DEVICE_NAME="emulator-5554"
export BUBBLEGUM_ANDROID_APP="/path/to/app.apk"   # or PACKAGE + ACTIVITY

python -m pytest tests/real_env/android -v -m android_emulator
```

Without those variables the same command reports the mobile tests as skipped —
which is the expected result on a machine with no device attached.
