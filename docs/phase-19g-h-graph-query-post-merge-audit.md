# Phase 19G-H: Graph Query Planner Design Post-Merge Audit and Diagnostics-MVP Readiness

## 1) Scope

This phase is a post-merge audit of Phase 19G-G design outputs only.

In-scope:
- verify design completeness against required diagnostics-first principles
- verify non-goals remain explicit
- decide GO/NO-GO for metadata-only diagnostics MVP

Out-of-scope:
- runtime graph query execution
- candidate narrowing/filtering in grounding flow
- ranker/scoring/confidence changes
- resolver/engine threshold or ordering changes
- parser/schema/API/dependency/version changes

## 2) Inputs audited

- `docs/phase-19g-graph-query-planner-design.md`
- existing relational intent design doc and seed/spec docs
- current graph and graph signal capability docs/tests
- baseline benchmark + test health expectations

## 3) Audit checklist and findings

### 3.1 Design completeness vs required content

Phase 19G-G design doc includes:
- problem statement
- current graph capabilities
- current relational intent metadata contract
- diagnostics-first rationale
- recommended module location (`bubblegum/core/elements/query.py`)
- proposed interface (`build_graph_query_diagnostics(...)`)
- compact JSON-safe diagnostics contract
- deterministic relation mappings (`label_for`, `same_row_as_text`, `within_card`, `within_modal`, `within_region`, `mobile_attr_hint`)
- container-detection heuristics
- fail-closed ambiguity policy and statuses
- control/mobile hint representation
- phased integration path
- non-goals
- required test plan
- risks/mitigations
- GO/NO-GO criteria

Finding: **PASS** (content-complete for design phase).

### 3.2 Determinism and safety posture

Confirmed design constraints:
- deterministic-first rules only
- no invented anchors/scopes
- no automatic tie-breaking under ambiguity
- explicit statuses (`ambiguous`, `no_anchor`, `no_scope`, `no_match`)
- JSON-safe compact payload contract

Finding: **PASS**.

### 3.3 Runtime neutrality posture

Design explicitly defers:
- runtime filtering/narrowing
- scoring/ranker changes
- resolver ordering/threshold changes
- parser/schema/API/version/dependency changes

Finding: **PASS**.

### 3.4 Integration readiness quality

Design defines a clear staged path:
- Phase 1: diagnostics-only metadata
- Phase 2: optional feature-flagged filtering
- Phase 3: benchmark-backed scoring discussion

Finding: **PASS**, with one readiness caveat below.

## 4) Gap analysis for diagnostics-MVP readiness

### 4.1 Remaining clarifications required before coding

Although Phase 19G-G is complete, the diagnostics MVP should lock a small implementation appendix first:

1. **Canonical reason codes**
   - Define finite reason enum for `reasons[]`, `anchor_resolution.reason`, `scope_resolution.reason`.
   - Example: `anchor_missing_text`, `anchor_not_found`, `scope_multiple_candidates`, `kind_filter_eliminated_all`.

2. **Control-kind normalization table**
   - Explicit map from role/tag/widget tokens to `button|input|dropdown|checkbox|radio` buckets.

3. **Container heuristic precedence table**
   - Ordered tie-break policy for card/modal/region detection to ensure deterministic outcomes.

4. **Output size guardrails**
   - cap `matched_ids`/`excluded_ids` lengths for compact diagnostics payloads (with overflow reason code).

These are implementation-spec details, not runtime behavior changes.

## 5) Diagnostics-MVP GO/NO-GO decision (Phase 19G-H)

Decision: **CONDITIONAL GO** for Phase 19G-I metadata-only diagnostics MVP.

GO conditions:
- retain docs-defined diagnostics-only scope (no filtering/select/scoring behavior)
- add canonical reason-code appendix before/with implementation
- add deterministic ordering and JSON-safety tests first
- preserve all existing benchmark/test/public API baselines

NO-GO triggers:
- any proposal to narrow candidate sets in grounding runtime by default
- any resolver confidence/ranker/threshold/order changes
- parser/schema/API/dependency/version changes

## 6) Required pre-implementation test gate (unchanged)

Before merging diagnostics MVP code:
1. unit tests for each relation mapping path
2. negative/ambiguity status tests
3. JSON-safe contract shape tests
4. deterministic ordering tests
5. default benchmark parity (12/12 static, 12/12 execute)
6. object-seed summary parity (`--cases seed_cases.json`)
7. public API parity
8. collect-only baseline parity

## 7) Recommendation for next phase scope

Recommended next phase: **Phase 19G-I — metadata-only graph query diagnostics MVP** with strict non-goals:
- no runtime candidate filtering/narrowing
- no score/threshold/order changes
- no parser/schema/API changes

Suggested first implementation surface:
- new internal module `bubblegum/core/elements/query.py`
- pure function `build_graph_query_diagnostics(...)`
- additive metadata emission only, gated to non-breaking diagnostics path

## 8) Audit conclusion

Phase 19G-G design is judged sufficiently complete and aligned with deterministic, fail-closed, diagnostics-first principles.

**Phase 19G-H outcome:**
- Design post-merge audit: complete
- Diagnostics MVP readiness: **GO with conditions** (as listed)
