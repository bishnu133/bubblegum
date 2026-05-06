# Phase 10J — Post-OCR MVP verification and next slice selection

## 1) Current status after Phase 10I / 10I.1

Phase 10I is complete with deterministic OCRResolver behavior that consumes injected OCR blocks from `intent.context["ocr_blocks"]` and is gated by `config_ocr_enabled`.

Phase 10I.1 status note:
- Include the Phase 10I.1 sentence in release/phase summaries only when the async helper fix from Phase 4 is already merged and validated on `main`.
- For this planning slice, treat that note as conditional and repository-state dependent.

At this point, the OCR path is intentionally MVP-scoped and deterministic, designed to validate plumbing, ranking signals, synthetic refs, and metadata without introducing external OCR runtime dependencies.

## 2) What the OCR injected-block MVP supports

The current MVP supports:
- deterministic OCR candidate generation from injected context blocks (`ocr_blocks`),
- config-gated enablement via `config_ocr_enabled`,
- synthetic stable refs in `ocr://block/<index>` format,
- metadata and signals suitable for ranker participation,
- unit-test coverage for resolver behavior, channels, gating, duplicate/weak matching behavior, and ranker compatibility.

This provides a fallback-first substrate for OCR-like grounding without requiring screenshot capture pipelines or third-party OCR engines.

## 3) Intentionally out of scope (Phase 10J)

This planning phase does **not** implement:
- real OCR engine integration,
- screenshot-to-OCR-block pipeline,
- VisionModelResolver,
- Anthropic provider,
- Ollama/local provider,
- Appium runtime hardening,
- iOS support,
- package version changes,
- release publishing.

## 4) Validation baseline (Phase 10J audit run)

Commands executed and outcomes:

1. `python scripts/validate_package.py`
   - Result: pass.
   - Notes: confirms import smoke and license presence; installed distribution metadata is optional in default mode.

2. `python scripts/validate_package.py --strict`
   - Result: fail in current environment.
   - Cause: strict mode requires editable install metadata and `build` module availability.

3. `python -m build`
   - Result: fail in current environment.
   - Cause: `build` module not installed.

4. `python scripts/run_benchmarks.py`
   - Result: pass; static validation 12/12.

5. `python scripts/run_benchmarks.py --execute`
   - Result: pass; execution validation 12/12.

6. `pytest --collect-only -q`
   - Result: pass; **463 tests collected**.

Baseline summary:
- Package default validation: passing.
- Strict/build checks: environment-limited (missing install/build prerequisites).
- Benchmark guardrails: unchanged and green (12/12 static, 12/12 execute).
- Test collection count: 463.

## 5) Risk assessment for next options

### A) Real OCR engine adapter / screenshot-to-OCR-block pipeline

Risk: **Medium-High**.
- Introduces external dependencies, OS/runtime variability, and non-deterministic OCR quality.
- Increases CI complexity and likely requires fixture/pipeline redesign for repeatability.
- May blur boundary between deterministic grounding and probabilistic extraction unless carefully isolated.

### B) VisionModelResolver design

Risk: **High**.
- API and policy surface expands quickly (image handling, privacy controls, provider differences, cost tiers).
- Requires strong contract design before implementation to avoid rework across providers.
- Hard to validate deterministically without robust mocks and explicit confidence semantics.

### C) Anthropic/Ollama provider completion

Risk: **Medium**.
- Adds provider matrix complexity (auth, models, response formats, failure modes).
- Improves optional AI coverage but does not directly improve deterministic onboarding flows.
- Testing burden rises for compatibility and error taxonomy consistency.

### D) iOS Appium hardening

Risk: **Medium-High**.
- Device/runtime variability and capability matrix complexity are substantial.
- Runtime hardening often requires broader infra and manual validation burden.
- Valuable long-term, but higher ops overhead than documentation/examples slices.

### E) Hybrid web + mobile examples

Risk: **Low**.
- Primarily docs/examples and usage-pattern validation.
- Strengthens adoption and clarifies API usage without destabilizing resolver internals.
- Supports fallback-first positioning while deferring heavy dependency/runtime additions.

## 6) Recommendation for next phase

## Recommended next slice: **Phase 10K — Hybrid web + mobile examples**

Rationale:
- low-risk with high adoption impact,
- validates public API ergonomics in realistic mixed-channel workflows,
- aligns with fallback-first strategy before adding real OCR/vision dependencies,
- preserves deterministic benchmark and resolver baselines while improving practical onboarding.

Suggested Phase 10K scope guardrails:
- add end-to-end narrative examples spanning web then mobile steps,
- keep examples deterministic where possible and clearly separate manual-runtime sections,
- avoid provider/runtime feature expansion in the same slice,
- keep benchmark fixtures and core resolver behavior unchanged.
