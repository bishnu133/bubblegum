# Manual → Automation Converter (`bubblegum convert`)

Turn a spreadsheet of manually authored test scenarios into reviewable
automation **scaffolds**: normalized Gherkin `.feature` files plus step
definitions for Python (pytest-bdd) and TypeScript (playwright-bdd) that call
Bubblegum's `act` / `verify` / `extract`.

> **Scaffolds, not magic.** Bubblegum already turns a plain-English step into a
> grounded UI action at runtime. The converter's job is *authoring*: read your
> manual scenarios and generate the test files that call those primitives. Steps
> that still need a human — a locator for an abstract assertion, test-data setup,
> or a backend behaviour — are emitted with explicit markers rather than
> silently-wrong code.

---

## Quick start

```bash
pip install "bubblegum-ai[convert]"    # adds openpyxl for .xlsx reading

bubblegum convert scenarios.xlsx -o generated/
```

Output:

```
generated/
├── features/      one .feature per Feature/Epic
├── python/        test_<feature>.py   (pytest-bdd + bubblegum)
├── typescript/    <feature>.steps.ts  (playwright-bdd + @bubblegum-ai/node)
└── CONVERT_REPORT.md   step counts by classification
```

CLI options:

| Flag | Meaning |
|---|---|
| `-o, --out DIR` | Output directory (default: profile `output.dir`, else `generated`). |
| `--config PATH` | Path to `bubblegum.convert.yaml` (default: `./bubblegum.convert.yaml`). |
| `--languages a,b` | Subset of `feature,python,typescript` to emit. |
| `--ai` | Enable the optional AI fallback for steps the grammar can't split. |

---

## How it works

```
scenarios.xlsx
   │  ingest          columns mapped via the profile (Feature/Epic, Test
   ▼                  Scenario, User Persona, Jira, Verify …)
RawScenario[]
   │  normalize       Gherkin parsed → each step run through Bubblegum's
   ▼                  deterministic `decompose` grammar (+ optional AI) →
CanonicalStep[]       classified AUTO / NEEDS_DATA / BACKEND / MANUAL
   │  group by Feature/Epic
   ▼
Feature[]  ──emit──▶  .feature   +   pytest-bdd steps   +   playwright-bdd steps
```

**Deterministic-first, AI-optional.** Every step is first parsed with the same
rule-based grammar the SDK uses at runtime (`bubblegum.core.parser.decompose`).
The AI fallback is off by default and, when enabled, is consulted *only* for
steps the grammar can't confidently split — mirroring Bubblegum's fallback-first
posture. AI never sees your DOM or screenshots, only the short step text.

### Step classification

| Kind | Meaning | Emitted as |
|---|---|---|
| ✅ **AUTO** | Clean action or assertion with a concrete target. | A real `act` / `verify` / `extract` call. |
| ⚠️ **NEEDS_DATA** | Precondition / login / test data a human must wire. | `pytest.skip` (Py) / pending no-op (TS) + TODO. |
| 🔧 **BACKEND** | Non-UI backend behaviour (`[Backend]` feature tag). | Skipped stub + TODO. |
| ✋ **MANUAL** | Abstract assertion or unparseable step. | Skip + TODO for a human. |

The generated `.feature` files annotate every non-AUTO step inline:

```gherkin
  Scenario: Verify a valid coupon applies a discount
    Given I am logged in as a "Shopper"
    # ^ NEEDS_DATA: Login/persona precondition — map to an auth fixture.
    And I open the Checkout page
    When I enter "SAVE10" into the Coupon code field
    And I click the Apply button
    Then I see the Discount applied message
```

### Why the generated calls are robust

An AUTO step passes its **subject-stripped natural-language text** straight to a
Bubblegum primitive:

```python
@when("I enter \"SAVE10\" into the Coupon code field")
async def step_when(page):
    await act("enter \"SAVE10\" into the Coupon code field", page=page)
```

Bubblegum re-parses that text at runtime with the same grammar, so there is no
brittle call reconstruction — and the Python and TypeScript emitters stay in
lockstep because they share one call-mapping helper.

---

## Team conventions — `bubblegum.convert.yaml`

Every team keeps config, data and waits differently. All of that lives in a
profile so the engine stays generic. See
[`examples/bubblegum.convert.yaml`](../examples/bubblegum.convert.yaml) for a
fully commented template.

```yaml
convert:
  input:
    sheet: null                 # null = active/first sheet
    header_row: 1
    columns:                    # logical name → your spreadsheet's header text
      feature: "Feature/Epic"
      title:   "Test Scenario"
      persona: "User Persona"
      jira:    "Functional Jira Story"
      steps:   "Verify"
    backend_markers: ["[Backend]"]
  output:
    languages: ["feature", "python", "typescript"]
    dir: "generated"
    python:
      bubblegum_import: "from bubblegum import act, verify, extract"
    typescript:
      client_import: "@bubblegum-ai/node"
  waits:
    strategy: "auto"            # auto | explicit | none
  glossary:                     # domain phrase → canonical step text
    "the standard login": "I open the Login page"
  data: {}                      # token → data-binding expression (reserved)
  ai:
    enabled: false
    provider: null              # falls back to bubblegum.yaml `ai:` block
    model: null
```

- **`columns`** lets any team point the converter at their own header names.
- **`backend_markers`** flags rows as non-UI so they don't emit broken tests.
- **`glossary`** rewrites a recurring phrase to a canonical, automatable step —
  the machine-readable half of the "rules" layer (the human-readable half is the
  [authoring style guide](authoring-scenarios-style-guide.md)).
- **`ai`** reuses Bubblegum's existing provider factory, so `anthropic`,
  `openai`, `gemini`, and local/Ollama all work by config alone.

---

## Authoring scenarios that convert well

The converter is only as good as its input. Scenarios written at a **concrete,
UI-observable level** convert almost entirely to AUTO steps; abstract acceptance
criteria produce more TODOs. The one-page
[authoring style guide](authoring-scenarios-style-guide.md) has the rules and
before/after examples. In short:

- one action or one assertion per line (no "and … and …"),
- name the actual UI element ("View All button"), not the concept,
- precondition in `Given`, action in `When`, checkable result in `Then`,
- split `if` / `e.g.` variants into separate scenarios.

Legacy abstract scenarios still convert — they just come out with more
NEEDS_DATA / MANUAL markers for a human to finish.

---

## Programmatic API

```python
from bubblegum.convert import convert_workbook, ConvertProfile

result = convert_workbook("scenarios.xlsx", out_dir="generated")
print(result.stats())   # {'auto': 13, 'needs_data': 1, 'backend': 3, ...}

# Dry run (build the IR, write nothing):
result = convert_workbook("scenarios.xlsx", write=False)
```

---

## Roadmap

- **Now:** Excel ingest, Gherkin normalization + classification, `.feature` +
  pytest-bdd + playwright-bdd emitters, deterministic-first parsing, optional
  AI fallback, per-team profile.
- **Next:** data-binding layer (`data:` tokens → fixtures), reusable-flow macros
  (persona → login `Background`), the Gemini provider, a Claude skill mirroring
  the glossary, and dry-run validation of generated tests against the resolver
  chain.
```
