# Phase 22D — Web Widget Expansion Design

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
| React Native (device) | Native views | Existing Appium adapter; expand widget taxonomy in parallel. |
| Flutter Web | `<canvas>` | DOM resolvers do not apply. Deferred — needs flutter_driver / semantics. |

The first four converge on the same DOM work. That is what this phase covers.

## Widget taxonomy and priorities

Widgets are grouped by tier. Tier 1 is required to call the phase done; Tier 2
follows immediately; Tier 3 is deferred and listed for visibility.

### Tier 1 — minimum viable widget set
1. **Native `<select>` dropdown** — single and multi-select.
2. **Custom dropdown / combobox** — ARIA `role="combobox"` + portal-rendered listbox (MUI/Angular Material pattern).
3. **Radio group** — by group label + option label.
4. **Checkbox group** — by group label + option label (single checkbox already partially handled).
5. **Modal / dialog** — open detection, scope subsequent steps within it, close via `Cancel`/`X`/Esc.
6. **Link** — distinct from button, especially when same label exists as both.
7. **File upload `<input type="file">`** — set file path without clicking through the OS picker.

### Tier 2 — common but not blocking
8. **Date picker** (native `<input type="date">` and portal-based pickers).
9. **Slider / range** — set value by step or by labelled value.
10. **Tabs** — switch active tab by label, scope subsequent steps to its panel.
11. **Autocomplete** — type, wait for listbox, select option by text.
12. **Table cell** — select/click cell by row anchor + column header.
13. **Toggle / switch** — turn on/off by label.
14. **Accordion** — expand/collapse by header label.

### Tier 3 — deferred this phase
- Drag-and-drop.
- Rich-text editors (contenteditable, CodeMirror, Monaco).
- Tree views.
- Native browser dialogs (alert/confirm/prompt) — already routable via Playwright `dialog` events; needs an SDK wrapper.
- Frames / iframes scoping.
- Drawing canvases.

## What each new widget needs

For every Tier 1 widget, the work has the same shape across three layers:

### 1. Parser (`bubblegum/core/parser/instruction.py`)
Add intent recognition so NL phrasings map to a `control_kind_hint` and the
right `action_type`. Concrete additions:

- "Select `<value>` from `<label>` dropdown" → already partly covered by the
  `_VALUE_INTO_TARGET_RE` + `within_region/dropdown` rule. Verify it also
  yields `control_kind_hint=dropdown` when no explicit "dropdown" word is
  used (currently only set when the word "dropdown" appears).
- "Choose `<label>` radio" / "Pick `<label>` from `<group>` radio group" →
  `control_kind_hint=radio`, `relation_type=label_for` or
  `within_region+radio`.
- "Check `<label>` checkbox" → already partly covered (line 203-213); extend
  for "Uncheck `<label>`", "Tick `<label>`", "Toggle `<label>`".
- "Open `<label>` modal" / "In the `<name>` dialog" → `within_modal` (already
  present). Add "close `<name>` dialog" → action_type=`click`, target=close
  button within scope.
- "Click `<label>` link" → `control_kind_hint=link` (new value).
- "Upload `<path>` to `<label>`" / "Attach `<path>` as `<label>`" →
  new action_type `upload`, value=path, target=label/input.
- "Switch to `<label>` tab" → `control_kind_hint=tab`, action_type=`click`.
- "Toggle `<label>`" / "Turn on `<label>`" → `control_kind_hint=switch`,
  action_type=`click`.

Each new `control_kind_hint` value must be added to `_match_control_kind` in
`bubblegum/core/elements/query.py` with the relevant role/tag/widget triggers
(e.g. `link → role in {link} or tag == a`; `radio → role == radio or
attributes.type == radio`; `switch → role == switch or attributes.role ==
switch`; `tab → role == tab`).

### 2. Resolver chain (`bubblegum/core/grounding/resolvers/`)
- **AccessibilityTreeResolver** — already enumerates roles; gaps are
  scope-following (`aria-controls`, `aria-owns`) and dialog detection
  (`role=dialog` with `aria-modal=true`). Both are additive, not new
  resolvers.
- **Explicit selector** — keep as escape hatch for unlabeled widgets.
- **No new resolver classes are required for Tier 1.** If anything,
  `accessibility_tree.py` grows two helpers: `follow_aria_controls(id)`
  and `find_open_dialog()`. Adding a new resolver class is a Tier 3
  consideration (e.g. an `OverlayResolver` once we have evidence the
  existing chain is insufficient).

### 3. Adapter action (`bubblegum/adapters/web/playwright/adapter.py`)
The Playwright adapter must learn how to *execute* each new action_type once
the resolver hands back a locator. New entries:

- `select` — call `locator.select_option(value=…)` for `<select>`; for
  combobox, click to open, wait for the owned listbox, click the option whose
  text matches `input_value`.
- `upload` — call `locator.set_input_files(input_value)`.
- `check` / `uncheck` — call `locator.check()` / `locator.uncheck()` (these
  are idempotent and avoid the "already checked" race).
- `close_dialog` — locate the open dialog (via `find_open_dialog()`) then
  click its close affordance (`role=button` whose name matches /close|cancel|x/i)
  or press `Escape`.

The adapter must dispatch on `action_type`; today it has only `click` and
`type` paths. The dispatch table lives in one place — extending it does not
require touching the resolver chain.

## Component-library quirks worth encoding now

Picking these up while we add Tier 1 avoids a re-design later.

- **MUI / React portals.** Menus and dialogs render to `document.body`, not
  inside the trigger's subtree. `follow_aria_controls` resolves this without
  hardcoding portal selectors.
- **Angular Material CDK overlay.** Same pattern — `mat-select` opens a
  `cdk-overlay-container` panel. Same `aria-controls` fix applies.
- **Tailwind.** No built-in semantics. The fuzzy + label-for resolvers
  already cover the common case ("Click Submit" → button with text "Submit").
  Document that headless Tailwind components without ARIA require explicit
  selectors as a known limitation.

## Validation harness — the-internet.herokuapp.com

Use the same dummy app as the existing example. Pages and the widget each
exercises:

| Page | Widget(s) under test |
|---|---|
| `/dropdown` | native `<select>` |
| `/checkboxes` | checkbox group |
| `/inputs` | numeric input (already covered) |
| `/upload` | file upload |
| `/javascript_alerts` | native browser dialog (Tier 3, document only) |
| `/dynamic_loading/1` | wait-for-element after click |
| `/hovers` | hover + revealed content |
| `/horizontal_slider` | slider (Tier 2) |
| `/iframe` | iframe scoping (Tier 3) |
| `/tables` | table cell (Tier 2) |
| `/login` | text input + button (regression) |

For this phase the matrix is restricted to Tier 1: `/dropdown`,
`/checkboxes`, `/upload`, plus a regression run of `/login`. Each scenario
becomes a self-contained example under
`examples/web/widgets/<widget>/run_example.py`, mirroring the shape of
`examples/web/simple_login/run_example.py` so the existing runner pattern is
reused.

The matrix does not yet include MUI or Angular Material demo apps. Those are
added once Tier 1 passes against the-internet, so the portal/`aria-controls`
work is exercised against a real component library. That work falls in the
next phase.

## Phased delivery

Each step is a separate PR. Tests live alongside the change.

1. **22D-1 — Parser + query extensions.** Add `link`, `radio`, `tab`,
   `switch` to `control_kind_hint` and `_match_control_kind`. Extend
   `parse_relational_intent` for "uncheck/toggle", "select from … dropdown"
   without the "dropdown" suffix, and "in the … dialog → close".
   Unit tests only; no adapter changes.
2. **22D-2 — Adapter action dispatch.** Refactor
   `adapters/web/playwright/adapter.py` to dispatch on `action_type` from a
   table. Add `select`, `upload`, `check`, `uncheck` paths. Keep `click`/`type`
   behavior identical for regression.
3. **22D-3 — Accessibility-tree helpers.** Add `follow_aria_controls` and
   `find_open_dialog`. Use them inside the resolver to widen matches; unit
   tests on fixture DOMs.
4. **22D-4 — Validation example: native `<select>`.** New example under
   `examples/web/widgets/select/`. Mirrors `simple_login` structure.
   Scenario: open `/dropdown`, select "Option 2", verify it's selected.
5. **22D-5 — Validation example: checkbox group.** `/checkboxes`. Scenarios:
   check #1, uncheck #2, verify both states.
6. **22D-6 — Validation example: file upload.** `/upload`. Scenario: upload
   a small fixture file, verify the result page reports the filename.
7. **22D-7 — Tier-1 regression run.** A single script that runs all Tier 1
   examples back-to-back, captures pass/fail per scenario, and prints a
   summary table — same shape as the existing simple_login summary.

PRs 22D-1..3 are pure framework changes and can be reviewed in any order;
22D-4..7 are sequenced because they depend on the new actions.

## Acceptance criteria

The phase is GO when all of the following hold:

- Tier 1 widget set (select, custom dropdown, radio, checkbox group, modal,
  link, file upload) has a resolver path that does not require an explicit
  selector for labeled cases.
- A single NL instruction can drive each Tier 1 widget against
  the-internet.herokuapp.com.
- The Tier 1 regression run (22D-7) passes for two consecutive runs locally.
- Existing real-web tests (the 14 from `100db01`) still pass; no regression.
- The known-limitations list in the README is updated to call out: canvas
  rendering (Flutter), drag-drop, rich text, iframe scoping.

## Deferred work (tracked, not blocking)

- **Flutter Web adapter.** Canvas + semantics-tree path. Distinct adapter
  module under `bubblegum/adapters/web/flutter/`. Needs separate design.
- **Native React Native widget expansion.** Mirrors this phase for
  Appium-side widget taxonomy; not free-rides on DOM changes.
- **Component-library demo runs.** MUI dashboard template and Angular
  Material demo. Gated on Tier 1 passing here.
- **Rich text, drag-drop, iframes.** Tier 3 above.

## Open questions for review

1. Do we add a new `action_type=upload` or fold it under `type`+kwarg
   `as_file=True`? Recommendation: separate `upload` — clearer intent, easier
   to fail loudly if used on the wrong element.
2. Should `close_dialog` be its own action or an SDK helper that emits a
   `click` step against the resolved close affordance? Recommendation: SDK
   helper. Keeps the action vocabulary small.
3. When a label matches both a `<button>` and an `<a>` (e.g. "Sign in"),
   which wins by default? Recommendation: button, unless the instruction
   says "link" explicitly. Worth confirming before 22D-1.
