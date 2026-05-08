# Phase 11L — Callable Vision Enablement Docs + Provider Lifecycle Audit

## Scope

Phase 11L established docs/planning; Phase 11N finalizes minimal public provider lifecycle registration.

What this phase does:
- documents how to use callable vision safely and predictably
- clarifies required privacy/config gates
- explains manual injection vs optional SDK screenshot-to-vision wiring
- captures provider lifecycle/API audit recommendations for a future phase

What this phase does **not** do:
- no SDK runtime changes
- no public API changes
- no adapter changes
- no real OpenAI/Anthropic/Ollama vision provider implementation
- no new dependencies

---

## Current callable vision posture (as of Phase 11J/11K)

- Vision is **default-off**.
- `VisionModelResolver` remains **injected-candidate based**.
- `vision://...` refs are **synthetic** and **non-executable** by adapters.
- No bundled real vision model dependency is included.
- No OpenAI/Anthropic/Ollama vision provider integration is bundled.
- Raw screenshot bytes must not be persisted to traces/metadata/log payloads.

---

## What `CallableVisionProvider` is

`CallableVisionProvider` is a thin adapter that wraps your callable and exposes the internal `VisionProvider` protocol.

Callable signature:

```python
def my_vision_callable(
    image_bytes: bytes,
    instruction: str,
    context: dict | None,
) -> list[dict] | list[VisionCandidate]:
    ...
```

Your callable receives:
- `image_bytes`: screenshot bytes (only when all gates pass and screenshot is present)
- `instruction`: user step instruction
- `context`: small runtime context (e.g., channel/platform)

Your callable returns:
- `list[VisionCandidate]` **or**
- `list[dict]` with fields:
  - `label` (required, non-empty string)
  - `bbox` (`[x1, y1, x2, y2]`, optional)
  - `confidence` (`0.0..1.0`, optional but recommended)
  - `role` (optional)
  - `text` (optional)

Malformed items are dropped by normalization.

---

## Required gates for optional SDK screenshot-to-vision wiring

The SDK requests/processes screenshots for callable vision only when **all** are true:

1. `grounding.enable_vision: true`
2. `privacy.send_screenshots: true`
3. `privacy.process_screenshots_for_vision: true`
4. a runtime vision provider is configured (internal/private hook today)

If any gate is false, provider invocation is skipped.

### Example config

```yaml
grounding:
  enable_vision: true

privacy:
  send_screenshots: true
  process_screenshots_for_vision: true
```

---

## Integration paths

## 1) Manual injected `vision_candidates` path (explicit + deterministic)

You inject candidates into `intent.context["vision_candidates"]` before grounding.

Characteristics:
- bypasses screenshot-to-vision auto wiring
- preserves caller control
- existing manual candidates are not overwritten by SDK wiring

Use this when:
- you already run your own image pipeline externally
- you want deterministic tests with precomputed candidates

## 2) Optional SDK screenshot-to-vision path

SDK can request screenshot context and call provider to produce normalized candidates, then inject into `intent.context["vision_candidates"]`.

Characteristics:
- still privacy/config gated
- still default-off
- fail-safe: provider exceptions yield empty candidates (no hard crash from provider)

Use this when:
- you want runtime convenience
- you accept gated screenshot processing in your environment

---

## Why provider may not be invoked (troubleshooting)

Check these first:

- `enable_vision` is false
- `privacy.send_screenshots` is false
- `privacy.process_screenshots_for_vision` is false
- no provider configured
- manual `vision_candidates` already present (SDK skips provider to avoid overwrite)
- screenshot bytes missing from collected context

If provider throws, pipeline fails-safe and returns no candidates.

---

## Privacy and data-handling rules

- Do not persist raw screenshot bytes into resolver metadata.
- Do not add raw screenshot bytes into traces.
- Do not log raw screenshot payloads in production/CI.
- Keep screenshot use purpose-limited to candidate detection when gates pass.

Phase 11L policy remains: screenshot-derived candidate injection is allowed only under explicit opt-in gates.

---

## Synthetic `vision://` references limitation

`VisionModelResolver` emits synthetic refs like `vision://target/<index>`.

These refs are for resolver/ranking metadata flow only and are **not** adapter-executable selectors.

Any future adapter-executable mapping for vision output requires a separate design/implementation phase.

---

## No bundled real vision dependency

Bubblegum continues to avoid bundling a real vision model dependency in this phase.

Real provider integrations (OpenAI/Anthropic/Ollama/etc.) remain deferred until provider registration lifecycle and API boundaries are finalized.

---

## Provider lifecycle/API audit note (for future Phase 11M)

## Current state

- Internal runtime currently uses a private test hook for provider wiring.
- This hook should remain private for now.

Rationale:
- avoids premature API lock-in
- avoids thread-safety and lifecycle ambiguity leaking into public contract
- keeps Phase 11J/11L conservative and low-risk

## Public provider registration API options (future)

Potential options to evaluate in Phase 11M:

1. **Global registration**
   - e.g., `configure_runtime(..., vision_provider=...)`
   - simple ergonomics
   - risk: shared mutable global state across concurrent tests

2. **Per-call registration**
   - e.g., `act(..., vision_provider=...)` (future, not now)
   - strong isolation
   - risk: public API expansion and signature churn

3. **Context-managed/session registration**
   - explicit setup/reset lifecycle around test scope
   - clearer ownership boundaries
   - moderate complexity

## Lifecycle expectations to define before public API

- initialization semantics (when provider becomes active)
- reset semantics (how to clear provider between tests)
- precedence rules (manual candidates vs provider output)
- deterministic behavior in parallel execution

## Thread-safety concerns

If registration is global, provider pointer mutations can race across:
- concurrent tests
- async tasks
- parallel workers

Phase 11M should require a thread-safe strategy (or explicit documentation of scope limits).

## Error-handling expectations

Maintain fail-safe behavior:
- provider exceptions should not crash core grounding flow
- invalid candidate items should be normalized/dropped
- decision traces should remain screenshot-byte-free

## Privacy gate enforcement

Public registration must not bypass existing gates:
- `enable_vision`
- `send_screenshots`
- `process_screenshots_for_vision`

Gate checks should remain centralized and test-covered.

## Phase 11M recommendation

Recommended target:
- API design/audit + minimal implementation proposal for **safe provider registration lifecycle**
- include concurrency/lifecycle test plan before exposing a stable public registration contract
- keep real OpenAI/Anthropic/Ollama provider implementation deferred until registration lifecycle is stable



## Phase 11N finalized lifecycle API

Public SDK exports now include:
- `configure_vision_provider(provider)`
- `clear_vision_provider()`

Lifecycle semantics:
- Provider must expose callable `detect_targets(image_bytes, instruction, context=None)`.
- Invalid providers raise clear registration errors (`TypeError`/`ValueError`).
- `clear_vision_provider()` is idempotent and resets provider to `None`.
- Registration/reset do not invoke provider and do not alter privacy gates.

Safety invariants remain unchanged:
- Provider executes only when all screenshot/vision gates pass.
- Manual `vision_candidates` are not overwritten.
- Provider exceptions fail-safe to empty candidates.
- Raw screenshot bytes must not be persisted in traces/metadata.
- Real OpenAI/Anthropic/Ollama provider integrations remain deferred.
