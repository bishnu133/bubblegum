# Phase 19B — Object Intelligence Benchmark and Regression Design

Status: **Design/specification only** (no runtime/API/schema/dependency/version changes).

## 1) Scope and framing

Phase 19A concluded:
- architectural strength: **strong alpha**
- empirical capability: **unrated** until a benchmark exists

Phase 19B defines how Bubblegum will measure object-identification capability without changing resolver/runtime behavior.

### Explicit non-goals for Phase 19B
- No resolver tuning.
- No benchmark fixture implementation in this phase.
- No benchmark runner behavior changes in this phase.
- No runtime/API/schema/dependency/version changes.
- No release tag/publish actions.

---

## 2) Clear separation: Benchmark vs Regression

## Object Intelligence Benchmark (capability measurement)
**Purpose:** Measure how reliably Bubblegum identifies the intended UI object from natural-language steps across web and mobile.

This suite answers: “How good is object identification?”

## Regression Suite (correctness/stability guardrail)
**Purpose:** Prevent accidental breakage of existing behavior and contracts.

This suite answers: “Did we break existing behavior?”

### Why separation is mandatory
- Regression tests are pass/fail stability checks.
- Capability benchmarks are comparative quality/latency measurements.
- A green regression suite does **not** imply strong object-identification capability.

---

## 3) Object Intelligence Benchmark design

## 3.1 Purpose
Measure target-identification quality, safety, and cost/latency behavior for realistic object-targeting tasks across deterministic, memory-assisted, and visual/provider-assisted paths.

## 3.2 Taxonomy (object categories)
Benchmark categories must include:
1. simple button/link/text
2. input field
3. dropdown/select
4. checkbox/radio
5. modal/popup
6. duplicate labels
7. table/list/card row action
8. iframe
9. shadow DOM
10. icon-only controls
11. OCR visual text
12. vision visual target
13. stale/re-render scenario
14. hidden/offscreen/scroll-to-find element

## 3.3 Mobile benchmark slice taxonomy
Mobile categories must include:
1. native Android hierarchy
2. Jetpack Compose
3. native iOS
4. SwiftUI
5. React Native
6. Flutter
7. mobile WebView/hybrid
8. system dialogs
9. mobile icon-only controls
10. empty input fields
11. scroll-to-find
12. list item action
13. permission dialog
14. orientation/density-sensitive mapping

## 3.4 Ground-truth case format (spec)
Each benchmark case should define:
- `case_id`
- `channel`
- `platform_framework`
- `screen_fixture`
- `instruction`
- `action_type`
- `expected_target`
- `expected_relation` (optional; row/card/list context)
- `acceptable_refs`
- `expected_failure_mode` (negative cases)
- `expected_tier` or `allowed_tiers`
- `latency_budget_ms`
- `requires_provider`
- `requires_device_browser_network`
- `tags`

### Example shape (design-only)
```json
{
  "case_id": "web_table_row_edit_001",
  "channel": "web",
  "platform_framework": "playwright-dom",
  "screen_fixture": "fixtures/web/accounts_table.html",
  "instruction": "Click Edit for John Smith",
  "action_type": "click",
  "expected_target": {
    "role": "button",
    "name": "Edit",
    "row_anchor": "John Smith"
  },
  "expected_relation": {
    "type": "same_row_as",
    "anchor_text": "John Smith"
  },
  "acceptable_refs": [
    "role=button[name=\"Edit\"]@row_anchor=John Smith",
    "css=[data-row='john-smith'] button.edit"
  ],
  "expected_failure_mode": null,
  "allowed_tiers": [1, 2],
  "latency_budget_ms": 250,
  "requires_provider": false,
  "requires_device_browser_network": {
    "device": false,
    "browser": true,
    "network": false
  },
  "tags": ["table", "row_action", "duplicate_label_risk"]
}
```

## 3.5 Baseline comparisons (required)
Every benchmark report must include comparison against:
1. **Raw Playwright baseline** (`get_by_role`/`get_by_text` directly)
2. **Raw vision/LLM grounding baseline** (provider-first grounding path)
3. **Current Bubblegum pipeline baseline** (deterministic-first + memory + fallback)

## 3.6 Metrics (required)
At minimum report:
- success rate by object category
- wrong-target rate
- ambiguity rate
- no-candidate rate
- validation-mismatch rate
- tier escalation rate
- p95 latency by tier/resolver
- model/provider call count
- failure mode taxonomy distribution

## 3.7 Failure mode taxonomy (required)
Use these canonical labels:
- `no_candidate`
- `wrong_candidate`
- `ambiguous_candidate`
- `low_confidence`
- `validation_mismatch`
- `stale_after_resolution`
- `action_intercepted`
- `unsupported_surface`
- `provider_or_vision_unavailable`
- `hydration_failed`

## 3.8 Fixture strategy
- Design target scale: **200–400 total benchmark cases** over time.
- Per major category target: **15–25 cases** over time.
- Mobile track target: grows toward **~100 cases**.
- Start with a smaller seed set in a later implementation phase.
- Keep deterministic/local fixtures as default; isolate provider/device-required slices with explicit tags/requirements.

## 3.9 Execution policy
- Split deterministic local execution from provider/device-required slices.
- Mark case prerequisites explicitly (`requires_provider`, `requires_device_browser_network`).
- Do not treat unavailable provider/device prerequisites as deterministic regressions.

## 3.10 Reporting expectations
Benchmark output should include:
- overall and per-category summaries
- per-baseline comparison tables
- per-tier escalation and latency summaries
- failure taxonomy breakdowns
- slice-level summaries (web, mobile, provider-assisted)

## 3.11 Deferrals in this phase
- No multilingual feature claim.
- Multilingual is benchmark slice first, feature later.
- No full device-cloud matrix in Phase 19B.
- No Selenium adapter in Phase 19B.

---

## 4) Regression Suite design

## 4.1 Purpose
Regression suite protects existing behavior and contracts, including:
- API surface stability
- deterministic resolver ordering/eligibility
- hydration safety and diagnostics non-leakage
- benchmark runner static/execute invariants
- packaging/documentation and smoke script integrity

## 4.2 What existing tests protect
Current tests already guard:
- resolver behavior and ranking invariants
- OCR/vision injected-candidate behavior
- visual-ref hydration safety and deterministic mapping contracts
- adapter execution/retry/wait/reporting invariants
- benchmark fixture schema and deterministic execute harness behavior

## 4.3 How regression differs from capability benchmarking
- Regression: “same behavior as before?”
- Benchmark: “how well does object identification perform relative to baselines?”

## 4.4 Regression non-goals
- No comparative quality scoring claim.
- No capability rating.
- No model/provider leaderboard.

---

## 5) v0.0.6-alpha focus statement

For v0.0.6-alpha planning, focus should be **Object Intelligence Foundation**, not feature-claim expansion:
- normalized cross-platform element model
- UI element graph
- resolver/ranker graph signal integration
- parser-to-graph query emission
- relational targeting
- explanation/analytics

Empirical capability remains **unrated** until benchmark implementation and baseline comparison results exist.

---

## 6) Reordered Phase 19 roadmap

1. **Phase 19B** — Object Intelligence Benchmark and Regression Design
2. **Phase 19C** — Normalized Cross-platform Element Model MVP
3. **Phase 19D** — UI Element Graph MVP
4. **Phase 19E** — Resolver/ranker integration with graph signals
5. **Phase 19F** — Semantic Parser 2.0 emitting graph queries
6. **Phase 19G** — Relational Targeting MVP
7. **Phase 19H** — Object Match Explanation and Analytics
8. **Phase 19M** — Parallel Mobile Object Intelligence track

---

## 7) Phase 19M (parallel mobile track) design scope

Phase 19M should include:
- FrameworkDetector design
- WebView context switching design
- SystemDialogHandler design
- IconLibraryResolver design
- mobile-aware screen signatures
- mobile benchmark slice design/expansion

