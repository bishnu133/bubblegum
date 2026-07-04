# Unreleased

## 0.0.6a23 — feat(web): resolve hidden file inputs for `upload` steps (multi-section)

- `Upload "<path>" into <target>` now resolves the real `<input type=file>` even
  when it's **hidden** behind a styled button (Ant/MUI `Upload`), which the a11y
  tree and the visible-input fallback can't reach. New pre-grounding resolver
  `file_input_dom` scores every file input by its form-item label, **nearest
  section heading**, and id/name/testid (camelCase + kebab split into words).
- Handles **multiple upload widgets on one page** with repeated labels: name the
  section in the phrase to disambiguate, e.g. `Upload "..." into Awarded Album
  View` vs `... into Upcoming Album View` (the six Album/Front/Back × Awarded/
  Upcoming uploaders on the H365 Create-Badge page all resolve uniquely).
- Scoped and safe: only fires for `upload` steps that name a target, and is a
  no-op on pages with no file input. Verified end-to-end against a **real Ant v5
  `Upload`** (file registers in antd's list). Coverage:
  `tests/unit/test_upload_fallback.py`. Engine `0.0.6a22` → `0.0.6a23`.

## 0.0.6a22 — fix(web): commit typed value into date/time picker inputs (Enter)

- Typing into a date/time picker input now **activates and commits** the field
  (click → fill → Enter) instead of a bare `fill()`. Ant `RangePicker` keeps
  "active editing" on one field until Enter, so a plain fill sent the *end* value
  into the *start* input (both range values landed in "Start date", e.g.
  `06/07/2026 07:0016/07/2026 23:59`). With the commit keystroke, start and end
  each land in their own field.
- Detected generically (no per-app selectors): the input is inside `.ant-picker`
  / a `*[class*="DatePicker"|"datepicker"|"TimePicker"|"MuiPickers"]` widget, or
  carries a `date-range` attribute. Ordinary text inputs keep the plain `fill()`
  path — no stray Enter, so form submits aren't triggered.
- Verified end-to-end against a **real Ant v5 `RangePicker`** (React + antd UMD),
  not just static markup. Coverage: `tests/unit/test_picker_type_commit.py`.
  Engine `0.0.6a21` → `0.0.6a22`; npm client unchanged.

## 0.0.6a21 — fix(web): deterministic resolver for date-range picker start/end inputs

- `type "…" into Start date` / `End date` now pins the exact input of an Ant
  `RangePicker` from the DOM **before** name-based grounding runs, instead of
  letting a nameless picker input (no id/label/aria — only a `date-range`
  attribute or a "Start date"/"End date" placeholder) get mis-matched to some
  other "date"-ish element on the page. The phrase's side word (`start`/`from`/
  `begin` vs `end`/`until`/`finish`) selects which input; when a page has more
  than one range picker, the form-item label breaks the tie. New resolver
  `date_range_dom` (confidence 0.9).
- Scoped and safe: only fires for `type`/`fill` steps whose phrase names a side,
  and is a **no-op on pages without a range picker**, so ordinary text fields are
  unaffected (they keep resolving via the a11y tree / `input_dom` fallback).
- Coverage: `tests/unit/test_date_range_fallback.py`; validated against the real
  H365 Create-Badge "Visibility Period" range picker markup. Engine `0.0.6a20` →
  `0.0.6a21`; npm client unchanged.

## 0.0.6a20 — feat: absolute time-of-day in date tokens (`@HH:MM`); consolidates a18+a19

- Dynamic-value date tokens gain an **`@` absolute-time setter** so you can pin a
  computed date to a specific clock time instead of midnight or "now shifted":
  - `{{today+2d@07:00|%d/%m/%Y %H:%M}}` — 2 days out, at 07:00.
  - `{{tomorrow@9am|%d/%m/%Y %H:%M}}` — accepts `9am` / `9:30pm` / `23:59` /
    `07:00:00`. Applied after any date offset. When `@` is present and no `|`
    format is given, the default format includes the time (`%Y-%m-%d %H:%M`).
- Consolidation release: this is the first version published from `main` that
  contains **both** the uniqueness tokens (`{{timestamp}}`/`{{uuid}}`/`{{random}}`,
  originally `a18`) and the `a19` web clickable-fallback fix. `a18` was never on
  `main` and `a19` was cut from `a17` without the tokens; `a20` merges both so
  `pip install -U bubblegum-ai` gets every feature. Engine `0.0.6a19` → `0.0.6a20`.

## 0.0.6a18 — feat: uniqueness dynamic-value tokens ({{timestamp}}, {{uuid}}, {{random}})

- Dynamic-value tokens now cover **run-time uniqueness**, not just relative
  dates, so a field with a unique constraint (a badge name, an email, any
  create-form value) can be parameterised inline instead of hard-coded:
  - `{{timestamp}}` — Unix epoch seconds; `:ms` for milliseconds, or a `|`
    strftime for a readable stamp, e.g. `Badge_{{timestamp|%Y%m%d%H%M%S}}`.
  - `{{uuid}}` — random uuid4 hex (32 chars); `:N` keeps the first N chars
    (`{{uuid:8}}`). Unique regardless of the clock.
  - `{{random}}` — N random digits, default 6 (`{{random:6}}`).
- Same engine-side substitution path as the date tokens (`_decompose_for` in
  `sdk.py`), so it works identically for the Python SDK and the Node client
  across web, mobile, and CDP-attach. Malformed arguments and unrecognised
  tokens are left verbatim; literal values are untouched.
- Coverage: extended `tests/unit/test_dynamic_value_tokens.py`. Documented in
  `docs/USER_GUIDE.md`, `docs/HOW_TO_USE_TYPESCRIPT.md`, and the Node README
  (this fills a gap — the date tokens were previously undocumented in the guide).
  Engine `0.0.6a17` → `0.0.6a18`; npm client unchanged (engine‑side feature).
=======
## 0.0.6a19 — fix(web): clickable fallback strips trailing widget nouns

- `Click the <X> menu` (and `button`/`link`/`tab`/`option`/`item`/`field`) now
  resolves the control named `<X>` via the DOM clickable fallback: when the exact
  phrase doesn't match, it retries with the trailing widget word removed. Fixes
  `Click the Badges menu` matching the `Badges` nav item whose accessible name is
  just "Badges". (Only helps when the item is actually visible — an item hidden
  in an Ant `...` overflow menu must be reached by clicking the overflow first.)
- No parser behaviour change (the "X menu" target phrase is preserved, as some
  controls are literally named "… menu"). Note: `0.0.6a18` on PyPI was **not**
  published from this repository's `main` — this is the next release from `main`
  after `a17`. Engine `0.0.6a17` → `0.0.6a19`; npm unchanged.

## 0.0.6a17 — fix(web): DOM input fallback for nameless text fields

- `type`/`enter` into a field with **no accessible name** (e.g. a `<textarea>`
  whose `<label for=...>` points at a missing id — like the H365 "Remarks"
  field) now resolves via a DOM fallback that scores visible, enabled
  inputs/textareas by associated label / placeholder / nearby form-item label
  against the target phrase. Ant-select search inputs and disabled fields are
  excluded. Same proven pattern as the select / click / link / table fallbacks.
- Coverage: `tests/unit/test_input_fallback.py`; validated against the real H365
  Update-Account-Status dialog markup. Engine `0.0.6a16` → `0.0.6a17`; npm
  unchanged.

## @bubblegum-ai/node 0.0.6-alpha.5 — preflight() script validation

- New `bg.preflight(steps[])`: dry-runs each step against the current page and
  returns `{ instruction, ok, status, confidence, resolver, ref, error }[]`
  **without executing anything** — so you can validate a page's steps in one
  batch (`console.table(report)`) instead of discovering failures one run at a
  time. Steps may be strings or `{ instruction, options }`. Nothing executes, so
  call it once per screen with that screen's steps. Engine unchanged
  (`0.0.6a16`); client `0.0.6-alpha.4` → `0.0.6-alpha.5`.

## 0.0.6a16 — fix(web): DOM clickable fallback for ambiguous clicks

- When a click can't be ground to a unique element from the a11y snapshot
  (e.g. Ant renders two equal `role=button` candidates for one labelled button),
  `act` now falls back to a DOM resolver that finds the single interactive
  element by accessible name + role (the quoted text in the step, else the
  target phrase), collapsing nested matches to the outermost interactive
  ancestor. Same proven pattern as the select / link / table-cell fallbacks —
  so `Click the "Update account status" button` resolves across apps instead of
  raising AmbiguousTargetError.
- Coverage: `tests/unit/test_clickable_fallback.py`; logic validated against the
  real H365 button markup. Engine `0.0.6a15` → `0.0.6a16`; npm unchanged.

## 0.0.6a15 — fix(grounding): role-aware tie-break for clicks (button vs text twin)

- A click on a labelled control that wraps a same-text node (e.g. `<button><span>
  Update account status</span></button>`) no longer raises a 0.00-gap
  AmbiguousTargetError. When two candidates tie on confidence, the engine now
  prefers the one whose role best fits the action (button/link/option… over a
  non-interactive text twin) and only reports ambiguity when they're genuinely
  equivalent. Duplicates of the same *specific* ref are collapsed; distinct
  generic role-only refs (e.g. several nameless comboboxes) stay distinct, so
  real ambiguity is still surfaced.
- Coverage: `tests/unit/test_ambiguity_role_tiebreak.py`. Engine `0.0.6a14` →
  `0.0.6a15`; npm client unchanged (`0.0.6-alpha.4`).

## 0.0.6a14 — fix(web): verify checks quoted text inside a descriptive phrase

- `verify` now treats **quoted text as the literal thing to assert**, so a
  natural description works: `verify('the page is shown with an "Update account
  status" button')` checks for `Update account status`, and
  `verify('account status is "Active"')` checks for `Active` — instead of
  failing because the whole sentence isn't literally on the page. Multiple
  quoted phrases must all be visible (`verify('shows "Active" and "Verified"')`).
  Unquoted verifies and an explicit `expected_value` are unchanged.
- Coverage: `tests/unit/test_verify_quoted_text.py`. Engine `0.0.6a13` →
  `0.0.6a14`; npm client unchanged (`0.0.6-alpha.4`).

## 0.0.6a13 — feat(web): click by table cell (column + row) and by link text

- Two new ways to click an element addressed by **what it is**, not its (often
  dynamic) text — e.g. a table link whose label is a UUID:
  - **By table coordinates:** "under the PPHID column, click the 1st row value",
    "Click the PPHID link in the first result row", "click the last row Name",
    or 'in the row where Name is "X", click the PPHID value'. Structured form:
    `act("…", column="PPHID", row="first")` / `row=-1` / `row_match={"Name": x}`.
    Locates the table (Ant `.ant-table`, native `<table>`, ARIA grid), the column
    by header, the row by index (1-based, -1 = last) or by another column's value,
    and clicks the cell's link/button (or the cell).
  - **By link text:** "click the link with text \"<id>\"" or `act("…",
    link_text=id)` — exact → case-insensitive → substring; great for DB-sourced
    ids.
- Node client: `bg.clickInTable({ column, row?|rowMatch?, timeoutMs? })` and
  `bg.clickLink(text, { exact?, timeoutMs? })`.
- Coverage: `tests/unit/test_table_action.py`, Node forwarding tests, and
  `tests/integration/test_table_action_web.py` against the `ant_table` page
  (PPHID cells now contain dynamic-id links). Validated against the real H365
  table markup. Engine `0.0.6a12` → `0.0.6a13`; `@bubblegum-ai/node`
  `0.0.6-alpha.3` → `0.0.6-alpha.4`.

## 0.0.6a12 — fix(web): DOM fallback disambiguates multiple nameless selects

- "Select X from the Y dropdown" now works on pages with **several nameless
  comboboxes** (the case a11 still failed: best 0.57, "15 candidates"). When the
  a11y snapshot can't ground a unique combobox, the SDK falls back to a
  DOM-based resolver that scores every visible select/combobox by its associated
  **label** (strongest), **placeholder**, **currently-displayed value**, and
  text against the step's target phrase and value, then drives the best match.
  This picks the right control whether it's identified by a form label
  ("Participant status", "Reason") or by the value it shows ("search type" →
  the select showing "Participant"). Works across Ant Design / MUI / CDK /
  native `<select>`.
- Coverage: `tests/unit/test_select_trigger_fallback.py` and a new `multi_select`
  widget-lab page + `tests/integration/test_multi_select_web.py`. The scoring was
  validated against the real captured H365 markup.
- Engine `0.0.6a11` → `0.0.6a12`; npm client unchanged (`0.0.6-alpha.3`).

## 0.0.6a11 — fix(grounding): reliably resolve nameless/value-named selects

- A "select X from the Y dropdown" step could flake between resolving (~0.72)
  and failing with `LowConfidence` (~0.57) depending on whether the page exposed
  the combobox as nameless or with its value as the accessible name. The
  grounding engine now, **only for dropdown/select intents**, accepts the best
  `combobox`/`listbox` candidate above the reject threshold (0.50) instead of
  requiring the 0.70 review bar — a custom select legitimately tops out at
  role-fit confidence. It fires for a uniquely-identifiable combobox (named, or
  the single combobox on the page); multiple indistinguishable nameless
  comboboxes still fail safely rather than guessing.
- Clearer `LowConfidenceError` message (no longer hard-codes "reject threshold
  0.50").
- No behaviour change for non-dropdown steps. Coverage:
  `tests/unit/test_dropdown_select_relax.py`. Engine `0.0.6a10` → `0.0.6a11`;
  npm client unchanged (`0.0.6-alpha.3`).

## 0.0.6a10 — feat(web): table assertions (columns + cell values by row)

- New page-scoped **table verification**. `verify` can now assert a data table's
  columns and cell values instead of only checking that text exists somewhere on
  the page — the real automation need ("does column X exist?", "is the value for
  this row, under that column, what the DB says?").
  - **Structured (deterministic):**
    `verify("…", assertion_type="table", columns=[…])` and
    `verify("…", assertion_type="table", row_match={col: val}, cell={col: val})`.
  - **Natural language (AI-style):**
    `verify("the table has columns PPHID, Account Status and Profile Status")`,
    `verify('in the row where Name is "X", Account Status is "Active"')`,
    `verify('the Account Status column shows "Active"')`.
  - Reads native `<table>`, **Ant Design `.ant-table`** (header/body split across
    two inner tables — the exact H365 structure), and ARIA `role=table/grid`.
    Matching is whitespace-normalised, case-insensitive, and tolerates a value
    rendered inside a badge (e.g. a "✓ Active" pill). The assertion polls until
    it holds or the timeout elapses, so it waits out async-loaded rows.
  - Node client: new typed `bg.verifyTable({ columns?, row?, cell?, timeoutMs? })`.
- Coverage: `tests/unit/test_table_assertions.py` (NL parsing, matcher eval,
  verify routing), `tests/integration/test_table_assertions_web.py` against a new
  `ant_table` widget-lab page, and a Node `verifyTable` forwarding test.
- Engine `0.0.6a9` → `0.0.6a10`; `@bubblegum-ai/node` `0.0.6-alpha.2` →
  `0.0.6-alpha.3`.

## 0.0.6a9 — fix(web): match Ant Design option rows directly by class + title/text

- 0.0.6a8 resolved role-less options via the trigger's `aria-controls` listbox,
  but Ant Design's `rc-select` points `aria-controls` at a *separate, off-screen*
  a11y listbox — the **visible**, clickable rows live in the `.ant-select-dropdown`
  popup as `<div class="ant-select-item-option" title="V">` (label in a
  `.ant-select-item-option-content` child). So the option still wasn't found.
  `_do_select` now also matches the visible option **directly** by
  `.ant-select-item-option[title="…"]` / by option-class text, plus a generic
  open-popup (`role=listbox`/`menu`/`.ant-select-dropdown`) text/title match.
  Verified the selector resolves uniquely against the real captured DOM (and
  does not hit the trigger's `.ant-select-selection-item` label).
- Resolution now waits once for the popup to render, then uses `count()` to skip
  non-matching shapes instantly (no per-attempt timeout burn).
- The `ant_select` widget-lab page now mirrors the real structure (portal
  `.ant-select-dropdown` with role-less rows + a separate off-screen
  `aria-controls` listbox). Engine `0.0.6a8` → `0.0.6a9`; npm unchanged.

## 0.0.6a8 — fix(web): resolve role-less combobox options via the owned listbox

- Ant Design's `rc-select` renders option rows as **role-less**
  `<div class="ant-select-item-option" title="…">` inside a virtualized list, so
  the `get_by_role("option")` lookup added in 0.0.6a7 found nothing and `select`
  failed with "could not find a dropdown option …". `_do_select` now falls
  through to the listbox the trigger **owns** (`aria-controls` / `aria-owns`) and
  matches the option by **text, then title** *within that container* — standard
  ARIA, and scoping to the popup keeps the match off the trigger's own selection
  label (which carries the same value text). Standard `role=option`/`menuitem`
  widgets are still matched first.
- The `ant_select` widget-lab page is now role-less to mirror real rc-select;
  unit coverage adds the owned-listbox text and title fallbacks.
- Engine `0.0.6a7` → `0.0.6a8` (PyPI). npm client unchanged (`0.0.6-alpha.2`).

## 0.0.6a7 — fix(web): force-open Ant Design-style comboboxes (overlay interception)

- The custom-combobox `select` (0.0.6a6) opened the trigger with a normal click,
  which Ant Design (and similar widgets) break: the inner `role="combobox"`
  `<input>` is covered by a `.ant-select-selection-item` `<span>` that intercepts
  the click (Playwright: "`<span>` intercepts pointer events"), so opening timed
  out. `PlaywrightAdapter._do_select` now **force-clicks the trigger open when a
  normal click is intercepted** (a short normal-click probe runs first, so
  plain-clickable `<button>`/`<div>` comboboxes keep their full actionability
  checks).
- New `ant_select` widget-lab page reproduces the overlay structure (inner
  `role=combobox` input under a selection span, current value also an option).
  Coverage: unit `test_custom_combobox_force_opens_when_overlay_intercepts` and
  the `--playwright` integration `test_one_step_select_from_ant_style_overlay_combobox`.
- Engine `0.0.6a6` → `0.0.6a7` (PyPI). npm client unchanged (`0.0.6-alpha.2`).

## 0.0.6a6 — feat(web): one-step selection from custom (non-native) comboboxes

- Engine `0.0.6a5` → `0.0.6a6` (PyPI `bubblegum-ai`). Upgrade with
  `pip install -U "bubblegum-ai==0.0.6a6"`.
- `@bubblegum-ai/node` `0.0.6-alpha.1` → `0.0.6-alpha.2` (npm): **version-parity
  bump only — no client code change.** The feature is entirely engine-side; the
  existing client already forwards the natural-language step. The `alpha.1`
  client also works against engine `0.0.6a6`.

- **`select` now drives div/button-based comboboxes**, not just native
  `<select>`. Ant Design / MUI / Angular CDK / React-Select render
  `role="combobox"` triggers whose options live in a portal listbox;
  `locator.select_option()` can't drive these. `PlaywrightAdapter._do_select`
  now detects the trigger is not a `<select>` (by tag name — both surface as
  `role=combobox` in the a11y tree) and instead **opens the trigger, then clicks
  the matching `role="option"`/`role="menuitem"`**. The native `<select>` path
  is unchanged.
- This lets testers select from custom dropdowns with a single plain-English
  line and **no DOM selectors** — e.g. `Select "Participant" from the search
  type dropdown`. Searching options by accessible name also resolves the common
  ambiguity where the trigger displays the selected value and an option carries
  the same text (the option is targeted explicitly). The existing two-step flow
  (`Open the X dropdown` + `Click <option>`) keeps working.
- Coverage: `tests/unit/test_custom_combobox_select.py` (dispatch: native vs.
  custom, exact→non-exact option fallback, clear error on no match) and
  `tests/integration/test_custom_combobox_select_web.py` (live `--playwright`
  flow against the `combobox` / `nameless_combobox` / `select` widget-lab pages).

## 0.0.6a5 — fix: report.write over the bridge

- Fixed `report.write` (Node-client reporting) crashing with
  `TypeError: 'method' object is not iterable`. `BubblegumSession.results` is a
  **method**, but the bridge handler used it as a property and passed the bound
  method to the reporters. Now normalized (calls it when callable). The unit-test
  fake modelled `results` as a property, which hid the bug — it now mirrors the
  real method shape so the regression is covered.
- Engine `0.0.6a4` → `0.0.6a5`. Node client unchanged (`bg.report(...)` is fixed
  purely engine-side; upgrade with `pip install -U "bubblegum-ai==0.0.6a5"`).

## Release: engine 0.0.6a4 + @bubblegum-ai/node 0.0.6-alpha.1

- Engine `0.0.6a3` → `0.0.6a4` (PyPI): ships the `report.write` bridge
  capability, dynamic-value tokens, and trailing-context stripping.
- Client `@bubblegum-ai/node` `0.0.6-alpha.0` → `0.0.6-alpha.1` (npm): ships
  `bg.report(...)` and the dual ESM/CommonJS build.
- Release order matters: publish the **engine first** (the client's `report()`
  capability-checks for `report.write` and throws against an older engine).

## Node client: reports + dual ESM/CommonJS build

- **Reports from the Node client.** New `report.write` bridge method (capability
  `report.write`) writes Allure / HTML / JSON / JUnit from the session's
  accumulated `StepResult`s, reusing the same writers as the pytest plugin — so a
  Node-driven run gets identical reports without pytest. Exposed as
  `bg.report({ html, allure, junit, json, title, suiteName })` →
  `{ written, steps }`; each format optional (`true` = default name). Engine
  coverage in `tests/unit/test_bridge.py`; client coverage in
  `clients/node/test/client.test.mjs`.
- **Dual ESM + CommonJS build** for `@bubblegum-ai/node`. `tsc` now emits ESM to
  `dist/esm` and CommonJS to `dist/cjs` (with per-dir `package.json` `type`
  markers); the package `exports` map routes `import` and `require` accordingly.
  Consumers on CommonJS runners (e.g. Jest's default runtime) can `require(...)`
  without the `.mts` rename or loader flags; ESM `import` is unchanged. CJS load
  smoke-tested in `clients/node/test/cjs-require.test.cjs`.

## Parameterised values + target-isolation polish + one-click PyPI

- **Dynamic-value tokens** (parameterised dates/times). Any step value may now
  contain a `{{ ... }}` token that expands at run time, so a date picker can be
  fed a *relative* date instead of a literal that goes stale:
  `act('Enter "{{today+7d|%d/%m/%Y}}" into Start date')`,
  `act('Enter "{{now+2h|%d/%m/%Y %H:%M}}" into Appointment')`. Bases `today` /
  `now` / `tomorrow` / `yesterday`; chainable signed offsets `+7d -3d +2w +1mo
  -1y +2h +30min +45s`; optional `|strftime` format (defaults `%Y-%m-%d` and
  `%Y-%m-%d %H:%M`). Token-free and unrecognised values pass through untouched.
  Substitution runs in `_decompose_for` so it covers every channel and both the
  Python SDK and the Node client over the bridge. New module
  `bubblegum/core/parser/dynamic_value.py`; coverage in
  `tests/unit/test_dynamic_value_tokens.py`.
- **Trailing positional-context stripping.** Target isolation now drops a
  trailing "where on the page" tail so it stops diluting text matching:
  `Click the Save button on the Challenges page` → `Save`, `Click the Customer
  Care menu in the top navigation bar` → `Customer Care menu`. Deliberately
  narrow — requires a preposition + article + page-region noun (`page`,
  `screen`, `header`, `footer`, `nav(igation) bar`, `toolbar`, `sidebar`,
  `banner`, …), so bare region names and meaningful relational scopes
  (`in the confirmation modal`, `from the country dropdown`) are untouched.
  Coverage in `tests/unit/test_trailing_context_strip.py`.
- **One-click PyPI publish.** `publish.yml` now takes a `publish` boolean on
  `workflow_dispatch` (mirroring `npm-publish.yml`): unchecked = dry-run to
  TestPyPI, checked = real release to PyPI from the Actions UI — no tag, no
  stale-commit risk. The existing `v*` tag-push path is unchanged.

## 0.0.6a3 — hover role-fit (no more button-vs-span ambiguity)

- The `hover` action now shares the interactive-role preference of `click`/`tap`
  in `role_fit_score`, so hovering an antd `ant-dropdown-trigger` `<button>`
  cleanly outranks its inner text `<span>` instead of tying into an
  `AmbiguousTargetError` (top-2 within the 0.05 gap). Coverage added in
  `tests/unit/test_hover_action.py`.
- Version bump `0.0.6a2` → `0.0.6a3`.

## Engine 0.0.6a2 — CDP attach + hover on PyPI

- Bumped `0.0.6a1` → `0.0.6a2` so the first published build containing **both**
  CDP attach and the new `hover` action gets a distinct version — a clean
  `pip install -U bubblegum-ai` (avoids colliding with the interim `0.0.6a1`
  installed straight from git).

## Web: native `hover` action (reveal hover-triggered menus)

- Added a first-class `hover` web action so hover-revealed dropdowns/menus no
  longer need a raw-Playwright fallback. `act("Hover over the Create menu")` (or
  `act('Hover "+ Create a challenge"', { action_type: "hover" })`) resolves the
  element and dispatches `locator.hover()`.
- Parser maps the `hover` verb (and the natural "hover over X" phrasing) to
  `action_type="hover"`; added to the `ActionPlan` schema and the web adapter
  dispatch table. Click/tap/etc. target extraction is unchanged.
- Coverage: `tests/unit/test_hover_action.py`. Mobile/other channels unchanged.

## Engine 0.0.6a1 — ship CDP attach to PyPI

- Bumped the engine `0.0.6a0` → `0.0.6a1`. The PyPI `0.0.6a0` build predated the
  CDP-attach feature (`channel.web.cdp`, PR #226), so `@bubblegum-ai/node`'s
  `attach()` correctly refused against it (`BridgeError -32003 ... upgrade
  bubblegum-ai`). `0.0.6a1` is the first PyPI engine that advertises
  `channel.web.cdp`, realigning the published engine with the npm client.
- No code changes beyond the version bump — CDP support already merged on `main`.

## npm: one-click publish + Node client demo examples

- `npm-publish.yml` now supports a **one-click "publish for real"**: a manual
  `workflow_dispatch` run with the `publish` box checked publishes from `main`
  (no tag, no stale-commit risk); unchecked stays a dry run. Tag-push
  (`node-v*`) publishing is unchanged. `docs/publishing.md` documents both paths.
- Added `clients/node/examples/` — copy-paste demos: `demo-engine-owned.mjs`
  (quickest try; the engine launches its own browser) and `login.spec.ts`
  (`@playwright/test` + CDP attach, driving the test's own browser), plus a
  README with prerequisites and troubleshooting. Examples are repo-only (not
  shipped in the npm tarball).

## Docs + CI: TypeScript/JS how-to guide and npm publish workflow

- Added `docs/HOW_TO_USE_TYPESCRIPT.md` — a tester-facing copy-paste guide for
  driving Bubblegum from JS/TS via `@bubblegum-ai/node`: prerequisites (Python
  engine + Node), install, the four primitives, `StepResult`, per-call options,
  CDP attach (client-owned browser), a `@playwright/test` fixture pattern,
  mobile, error handling, versioning, and troubleshooting. Linked from the README
  and the Web how-to guide.
- Added `.github/workflows/npm-publish.yml` — publishes `@bubblegum-ai/node` to
  npm: manual dispatch does `npm publish --dry-run`; a pushed `node-v*` tag does a
  real `npm publish --provenance`. Uses a separate `node-v*` tag namespace so it
  never collides with the Python `v*` releases, and a normal merge never
  publishes. `docs/publishing.md` documents the one-time npm org/scope + token
  setup and the release runbook.

## Client-owned browser: CDP attach (0.3.0 slice)

- The bridge can now attach the engine to a **caller-owned Chromium over CDP**
  instead of launching its own, so a TS/JS Playwright test and the engine share
  one browser. `session.open` gains `cdp_endpoint` (e.g. `http://localhost:9222`)
  and `page_index`; the engine connects via `connect_over_cdp`, resolves against
  an existing page, and on close only **disconnects** — it never creates or
  closes the caller's browser/page.
- Advertised as a new capability `channel.web.cdp` (additive — `PROTOCOL_VERSION`
  stays `1`; older clients are unaffected). `select_cdp_page` flattens pages
  across contexts and raises clear errors for an empty endpoint / out-of-range
  index. Coverage: `tests/unit/test_bridge_cdp.py` (fake browser, no real CDP).
- `@bubblegum-ai/node`: new `Bubblegum.attach({ cdpEndpoint, pageIndex? })` (and
  `cdpEndpoint`/`pageIndex` on `launch`) that feature-detects `channel.web.cdp`
  and throws a clear error against an engine too old to support it. Client tests
  cover the present/absent-capability paths.
- Docs: `docs/bridge-protocol.md` (cdp params + capability) and the client README
  (CDP attach example) updated.

## npm client scaffold: @bubblegum-ai/node (0.2.0 slice)

- Added `clients/node/` — a Node/TypeScript client (`@bubblegum-ai/node`) that
  drives the engine from JS/TS by spawning `python -m bubblegum.bridge` and
  speaking its JSON-RPC protocol. No grounding logic is re-implemented in TS; the
  Python engine stays the single source of truth (per
  `docs/distribution-npm-and-pypi.md`).
- `Bubblegum.launch()` spawns the bridge, negotiates via `handshake` (refuses an
  unsupported `protocol_version`), and opens an engine-owned session; `act` /
  `verify` / `extract` / `recover` / state probes / `explain` / `summary` /
  `close` proxy 1:1 to the bridge and return the same `StepResult` shape as the
  Python SDK. Typed mirrors of the protocol + schemas live in `src/protocol.ts`
  and `src/types.ts`.
- Lower-level `BridgeClient` with an injectable `Transport` (default spawns the
  Python process); 8 browser/Python-free tests drive the full client/session over
  a mock transport (`test/client.test.mjs`). Verified end-to-end against the real
  bridge (handshake) too.
- Added `.github/workflows/node-client.yml` (type-check + build + test, scoped to
  `clients/node/**`). Client README documents prerequisites, the API, versioning,
  and the not-yet-built client-owned (CDP-attach) browser model.

## Post-release: v0.0.6-alpha published + publish-workflow hardening

- `bubblegum-ai 0.0.6a0` is **published to PyPI** (first PyPI release), via the
  tag-push (`v0.0.6-alpha`) run of the Trusted-Publishing workflow.
- Hardened `.github/workflows/publish.yml` with `skip-existing: true` on both the
  TestPyPI and PyPI publish steps, so re-running a build for an already-uploaded
  version is a no-op success instead of a hard `400 File already exists` (which is
  what a repeat manual TestPyPI dry run hit — harmless, but noisy/red).
- Flipped the README "latest release" badge `v0.0.5-alpha` → `v0.0.6-alpha`.
- Synced `RELEASE_CHECKLIST.md` to `0.0.6a0` / `v0.0.6-alpha` and updated the
  "publishing deferred" notes — PyPI publishing is now enabled (see
  `docs/publishing.md`).

## CI: PyPI publish workflow (Trusted Publishing / OIDC)

- Added `.github/workflows/publish.yml` — publishes the built distribution via
  **PyPI Trusted Publishing** (OIDC), so no API tokens are stored as repo
  secrets. A `build` job runs the strict release gates (`validate_package.py`
  default + `--strict`, metadata tests, `python -m build`, `twine check`); a
  manual run uploads to **TestPyPI** (dry run) and a pushed `v*` tag uploads to
  **PyPI**. A normal merge never publishes — only a tag push does.
- Added `docs/publishing.md` — the one-time maintainer setup (exact pending
  trusted-publisher values for TestPyPI/PyPI + the `testpypi`/`pypi`
  environments) and the dry-run → tag-release → verify runbook.

## Release prep: bump to 0.0.6a0 + correct repository URLs

- Bumped the package version `0.0.5a0` → `0.0.6a0` (`pyproject.toml`,
  `bubblegum.__version__`, and the `test_package_metadata` assertion) to open the
  `v0.0.6-alpha` pre-release line — the first version targeting PyPI publish and
  the npm client per `docs/distribution-npm-and-pypi.md`.
- Corrected the repository URLs from the placeholder `bubblegum-ai/bubblegum`
  org to the actual `bishnu133/bubblegum` repo, in the `pyproject.toml`
  `[project.urls]` metadata (Homepage/Repository/Issues) and the README badges,
  so published package metadata links resolve.
- The README "latest release" badge still points at `v0.0.5-alpha` — it is
  updated when the `v0.0.6-alpha` GitHub release is actually cut.

## Bridge: drive the engine over JSON-RPC (npm/non-Python clients)

- Added `bubblegum.bridge` — a **JSON-RPC 2.0** server that exposes the engine to
  non-Python clients (the foundation for the planned `@bubblegum-ai/node` npm
  package; see `docs/distribution-npm-and-pypi.md`). Newline-delimited, one
  request per line, served over stdio via the new `bubblegum bridge` command
  (and `python -m bubblegum.bridge`).
- Methods mirror the SDK 1:1: `handshake` (version/capability negotiation),
  `session.open`/`session.close` (engine-owned Playwright/Appium sessions keyed
  by id), `act`/`verify`/`extract`/`recover`, `explain`, the state probes
  (`is_visible`/`is_checked`/`selected_value`), `summary`, and
  `configure_runtime`. Primitive results are the existing `StepResult`
  serialized as JSON, so the wire shape matches the Python SDK exactly.
- `PROTOCOL_VERSION = 1`, advertised with a capability list, so future
  enhancements ship **additively** (newer engine keeps serving older clients).
- Handlers are a thin adapter over `BubblegumSession`/`bubblegum.core.sdk` — no
  grounding logic is duplicated. Session construction goes through an injectable
  factory, so the protocol/dispatch/handlers are unit-tested with no browser or
  device (`tests/unit/test_bridge.py`, 14 tests). Reference: `docs/bridge-protocol.md`.
- Additive only: no changes to existing SDK/schema/public API.

## Documentation: split how-to guides + npm/PyPI distribution strategy

- Added `docs/HOW_TO_USE_WEB.md` and `docs/HOW_TO_USE_MOBILE.md` — two focused,
  self-contained, copy-paste how-to guides (split out of the combined
  `USER_GUIDE.md`) so web (Playwright) and mobile (Appium) adopters each get a
  channel-specific reference: install, the four primitives, `BubblegumSession`,
  the NL grammar, every action type, verify/extract, channel-specific features
  (web: iframes/nav-wait/a11y/network asserts; mobile: system dialogs, WebView
  switching, network conditions, device cloud), self-healing, pytest, and the
  full config reference.
- Added `docs/distribution-npm-and-pypi.md` — design/strategy for shipping
  Bubblegum on **both PyPI and npm**. Recommends a single Python engine exposed
  over a thin JSON-RPC **bridge** with a typed Node/TypeScript client
  (`@bubblegum-ai/node`), rather than a second TS engine. Covers the bridge
  module + `bubblegum bridge` CLI, engine-owned vs client-owned (CDP attach)
  browser models, a SemVer + `PROTOCOL_VERSION` (additive-first, capability-
  negotiated) versioning scheme so newer engines keep serving older clients, a
  forward-looking release ladder to a `1.0.0` stable contract, and dual-publish
  CI mechanics. Design-only — no engine code changes.
- README now links the two how-to guides and the distribution strategy.

## Documentation: end-to-end user guide

- Added `docs/USER_GUIDE.md` — a single, example-driven reference covering every
  Bubblegum capability with **separate Web and Mobile sections**: the four
  primitives, `BubblegumSession`, the natural-language grammar, all action types,
  iframes, nav-wait, select-by-label, state probes, dialogs/scopes, re-grounding,
  `recover()`, self-healing, memory cache, vision/OCR, BDD, the pytest plugin,
  and the full config reference. Intended as the copy-paste starting point for
  teams adopting Bubblegum in their automation.

## Web reliability: iframes, bounded nav-wait, select-by-label, strict-mode + re-grounding

Five web-channel improvements to the Playwright adapter and SDK resolution loop:

- **iframe support.** `collect_context()` now merges child-frame accessibility
  snapshots, so elements inside same-origin `<iframe>`s are discoverable by the
  resolvers. Execution and text extraction route into the owning frame
  (`_resolve_action_locator`). Gated by `ContextRequest.include_frames`
  (default on); a no-op for frameless pages.
- **Bounded, configurable post-click navigation wait.** A non-navigating
  (AJAX/SPA) click previously burned a fixed 5 s on the `wait_for_url` probe.
  It is now two-phase — cheaply detect whether a navigation commits within
  `ExecutionOptions.nav_wait_ms` (default 1 s), and only then wait for the new
  document to settle using the full action timeout. Set `nav_wait_ms=0` to skip.
- **`<select>` by visible label.** `select` now tries the option value, then
  falls back to the visible label, so `Select "United States" from Country`
  works even when the option value differs (`value="US"`).
- **Strict-mode retry.** An action whose ref matches more than one DOM node
  retries on `.first` (mirroring the read path) instead of failing the step.
- **Re-grounding for late-rendered elements.** `act()/verify()/extract()`
  re-collect context and retry resolution (`grounding.resolve_retries`,
  default 2 × `resolve_retry_interval_ms` 300 ms) when the first attempt finds
  nothing, so SPA elements that render a beat late resolve instead of failing.

Web text extraction now delegates to `PlaywrightAdapter.extract_text()` (parity
with the mobile channel). New fixtures: `widget_lab/iframe.html` +
`iframe_inner.html`. Coverage: `tests/unit/test_web_resilience.py` (browser-free)
and `tests/integration/test_phase22e10_web_resilience_e2e.py` (live, `--playwright`).

## Self-healing advisory survives memory-cache replays

- A self-healing substitution (e.g. a step written for "login" that resolves to
  "Sign In") was flagged on the first run but went silent on every subsequent
  run, because the step then replayed from the memory cache (`memory_cache`
  resolver) rather than `fuzzy_text`. The advisory is now built **before** the
  resolution is persisted, so it is stored in the cached metadata and
  re-surfaced on replay (tagged `replayed_from_cache`). A replayed healed step
  stays `recovered` instead of being silently downgraded to `passed`.
  Coverage: `tests/unit/test_self_healing_advisory.py`.

## Vision tier validation on deterministic-hard targets

- Added `tests/unit/test_vision_deterministic_hard.py`: proves the AI (vision)
  tier wins grounding on an icon/image control with **no** accessible name (where
  the text/role resolvers cannot match), that it does **not** displace a clean
  deterministic match, and that the same target fails to resolve when vision is
  unavailable or cost-blocked. No API key required (candidates are injected
  exactly as the screenshot→provider pipeline injects them).
- Note: web *execution* of a vision win still relies on the deterministic
  hydrator mapping the candidate to a role/text ref — coordinate (bbox) clicking
  for truly nameless controls remains a future enhancement.

## Mobile re-grounding parity

- The SDK re-grounding loop is channel-agnostic, so the late-render retry now
  benefits mobile too. Coverage: `tests/unit/test_mobile_reground.py` (fake
  Appium adapter; full on-device e2e runs via the env-gated
  `tests/real_env/android|ios` suites).

## BDD step library + nameless-combobox fallback

- Added `bubblegum.bdd`: plain-English Given/When/Then on top of the NL engine
  for manual-QA personas. Core is a framework-agnostic dispatcher
  (`execute_step`); `bubblegum.bdd.steps` ships catch-all pytest-bdd When/Then
  bindings (optional extra `bdd` = `pytest-bdd>=7`). Runnable example under
  `examples/web/bdd/`.
- Nameless-combobox resolver fallback: a `role="combobox"` trigger with no
  accessible name (MUI / Angular CDK overlays) now resolves by role + uniqueness
  when the step signals a dropdown, instead of failing below the review band.

## Packaging: bundle quickstart sample pages (v0.0.5a)

- The `widget_lab` and `sample_app` quickstart pages now ship **inside** the
  package (`bubblegum/testing/pages/`), so `pip install bubblegum-ai` users get
  the fixtures without a repository checkout. `find_pages_dir()` resolves a repo
  checkout first (dev) and falls back to the bundled copies (pip install).
- Added `[tool.setuptools.package-data]` so the HTML pages are included in the
  wheel, and a drift guard (`tests/unit/test_packaged_sample_pages.py`) that
  keeps the bundled copies byte-for-byte in sync with the example sources.

## CI + self-healing + AI-first object recognition

- CI now runs the full unit suite on every PR (`.[test,anthropic]`); fixed the
  17 stale baseline test failures so the gate is meaningful.
- Self-healing is no longer silent: a fuzzy/synonym substitution (e.g. a step
  written for "login" that resolves to "Sign In") marks the step `recovered`,
  attaches a `healing` advisory, and is highlighted in the HTML/JSON reports as
  a possible defect to revisit.
- Added an Anthropic (Claude) vision backend for element grounding from
  screenshots and an opt-in `grounding.ai_first` strategy that runs the AI tier
  before the deterministic tiers (cost-gated, with deterministic fallback).

## Phase 19G-E1 (release checklist baseline sync)

- Phase 19G-E1 docs/checklist-only cleanup: updated `RELEASE_CHECKLIST.md` collect-only baseline references from 643 to 654 to match the current mainline pytest collection baseline. No runtime/parser/planner/schema/resolver/ranker/confidence/API/dependency/version changes.

## Phase 19F-F (Object Intelligence static summary/reporting MVP)

- Added compact static summary/reporting for Object Intelligence seed fixtures when selected via
  `python scripts/run_benchmarks.py --cases tests/benchmarks/object_intelligence/seed_cases.json`.
- Summary includes deterministic counts for total cases, channel, category, positive vs negative,
  failure modes, baseline expectations, expected graph-signal true counts, relation types, and tags.
- Execution remains intentionally unsupported for object seed fixture shape under `--execute`, with
  clear nonzero operator message unchanged.
- Default regression benchmark behavior remains unchanged when `--cases` is omitted.

## Phase 19F-D (minimal benchmark runner case-path selection)

- Added non-breaking optional benchmark runner case selection via
  `python scripts/run_benchmarks.py --cases <path>`.
- Default behavior remains unchanged: omitting `--cases` still runs regression fixtures from
  `tests/benchmarks/fixtures/cases.json` with existing static/execute behavior.
- Added safe validation-only support for non-regression fixture shapes (including Object
  Intelligence seed fixture format with top-level `{"cases": [...]}`); these can be loaded in
  static mode and report a clear unsupported message in `--execute` mode.
- Added unit coverage for explicit default fixture path parity, object seed opt-in validation path,
  non-supported execute path behavior, and clear invalid-path failure.

## Phase 19F-B (Object Intelligence benchmark seed fixtures MVP)

- Added Object Intelligence seed spec doc at
  `docs/phase-19f-object-intelligence-seed-spec.md`.
- Added separate Object Intelligence seed fixtures at
  `tests/benchmarks/object_intelligence/seed_cases.json`.
- Added dedicated Object Intelligence seed schema at
  `tests/benchmarks/object_intelligence/schema.json`.
- Added unit validation for seed/schema shape and safety checks at
  `tests/unit/test_object_intelligence_seed_schema.py`.
- Scope is docs/fixtures/schema-validation only; no runner runtime logic, scoring,
  resolver priority, or engine behavior changes in this phase.

# Changelog

- Phase 19E-B metadata-only graph diagnostics MVP: added internal `graph_signals` helper to compute compact, deterministic, JSON-safe graph-context diagnostics (`label_for_match`, `same_row_match`, `same_container_match`, `nearby_label_match`, `role_match_with_graph_context`, `unique_in_scope`, `visible_enabled_match`) and emitted these under `metadata["graph_signals"]` in AccessibilityTreeResolver and AppiumHierarchyResolver candidates. No engine/ranker/confidence/threshold changes, no resolver priority/order changes, no SDK/API/schema/dependency/version changes, and no adapter runtime behavior changes.
- Phase 19E-D graph signal reporting/analytics MVP: report surfaces now preserve sanitized `metadata["graph_signals"]` in JSON output, redact unsafe graph diagnostic payload keys, render an optional compact per-step “Graph Signals” section in HTML reports, and add aggregate `graph_signal_summary` analytics (`total_events`, `presence_counts`, `reason_counts`, `field_true_counts`). Reporting-only scope; no scoring/ranker/confidence/engine/resolver/API/schema/dependency/version changes.

All notable changes to this project will be documented in this file.

## Unreleased
- Phase 19G-O object seed diagnostic runner MVP: added opt-in metadata-only script `scripts/run_object_seed_diagnostics.py` that loads object seed cases + synthetic element sidecar, parses relational intent via existing parser helper, builds `NormalizedElement`/`ElementGraph`, runs `build_graph_query_diagnostics(...)`, and emits compact summary counts with optional compact JSON artifact output. Added synthetic sidecar fixture `tests/benchmarks/object_intelligence/synthetic_elements.json` and focused unit coverage in `tests/unit/test_phase19g_object_seed_diagnostics_runner.py`. No action execution, no resolver/ranker/scoring/filtering/runtime targeting changes, no default benchmark behavior changes, no SDK/API/schema/dependency/version changes.
- Phase 19G-L graph query diagnostics reporting/analytics support: JSON reports now preserve sanitized `metadata["graph_query_diagnostics"]` (safe compact keys only), HTML reports render optional escaped "Graph Query Diagnostics" step sections only when present, and reporting analytics include compact `graph_query_summary` aggregates (`total_events`, `status_counts`, `relation_type_counts`, `ambiguity_count`, `reason_counts`, `matched_id_total`) derived from sanitized diagnostics only. Reporting-only scope; no resolver/query/parser/planner/schema/ranker/confidence/engine/API/dependency/version changes.
- Phase 19G-K resolver metadata-only graph query diagnostics integration: AccessibilityTreeResolver and AppiumHierarchyResolver now attach internal `metadata["graph_query_diagnostics"]` when both relational intent and an ElementGraph context (`element_graph` or `graph`) are available. Diagnostics are produced by existing `build_graph_query_diagnostics(...)` and remain metadata-only (no candidate filtering, no scoring/confidence changes, no resolver priority/order changes, no engine/parser/planner/schema/API/dependency/version changes).
- Phase 19G-I metadata-only graph query diagnostics MVP: added internal `build_graph_query_diagnostics(...)` in `bubblegum/core/elements/query.py` to map `relational_intent` into deterministic, compact, JSON-safe graph-query diagnostics (`status`, `relation_type`, `anchor_resolution`, `scope_resolution`, `matched_ids`, `excluded_ids`, `ambiguity`, `reasons`) across `label_for`, `same_row_as_text`, `within_card`, `within_modal`, `within_region`, and `mobile_attr_hint`. Diagnostics-only scope: no runtime candidate filtering/selection, no engine/resolver/ranker/confidence changes, no parser/planner/schema/API/dependency/version changes.
- Phase 19G-G graph query planner design/spec added (`docs/phase-19g-graph-query-planner-design.md`): defines deterministic `relational_intent`→ElementGraph diagnostics mapping, fail-closed ambiguity/status model, container-detection heuristics, JSON-safe diagnostics contract, and phased integration path (diagnostics-first; runtime filtering/scoring deferred). Docs-only; no runtime/parser/planner/schema/resolver/ranker/engine/API/dependency/version changes.
- Phase 19G-E1 docs/checklist baseline sync: updated `RELEASE_CHECKLIST.md` collect-only baseline references from 643 to 654 to match current mainline test collection. Docs/checklist-only change; no runtime/parser/planner/schema/resolver/ranker/API/dependency/version changes.
- Phase 19G-D parser relational metadata MVP: added internal rule-based `parse_relational_intent(...)` helper for safe relational hints (`for <anchor>`, modal scope phrases, dropdown scope phrases, checkbox label phrases) and metadata-only planner propagation into `StepIntent.context["relational_intent"]` when matched. No resolver/engine/ranker/confidence/schema/API/dependency/version changes; no runtime targeting behavior changes.

- Phase 19G-B relational intent contract design/spec added (`docs/phase-19g-relational-intent-design.md`): defines schema-stable `StepIntent.context["relational_intent"]` metadata proposal, initial relation taxonomy (`label_for`, `same_row_as_text`, `within_card`, `within_modal`, `within_region`, `mobile_attr_hint`), conservative parser principles, backward-compat strategy, pre-implementation test gates, and phased follow-on plan. Design-only: no parser/planner/runtime/ranker/schema/API/dependency/version changes.

- Phase 19C Normalized Cross-platform Element Model MVP added internal-only normalized element contracts in `bubblegum/core/elements/normalized.py` (`NormalizedElement`, `NormalizedBounds`) plus deterministic web/mobile normalization helpers and JSON-safe serialization. Added focused unit coverage for defaults, serialization safety, web/mobile mapping, bounds parsing/clamping, and parent/child linkage. No runtime resolver/ranker/adapter behavior changes, no SDK public API changes, no dependency/version changes.

- Phase 19B Object Intelligence Benchmark and Regression Design docs added (`docs/phase-19b-object-intelligence-benchmark.md`), explicitly separating capability benchmarking from regression protection. Defines benchmark taxonomy (web/mobile), baseline comparison strategy (raw Playwright, raw vision/LLM grounding, current Bubblegum pipeline), required metrics/failure taxonomy, ground-truth case format, fixture scale targets, mobile-specific design track (FrameworkDetector/WebView/SystemDialog/IconLibrary/screen signatures), roadmap reorder through 19M, and explicit deferrals (no multilingual claim yet, no full device-cloud matrix, no Selenium adapter in this phase). Docs/design-only scope; no runtime/API/schema/dependency/version changes.

- Phase 15H wait observability metadata/reporting MVP: adapter execute paths now emit safe wait metadata on existing `StepResult.target.metadata` (`wait_used`, `wait_mode`, `wait_outcome`, `wait_adapter`, optional `wait_duration_ms`) only when `wait_for` is configured. JSON/HTML reporting preserves and safely renders wait metadata while redacting unsafe wait diagnostics fields. Observability-only scope; no wait behavior/retry behavior/schema/public-API/dependency/version changes.

- Phase 15F adapter-level explicit wait_for MVP: execute-path adapters now consume existing `ExecutionOptions.wait_for` + `timeout_ms` without schema/API changes. Playwright supports `visible`/`attached`/`enabled` pre-action waits; Appium supports `present`/`visible` pre-action waits with timeout-bounded visibility polling. Defaults remain backward-compatible when `wait_for` is `None`; retry cap/classification/metadata behavior unchanged. Added focused mock-based unit tests for wait modes, unsupported-mode failure clarity, and retry-with-wait behavior.
- Phase 15D retry observability metadata/reporting MVP: adapter execute paths now surface safe retry metadata on existing `StepResult.target.metadata` fields (`retry_attempts`, `retry_transient`, `retry_reason`, `retry_adapter`) for Playwright/Appium execution outcomes. JSON/HTML reporting preserves and safely renders retry metadata while redacting unsafe retry diagnostics fields. Observability-only scope; no retry behavior change, no schema/public-API/dependency/version changes.
- Phase 15B adapter-level transient retry/wait MVP: added conservative execute-only transient retry helpers in Playwright and Appium adapters (retry budget capped to 1, transient-message classification only, no resolver/grounding/provider retries). Added focused unit tests for transient/pass, permanent/fail, and retry-budget behavior. No public API/schema/dependency/version changes.
- Phase 14E docs/examples polish pass: added explicit run commands for key local examples, clarified direct-NL adoption wording around config/cost/provider/privacy-gated fallback behavior, and documented reserved pytest plugin flags (`--bubblegum-ai`, `--bubblegum-memory`). Docs/examples-only scope with no runtime/API/dependency/version changes.
- Phase 14C adoption/examples smoke-kit docs MVP added: `docs/adoption.md`, `docs/pytest-plugin.md`, `docs/ci.md`, plus new examples `examples/web_nl_quickstart.py`, `examples/ocr_callable_hydration_example.py`, and `examples/report_artifacts_example.py`. Updated `README.md`, `examples/README.md`, and `RELEASE_CHECKLIST.md` with adoption links and verification commands. Docs/examples-only scope with no runtime/API/dependency/version changes.

- Phase 19D UI Element Graph MVP added internal `ElementGraph` over `NormalizedElement` (`bubblegum/core/elements/graph.py`) with deterministic parent/child/sibling/nearby/label_for/same_row/same_container relationships and safe query helpers (`get_element`, `children_of`, `parent_of`, `siblings_of`, `nearby`, `labels_for`, `controls_for_label`, `elements_with_text`, `elements_by_role`) plus JSON-safe summary export. Added unit coverage for graph construction, deterministic relations, lookup helpers, unknown-id safety, and serialization safety. No resolver/ranker/adapter runtime integration, no SDK public API changes, no dependency/version changes.

## v0.0.5-alpha
- Release scope finalized for GitHub pre-release `v0.0.5-alpha` with package version `0.0.5a0` (PEP 440).
- Scope includes:
  - Phase 17A roadmap reset and `v0.0.5-alpha` planning
  - Phase 17B real smoke kit/adoption readiness audit
  - Phase 17C real smoke kit docs/examples MVP
  - Phase 17D smoke runner audit
  - Phase 17E dependency-free infra-free smoke runner MVP
  - Phase 17F smoke runner post-merge verification
  - Phase 17G release checklist collect-only baseline sync to 615
  - Phase 18B release metadata/docs/checklist preparation
- No runtime behavior changes.
- No SDK public API changes.
- No schema changes.
- No dependency changes.
- No provider/network/browser/device CI smoke added.
- PyPI/TestPyPI publishing remains deferred; release target remains GitHub pre-release only.

## v0.0.4-alpha
- Release scope finalized for GitHub pre-release `v0.0.4-alpha` with package version `0.0.4a0` (PEP 440).
- Scope includes:
  - Phase 14 adoption docs/examples polish
  - Phase 15B adapter-level transient retry MVP
  - Phase 15D retry observability metadata/reporting
  - Phase 15F adapter-level explicit `wait_for` MVP
  - Phase 15H wait observability metadata/reporting
- No SDK public API changes.
- No schema changes.
- No dependency changes.
- No provider/LLM/OCR/vision retry behavior changes.
- PyPI/TestPyPI publishing remains deferred; release target remains GitHub pre-release only.

## v0.0.3-alpha
- Release scope finalized for GitHub pre-release `v0.0.3-alpha` with package version `0.0.3a0` (PEP 440).
- Phase 13 feature track included: VisualRefHydrator safe boundary/fail-safe behavior, deterministic web hydration (OCR/vision metadata), deterministic mobile hydration (`hierarchy_xml` text/content-desc/resource-id), sanitized SDK hydration diagnostics, JSON/HTML hydration diagnostics reporting, and hydration analytics summary.
- Publish-check hygiene from Phase 13C/13E retained for clean artifact verification (`rm -rf dist build *.egg-info` before `python -m build`).
- No runtime behavior changes, no public API breaking changes, no dependency changes in this release-prep slice.
- PyPI/TestPyPI publishing remains deferred; release target remains GitHub pre-release only.

- Phase 13Q hydration diagnostics analytics summary MVP: reporting analytics now include `hydration_summary` aggregate categorical counts (`total_events`, status/source/strategy/channel/reason) derived from report-safe hydration metadata only. Excludes refs and raw/sensitive payload-bearing fields. Reporting-only scope with no SDK/public-API/runtime/adapter/resolver/provider/dependency/version changes.
- Phase 13O hydration diagnostics reporting MVP: JSON reporting preserves sanitized hydration metadata with report-layer non-leakage guardrails; HTML reporting now renders a compact per-step hydration diagnostics section only when hydration metadata exists. Reporting-only scope with no SDK/public-API/runtime/adapter/resolver/provider/dependency/version changes.
- Phase 13M hydration diagnostics visibility MVP: SDK hydration boundary for visual refs now surfaces stable non-sensitive hydration metadata (status/reason/original_ref/hydrated_ref/channel/source/strategy plus match_field and match_count for ambiguous/no-match cases) on StepResult-facing outputs without changing hydration decisions or execution behavior. Sanitization excludes hierarchy XML, screenshots/bytes, base64/raw payloads, secrets, and candidate dumps. No public API/adapter/resolver/provider/dependency/version changes.
- Phase 13K deterministic mobile visual-ref hydration MVP: `VisualRefHydrator` now supports mobile hierarchy XML exact mapping for synthetic visual refs using deterministic metadata and priority fields `text` -> `content-desc` -> `resource-id`, emitting Appium-executable JSON XPath refs on unique matches. Stable fail-safe reasons are used for missing/invalid hierarchy, unsupported metadata, no-match, and ambiguous matches. No bbox/center-tap fallback, no screenshot/provider calls, and no public API/adapter/resolver/provider/dependency/version changes.
- Phase 13I deterministic web visual-ref hydration MVP: `VisualRefHydrator` now maps supported synthetic refs to executable web refs using deterministic metadata only (OCR `matched_text`/`text` -> `text="..."`; vision `role` + label/text -> `role=...[name="..."]`, fallback text ref). Mobile visual hydration remains deferred fail-safe. No bbox/center-click fallback, no provider/screenshot calls added, and no public API/adapter/resolver/provider/dependency/version changes.
- Phase 13G visual ref hydration fail-safe MVP: added `VisualRefHydrator` abstraction and synthetic visual ref detection (`ocr://`, `vision://`) at SDK orchestration boundary for `act()` and `extract()`. Synthetic visual refs are never executed directly; hydration currently fails safe with stable `VisualRefHydrationError` when deterministic mapping is unavailable. No adapter/resolver/provider/public-API/dependency/version changes.
- Phase 13E publish-check artifact hygiene update: publish-readiness workflow now removes stale `dist/`, `build/`, and `*.egg-info` artifacts before `python -m build`; release checklist mirrors the same cleanup command to avoid ambiguous mixed-version artifact checks. No runtime/API/dependency/version changes.
- Phase 13C publish-readiness preparation: added manual-only `.github/workflows/publish-check.yml` to run packaging/validation/build/twine/benchmark/targeted-test/collection gates and upload `dist/` artifacts without publishing. Updated release checklist/readiness notes for deferred TestPyPI/PyPI posture and future trusted-publishing recommendation. No runtime/API/adapter/resolver/dependency/version changes.
- Phase 12D v0.0.2-alpha release-notes/checklist cleanup: finalized release wording and checklist gates for GitHub pre-release readiness. Scope remains documentation-only with no runtime/API/adapter/resolver/dependency/version changes.
- v0.0.2-alpha release scope summary finalized: callable OCR backend + OCR privacy gating; vision abstraction (`VisionProvider`) + callable backend (`CallableVisionProvider`); optional/dependency-light `OpenAIVisionProvider`; provider registration lifecycle (`configure_vision_provider` / `clear_vision_provider`); SDK screenshot-to-vision wiring with explicit privacy gates; `max_cost_level="high"` gate for provider-based screenshot vision; sanitized OpenAI diagnostics; API-correct manual OpenAI example; no mandatory OCR/OpenAI dependencies.
- Release/distribution posture reaffirmed: package version remains `0.0.2a0` for GitHub pre-release `v0.0.2-alpha`; PyPI/TestPyPI publishing remains deferred.
- Phase 11Z SDK cost gating for screenshot-to-vision provider invocation: runtime provider calls now require `ExecutionOptions.max_cost_level="high"` in addition to existing vision/privacy/provider/screenshot gates. Low/medium cost levels fail-safe skip screenshot request (when needed only for provider vision) and skip provider invocation; manual `vision_candidates` remain preserved and unblocked. Added SDK wiring/registration unit coverage.
- Phase 11X OpenAI vision diagnostics hardening: `OpenAIVisionProvider` now exposes sanitized failure metadata (`last_diagnostic` and `get_last_diagnostic()`) with stable `provider`/`code`/`stage`/`recoverable`/`message`/`exception_type` fields while preserving fail-safe `[]` behavior. Diagnostics exclude raw screenshot bytes, base64 payloads, request payloads, API keys/secrets, and raw provider response bodies. Added mock-only diagnostics coverage.
- Phase 11V docs/examples adoption hardening: added manual optional real-provider usage example (`examples/openai_vision_provider_manual_example.py`) and linked guidance in README/examples/docs for user-installed OpenAI SDK + `OPENAI_API_KEY`, required vision/privacy gates, and `clear_vision_provider()` teardown. No runtime/API/adapter/resolver/dependency/version changes; network tests/benchmarks remain unchanged.
- Phase 11T OpenAI vision hardening: `OpenAIVisionProvider` now validates explicit `model` (non-empty) and `timeout` (positive), preserves injected-client behavior, propagates timeout during optional lazy SDK client creation, and expands deterministic/mock-only parsing support for `output_text`, plain-string JSON, and simple nested response text shapes. Fail-safe `[]` error handling and screenshot-byte non-persistence policy remain unchanged; no SDK public API/adapter/dependency/version changes.
- Phase 11R optional OpenAI vision backend added (`bubblegum/core/vision/backends/openai.py`) via `OpenAIVisionProvider` implementing the existing VisionProvider contract (`detect_targets(image_bytes, instruction, context=None)`). Supports injected client or optional SDK client creation, encodes image bytes as base64 transport payload, requests structured JSON candidates, normalizes outputs, and fails safe to empty candidates on provider/parse/network errors. Includes mock-only unit coverage; no mandatory OpenAI dependency, no SDK public API/adapter/resolver changes, and no raw screenshot-byte persistence.
- Phase 11P docs/examples adoption slice added: new end-to-end callable vision provider lifecycle example (`examples/vision_callable_provider_example.py`) plus README/docs linkage and recommended setup/teardown (`configure_vision_provider(...)` + `clear_vision_provider()` in `finally`) with required gates (`enable_vision`, `send_screenshots`, `process_screenshots_for_vision`). No runtime/API/adapter/dependency/version changes; real OpenAI/Anthropic/Ollama providers remain deferred.
- Phase 11N public vision provider lifecycle API added: exported `configure_vision_provider(provider)` and `clear_vision_provider()` with provider contract validation (`detect_targets(...)`) and idempotent reset semantics. Registration does not invoke provider or bypass privacy/config gates; manual `vision_candidates` precedence, provider fail-safe behavior, and screenshot-byte non-persistence policy remain unchanged.
- Phase 11L callable vision enablement documentation added (`docs/phase-11l-callable-vision-enablements.md`), including callable contract/output examples, required privacy/config gates, manual `vision_candidates` vs optional SDK screenshot wiring guidance, provider non-invocation troubleshooting, raw screenshot persistence prohibition, synthetic `vision://` limitation, and explicit note that real OpenAI/Anthropic/Ollama vision providers remain deferred. Added provider lifecycle/API audit note and Phase 11M recommendation (keep private hook private for now; evaluate safe public registration lifecycle before real provider integrations).
- Phase 11J optional SDK screenshot-to-vision context wiring added: internal runtime plumbing can request screenshots and inject normalized `vision_candidates` only when all gates pass (`enable_vision`, `send_screenshots`, `process_screenshots_for_vision`, provider configured, screenshot present). Default behavior remains off; manually injected candidates are preserved; no raw screenshot bytes are stored in traces/metadata; no resolver/adapter/public API signature changes.
- Phase 11H vision privacy/config contract hardening: added `privacy.process_screenshots_for_vision` (default `false`) to make screenshot-to-vision processing an explicit opt-in flag. No SDK runtime auto-wiring was added; resolver behavior remains injected-candidate-only and `vision://` refs remain synthetic/non-executable.
- Phase 11F user-supplied vision callable backend added (`bubblegum/core/vision/backends/callable.py`) via `CallableVisionProvider`, enabling runtime-provided vision candidate callables to feed the existing normalized screenshot vision pipeline (still opt-in/privacy-gated, no bundled real vision model dependency).
- Phase 11D VisionModelResolver injected-candidate MVP implemented: resolver now consumes `intent.context["vision_candidates"]`, normalizes via existing vision engine helpers, emits synthetic `vision://target/<index>` candidates with ranker-compatible signals/metadata, and suppresses weak unrelated matches. No real vision provider/model dependency or adapter-executable vision refs added.
- Phase 11B vision abstraction scaffold added (`bubblegum/core/vision/engine.py`): `VisionCandidate`, `VisionProvider` protocol, deterministic `FakeVisionProvider`, candidate normalization, and safe screenshot-to-vision pipeline helper (mock/fake only; no bundled real vision model dependency).

## v0.0.2-alpha
- Phase 10Q release/docs readiness cleanup completed: release checklist collect-only baseline synced to 476, and OCR callable-only contract/privacy gate/synthetic `ocr://` ref limitation documented for v0.0.2-alpha readiness.
- Appium onboarding documentation improvements across README and examples.
- Manual mobile smoke guidance clarified (Appium runtime smoke remains manual and non-CI-gated).
- Release checklist consistency cleanup for reusable pre-release gates.
- OCRResolver injected-block MVP added (context-driven `ocr_blocks`, deterministic synthetic refs `ocr://block/<index>`, no external OCR engine dependency yet).
- Phase 10J planning documentation added for post-OCR MVP verification, risk assessment, and next-slice recommendation (Phase 10K hybrid web + mobile examples).
- Phase 10K hybrid web + mobile examples added (`examples/hybrid_web_mobile_example.py`) with README linkage and guidance (docs/examples only; no runtime behavior changes).
- Phase 10M OCR engine abstraction added (`bubblegum/core/ocr/engine.py`) with deterministic fake engine, OCR block normalization, and mocked screenshot-to-block pipeline helper (no external OCR dependency, no adapter/runtime behavior changes).
- Phase 10O user-supplied OCR callable backend added (`bubblegum/core/ocr/backends/callable.py`) via `CallableOCREngine`, enabling runtime-provided OCR functions to feed the existing normalized screenshot OCR pipeline (still opt-in, no bundled real OCR dependency).
- PyPI/TestPyPI publishing remains deferred; release target continues to be GitHub pre-release tagging for `v0.0.2-alpha`.

## v0.0.1-alpha (MVP RC)

### Highlights
- Playwright explicit-selector quickstart path is in place for deterministic first-run smoke usage.
- Playwright natural-language `act`, `verify`, and `extract` usage paths are available for MVP workflows.
- Mobile channel routing supports `act`, `verify`, and `extract` via Appium adapter wiring.
- Appium quickstart is provided as a real-infrastructure template (server/device/app/capability aligned environment).
- Deterministic benchmark baselines are passing:
  - Static validation: 12/12
  - Execute validation: 12/12

### Known limitations
- Appium quickstart requires real mobile infrastructure:
  - running Appium server
  - running emulator/device
  - installed target app
  - local capability alignment
- Playwright quickstart is deterministic local smoke (`page.set_content(...)`) and is not full real-app coverage.
- Tier 3 AI/LLM/vision/ocr behavior remains optional and depends on explicit configuration, provider setup, and environment.
- PyPI/TestPyPI publishing is deferred for this MVP RC; release target is GitHub pre-release tagging.
