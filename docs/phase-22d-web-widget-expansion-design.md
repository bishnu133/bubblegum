# Phase 22D — Web Widget Expansion Design

> **Status:** GO with revisions applied from review. This revision incorporates
> the nine review items (Tier 1 scope/validation alignment, local fixture app,
> capability matrix, separate `upload` action, `close_dialog` as helper,
> active scope model, ambiguity policy, state-based verification, golden
> dataset).

## Purpose
The simple_login validation (Phase 22A/C) proved Bubblegum can resolve and act
on three widget types: text input, button, and visible text. Real applications
use a much broader vocabulary — selects, date pickers, sliders, autocompletes,
modals, tabs, file pickers, drag handles, tables. This phase scopes the work
needed to make Bubblegum a credible automation layer for that broader
vocabulary, without expanding to a new platform adapter.

Out of scope for this phase: native React Native, Flutter (canvas-rendered),
and any non-DOM target. Those need separate adapters and are tracked
separately (see "Deferred" below).

## Architectural fit
Phase 22D preserves Bubblegum's core principle: **shared core (parser,
planner, resolvers, scope model) + channel-specific adapters**. New widget
knowledge lives in core; only the *execution* of a new action lives in the
Playwright adapter. Mobile adapters can later reuse the same parser/resolver
hints without duplication.

## Framing: tech stacks vs widgets

Most of the "tech stacks" raised in the request (React + Next.js + Tailwind,
Angular + Material UI, React Native Web) render to the DOM. Playwright already
drives them. The work that actually unblocks coverage on those stacks is
**better widget handling**, plus a few component-library quirks:

| Stack | Renders to | Bubblegum gap |
|---|---|---|
| React + Next.js + Tailwind | DOM | Tailwind classes carry no ARIA — accessibility-tree resolver gets weaker; need stronger fuzzy + label-for fallback. |
| Angular + Material UI | DOM | Material widgets attach panels via CDK overlay (out-of-tree); resolver must follow `aria-owns`/`aria-controls`. |
| React + MUI | DOM | MUI uses React portals for menus/dialogs — same out-of-tree issue. |
| React Native Web | DOM | Same as React. |
| React Native (device) | Native views | Existing Appium adapter; widget taxonomy reuses core parser hints. |
| Flutter Web | `<canvas>` | DOM resolvers do not apply. Deferred — needs flutter_driver / semantics. |

## Tier 1 split: 22D-A and 22D-B

Tier 1 is split into two internal sub-phases so the acceptance criteria stay
honest. Each sub-phase has its own validation matrix and ships independently.

### 22D-A — Native / basic widgets
Widgets that resolve fully from in-tree DOM without overlay logic.

1. **Native `<select>` dropdown** — single-select.
2. **Radio group** — by group label + option label.
3. **Checkbox group** — by group label + option label.
4. **Link** — distinct from button when both share a label.
5. **File upload `<input type="file">`** — set file path without OS picker.

### 22D-B — Overlay / scoped widgets
Widgets that require following `aria-controls`/`aria-owns` and/or maintaining
an active scope across steps.

6. **Custom dropdown / combobox** — `role="combobox"` + portal-rendered listbox.
7. **Modal / dialog** — open detection, scope subsequent steps within it,
   close via SDK helper (see §close_dialog).

### Tier 2 — common but not blocking (next phase)
8. **Date picker** (native and portal).
9. **Slider / range**.
10. **Tabs** (uses the scope model from 22D-B).
11. **Autocomplete**.
12. **Table cell** (row anchor + column header).
13. **Toggle / switch**.
14. **Accordion**.

### Tier 3 — deferred this phase
Drag-and-drop, rich-text editors, tree views, native browser dialogs,
iframe scoping, drawing canvases.

## Widget capability matrix

Tracks per-widget completion across all five layers. A row is "done" only
when every column is green.

| Widget       | Parser  | Query hint           | Resolver                  | Adapter action     | Unit test | E2E example     | Sub-phase |
|---|---|---|---|---|---|---|---|
| Native select | New    | `dropdown`/`select`  | Existing (a11y tree)      | `select` (new)     | New       | `/dropdown` + lab | 22D-A    |
| Checkbox     | Extend  | `checkbox`           | Existing                  | `check`/`uncheck` (new) | New   | `/checkboxes` + lab | 22D-A    |
| Radio        | New     | `radio` (new)        | Existing                  | `click` (reuse)    | New       | lab fixture       | 22D-A    |
| Link         | New     | `link` (new)         | Existing                  | `click` (reuse)    | New       | lab fixture       | 22D-A    |
| File upload  | New     | `file`/`upload`      | Existing                  | `upload` (new)     | New       | `/upload` + lab   | 22D-A    |
| Modal        | Extend  | `dialog`/`modal`     | + `find_open_dialog`      | scope + SDK helper | New       | lab fixture       | 22D-B    |
| Combobox     | Extend  | `combobox` (new)     | + `follow_aria_controls`  | `select` (extend)  | New       | lab fixture       | 22D-B    |

Each row also requires golden dataset entries (§9) and state-based
verification (§8).

## What each new widget needs

For every widget the work has the same shape across three layers.

### 1. Parser (`bubblegum/core/parser/instruction.py`)
Add intent recognition so NL phrasings map to a `control_kind_hint` and the
right `action_type`. Concrete additions:

- "Select `<value>` from `<label>`" → `control_kind_hint=dropdown` even when
  the word "dropdown" is absent. Today the hint is only set when "dropdown"
  appears (line 199).
- "Choose `<label>` radio" / "Pick `<label>` from `<group>`" →
  `control_kind_hint=radio`, `relation_type=label_for` or
  `within_region+radio`.
- "Check/Tick/Uncheck/Untick/Toggle `<label>`" → existing checkbox path
  extended for negative forms.
- "Click `<label>` link" → `control_kind_hint=link` (new).
- "Upload `<path>` to `<label>`" / "Attach `<path>` as `<label>`" →
  new `action_type=upload`, value=path, target=label/input.
- "Open `<label>` dialog" / "In the `<name>` dialog … Close the dialog" →
  scope set to dialog (§scope model); close is an SDK helper, not an action.

### 2. Query / control-kind matching (`bubblegum/core/elements/query.py`)
Introduce a normalized `ControlKind` enum (string-valued) so the set of hints
is closed and lints-able instead of scattered string literals. Values:
`none, button, input, dropdown, select, combobox, checkbox, radio, link,
dialog, tab, switch`.

`_match_control_kind` gains entries for the new values:
- `link → role in {link} or tag == a`
- `radio → role == radio or (tag == input and attributes.type == radio)`
- `combobox → role == combobox`
- `dialog → role in {dialog, alertdialog} or attributes.role == dialog`
- `tab → role == tab`
- `switch → role == switch`

### 3. Resolver chain (`bubblegum/core/grounding/resolvers/`)
- **AccessibilityTreeResolver** — additive helpers, not new resolver classes:
  - `follow_aria_controls(node)` — given a combobox/disclosure trigger,
    return the controlled listbox/dialog (handles MUI/MatSelect portals).
  - `find_open_dialog()` — locate an open `role=dialog` with
    `aria-modal=true` for scope binding.
- **Explicit selector** remains the escape hatch for unlabeled widgets.
- No new resolver class is created in Tier 1.

### 4. Adapter action (`bubblegum/adapters/web/playwright/adapter.py`)
Refactor to a dispatch table keyed on `action_type`. New entries:
- `select` — `<select>`: `locator.select_option(...)`; combobox: open via
  click, locate listbox through `follow_aria_controls`, click the option.
- `upload` — `locator.set_input_files(input_value)`. Fails loudly if the
  resolved element is not a file input.
- `check` / `uncheck` — `locator.check()` / `locator.uncheck()`.

`close_dialog` is **not** added as an action (see §close_dialog).

## Active scope model

Modals, tabs (Tier 2), accordions (Tier 2) and iframes (Tier 3) all share the
same problem: once a container is open/active, subsequent steps should resolve
*inside it first*. Without this, "Enter `<name>` into Name" inside a Settings
dialog will match the wrong field on the page behind.

Add a lightweight per-session scope stack in the SDK layer:

```text
SessionScope:
  type:          page | dialog | tab_panel | iframe
  label:         "Settings"           # human-readable, for traces
  root_locator:  <Playwright Locator> # all resolvers receive this as root
  opened_by:     step_index           # for auto-pop on dialog close
```

Behavior:
- Default scope is `page` (root).
- "Open `<label>` dialog" / a click that triggers a `role=dialog` to appear
  → push `dialog` scope.
- "Close the dialog" → pop scope.
- All resolvers accept an optional `scope_root` and search there first; if no
  match, fall back to the full page only when the relational intent does not
  pin to scope.
- Scope is recorded in every trace entry so failures are diagnosable.

This is introduced in 22D-B (PR 22D-6) and reused by Tier 2 tabs/accordions
later.

## close_dialog: helper, not action

Do not add `close_dialog` as a core action_type. Implement it as an SDK helper
that lowers to existing primitives:

```text
session.close_dialog()  →
  1. Find active dialog scope (or find_open_dialog()).
  2. Resolve close affordance inside it: role=button whose accessible
     name matches /^(close|cancel|dismiss|×|x)$/i.
  3. If found → click; else press Escape.
  4. Pop dialog scope.
```

Promote to a real action only if we later need richer policy (e.g. "Close all
modals", confirmation prompts before close).

## Ambiguity policy

When the resolver finds multiple matches:

1. **Same kind, equal text/role match** → ambiguous. Do **not** silently pick.
   Return an `Ambiguous` result with top-N candidates and require either
   (a) an explicit selector, (b) a relational hint, or (c) a re-phrasing.
2. **Different kinds, same label** (e.g. `<button>Sign in</button>` and
   `<a>Sign in</a>`):
   - Default: **button wins**.
   - "Click `<label>` link" → link wins.
   - "Click `<label>` button" → button wins (already implied).
3. **Confidence within `ambiguity_margin` (e.g. 0.05)** → treat as case (1).

This matches the existing `ambiguity_policy: fail_on_ambiguous` field already
in `_base_relational_payload()`; we just extend it to cover the kind-tied case
and surface candidate diagnostics.

## State-based verification

Every E2E example must verify the resulting widget *state*, not just visible
text. Concrete checks per widget:

| Widget       | State check |
|---|---|
| Native select | `locator.input_value()` equals expected option value |
| Checkbox     | `locator.is_checked()` |
| Radio        | the chosen option's `is_checked()`; others' `is_checked()` is false |
| Link         | URL transition (`page.url`) or the destination page identifier |
| File upload  | Server-rendered filename, plus DOM check that `input.files` is non-empty before submit |
| Modal        | Dialog visibility on open; dialog absence/`aria-hidden` after close |
| Combobox     | Triggered control's accessible value / selected listbox option |

This aligns with the PRD's validation requirement (text, visibility,
transition, state).

## Validation harness

Two sources of validation, used in tandem:

### A. Local widget lab (primary, deterministic)
A small static HTML app under `examples/web/widgets/widget_lab/` (or
`tests/fixtures/web/widgets/`), served by a tiny built-in HTTP server in the
example runner. Pages it contains:

- `select.html` — labeled native select; second select with no label but
  nearby text.
- `radio.html` — radio group with group label.
- `checkbox.html` — checkbox group with labels.
- `link_vs_button.html` — duplicate "Sign in" as both `<button>` and `<a>`.
- `upload.html` — file upload with success message after submit.
- `dialog.html` — modal with `Close (×)`, `Cancel`, and Escape support;
  input fields inside.
- `combobox.html` — ARIA combobox with portal-rendered listbox
  (mimics MUI/Angular Material).

Benefits: stable, offline, exercises edge cases the public site does not
cover (unlabeled select, button-vs-link clash, true portal listbox).

### B. Public site (regression smoke)
`the-internet.herokuapp.com` pages used as cross-checks:

| Page | Widget(s) under test | Sub-phase |
|---|---|---|
| `/login` | regression: text input + button | 22D-A |
| `/dropdown` | native `<select>` | 22D-A |
| `/checkboxes` | checkbox group | 22D-A |
| `/upload` | file upload | 22D-A |

Public site covers smoke; the lab covers correctness. CI runs the lab;
the public-site run is opt-in to avoid external flakiness gating CI.

Component-library demos (MUI dashboard, Angular Material) are deferred to
the phase after 22D, gated on 22D-B passing on the local combobox fixture.

## Golden parser/resolver dataset

For every new parser pattern, add an entry under
`tests/benchmarks/web_widgets/parser_cases.json`:

```json
[
  {
    "instruction": "Select India from Country",
    "expected": {
      "action_type": "select",
      "target_phrase": "Country",
      "input_value": "India",
      "control_kind_hint": "dropdown"
    }
  },
  {
    "instruction": "Click the Sign in link",
    "expected": {
      "action_type": "click",
      "target_phrase": "Sign in",
      "control_kind_hint": "link"
    }
  }
]
```

DOM fixtures (small HTML snippets) for resolver-level cases go under
`tests/benchmarks/web_widgets/dom_fixtures/`. Each fixture pairs with a
test that asserts the resolver picks the expected element id given a
specific `ParsedIntent`. This matches the existing testing-strategy
guidance about reusable datasets of screen states, expected targets,
NL instructions, and expected structured plan output.

## Revised phased delivery

Each step is a separate PR. Tests live alongside the change.

| PR | Scope |
|---|---|
| **22D-1** | `ControlKind` enum normalization in `query.py`; add `link, radio, combobox, dialog, tab, switch` values + matching rules. Unit tests only. |
| **22D-2** | Parser synonym expansion: select-without-"dropdown", radio, link, upload, uncheck/toggle, dialog scope phrases. Golden parser cases in `tests/benchmarks/web_widgets/parser_cases.json`. |
| **22D-3** | Adapter dispatch table: `click`, `type`, `select`, `upload`, `check`, `uncheck`. Regression on existing click/type paths. |
| **22D-4** | Widget lab fixture app under `examples/web/widgets/widget_lab/` + tiny HTTP server in runner. E2E examples for native select and file upload using the lab. |
| **22D-5** | E2E examples for checkbox group, radio group, and link-vs-button using the lab. |
| **22D-6** | Active scope model (`SessionScope` stack) in SDK; `close_dialog` helper. Unit tests with mock locators. |
| **22D-7** | Accessibility-tree helpers `follow_aria_controls` and `find_open_dialog`. Unit tests on fixture DOMs. |
| **22D-8** | E2E examples for custom combobox and modal using the lab (exercises 22D-6 + 22D-7). |
| **22D-9** | Tier-1 regression runner that executes all 22D examples back-to-back, prints summary table, captures evidence. Adds the public-site smoke (`/dropdown`, `/checkboxes`, `/upload`, `/login`) behind an opt-in flag. |

22D-1..3 and 22D-7 are pure framework changes (any order). 22D-4..6 and
22D-8..9 depend on the framework PRs and are sequenced.

## Acceptance criteria

GO when all of the following hold:

- 22D-A widget set (native select, radio, checkbox group, link, file upload)
  has a resolver path that does not require an explicit selector for labeled
  cases.
- 22D-B widget set (custom combobox, modal) works against the local widget
  lab using `aria-controls` and the active scope model.
- A single NL instruction drives each Tier 1 widget against the lab and the
  public-site smoke pages.
- Every Tier 1 E2E example verifies widget *state*, not just text.
- Golden parser dataset covers every new NL pattern; all entries pass.
- The Tier 1 regression runner (22D-9) passes for two consecutive runs.
- Existing real-web tests (the 14 from `100db01`) still pass; no regression.
- README "known limitations" updated to call out: canvas (Flutter),
  drag-drop, rich text, iframe scoping.

## Explicitly out of scope for 22D

These are valid but would distract from making deterministic widget execution
strong first:

- AI/OCR fallbacks (existing chain unchanged).
- Drag-and-drop, rich-text editors, iframe scoping.
- Flutter Web (canvas) adapter.
- React Native native widget expansion.
- MUI / Angular Material full demo suites.

## Deferred work (tracked, not blocking)

- **Flutter Web adapter.** Canvas + semantics-tree path. Distinct adapter
  module under `bubblegum/adapters/web/flutter/`. Needs separate design.
- **Native React Native widget expansion.** Reuses `ControlKind` enum and
  parser hints; adapter work only.
- **Component-library demo runs.** Gated on 22D-B passing locally.
- **Tier 2 widgets** (date picker, slider, tabs, autocomplete, table cell,
  switch, accordion).
- **Tier 3** (drag-drop, rich text, iframes, browser dialogs, canvases).

## Resolved review questions

1. **`upload` action type?** Separate, first-class `upload` action. Fails
   loudly when the target is not a file input. (Item 4.)
2. **`close_dialog`?** SDK helper, not a core action. Lowers to existing
   click/Escape primitives. (Item 5.)
3. **Button vs link tie?** Button wins by default; link wins only when the
   instruction says "link" explicitly. Ambiguity-margin ties surface
   candidates instead of silent guesses. (Item 7.)
