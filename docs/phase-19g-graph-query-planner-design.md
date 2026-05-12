# Phase 19G-G: Graph Query Planner Design/Spec (Diagnostics-First)

## 1) Problem statement

`relational_intent` metadata now exists as parser/planner context, but runtime grounding still resolves targets without deterministic relational graph-query planning.

This phase defines a **design-only** specification for how future relational metadata should map into deterministic `ElementGraph` query steps and compact diagnostics, while preserving current behavior.

## 2) Current graph capabilities

Current `ElementGraph` primitives already provide deterministic, JSON-safe relationships:
- hierarchy: `parent`, `child`
- adjacency: `sibling`, `nearby`
- semantic relation: `label_for` (label -> controls and control -> labels)
- spatial row grouping: `same_row`
- local scope peer grouping: `same_container`
- lookups: exact text and role matching (`elements_with_text`, `elements_by_role`)

These are sufficient to define first-pass relational diagnostics without introducing new runtime behavior.

## 3) Current `relational_intent` metadata contract

Current parser/planner contract (in `StepIntent.context["relational_intent"]`) is metadata-only and optional.

Current/target fields:
- `primary_target_text`
- `relation_type`
- `anchor_text`
- `scope_type`
- `scope_label`
- `control_kind_hint`
- `mobile_attr_preference`
- `ambiguity_policy`

Relation enum target surface:
- `none`, `label_for`, `same_row_as_text`, `within_card`, `within_modal`, `within_region`, `mobile_attr_hint`

## 4) Why graph query planning must be diagnostics-first

Diagnostics-first is required to protect existing behavior and release baselines:
- no resolver winner/order changes
- no ranker/scoring changes
- no threshold changes
- no runtime candidate narrowing
- no API/schema changes

A diagnostics-first slice validates mapping quality before behavior-affecting integration.

## 5) Recommended implementation location

Future implementation should live in:
- `bubblegum/core/elements/query.py`

Rationale:
- keeps graph-query semantics near graph primitives
- avoids coupling to grounding orchestration details
- allows reuse by multiple resolvers/diagnostic reporters

## 6) Proposed future interface

Preferred function-oriented interface:

```python

def build_graph_query_diagnostics(
    graph: ElementGraph,
    relational_intent: dict[str, Any] | None,
    *,
    action_type: str | None = None,
) -> dict[str, Any]:
    ...
```

Optional thin wrapper class (future):

```python
class GraphQueryPlanner:
    def plan(self, graph: ElementGraph, relational_intent: dict[str, Any] | None, *, action_type: str | None = None) -> dict[str, Any]:
        ...
```

For first implementation slice, keep a pure function for testability and deterministic behavior.

## 7) Proposed JSON-safe output contract

```json
{
  "status": "ok|no_relation|no_anchor|no_scope|no_match|ambiguous|unsupported",
  "relation_type": "label_for|same_row_as_text|within_card|within_modal|within_region|mobile_attr_hint|none",
  "anchor_resolution": {
    "status": "resolved|missing|ambiguous|not_required",
    "anchor_text": "...",
    "anchor_ids": ["..."],
    "reason": "..."
  },
  "scope_resolution": {
    "status": "resolved|missing|ambiguous|not_required",
    "scope_type": "row|card|modal|region|label|mobile_screen|none",
    "scope_label": "...",
    "scope_ids": ["..."],
    "reason": "..."
  },
  "matched_ids": ["..."],
  "excluded_ids": ["..."],
  "ambiguity": {
    "is_ambiguous": false,
    "kind": "none|anchor|scope|match",
    "candidate_ids": ["..."]
  },
  "reasons": ["..."]
}
```

Constraints:
- JSON-safe primitives only
- deterministic ordering (sorted IDs/reasons)
- compact payload (no raw snapshots, no full element dumps)

## 8) Deterministic mapping rules by `relation_type`

### 8.1 `label_for`
1. Require `primary_target_text` (label text anchor).
2. Resolve label anchors via `elements_with_text(primary_target_text)`.
3. Derive controls via `controls_for_label(primary_target_text)`.
4. Optionally apply `control_kind_hint` filter.
5. Output matched control IDs as diagnostics only.

Fail-closed:
- no anchor text -> `no_anchor`
- multiple anchor labels mapping to disjoint controls -> `ambiguous`

### 8.2 `same_row_as_text`
1. Require `anchor_text`.
2. Resolve anchors via `elements_with_text(anchor_text)`.
3. Collect row peers from `same_row` for each anchor.
4. Optionally apply `control_kind_hint`.
5. Emit matched peer IDs.

Fail-closed:
- missing anchor -> `no_anchor`
- multiple independent row scopes -> `ambiguous`

### 8.3 `within_card`
1. Require anchor (`anchor_text` preferred; `scope_label` fallback if explicitly present).
2. Resolve anchor elements by text.
3. For each anchor, walk ancestors and select **nearest card-like container**.
4. Candidate scope = descendants of selected card container.
5. Apply `control_kind_hint` filter to diagnostics set.

Fail-closed on multiple plausible card scopes.

### 8.4 `within_modal`
1. Resolve modal scope by explicit `scope_label` (if provided) + modal-like hints.
2. If label absent, resolve modal-like containers deterministically.
3. Candidate scope = descendants of modal container.
4. Apply `control_kind_hint` if present.

Fail-closed on multiple plausible modal scopes.

### 8.5 `within_region`
1. Resolve region anchor by `scope_label`/`anchor_text`.
2. Ascend to nearest region-like container.
3. Candidate scope = descendants.
4. If `control_kind_hint=dropdown`, constrain diagnostics to dropdown-like controls.

Fail-closed on ambiguous region container resolution.

### 8.6 `mobile_attr_hint`
1. Do not narrow candidates in runtime.
2. Emit attribute preference diagnostics (`content_desc`, `resource_id`, `text`).
3. Optionally annotate which in-scope elements expose the preferred attribute.

Status remains `ok`/`no_match` only in diagnostics context.

## 9) Container-detection rules (deterministic hints)

Container detection should rely only on existing normalized fields (`role`, `tag`, `widget_type`, `attributes`, `metadata`) and deterministic token checks.

### 9.1 Card-like hints
- role/tag/widget/class tokens: `card`, `panel`, `listitem`, `group`
- rectangular visible container with multiple child controls/text
- nearest ancestor wins

### 9.2 Modal-like hints
- role/tag/widget/class tokens: `dialog`, `modal`, `alertdialog`, `sheet`, `popup`
- explicit scope label match (if provided) is strongest signal
- nearest matching ancestor wins

### 9.3 Region-like hints
- role/tag tokens: `region`, `group`, `fieldset`, `section`, `form`
- anchor-descendant association preferred over global region scan
- nearest matching ancestor wins

### 9.4 Mobile container hints
- widget/class tokens: `RecyclerView`, `CardView`, `ViewGroup`, `LinearLayout`, `FrameLayout`
- use only as structural hints, not as auto-selection tie breakers

## 10) Ambiguity and fail-closed behavior

Required rules:
- no invented anchors
- no invented scope labels
- no automatic tie-breaking when multiple plausible anchors/scopes remain
- emit explicit statuses: `ambiguous`, `no_anchor`, `no_scope`, `no_match`

If ambiguity exists, diagnostics should preserve candidate IDs and reason codes; runtime behavior remains unchanged.

## 11) `control_kind_hint` filtering in diagnostics

Map control hints using normalized role/tag/widget heuristics:
- `button`: role/tag/button-like widget
- `input`: textbox/input/edittext/textarea
- `dropdown`: combobox/select/spinner
- `checkbox`: checkbox/checked-capable controls
- `radio`: radio/radiobutton controls

Filter applies only to `matched_ids`/`excluded_ids` diagnostics. No runtime selection change.

## 12) `mobile_attr_preference` representation

Supported values:
- `content_desc`
- `resource_id`
- `text`
- `none`

Diagnostics should include which matched/in-scope IDs satisfy preferred attribute presence.

No runtime resolver priority or matching-order change in Phase 1.

## 13) Future integration path

### Phase 1: metadata-only diagnostics
- Build planner diagnostics payload and attach to resolver metadata (or step-level diagnostics) without affecting winner/confidence.

### Phase 2: optional feature-flagged filtering
- Add gated, off-by-default candidate filtering using same deterministic planner.
- Must include strict regression parity checks and ambiguity protections.

### Phase 3: scoring consideration
- Benchmark-backed evaluation of graph-informed scoring only after Phase 2 stability.
- Requires explicit approval and separate design gate.

## 14) Relationship to Object Intelligence seed fixture fields

This design aligns with seed relation categories/signals:
- relation types: label/row/card/modal/region/mobile hint
- graph signals and ambiguity-focused cases
- static summary/reporting fields remain unchanged

No seed schema changes are required for this design phase.

## 15) Relationship to existing `graph_signals` diagnostics

`graph_signals` currently provides compact per-candidate booleans and `score_hint`.

Graph-query planner diagnostics are complementary:
- `graph_signals`: candidate-centric local evidence
- graph-query diagnostics: relation/scope-centric deterministic planning evidence

Do not merge these contracts in Phase 1; keep additive metadata separation.

## 16) Non-goals (Phase 19G-G)

- no runtime target selection changes
- no graph candidate filtering
- no ranker/scoring/confidence changes
- no resolver priority/order changes
- no parser expansion
- no SDK/API/schema/version/dependency changes
- no benchmark fixture changes

## 17) Test plan required before implementation

Before metadata-only implementation:
1. unit tests for each relation mapping path (`label_for`, `same_row_as_text`, `within_card`, `within_modal`, `within_region`, `mobile_attr_hint`)
2. negative/ambiguity tests (`no_anchor`, `no_scope`, `ambiguous`, `no_match`)
3. JSON-safety and deterministic ordering tests
4. benchmark non-regression checks (12/12 static, 12/12 execute)
5. object seed summary unchanged check (`--cases .../seed_cases.json`)
6. public API unchanged test
7. collect-only baseline stability check

## 18) Risks and mitigations

Risks:
- false negatives from strict anchor/scope detection
- cross-platform container heuristic drift
- accidental hidden behavior coupling if diagnostics leak into ranking early

Mitigations:
- diagnostics-first rollout
- strict fail-closed ambiguity policy
- explicit reason/status codes
- deterministic fixtures and parity gates before any filtering enablement

## 19) GO/NO-GO criteria for metadata-only diagnostics MVP

**GO** when all are true:
- mapping rules are fully specified and test cases enumerated
- output contract is stable and JSON-safe
- no runtime winner/confidence/order/threshold regressions
- benchmark/public API/collection baselines remain unchanged

**NO-GO** if any are true:
- unresolved mapping ambiguity for card/modal/region scopes
- diagnostics contract not deterministic/compact
- implementation proposal includes runtime filtering or score/order changes
