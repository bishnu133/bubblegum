# AI Grounding Enhancements (0.0.6a51) — what changed, setup & real-app testing

This release makes Bubblegum's AI layer **actually fire, more accurate, faster,
cheaper, and enterprise-ready**. Every new capability is **off / dormant by
default** and **backward-compatible** — if you upgrade and change nothing, you
get the same behaviour you had before. You opt in per feature via
`bubblegum.yaml`.

- **Audience:** existing Bubblegum users (Python or TypeScript/Playwright) who
  want to turn the new AI grounding on and validate it against a real app.
- **TL;DR:** set `ai.provider` + `ai.model` (+ an API key) to light up the AI
  fallback; add `embedding_model` / `vision_backend` / `observability` to enable
  the extra tiers; use `grounding.ai_mode: replay` for zero-cost CI.

---

## 1. What changed

| Area | Before | Now |
|------|--------|-----|
| **AI fallback** | Registered but **never wired** — silently returned "not found", so every edge case became a hand-coded fix | Wired from config; a successful AI hit is saved as a **durable locator** and replayed as a Tier-1 cache hit (0 model calls) next run |
| **Model use** | One model for everything; client rebuilt each call | Cheap **fast model** by default, optional **escalation** to a strong model only when unsure; prompt caching; reused clients |
| **AI output** | "please reply in JSON" + fence-stripping (silent parse failures) | Provider-native **structured output / tool-use** — schema guaranteed |
| **Matching** | Deterministic → edit-distance fuzzy → (dead) AI | Adds a **semantic (embedding) tier** that matches by meaning ("Submit"→"Continue") before the LLM |
| **Concurrency** | AI call ran on a throwaway thread + event loop | Runs natively on the event loop (async resolver contract) |
| **Vision** | Retry-only, hosted-only, manual wiring | **Pluggable, config-selectable** backend incl. **self-hosted** grounders (OmniParser/UI-TARS); first-class on mobile; screenshots can stay in-network |
| **Robustness** | No timeout/retry; hardcoded price table | Per-call **timeout + bounded retry/backoff**; **config-driven pricing** |
| **Observability** | End-of-run reports only | **Streaming per-step observations** (JSONL / OpenTelemetry) + **replay mode** for deterministic, zero-cost CI |
| **Code generator** | Active | `record` / `convert` in **maintenance mode** (paused) |

The tiered resolver chain is now:

```
Tier 1  deterministic   explicit selector → memory cache → a11y tree / appium → exact text
Tier 2  fuzzy+semantic  fuzzy (edit-distance) → semantic (embeddings)   [new]
Tier 3  AI              LLM grounding → OCR → vision/screenshot grounding
```

`memory cache` (Tier 1) is where learned AI resolutions replay from — that is
what makes the second run of any AI-resolved element fast and free.

---

## 2. Setup

### 2.1 Install

**Python engine (0.0.6a51):**

```bash
# From PyPI once the alpha is published:
pip install "bubblegum-ai==0.0.6a51"

# Extras for the AI providers you use:
pip install "bubblegum-ai[anthropic]"   # Claude
pip install "bubblegum-ai[openai]"       # OpenAI (also needed for OpenAI embeddings)
pip install "bubblegum-ai[web]"          # Playwright
pip install "bubblegum-ai[mobile]"       # Appium
```

Pre-publish (test the branch directly, no publish needed):

```bash
pip install "git+https://github.com/bishnu133/bubblegum@claude/ai-automation-improvements-5a76d8"
```

**TypeScript client (0.0.6-alpha.6):** see [§5](#5-typescript-project-usage).

### 2.2 API key

```bash
export ANTHROPIC_API_KEY=sk-ant-...     # if ai.provider: anthropic
export OPENAI_API_KEY=sk-...            # if ai.provider: openai  (also for embeddings)
```

Keys are read from the environment; they are never written to config or logs.

### 2.3 Minimal config to light up the AI fallback

`bubblegum.yaml`:

```yaml
ai:
  enabled: true
  provider: openai            # anthropic | openai | gemini | local
  model: gpt-4o-mini          # REQUIRED — no model = AI tier stays dormant (no surprise cost)
```

That single change makes the documented "AI when deterministic resolvers fail"
behaviour real. Nothing else is required.

### 2.4 Full reference config (all new knobs, with defaults)

```yaml
grounding:
  max_cost_level: medium      # low = deterministic only; medium = + text AI; high = + vision
  ai_mode: live               # live | replay  (replay = cache + deterministic only, no model calls)
  enable_semantic: true       # embedding Tier-2 (activates only when ai.embedding_model is set)
  semantic_min_similarity: 0.72
  enable_vision: false        # screenshot grounding master switch
  vision_backend: none        # none | anthropic | openai | http | callable
  # vision_endpoint: http://localhost:8000/ground        # for vision_backend: http (self-hosted)
  # vision_endpoint_timeout_ms: 30000
  max_run_cost_usd: 0.0       # per-run USD ceiling for AI calls (0 = off)

ai:
  enabled: true
  provider: openai
  model: gpt-4o-mini
  # Tiered routing (optional; both default to `model`):
  fast_model: gpt-4o-mini     # used for grounding + step parsing
  strong_model: gpt-4o        # escalation target
  escalate_on_low_confidence: false   # retry with strong_model when fast is unsure
  max_tokens: 1024
  prompt_caching: true
  # Resilience:
  timeout_ms: 30000
  max_retries: 2
  retry_backoff_ms: 500
  # Cost overrides (update prices without a release):
  # pricing:
  #   gpt-4o-mini: [0.00015, 0.0006]   # [usd_per_1k_input, usd_per_1k_output]
  # Semantic embeddings (set embedding_model to activate the semantic tier):
  # embedding_provider: openai         # defaults to `provider`
  # embedding_model: text-embedding-3-small
  # Vision model (for vision_backend: anthropic|openai):
  # vision_model: gpt-4.1-mini

privacy:
  send_screenshots: false     # true only to send screenshots to a HOSTED vision model
  vision_is_local: false      # true for a self-hosted grounder (vision_backend: http) — pixels stay in-network
  process_screenshots_for_vision: false   # master opt-in for the screenshot pipeline

observability:
  enabled: false
  export: none                # none | jsonl | otel | both
  file: .bubblegum/observability.jsonl
  service_name: bubblegum
```

### 2.5 Enabling each new tier

| Want | Set |
|------|-----|
| AI text grounding fallback | `ai.model` (+ key). That's it. |
| Cheaper default + smart escalation | `ai.fast_model`, `ai.strong_model`, `ai.escalate_on_low_confidence: true` |
| Semantic (meaning) matching | `ai.embedding_model: text-embedding-3-small` |
| Hosted screenshot grounding | `grounding.enable_vision: true`, `grounding.vision_backend: openai`, `ai.vision_model`, `privacy.send_screenshots: true`, `privacy.process_screenshots_for_vision: true`, and run steps at `max_cost_level: high` |
| **Self-hosted** grounding (OmniParser/UI-TARS, mobile-first) | `grounding.enable_vision: true`, `grounding.vision_backend: http`, `grounding.vision_endpoint: <your-url>`, `privacy.vision_is_local: true`, `privacy.process_screenshots_for_vision: true` |
| Streaming observability | `observability.enabled: true`, `observability.export: jsonl` |
| Zero-cost deterministic CI | `grounding.ai_mode: replay` (after warming the cache once) |

### 2.6 Offline / self-hosted embeddings (data residency)

No heavy ML dependency is imposed. Inject any embedding function (e.g.
`sentence-transformers`) in code:

```python
from sentence_transformers import SentenceTransformer
from bubblegum.core.sdk import configure_embedding_provider

m = SentenceTransformer("all-MiniLM-L6-v2")
configure_embedding_provider(lambda texts: m.encode(texts).tolist())
```

---

## 3. How to test against a real application

### 3.1 Web (Playwright, Python)

```python
import asyncio
from playwright.async_api import async_playwright
from bubblegum import act, verify
from bubblegum.core.sdk import configure_runtime

configure_runtime(config_path="bubblegum.yaml")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("https://your-app.example.com/login")

        # Plain-English steps. With the AI tier on, label drift resolves without
        # hand-coded selectors — and is cached for next time.
        await act("Type 'qa@demo.com' into the Email field", page=page)
        await act("Type 'secret' into the Password field", page=page)
        await act("Click the Sign in button", page=page)          # matches "Log in" too
        await verify("The dashboard heading is visible", page=page)

        await browser.close()

asyncio.run(main())
```

**What to look for**
- First run may call the model on the hard steps (watch your provider dashboard).
- Second run of the same screen/step: **no model call** — served from the memory
  cache (`.bubblegum/memory.db`). That is the cost/speed win.

### 3.2 Prove the "learn once, replay free" loop

```bash
# 1) Warm the cache (live AI) — run your suite once:
#    grounding.ai_mode: live
pytest tests/

# 2) Commit the learned cache so CI can reuse it:
git add .bubblegum/memory.db && git commit -m "chore: warm bubblegum cache"

# 3) Run CI with zero model calls, fully deterministic:
#    grounding.ai_mode: replay
pytest tests/
```

In `replay` mode the AI providers are dormant; steps resolve only from
deterministic resolvers + the learned cache. A cache miss surfaces as a normal
resolution failure (i.e. CI should be pre-warmed).

### 3.3 Mobile (Appium) with self-hosted screenshot grounding

Mobile a11y trees are often too thin to resolve from (Flutter / React Native /
canvas). Point Bubblegum at a self-hosted grounder so screenshots never leave
your network:

```yaml
grounding:
  enable_vision: true
  vision_backend: http
  vision_endpoint: http://localhost:8000/ground   # your OmniParser / UI-TARS server
privacy:
  vision_is_local: true
  process_screenshots_for_vision: true
```

Your endpoint receives `POST {instruction, image_base64, channel, platform}` and
returns any of:

```jsonc
{ "candidates": [ {"label":"Login","role":"button","bbox":[x1,y1,x2,y2],"confidence":0.9} ] }
{ "elements":   [ {"content":"Login","type":"button","bbox":[x1,y1,x2,y2]} ] }   // OmniParser / set-of-mark
{ "point": [x, y] }                                                              // UI-TARS / computer-use
```

Labeled results are hydrated to a durable `resource-id` / `content-desc` /
`text` locator and cached; a bare `point` acts on the coordinate (enable
`grounding.coordinate_click_fallback`) and is **never** cached (a pixel is not
durable).

### 3.4 Verify each feature is actually working

| Check | How |
|-------|-----|
| AI tier is live | Python: `import bubblegum.core.sdk as s; print(s._registry.get("llm_grounding").has_provider)` → `True` |
| Semantic tier is live | `print(s._registry.get("semantic").has_provider)` → `True` (needs `ai.embedding_model`) |
| Vision backend is live | `print(type(s._vision_provider).__name__)` |
| Cost so far | `from bubblegum.core import cost; print(cost.spent())` |
| Per-step observations | `observability.export: jsonl` → tail `.bubblegum/observability.jsonl` (one JSON line per step: winner, candidates, tier, timing, cost) |
| Why a step resolved that way | `from bubblegum.reporting.explain import format_explanation; print(format_explanation(result))` |

---

## 4. Cost & privacy notes

- **No surprise spend:** the AI tier is dormant until you set `ai.model`. A
  per-run ceiling (`grounding.max_run_cost_usd`) hard-stops AI calls once hit.
- **Data residency:** hosted vision requires `privacy.send_screenshots: true`;
  a self-hosted grounder (`vision_is_local: true`) keeps pixels in your network.
- **DOM/labels:** text grounding sends a *filtered* accessibility subtree (roles
  relevant to the action), not the whole page, and never raw screenshots.

---

## 5. TypeScript project usage

The new capabilities live in the **engine** and are driven by `bubblegum.yaml`,
so TypeScript/Playwright projects using `@bubblegum-ai/node` get them **for
free** — no client code changes. The Node client speaks to the Python engine
over the bridge; point it at the same `bubblegum.yaml`.

```bash
npm install @bubblegum-ai/node@0.0.6-alpha.6
# Ensure the Python engine 0.0.6a51 is installed and on PATH (pip install bubblegum-ai==0.0.6a51)
```

```ts
import { Bubblegum } from "@bubblegum-ai/node";

// The engine reads bubblegum.yaml (ai.model, embeddings, vision_backend,
// observability, ai_mode) — the same config as Python.
const bg = await Bubblegum.attach(page, { config: "bubblegum.yaml" });

await bg.act("Type 'qa@demo.com' into the Email field");
await bg.act("Click the Sign in button");   // AI fallback + cache apply engine-side
await bg.verify("The dashboard heading is visible");
```

For `ai_mode: replay` in CI, commit the engine's `.bubblegum/memory.db` (warmed
by a prior `live` run) so the TypeScript suite replays with zero model calls
too. See [`docs/HOW_TO_USE_TYPESCRIPT.md`](HOW_TO_USE_TYPESCRIPT.md) and
[`docs/distribution-npm-and-pypi.md`](distribution-npm-and-pypi.md).

---

## 6. Upgrading from an earlier 0.0.6a5x

1. `pip install -U bubblegum-ai==0.0.6a51` (and `npm i @bubblegum-ai/node@0.0.6-alpha.6`).
2. No config change is required — everything new is opt-in.
3. To adopt the AI fallback, add `ai.model` (+ key), run your suite once to warm
   the cache, then commit `.bubblegum/memory.db` and switch CI to
   `grounding.ai_mode: replay`.

See [`CHANGELOG.md`](../CHANGELOG.md) for the full 0.0.6a51 entry.
