# Phase 17A — Post-v0.0.4 roadmap reset and v0.0.5-alpha planning

Date: 2026-05-10

## 1) Why this reset exists

`v0.0.4-alpha` completed the Phase 14/15 reliability and observability scope.
This phase resets the roadmap so the next pre-release (`v0.0.5-alpha`) has a clear, bounded target with explicit non-goals.

## 2) Outcomes from v0.0.4-alpha carried forward

- Adapter-level transient retry behavior is in place.
- Adapter-level explicit `wait_for` behavior is in place.
- Safe retry/wait observability metadata is available in reporting.
- Distribution posture remains GitHub pre-release first; PyPI/TestPyPI remains deferred.

## 3) v0.0.5-alpha planning objective

Deliver a **stabilization + packaging confidence** slice, focused on:

1. release hygiene,
2. deterministic test confidence,
3. docs/operator clarity,
4. no breaking SDK surface changes.

## 4) Proposed scope for v0.0.5-alpha

### A. Release/packaging confidence
- Keep `scripts/validate_package.py` and `python -m build` as hard gates.
- Reconfirm clean artifact workflow (`dist/`, `build/`, `*.egg-info` cleanup) in release checklist wording.
- Keep publish-check posture manual/collect-only (no automatic publish).

### B. Deterministic quality gates
- Preserve benchmark fixture schema + deterministic benchmark execution as release gates.
- Maintain focused unit coverage for retry/wait metadata semantics.
- Avoid adding network-required CI tests.

### C. Documentation/operator clarity
- Align README status/roadmap language with post-`v0.0.4-alpha` reality.
- Keep privacy/cost gating guidance explicit for optional OCR/vision/provider flows.
- Keep examples runnable with local deterministic defaults.

### D. Runtime/API policy
- No public API breaking changes.
- No schema contract breaks.
- No mandatory new model/provider dependencies.

## 5) Explicit non-goals for this planning window

- No PyPI/TestPyPI publishing activation.
- No automatic runtime provider invocation beyond current explicit gates.
- No expansion into network-dependent benchmark/CI requirements.
- No synthetic visual/ocr ref direct-execution behavior changes.
- No validation retry expansion work in this phase.
- No new wait mode expansion (`stable` / `clickable` / `gone`) in this phase.
- No SDK-level retry/wait behavior expansion in this phase.
- No provider/LLM/OCR/vision retry policy expansion in this phase.
- No Selenium adapter expansion in this phase.
- No iOS maturity expansion in this phase.
- No policy engine expansion in this phase.

## 6) Entry/exit criteria (planning)

### Entry
- `v0.0.4-alpha` release notes/checklist posture finalized.
- Current deterministic tests and benchmarks green in maintainer workflow.

### Exit (ready to execute 0.0.5-alpha implementation slices)
- Agreed short-list of implementation slices with owners.
- Release checklist updated for `v0.0.5-alpha` validation cadence.
- README/changelog status language synchronized to new roadmap.

## 7) Recommended first implementation slices after planning

1. Release checklist sync pass for `v0.0.5-alpha` wording and command order.
2. Targeted docs pass (README + CI/adoption cross-links) for roadmap/status consistency.
3. Narrow test pass focused on packaging/metadata/reporting regressions.

## 8) Recommended next phase

**Phase 17B — Real smoke kit and adoption readiness audit**

This should be **audit-only** (no runtime/API/schema/dependency/version changes) and should verify readiness before implementation expansion:

- inspect docs/examples for runnable smoke command clarity
- inspect CI snippets for practical adoption usage
- inspect report artifact generation flow (HTML/JSON)
- verify fallback-first and hybrid usage guidance consistency
- verify manual smoke checklist coverage for web/mobile/adoption paths

---

This document is planning-only and introduces no runtime behavior, API, schema, or dependency changes.
