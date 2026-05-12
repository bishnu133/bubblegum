# Phase 19G-B — Relational Intent Schema/Design (Spec Only)

Status: Design-only (no runtime implementation)

## 1) Problem statement

Current natural-language grounding is strong for direct target text/role matching, but weak for relational object-identification instructions where the actionable element is defined by context/scope/anchor rather than by unique direct text.

Examples:
- "Click Edit for Alice Johnson"
- "Click Delete in the confirmation modal"
- "Select Singapore from the Country dropdown"
- "Tap Scan QR when duplicate text exists"

These instructions require a structured representation of relation and scope semantics before safe runtime resolution can be implemented.

## 2) Current parser/planner limitations

Current parser/planner behavior is intentionally coarse:
- Parser infers broad action types (`click`, `type`, `select`, etc.) from keywords.
- Planner constructs `StepIntent` with instruction/channel/platform/action_type/options/context.
- There is no first-class relation/scope/anchor contract in parser outputs today.

This phase does not change that behavior.

## 3) Why relation-aware intent is needed for Object Intelligence

Object Intelligence seed fixtures introduce scenarios where direct text lookup alone is ambiguous or insufficient:
- same-row action selection
- modal/card/region scoping
- label-to-control relationships
- mobile content-desc/resource-id preference hints

A relation-aware intent contract enables deterministic, conservative downstream query planning and safer ambiguity handling.

## 4) Proposed `relational_intent` metadata contract (schema-stable)

Use namespaced optional metadata in existing `StepIntent.context`:

```python
context["relational_intent"] = {
  "primary_target_text": "...",
  "relation_type": "...",
  "anchor_text": "...",
  "scope_type": "...",
  "scope_label": "...",
  "control_kind_hint": "...",
  "mobile_attr_preference": "...",
  "ambiguity_policy": "fail_on_ambiguous"
}
```

Important:
- Optional field group; absent for plain instructions.
- No public schema changes in this phase.
- Contract is design target for future parser/planner/runtime phases.

## 5) Field-by-field definition

- `primary_target_text` (string | null)
  - Primary action/control text expected on target element (`Edit`, `Delete`, `Manage`, `Continue`, etc.).

- `relation_type` (enum)
  - Logical relation connecting target to anchor/scope.

- `anchor_text` (string | null)
  - Anchor content used to disambiguate target (`Alice Johnson`, `Pro Plan`, etc.).

- `scope_type` (enum | null)
  - Scope container class (`row`, `card`, `modal`, `region`, `label`, `mobile_screen`).

- `scope_label` (string | null)
  - Human-facing label/title for scope (`confirmation modal`, `Country dropdown`).

- `control_kind_hint` (enum | null)
  - Expected control type (`button`, `checkbox`, `radio`, `dropdown`, `input`, `link`).

- `mobile_attr_preference` (enum | null)
  - Preferred matching attribute for mobile disambiguation (`content_desc`, `resource_id`, `text`).

- `ambiguity_policy` (enum)
  - Default: `fail_on_ambiguous`.

## 6) Allowed values / enums

### `relation_type`
- `none`
- `label_for`
- `same_row_as_text`
- `within_card`
- `within_modal`
- `within_region`
- `mobile_attr_hint`

### `scope_type`
- `none`
- `row`
- `card`
- `modal`
- `region`
- `label`
- `mobile_screen`

### `control_kind_hint`
- `none`
- `button`
- `checkbox`
- `radio`
- `dropdown`
- `input`
- `link`

### `mobile_attr_preference`
- `none`
- `content_desc`
- `resource_id`
- `text`

### `ambiguity_policy`
- `fail_on_ambiguous` (default)
- `allow_review` (reserved for future explicit opt-in)

## 7) Example mappings for target instructions

1. **"Click Edit for Alice Johnson"**
   - `primary_target_text=Edit`
   - `relation_type=same_row_as_text`
   - `anchor_text=Alice Johnson`
   - `scope_type=row`
   - `control_kind_hint=button`
   - `ambiguity_policy=fail_on_ambiguous`

2. **"Click Delete in the confirmation modal"**
   - `primary_target_text=Delete`
   - `relation_type=within_modal`
   - `scope_type=modal`
   - `scope_label=confirmation modal`
   - `control_kind_hint=button`

3. **"Select Singapore from the Country dropdown"**
   - `primary_target_text=Singapore`
   - `relation_type=within_region`
   - `anchor_text=Country`
   - `scope_type=region`
   - `scope_label=Country dropdown`
   - `control_kind_hint=dropdown`

4. **"Check Terms and Conditions"**
   - `primary_target_text=Terms and Conditions`
   - `relation_type=label_for`
   - `scope_type=label`
   - `control_kind_hint=checkbox`

5. **"Click Manage in the Pro Plan card"**
   - `primary_target_text=Manage`
   - `relation_type=within_card`
   - `anchor_text=Pro Plan`
   - `scope_type=card`
   - `control_kind_hint=button`

6. **"Tap Continue on the Android screen"**
   - `primary_target_text=Continue`
   - `relation_type=mobile_attr_hint`
   - `scope_type=mobile_screen`
   - `control_kind_hint=button`
   - `mobile_attr_preference=text`

7. **"Tap Settings with content-desc"**
   - `primary_target_text=Settings`
   - `relation_type=mobile_attr_hint`
   - `mobile_attr_preference=content_desc`
   - `control_kind_hint=button`

8. **"Tap Scan QR when duplicate text exists"**
   - `primary_target_text=Scan QR`
   - `relation_type=mobile_attr_hint`
   - `mobile_attr_preference=resource_id` (if explicitly signaled by parser context/rules; else remain `none`)
   - `ambiguity_policy=fail_on_ambiguous`

## 8) Alignment with Object Intelligence seed fixture fields

This contract aligns directly with seed metadata dimensions:
- relation categories: `label_for`, `same_row_as_text`, `within_card`, `within_modal`, `within_region`
- expected graph signals: row/card/modal/label/resource-id/content-desc patterns
- positive/negative and ambiguity-focused cases

No fixture schema or runtime benchmark behavior changes are introduced in this phase.

## 9) Future graph query planner consumption (design guidance)

Later graph-query planning can consume `relational_intent` as **filter constraints**, not scoring modifiers:
1. Build candidate set by action/control hints.
2. Apply relation filter (`same_row_as_text`, `within_modal`, etc.).
3. Return narrowed set to existing resolver/ranker flow.

Graph-based scoring remains out-of-scope.

## 10) Conservative parser behavior principles

Future parser work should follow strict safety rules:
- rule-based first
- do not invent anchors or scope labels
- default `ambiguity_policy=fail_on_ambiguous`
- no unsafe assumptions when relation signals are weak
- if uncertain, emit minimal/partial `relational_intent` rather than hallucinated structure

## 11) Backward compatibility strategy

- Plain instructions remain unchanged.
- `relational_intent` is optional metadata in `context`.
- No public `StepIntent`/`ActionPlan` schema changes yet.
- Existing benchmark/runtime behavior remains unchanged until explicit implementation phases.

## 12) Non-goals (this phase)

- No runtime parser implementation
- No planner/runtime integration
- No ranker/confidence changes
- No graph-based scoring
- No object-seed execution harness
- No SDK/API/schema/version/dependency changes

## 13) Test plan required before implementation phases

Before parser/runtime changes:
1. parser pattern tests for each relation phrase pattern + negative cases
2. planner intent-shape tests for stable `context["relational_intent"]` payload
3. backward-compat tests for plain instructions
4. benchmark non-regression tests (default 12/12 static + 12/12 execute)
5. object-seed validation-only guard tests (and execute unsupported guard)

## 14) Phased implementation proposal (future)

- **19G-C**: parser relational metadata MVP (rule-based extraction only)
- **19G-D**: planner/context propagation + tests (no runtime relational query yet)
- **19G-E**: graph query planning audit/design (constraint consumption strategy)
- **19G-F**: object-seed execution readiness audit (go/no-go before enabling execute path)

## 15) Risks and mitigations

Risks:
- Premature runtime implementation could regress deterministic behavior.
- Over-eager parser may introduce unsafe implicit assumptions.
- Ambiguity could be mishandled without execution-backed validation.

Mitigations:
- Keep this phase design-only.
- Require strict pre-implementation test gates.
- Enforce conservative parser defaults and explicit ambiguity policy.
- Defer execution harness and graph-based scoring until readiness audits pass.

## 16) GO/NO-GO criteria for future parser implementation

**GO only if all are true:**
- relational contract finalized and reviewed
- parser tests for relation patterns + ambiguity pass
- backward compatibility/regression benchmarks unchanged
- object-seed validation-only guard remains intact until explicit execution-readiness phase
- no public API/schema/version/dependency drift

**NO-GO if any are true:**
- unresolved ambiguity semantics
- missing non-regression coverage
- proposed runtime changes depend on graph-based scoring or execution harness not yet approved
