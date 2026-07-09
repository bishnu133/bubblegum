# Authoring test scenarios for `bubblegum convert`

This is the **rules layer for humans** — how to write scenarios in the
spreadsheet so they convert into automation with the fewest TODOs. (The
machine-readable half is the `glossary:` / `data:` sections of
`bubblegum.convert.yaml`.)

The converter is deterministic-first: the more concrete and atomic your steps,
the more of them come out as ready-to-run **AUTO** steps instead of NEEDS_DATA /
MANUAL markers a human has to finish.

---

## The spreadsheet layout

Keep the columns your team already uses. The defaults the converter expects
(remappable in `bubblegum.convert.yaml`):

| Column | Purpose |
|---|---|
| `Feature/Epic` | Groups scenarios into one `.feature` file. Bracket tags like `[F][Web]` / `[Backend]` become Gherkin tags; `[Backend]` marks non-UI rows. |
| `Test Scenario` | The scenario title ("what we validate"). |
| `User Persona` | The login/precondition context → maps to an auth fixture. |
| `Functional Jira Story` | Traceability → becomes a `@jira` tag. |
| `Verify` | **The steps, written in Gherkin** (Given/When/Then/And). |

One scenario per row.

---

## The seven rules

### 1. One action or one assertion per line
Don't pack multiple checks into a single `Then`.

```gherkin
# ✗ hard to automate
Then the first 6 badges show and a View All button appears and names truncate

# ✓ converts cleanly
Then I see 6 badges in the "Special Edition" group
And I see the "View All" button in the "Special Edition" group
```

### 2. Name the real UI element, not the concept
The converter grounds on what you'd actually click or read.

```gherkin
# ✗ concept
Then the user will be able to see this badge group

# ✓ nameable element
Then I see the "Special Edition" badge group
```

### 3. Given = precondition, When = action, Then = checkable result

```gherkin
Given I am logged in as a "H365" user     # precondition → fixture
And I open the Badge Album page           # navigation → AUTO
When I click the "View All" button        # action → AUTO
Then I see the Badge Group detail view    # assertion → AUTO
```

### 4. Put data/state preconditions in `Given` (they map to setup)
State a row depends on becomes a NEEDS_DATA marker — expected and honest.

```gherkin
Given the "Special Edition" group has 8 eligible badges   # → NEEDS_DATA (seed it)
```

### 5. Split `if` / `e.g.` variants into separate scenarios
One conditional sentence is really several test cases.

```gherkin
# ✗ one row, two behaviours
Then if more than 6 badges show View All, else show all badges

# ✓ two rows
Scenario: Group with more than 6 badges shows View All
Scenario: Group with fewer than 6 badges shows all badges
```

Use a `Scenario Outline` + `Examples` table when only data varies.

### 6. Write the subject naturally — it's stripped automatically
"I", "they", "the user", "will", "should" at the start of a step are removed
before parsing, so `When I click Save` and `When the user clicks Save` both work.
Keep them for readability.

### 7. Reuse phrasing for repeated flows
Write the same precondition the same way every time (e.g. always
`Given I open the Login page`). Identical steps are de-duplicated into one step
definition, and you can map a recurring phrase to a canonical step via the
`glossary:` in `bubblegum.convert.yaml`:

```yaml
convert:
  glossary:
    "the standard login": "I open the Login page"
```

---

## What each rule buys you

| If you… | The step becomes… |
|---|---|
| name a concrete element + action | ✅ **AUTO** — a real `act`/`verify` call |
| state a data/state precondition | ⚠️ **NEEDS_DATA** — wire a fixture |
| describe backend/data behaviour (`[Backend]`) | 🔧 **BACKEND** — skipped stub |
| write an abstract "will be able to…" outcome | ✋ **MANUAL** — author by hand |

Aim for AUTO; accept the markers where a human genuinely has to decide. A
scaffold that is honest about its gaps beats one that silently passes on a step
nobody finished.
