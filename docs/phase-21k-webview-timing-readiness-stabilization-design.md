# Phase 21K — WebView Timing/Readiness Stabilization Design

## 1) Purpose

Phase 21K documents timing and readiness risks in real WebView context switching and defines a safe, bounded stabilization strategy for a future implementation phase.

This phase is **design/audit only** and is intended to reduce flakiness in Android/iOS/cloud sample-app trials while preserving current strict safety boundaries.

## 2) Current behavior summary

Current behavior after Phase 21J is:

- Real WebView switching is strict opt-in and limited to **validate/extract** paths.
- **Execute remains unwired** for real WebView switching and must remain so.
- Context inventory is collected before switch planning.
- Selection uses a **selected WebView context index** in the filtered WebView context list.
- Restore is attempted after a successful switch path; restore policy is fail-closed when configured.
- Android/iOS/cloud real-env smoke tests are skip-by-default and opt-in only.
- JSON/HTML reporting and real-env smoke tests include metadata/artifact safety checks.

## 3) Non-goals

This phase explicitly does **not** include:

- Runtime implementation of readiness waits.
- Execute-path WebView action support or wiring expansion.
- Provider-specific runtime workarounds/hacks.
- Resolver/ranker/scoring/confidence logic changes.
- Memory lookup behavior changes.
- Dependency additions, package version changes, or configuration rollout changes.

## 4) Timing/readiness risks

The following risks are the primary focus of this design:

1. **WebView context appears late** after initial context inventory capture.
2. **Context list changes after collection** (ordering/count differs on subsequent polls).
3. **Selected index becomes stale** when a refreshed list no longer matches prior indexing.
4. **WebView loaded but DOM not ready** for validate/extract operations.
5. **Validate target not visible yet** even when switch succeeds.
6. **Extract target unavailable** during transitional page load state.
7. **Native/system dialog interrupts** (permissions/system alerts) block expected flow.
8. **Cloud provider session delay** introduces late context stabilization.
9. **iOS WebView context naming delay** delays detectable WEBVIEW context names.
10. **Android WebView debugging/context exposure delay** delays switchable context appearance.

## 5) Proposed readiness model

Future implementation should use an explicit, safe readiness-state model:

- `not_checked`
- `waiting_for_webview_context`
- `context_available`
- `switching`
- `switched`
- `waiting_for_target`
- `target_ready`
- `restore_pending`
- `restored`
- `failed_closed`

Design intent:

- States are metadata-first and safe for reporting.
- Transitions are monotonic toward either success (`restored`) or safe failure (`failed_closed`).
- `failed_closed` is terminal for timeout/readiness failures under fail-closed policy.

## 6) Proposed wait strategy (design only)

A future implementation should introduce bounded waits in three places:

1. **WebView context availability wait**
   - Poll context inventory for WebView presence up to timeout.
   - Stop early on success.

2. **Selected context reference resolution wait**
   - If selected index/reference becomes stale, permit bounded refresh attempts.
   - Re-resolve only within bounded attempts/time.

3. **Post-switch target readiness wait**
   - After successful switch, allow bounded waiting before validate/extract executes.

Required constraints:

- All waits are bounded by timeout + poll interval.
- No infinite loop / no unbounded recursion.
- Configurable timeout and poll interval.
- No raw page source capture for readiness logic.
- Timeout/readiness failure must fail closed when enabled.

## 7) Config proposal (future; not implemented in 21K)

Proposed future fields (default-off / safe defaults):

- `webview_readiness_wait_enabled=False`
- `webview_context_wait_timeout_ms=0` (or a very small conservative default)
- `webview_context_poll_interval_ms=250`
- `webview_target_wait_timeout_ms=0` (or a very small conservative default)
- `max_context_refresh_attempts=1`
- `fail_closed_on_readiness_timeout=True`

Notes:

- `0` timeout preserves current no-wait behavior by default.
- Any non-zero default must remain conservative to avoid masking real bugs.
- This phase defines schema direction only; no config code changes are included.

## 8) Metadata proposal (future safe diagnostics)

Proposed metadata object:

- `webview_readiness_diagnostics`:
  - `enabled`
  - `status`
  - `reason`
  - `context_refresh_attempts`
  - `target_wait_attempted`
  - `timeout_ms`
  - `poll_interval_ms`
  - `evidence`
  - `warnings`
  - `safe_metadata_only`

Safety requirements:

- No raw context names.
- No page source/DOM snapshots.
- No screenshots.
- No provider payload/capability dumps.
- Diagnostics remain summary-only and sanitizer-compatible with existing artifact checks.

## 9) Testing strategy (future phases)

Future implementation validation should include:

- Unit tests for readiness wait-plan builder/state transitions.
- Fake-driver scenario where WebView context appears late.
- Stale selected-context-index scenario and bounded refresh handling.
- Timeout behavior assertions (including fail-closed path).
- Target wait success/failure coverage after switch.
- Restore behavior: if switch occurred and readiness fails later, restore is still attempted.
- JSON/HTML reporting tests for readiness metadata safety.
- Android/iOS/cloud strict-mode real-env smoke coverage with readiness opt-in.

## 10) Real trial impact

Readiness stabilization is expected to improve:

- **Android sample app trials** where WebView availability lags initial navigation.
- **iOS sample app trials** with delayed/sometimes-late WebView context naming/exposure.
- **pCloudy/cloud provider trials** where remote session startup and context surfacing are slower.
- General handling of **flaky WebView startup timing** without broadening execution scope.

## 11) Risk matrix

| Risk | Why it matters | Mitigation in proposed design | Residual risk |
|---|---|---|---|
| Hiding real bugs with waits | Over-wait can mask deterministic defects | default-off, bounded conservative timeouts, explicit status/reason metadata | Medium |
| Increased execution time | Waits can slow runs | strict bounded timeouts + small poll interval | Low/Medium |
| False pass after delayed target | Late readiness may pass unstable app state | preserve strict validate/extract assertions and explicit wait evidence | Medium |
| Stale context after wait | Reordering can invalidate selected index | bounded refresh + re-resolution + fail-closed | Medium |
| Provider-specific behavior drift | Cloud variance can push ad-hoc hacks | provider-neutral generic wait model only | Medium |
| Metadata leakage | Diagnostics can leak sensitive internals | safe-metadata-only fields, no raw names/source/payload | Low |
| Infinite wait risk | Stability bug can stall pipeline | hard timeout boundaries, no unbounded loops | Low |

## 12) Recommended implementation sequence

Recommended phased rollout:

1. **21L — WebView Readiness Wait Plan Helper (metadata-only)**
2. **21M — WebView Readiness Reporting/Analytics**
3. **21N — Opt-in Readiness Wait Integration for validate/extract**
4. **21O — Android Sample Trial with Readiness**
5. **21P — iOS Sample Trial with Readiness**
6. **21Q — Cloud/pCloudy Trial with Readiness**

## 13) GO/NO-GO recommendation

**Recommendation: GO for 21L only if all constraints are met:**

- Helper remains metadata-only in 21L.
- Wait logic is strictly bounded (no infinite waits).
- Behavior remains default-off/safe by default.
- No execute wiring changes.
- No raw context/source/provider-payload leakage.

If any constraint is violated, recommendation is **NO-GO** until corrected.
