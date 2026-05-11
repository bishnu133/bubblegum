<p align="center">
  <img src="docs/assets/bubblegum-ai-readme-logo.png" alt="Bubblegum AI" width="220"/>
</p>

<h1 align="center">Bubblegum</h1>

<p align="center">
  <strong>AI-powered recovery & natural-language execution for Playwright and Appium tests</strong>
</p>

<p align="center">
  <a href="https://github.com/bubblegum-ai/bubblegum/actions/workflows/ci.yml"><img src="https://img.shields.io/badge/CI-GitHub%20Actions-blue.svg" alt="CI workflow"/></a>
  <a href="https://github.com/bubblegum-ai/bubblegum/releases/tag/v0.0.5-alpha"><img src="https://img.shields.io/badge/release-v0.0.5--alpha-orange.svg" alt="v0.0.5-alpha release"/></a>
  <a href="https://github.com/bubblegum-ai/bubblegum"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+"/></a>
  <a href="https://github.com/bubblegum-ai/bubblegum/blob/main/README.md#quick-start"><img src="https://img.shields.io/badge/pip%20install-bubblegum--ai-pink.svg" alt="pip install bubblegum-ai"/></a>
  <a href="https://github.com/bubblegum-ai/bubblegum/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-lightgrey.svg" alt="MIT License"/></a>
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
# Base package
pip install bubblegum-ai

# Local development install with web extra (Playwright)
pip install -e ".[web]"
python -m playwright install chromium

# Local development install with mobile extra (Appium client)
pip install -e ".[mobile]"
# plus: running Appium server + running emulator/device + installed target app

# Local development install with all optional extras
pip install -e ".[all]"

# Package-user installs (non-editable)
pip install "bubblegum-ai[web]"
pip install "bubblegum-ai[mobile]"
```

### Public import pattern

```python
from bubblegum import act, verify, recover, extract, configure_runtime
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
  process_screenshots_for_vision: false
  process_screenshots_for_ocr:    false
```

> **No default model is set intentionally.** You must configure both `provider` and `model` to avoid surprise API costs.

### Recover a failing step in an existing Playwright test

```python
from bubblegum import recover

result = await recover(
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


## Quickstart examples

Runnable templates are available in:

- `examples/playwright_quickstart.py`
- `examples/appium_quickstart.py`
- `examples/hybrid_web_mobile_example.py`
- `examples/README.md`

These are intentionally minimal and avoid credentials/secrets.

The Playwright quickstart uses `page.set_content(...)` with deterministic local HTML by default, so first-run smoke does not depend on outbound network access.

The Appium quickstart is a real-environment template (Appium server + emulator/device + app/capabilities) and is intentionally not self-contained.

For quickstart troubleshooting (dependency/proxy issues, Playwright browser setup, Appium server/device requirements), see `examples/README.md`.

For Appium-specific onboarding (real-environment prerequisites, capability checklist, and common startup failures), jump to the Appium setup and troubleshooting sections in `examples/README.md`.

For hybrid web + mobile usage patterns (selector-first + natural-language fallback), see `examples/hybrid_web_mobile_example.py`.

For callable vision provider lifecycle setup/teardown with required privacy gates, see `examples/vision_callable_provider_example.py` and docs in `docs/phase-11l-callable-vision-enablements.md`.




Adoption/docs MVP links:
- Adoption guide: `docs/adoption.md`
- Web natural-language quickstart: `examples/web_nl_quickstart.py`
- OCR callable hydration pattern: `examples/ocr_callable_hydration_example.py`
- Report artifacts example: `examples/report_artifacts_example.py`
- Pytest plugin usage: `docs/pytest-plugin.md`
- CI usage snippet: `docs/ci.md`

Distribution posture note:
- Current distribution path is GitHub releases (latest pre-release: `v0.0.5-alpha`).
- PyPI/TestPyPI publishing is intentionally deferred until a later explicit release phase.

Optional OpenAI vision backend note:
- `OpenAIVisionProvider` is available as an optional vision backend under `bubblegum.core.vision.backends`.
- It requires either an injected compatible client or user-installed OpenAI SDK (not required by base install).
- Provider-based screenshot-to-vision invocation is runtime cost-gated and requires `max_cost_level="high"` in execution options plus all vision/privacy gates.
- Manually supplied `vision_candidates` remain allowed at any cost level and are not overwritten by SDK provider wiring.
- Phase 11T hardening: provider `model` must be non-empty and `timeout` must be a positive number.
- `timeout` is applied when using optional lazy SDK client creation (`create_client=True`); injected client remains preferred for deterministic tests.
- It is only used when you explicitly call `configure_vision_provider(...)` and all vision/privacy gates are enabled.
- No raw screenshot bytes are persisted to traces/metadata by Bubblegum vision plumbing.
- OpenAIVisionProvider now exposes sanitized failure diagnostics (`last_diagnostic` / `get_last_diagnostic()`), with stable code/stage metadata and no raw screenshot bytes/base64/request payload/API key leakage.
- Manual real-provider usage example: `examples/openai_vision_provider_manual_example.py` (optional/manual; user installs `openai`; the OpenAI SDK reads `OPENAI_API_KEY` from environment).

---

## Pytest reporter fixture integration

If you want Bubblegum HTML/JSON reports to include step-level SDK results, add the `bubblegum_reporter` fixture and append each `StepResult`:

```python
import pytest
from bubblegum import act

@pytest.mark.asyncio
async def test_login_flow(page, bubblegum_reporter):
    result = await act("Click Login", channel="web", page=page)
    bubblegum_reporter.add(result)
    assert result.status in {"passed", "recovered"}
```

Run with report outputs:

```bash
pytest --bubblegum-config bubblegum.yaml \
  --bubblegum-report artifacts/bubblegum-report.html \
  --bubblegum-report-json artifacts/bubblegum-report.json
```

---

### Phase 11L callable vision guide

For a complete callable vision enablement guide (gates, output shape, troubleshooting, and future provider lifecycle/API audit), see:

- `docs/phase-11l-callable-vision-enablements.md`

#### Phase 11N public provider lifecycle API

Bubblegum now exposes a minimal public runtime lifecycle API for optional vision wiring:

```python
from bubblegum import configure_vision_provider, clear_vision_provider
from bubblegum.core.vision.backends.callable import CallableVisionProvider

configure_vision_provider(CallableVisionProvider(my_vision_callable))
# ... run steps ...
clear_vision_provider()  # idempotent reset
```

Guardrails remain unchanged:
- Registration does not request screenshots or invoke providers by itself.
- Provider invocation remains default-off and requires all gates:
  `enable_vision`, `send_screenshots`, `process_screenshots_for_vision`, and registered provider.
- Manual `vision_candidates` still take precedence over provider output.
- Provider exceptions remain fail-safe (no hard grounding crash from provider errors).

---

### Optional vision callable backend (no bundled vision model dependency)

Bubblegum does not bundle a real vision model dependency by default.
You can provide a runtime callable backend via `CallableVisionProvider` that receives screenshot bytes, instruction text, and optional context, and returns raw vision candidates (`list[VisionCandidate]` or `list[dict]`).

- Screenshot processing remains opt-in and privacy-gated.
- `enable_vision: true` alone does **not** process screenshots.
- `send_screenshots: true` grants screenshot capture/sharing permission.
- `process_screenshots_for_vision: true` is also required before screenshot bytes should be processed into vision candidates.
- SDK runtime now supports optional internal screenshot-to-vision candidate wiring, but it is strictly disabled by default and runs only when **all** gates are true: `enable_vision`, `send_screenshots`, `process_screenshots_for_vision`, and a configured runtime vision provider/callable.
- `VisionModelResolver` behavior is unchanged: it consumes injected `intent.context["vision_candidates"]` only.
- If `vision_candidates` are already user-supplied in context, SDK wiring does not overwrite them.
- No raw screenshot bytes are persisted into resolver metadata/traces by the SDK wiring path.
- Vision refs remain synthetic (`vision://target/<index>`) and are not adapter-executed.
- No real bundled vision model dependency is added; runtime callable/provider remains integrator-supplied.

### Optional OCR callable backend (no bundled OCR dependency)

Bubblegum does not bundle a real OCR engine dependency by default.
You can provide a runtime callable backend that receives screenshot bytes and returns raw OCR blocks.
The callable contract is:

- Input: `image_bytes: bytes` (raw screenshot bytes)
- Output: `list[OCRBlock]` or `list[dict]`
- Canonical block shape after normalization:

```python
{
    "text": str,
    "bbox": [x1, y1, x2, y2],
    "confidence": float,
}
```


```python
from bubblegum.core.ocr.backends import CallableOCREngine
from bubblegum.core.ocr.engine import build_ocr_blocks_from_screenshot


def my_ocr_callable(image_bytes: bytes):
    # Integrator-owned OCR logic here
    # Return list[OCRBlock] or list[dict(text,bbox,confidence)]
    return [{"text": "Continue", "bbox": [10, 20, 100, 60], "confidence": 0.93}]


engine = CallableOCREngine(my_ocr_callable)
ocr_blocks = build_ocr_blocks_from_screenshot(
    screenshot=b"...png bytes...",
    enabled=True,
    process_screenshots_for_ocr=True,
    engine=engine,
)
```

`ocr_blocks` output is normalized into canonical context shape and is safe-by-default:

- Screenshot OCR processing runs only when `process_screenshots_for_ocr: true` is explicitly enabled.
- Bubblegum does **not** bundle a real OCR engine dependency yet.
- `OCRResolver` consumes normalized `context["ocr_blocks"]` and emits synthetic `ocr://block/<index>` refs.
- These `ocr://` refs are not adapter-executed yet (resolution/ranking signal only in current architecture).

## Public API

Four primitives. These are the only methods test authors need.

```python
# Natural language — direct mode (web)
await act("Click Login",          channel="web")
await verify("Dashboard visible", channel="web")
await extract("Get user email",   channel="web")

# Natural language — mobile
await act("Tap Continue",   channel="mobile", platform="android")
await verify("OTP screen",  channel="mobile", platform="ios")

# Fallback recovery — plug into an existing Playwright test
await recover(
    page=page,
    failed_selector="#submit-btn",
    intent="Click Submit"
)
```

> **Mobile `recover()`:** `recover()` supports mobile by passing `channel="mobile"` and an Appium `driver`.

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
- Phase 11D adds an injected-candidate MVP in `VisionModelResolver`: it consumes `intent.context["vision_candidates"]` (normalized), emits synthetic `vision://target/<index>` refs, and remains deterministic with no bundled real vision model dependency.
- Vision refs remain synthetic/non-executable in this phase; no adapter execution path for `vision://` refs is wired yet.
- Password fields (`input[type=password]`) are **never** included in any snapshot
- Fields labelled `secret`, `token`, `api_key`, or similar are **auto-redacted**
- Email and phone number redaction is configurable via `privacy.redact_pii: true`
- Every AI provider call is logged with **safe metadata only** — provider name, resolver name, token count, redaction status, response latency — not the raw prompt or screenshot content
- Raw payload logging is available only in `debug.log_raw_payloads: true` mode — never enable in CI

**Local / offline mode:** Set `ai.enabled: false` to disable all AI resolvers. Local model providers (e.g. Ollama) are supported via `provider: local`. The memory layer uses local SQLite only — no remote sync unless explicitly configured.

---

## Roadmap

Phase roadmap has been reset after `v0.0.4-alpha`.

- Planning phase: **Phase 17A — Post-v0.0.4 roadmap reset and v0.0.5-alpha planning**
- Planning doc: `docs/phase-17a-roadmap-reset-v0.0.5-alpha.md`
- Current release target: `v0.0.5-alpha`

Planned `v0.0.5-alpha` scope themes:

1. release/packaging confidence,
2. deterministic quality gates,
3. docs/operator clarity,
4. no SDK/API/schema breaking changes.

---

## Benchmark Strategy

### Current benchmark status (Phase 8 baseline)

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


## Release/package validation

These checks are intended for maintainers preparing an MVP release candidate (not required for normal package users).

CI-required release checks (current workflow):

```bash
# offline-safe package validation (default)
python scripts/validate_package.py

# strict maintainer/release-mode validation
python scripts/validate_package.py --strict

# build artifacts
python -m build
```

Optional maintainer check (local, if `twine` is installed):

```bash
python -m twine check dist/*
```

Publishing is not automated yet in CI.

## Project Status

| Item | Detail |
|---|---|
| Architecture version | v0.9 — Final Approved |
| Implementation readiness | 92% — Overall rating 9.2 / 10 |
| Current phase | **Phase 17A: Post-v0.0.4 roadmap reset and v0.0.5-alpha planning** |
| Next step | Execute the first v0.0.5-alpha slices: release-checklist sync, roadmap/docs consistency pass, and targeted packaging/reporting regression checks |
| Locked decisions | Keep fallback-first posture, preserve privacy/cost gates, no breaking SDK/API/schema changes, GitHub pre-release-first distribution |

---

<p align="center">
  <sub>Bubblegum · Architecture Candidate v0.9 — Final Approved · April 2026</sub>
</p>
