# Phase 19F-B: Object Intelligence benchmark seed fixtures (MVP)

## Purpose

This document defines the first **Object Intelligence benchmark seed fixture set** used to
measure object-identification capability before any scoring/ranking behavior changes.

This phase is **docs + fixtures + schema validation only**.

## Separation from regression benchmark

The existing regression benchmark remains unchanged:

- `tests/benchmarks/fixtures/cases.json` (current 12-case regression suite)
- Existing runner default behavior and pass/fail expectations remain intact.

Object Intelligence seeds are intentionally separate:

- `tests/benchmarks/object_intelligence/seed_cases.json`
- `tests/benchmarks/object_intelligence/schema.json`

No runtime scoring/resolver changes are introduced in this phase.

## Seed categories (MVP coverage)

### Web categories
1. duplicate button labels — positive/disambiguated
2. duplicate button labels — negative ambiguous
3. label/input association
4. same-row action
5. card/list scoped action
6. dropdown/select by label
7. checkbox/radio by label
8. modal-scoped action
9. hidden/offscreen/scroll-to-find placeholder negative (deferred runtime)

### Mobile categories
10. mobile native text match
11. mobile content-desc match
12. mobile resource-id fallback
13. mobile duplicate text ambiguity negative

## Ground-truth seed fields

Each seed case includes:

- `case_id`
- `category`
- `channel`
- `platform_framework`
- `fixture_path`
- `instruction`
- `action_type`
- `target_text`
- `expected_target`
- `acceptable_refs`
- `expected_relation`
- `expected_graph_signals`
- `allowed_resolvers` or `expected_resolver`
- `expected_confidence_range`
- `expected_failure_mode`
- `baseline_expectations`
- `tags`

## Baseline comparison fields

`baseline_expectations` always includes:

- `bubblegum_current`
- `playwright_raw_role_text`
- `llm_vision_raw`
- `manual_expected`

At this stage, values are expectation metadata only (pass/fail/ambiguous/no_candidate style),
not runtime-enforced benchmark logic.

## Failure taxonomy (supported labels)

Seed fixtures and schema support:

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

## Metrics this seed set prepares

- success rate by category
- wrong-target rate
- ambiguity rate
- no-candidate rate
- validation-mismatch rate
- graph-signal presence rate
- tier escalation rate (placeholder)
- p95 latency (placeholder)
- provider call count (placeholder)
- failure mode distribution

## Non-goals / deferrals (explicit)

This phase does **not**:

- change ranker/confidence scoring
- change resolver priority/order
- change engine thresholds
- change parser/planner behavior
- implement runtime relational targeting
- activate graph-based scoring
- modify SDK/API/version/dependency surface
- alter existing regression benchmark fixtures
- modify runner default behavior

## Future runner integration plan (post-MVP)

Future safe integration can add optional fixture-path selection (e.g., `--cases <path>`) while
preserving current default fixture behavior. Any such change is deferred beyond 19F-B.

## Notes

- Seed fixtures are intentionally compact and metadata-oriented.
- Raw screenshots/base64 payload dumps/full graph dumps are excluded from seed data.
- This separation enables evidence gathering before any scoring policy changes.
