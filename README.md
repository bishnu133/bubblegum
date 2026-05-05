<p align="center">
  <img src="docs/assets/bubblegum-ai-readme-logo.png" alt="Bubblegum AI" width="220"/>
</p>

<h1 align="center">Bubblegum</h1>

<p align="center">
  <strong>AI-powered recovery & natural-language execution for Playwright and Appium tests</strong>
</p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+"/></a>
  <a href="#"><img src="https://img.shields.io/badge/pip%20install-bubblegum--ai-pink.svg" alt="pip install bubblegum-ai"/></a>
  <a href="#"><img src="https://img.shields.io/badge/phase-0%20%E2%80%94%20foundation-orange.svg" alt="Phase 0"/></a>
  <a href="#"><img src="https://img.shields.io/badge/architecture-v0.9%20approved-brightgreen.svg" alt="Architecture Approved"/></a>
  <a href="#"><img src="https://img.shields.io/badge/license-MIT-lightgrey.svg" alt="MIT License"/></a>
</p>

---

> **Bubblegum is NOT a replacement for Playwright or Appium.**  
> It is an intelligent layer that attaches to your existing test framework, heals broken locators using a deterministic-first strategy, and lets you write new steps in plain English.

---

## Table of Contents

- [What is Bubblegum?](#what-is-bubblegum)
- [Quick Start](#quick-start)
- [Public API](#public-api)
- [How It Works](#how-it-works)
- [Resolver Chain](#resolver-chain)
- [Configuration](#configuration)
- [Error Handling](#error-handling)
- [Privacy & Security](#privacy--security)
- [Roadmap](#roadmap)
- [Benchmark Strategy](#benchmark-strategy)
- [Contributing Custom Resolvers](#contributing-custom-resolvers)
- [Architecture](#architecture)
- [Project Status](#project-status)

---

## What is Bubblegum?

QA automation breaks when UIs change. Locators go stale, button labels get renamed, and your CI pipeline turns red — not because the feature is broken, but because `#login-btn` became `.btn-login`.

Bubblegum solves this with a **tiered resolver chain**:

1. **Deterministic first** — tries stable, fast, zero-cost resolvers (accessibility tree, exact text, memory cache)
2. **Fuzzy fallback** — edit-distance and semantic matching when labels drift slightly
3. **AI when needed** — LLM/vision models only when deterministic approaches fail

Every decision produces a trace artifact with confidence scores, so your team always knows *why* a step was resolved the way it was.

| ✅ What Bubblegum IS | ❌ What Bubblegum is NOT |
|---|---|
| An intelligent layer on top of your existing tools | A replacement for Playwright or Appium |
| Fallback-first, AI-when-needed | A full autonomous test agent |
| Self-healing for broken locators | A test recorder or codegen tool |
| Natural language step execution | A black box — every decision is traceable |

**Target users (v1):** SDETs, automation engineers, framework owners, QA teams already using Playwright or Appium.

---

## Quick Start

### Install

```bash
pip install bubblegum-ai
```

### Add configuration

Create `bubblegum.yaml` in your project root:

```yaml
grounding:
  accept_threshold:  0.85
  review_threshold:  0.70
  ambiguous_gap:     0.05
  reject_threshold:  0.50
  max_cost_level:    medium   # low | medium | high
  enable_vision:     false
  enable_ocr:        true
  memory_ttl_days:   7

ai:
  enabled:   true
  provider:  anthropic          # anthropic | openai | gemini | local
  model:     <your-model-name>  # must be set explicitly — no default

privacy:
  redact_pii:         true
  send_screenshots:   false
  log_provider_calls: true
```

> **No default model is set intentionally.** You must configure both `provider` and `model` to avoid surprise API costs.

### Recover a failing step in an existing Playwright test

```python
import bubblegum

result = await bubblegum.recover(
    page=page,
    failed_selector="#login-btn",
    intent="Click Login"
)

assert result.status in ["passed", "recovered"]
# result.status == "recovered" means the original selector failed,
# but Bubblegum found and clicked the right element.
```

That's it. You get value from Bubblegum **before writing a single new natural-language test**.

---


## Pytest plugin reporting

Bubblegum ships with a pytest plugin entrypoint (`bubblegum.pytest_plugin`) that can emit HTML/JSON reports and manage artifacts during test sessions.

### Common commands

```bash
# HTML report
pytest --bubblegum-config bubblegum.yaml \
  --bubblegum-report artifacts/bubblegum-report.html

# JSON report
pytest --bubblegum-config bubblegum.yaml \
  --bubblegum-report-json artifacts/bubblegum-report.json

# HTML + JSON + explicit artifacts directory
pytest --bubblegum-config bubblegum.yaml \
  --bubblegum-artifacts artifacts \
  --bubblegum-report artifacts/bubblegum-report.html \
  --bubblegum-report-json artifacts/bubblegum-report.json

# Run benchmark validation at session end
pytest --bubblegum-benchmark
```

### GitHub Actions example

```yaml
- name: Run tests with Bubblegum reporting
  run: |
    pytest \
      --bubblegum-config bubblegum.yaml \
      --bubblegum-artifacts artifacts \
      --bubblegum-report artifacts/bubblegum-report.html \
      --bubblegum-report-json artifacts/bubblegum-report.json

- name: Upload Bubblegum artifacts
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: bubblegum-artifacts
    path: artifacts/
```

---

## Public API

Four primitives. These are the only methods test authors need.

```python
# Natural language — direct mode (web)
await bubblegum.act("Click Login",          channel="web")
await bubblegum.verify("Dashboard visible", channel="web")
await bubblegum.extract("Get user email",   channel="web")

# Natural language — mobile
await bubblegum.act("Tap Continue",   channel="mobile", platform="android")
await bubblegum.verify("OTP screen",  channel="mobile", platform="ios")

# Fallback recovery — plug into an existing Playwright test
await bubblegum.recover(
    page=page,
    failed_selector="#submit-btn",
    intent="Click Submit"
)
```

> **Mobile `recover()`:** In Phase 1/2, `recover()` accepts a Playwright `page` object. Appium session support will be added in Phase 4.

### StepResult — what every call returns

```python
class StepResult(BaseModel):
    status:      Literal["passed", "failed", "recovered", "skipped"]
    action:      str
    target:      ResolvedTarget | None
    confidence:  float
    validation:  ValidationResult | None
    artifacts:   list[ArtifactRef]
    duration_ms: int
    error:       ErrorInfo | None
    traces:      list[ResolverTrace]   # one entry per resolver that ran
```

`"recovered"` status flags that the original selector failed but Bubblegum fixed it — important for CI reporting so your team knows which steps need their locators updated.

---

## How It Works

### Execution Pipeline (10 steps)

| # | Step | What happens |
|---|---|---|
| 1 | **StepIntent received** | Natural-language instruction, channel, platform, action_type, options |
| 2 | **ContextCollector runs** | Captures a11y snapshot or hierarchy XML, screenshot, screen signature |
| 3 | **ResolverRegistry filters** | Filters resolvers by channel, platform, action_type, cost policy |
| 4 | **Tiered resolver execution** | Tier 1 (deterministic) → Tier 2 (fuzzy) → Tier 3 (AI) — stops at first confident match |
| 5 | **CandidateRanker selects** | Weighted formula: text match + role + visibility + uniqueness + position + memory history |
| 6 | **AmbiguityCheck** | Top 2 candidates within 0.05 confidence → raise `AmbiguousTargetError`, do not auto-execute |
| 7 | **Executor performs action** | Playwright (web) or Appium (mobile) executes via resolved ref |
| 8 | **ValidationEngine checks** | Verifies expected result separately from grounding |
| 9 | **MemoryLayer stores** | Saves screen_signature + step_hash → resolver + ref + confidence |
| 10 | **StepResult returned** | Full result with status, confidence, traces, and artifacts |

### Confidence Scoring

| Signal | Weight | Description |
|---|---|---|
| Text / name match | **30%** | Similarity between instruction text and element label |
| Role / type match | **20%** | Does element role match expected action (button for click, input for type) |
| Visibility / interactability | **15%** | Is the element visible, enabled, and not obscured |
| Uniqueness | **15%** | Is this the only matching element on the page |
| Location / proximity | **10%** | Is the element near the contextual anchor (modal, form, section) |
| Historical memory success | **10%** | Has this mapping succeeded before for this screen signature |

### Thresholds

| Threshold | Default | Behaviour |
|---|---|---|
| `accept_threshold` | **≥ 0.85** | Resolve immediately — stop, no further resolvers |
| `review_threshold` | **≥ 0.70** | Proceed but log a warning — check artifact trace |
| `ambiguous_gap` | **< 0.05** | Top 2 candidates too close — raise `AmbiguousTargetError` |
| `reject_threshold` | **< 0.50** | Low confidence — try next tier; after all tiers exhausted: raise error |

All thresholds are configurable in `bubblegum.yaml`.

---

## Resolver Chain

### Built-in Resolvers

| Resolver | Priority | Channels | Cost | Tier | Description |
|---|---|---|---|---|---|
| `ExplicitSelectorResolver` | 0 | web + mobile | low | 1 | Explicit selector passed by caller |
| `MemoryCacheResolver` | 10 | web + mobile | low | 1 | Screen fingerprint + step hash cache hit |
| `AccessibilityTreeResolver` | 20 | web only | low | 1 | Playwright `get_by_role` / `aria_snapshot` |
| `AppiumHierarchyResolver` | 20 | mobile only | low | 1 | Appium XML hierarchy, role + text match |
| `ExactTextResolver` | 30 | web + mobile | low | 1 | Exact label, placeholder, aria-label, hint |
| `FuzzyTextResolver` | 45 | web + mobile | low | 2 | Edit-distance, synonyms, partial text |
| `LLMGroundingResolver` | 50 | web + mobile | high | 3 | Filtered tree → text model → ranked candidates |
| `OCRResolver` | 60 | web + mobile | medium | 3 | Tesseract / cloud OCR on screenshot |
| `VisionModelResolver` | 70 | web + mobile | high | 3 | Screenshot → multimodal model → coordinates |

### Tiered Execution

```
Tier 1 — deterministic (priority 0–39):
  ExplicitSelectorResolver, MemoryCacheResolver,
  AccessibilityTreeResolver, AppiumHierarchyResolver,
  ExactTextResolver
  → If confidence ≥ 0.85: stop here.

Tier 2 — fuzzy / semantic (priority 40–49):
  FuzzyTextResolver
  → If confidence ≥ 0.70: stop here.

Tier 3 — AI fallback (priority 50+):
  LLMGroundingResolver, OCRResolver, VisionModelResolver
  → Only reached when Tiers 1+2 cannot meet review_threshold.
  → Blocked entirely if max_cost_level: low in config.
```

### Memory Self-Healing

On repeat CI runs, `MemoryCacheResolver` replays successful mappings without any AI call. Before replaying, it verifies:

- Screen signature still matches (fingerprint comparison within tolerance)
- Element still exists in current DOM/hierarchy
- Element text, role, and position are within drift threshold
- Last success was within TTL (default: 7 days)
- Failure count is below `max_failures` (default: 3)

If any check fails, it steps aside gracefully and lets a downstream resolver win.

### Step Artifact (per resolved step)

```json
{
  "step":             "Click Login",
  "channel":          "web",
  "resolvers_tried":  ["explicit_selector", "memory_cache", "accessibility_tree"],
  "candidates": [
    { "resolver": "accessibility_tree", "ref": "button[name='Login']",
      "confidence": 0.94, "matched_text": "Login" },
    { "resolver": "exact_text", "ref": "text=Login", "confidence": 0.86 }
  ],
  "selected":         { "resolver": "accessibility_tree", "confidence": 0.94 },
  "ambiguous":        false,
  "tier_stopped_at":  1,
  "duration_ms":      43,
  "screenshot":       "artifacts/step_001.png"
}
```

---

## Configuration

Full `bubblegum.yaml` reference:

```yaml
grounding:
  accept_threshold:    0.85
  review_threshold:    0.70
  ambiguous_gap:       0.05
  reject_threshold:    0.50
  max_cost_level:      medium   # low | medium | high
  enable_vision:       false    # must be true to use VisionModelResolver
  enable_ocr:          true
  memory_ttl_days:     7
  memory_max_failures: 3

ai:
  enabled:   true
  provider:  anthropic          # anthropic | openai | gemini | local
  model:     <your-model-name>  # e.g. claude-sonnet-latest, gpt-4o, gemini-pro

privacy:
  redact_pii:         true
  send_screenshots:   false
  log_provider_calls: true

debug:
  log_raw_payloads:    false   # never enable in CI or production
  log_resolver_traces: true    # safe — logs resolver names + confidence only
```

**Fully offline / deterministic mode:**

```yaml
ai:
  enabled: false   # disables all AI resolvers, no model provider required
```

---

## Error Handling

All errors extend `BubblegumError` and carry: step instruction, resolver name, candidates found, and a screenshot artifact reference.

| Error | When raised |
|---|---|
| `ResolutionFailedError` | All resolvers exhausted — no target found above threshold |
| `AmbiguousTargetError` | Multiple candidates within 0.05 confidence — Bubblegum will not auto-execute |
| `LowConfidenceError` | Best candidate found but confidence below `reject_threshold` (< 0.50) |
| `ExecutionFailedError` | Adapter action raised an exception after target was resolved |
| `ValidationFailedError` | Action executed but expected result was not observed |
| `ContextCollectionError` | DOM/hierarchy/screenshot could not be captured |
| `ProviderConfigError` | LLM or vision provider not configured or credentials invalid |
| `AICostPolicyBlockedError` | Resolver's cost_level exceeds configured `max_cost_level` |
| `MemoryStaleError` | Cached mapping exists but fails staleness checks — falls through to next resolver |

> **Safe failure over wrong click.** Bubblegum prefers raising `AmbiguousTargetError` over executing on a low-confidence match. Clicking the wrong element silently is worse than a clear, informative failure.

---

## Privacy & Security

Because Bubblegum may send DOM text and hierarchy data to external LLM providers:

- Only the **filtered accessibility tree or hierarchy XML** is sent — not the full raw DOM
- Screenshots are sent to the vision model **only** when `VisionModelResolver` is explicitly enabled
- Password fields (`input[type=password]`) are **never** included in any snapshot
- Fields labelled `secret`, `token`, `api_key`, or similar are **auto-redacted**
- Email and phone number redaction is configurable via `privacy.redact_pii: true`
- Every AI provider call is logged with **safe metadata only** — provider name, resolver name, token count, redaction status, response latency — not the raw prompt or screenshot content
- Raw payload logging is available only in `debug.log_raw_payloads: true` mode — never enable in CI

**Local / offline mode:** Set `ai.enabled: false` to disable all AI resolvers. Local model providers (e.g. Ollama) are supported via `provider: local`. The memory layer uses local SQLite only — no remote sync unless explicitly configured.

---

## Roadmap

| Phase | Duration | Name | Key Deliverables |
|---|---|---|---|
| **Phase 0** *(current)* | 2–3 wks | Foundation | All 13 Pydantic schemas, Resolver base, ResolverRegistry, GroundingEngine, BaseAdapter, error taxonomy, golden benchmark scaffold |
| **Phase 1A** | 2 wks | Web core | Playwright adapter, `act()` + `verify()`, ExplicitSelectorResolver, AccessibilityTreeResolver, ExactTextResolver |
| **Phase 1B** | 2 wks | Web complete | FuzzyTextResolver, `extract()`, screenshots, MemoryCacheResolver (SQLite), HTML report |
| **Phase 2** | 3–4 wks | Web AI fallback | LLM provider abstraction, LLMGroundingResolver, confidence scoring, `recover()` |
| **Phase 3** | 2–3 wks | Memory self-healing | Screen fingerprinting, staleness checks, replay without AI on repeat runs |
| **Phase 4** | 4–5 wks | Android Appium | Appium adapter, AppiumHierarchyResolver, tap/type/scroll/verify |
| **Phase 5** | 2–3 wks | Reporting + CI | Full HTML report, pytest plugin, per-resolver trace artifact, benchmark runner |
| **Phase 6** | 3–4 wks | iOS + advanced AI | XCUITest driver, OCRResolver, VisionModelResolver, shadow DOM, community resolver docs |

---

## Benchmark Strategy

### Phase 6Q benchmark status

Current deterministic benchmark expectations:

- static validation: 12/12 passed
- execute validation: total 12, executed 12, skipped 0, passed 12, failed 0

Static validation checks fixture schema, snapshot existence, and static expected winner/confidence ranges.
Execute validation runs deterministic benchmark execution and evaluates `execute_*` expectations, which may intentionally differ from static expectations.

`execute_allow_review=true` is benchmark-only review-pass handling and does not change SDK/engine runtime semantics.
Deterministic execution excludes Tier 3 AI/OCR/Vision resolvers. Memory benchmark runs with ephemeral DB setup/pre-seeding and does not use `.bubblegum/memory.db`.

Benchmark commands:

```bash
python scripts/run_benchmarks.py
python scripts/run_benchmarks.py --execute
```

A golden dataset is created in Phase 0. Without it, Bubblegum cannot be proven better than plain Playwright.

### Dataset Composition (100 scenarios)

- **50** standard web UI steps — buttons, forms, links, dropdowns, modals
- **20** broken-selector cases — element exists but selector is stale/wrong
- **10** changed-label cases — button text changed slightly (Login → Sign In)
- **10** duplicate-label cases — multiple matching elements on page
- **10** dynamic/modal/overlay cases — element appears after an interaction

### Metrics Tracked

- Deterministic success rate (Tier 1–2 resolver wins)
- AI recovery success rate (Tier 3 resolver wins)
- False positive rate (wrong element selected)
- Ambiguous target rate (`AmbiguousTargetError` frequency)
- Average step latency per resolver (ms)
- Model calls per scenario (cost proxy)
- Estimated cost per test run (USD via token counting)
- Resolver win distribution by action type

---

## Contributing Custom Resolvers

Zero core changes required. Ship a resolver as a standalone class:

```python
from bubblegum.core.grounding.resolver import Resolver, StepIntent, ResolvedTarget

class MaterialUIResolver(Resolver):
    name       = "material_ui"
    priority   = 25          # runs between AccessibilityTreeResolver and ExactTextResolver
    channels   = ["web"]
    cost_level = "low"
    tier       = 1

    def required_context(self): return ["a11y_snapshot"]
    def supports(self, intent): return intent.action_type in ["click", "type", "select"]

    def resolve(self, intent: StepIntent) -> list[ResolvedTarget]:
        # MUI-specific matching logic
        ...
```

Register it in one line (e.g. in `conftest.py`):

```python
bubblegum.registry.register(MaterialUIResolver())
```

Community resolvers can be published as separate packages:

```bash
pip install bubblegum-salesforce-resolver
pip install bubblegum-flutter-resolver
```

---

## Architecture

### Repository Structure

```
bubblegum/
├── core/
│   ├── grounding/
│   │   ├── engine.py           # GroundingEngine orchestrator
│   │   ├── registry.py         # ResolverRegistry
│   │   ├── resolver.py         # Resolver abstract base
│   │   ├── ranker.py           # CandidateRanker + confidence formula
│   │   ├── confidence.py       # Threshold logic
│   │   ├── errors.py           # Full error taxonomy
│   │   └── resolvers/          # One file per resolver
│   ├── schemas.py              # All 13 Pydantic schemas
│   ├── parser/                 # NL instruction → StepIntent
│   ├── planner/                # StepIntent → ActionPlan
│   ├── validation/             # ValidationEngine
│   ├── recovery/               # RecoveryEngine
│   ├── memory/                 # MemoryLayer (SQLite)
│   └── models/                 # LLM provider abstraction
├── adapters/
│   ├── web/playwright/         # PlaywrightAdapter
│   └── mobile/appium/          # AppiumAdapter
├── reporting/                  # HTML/JSON report, pytest plugin
└── tests/
    ├── unit/                   # Each resolver tested in isolation
    ├── integration/
    ├── e2e/
    └── benchmarks/             # Golden dataset runner
```

### Schema Catalogue (13 Pydantic Models)

| Schema | Purpose |
|---|---|
| `ContextRequest` | Controls what `collect_context()` captures |
| `StepIntent` | Input to every resolver: instruction, channel, platform, action_type |
| `ExecutionOptions` | Reusable options: timeout_ms, retry_count, wait_for, use_ai, max_cost_level |
| `UIContext` | Collected page state: a11y_snapshot, hierarchy_xml, screenshot, screen_signature |
| `ActionPlan` | Execution plan derived from StepIntent |
| `ResolvedTarget` | Resolver output: ref, confidence, resolver_name, metadata |
| `ExecutionResult` | Adapter execution output: success, duration_ms, element_ref, error |
| `ValidationPlan` | What to verify: assertion_type, expected value, timeout |
| `ValidationResult` | Outcome: passed, actual value, screenshot, duration_ms |
| `StepResult` | Top-level SDK return — the contract with test frameworks |
| `ArtifactRef` | Reference to a file artifact: type, path, timestamp |
| `ErrorInfo` | Structured error: error_type, message, resolver_name, candidates, screenshot |
| `ResolverTrace` | Per-resolver debug log: resolver_name, duration_ms, candidates, can_run result |

---

## Project Status

| Item | Detail |
|---|---|
| Architecture version | v0.9 — Final Approved |
| Implementation readiness | 92% — Overall rating 9.2 / 10 |
| Current phase | **Phase 0: Foundation** |
| Next step | Implement all 13 Pydantic schemas, Resolver base, ResolverRegistry, GroundingEngine skeleton, golden benchmark scaffold |
| Locked decisions | Positioning, public API, resolver chain, cost policy, memory staleness, artifact output format, benchmark dataset |

---

<p align="center">
  <sub>Bubblegum · Architecture Candidate v0.9 — Final Approved · April 2026</sub>
</p>
