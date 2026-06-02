# Bubblegum — Next Implementation Plan

## 1. AnthropicProvider

**Why**: Claude Sonnet/Haiku outperforms GPT-4o-mini on structured UI reasoning tasks and costs less. Currently the provider factory has a stub that raises on use.

### Files to change
- `bubblegum/core/models/anthropic_provider.py` — full implementation
- `bubblegum/core/models/factory.py` — already wired, just needs working provider
- `docs/bubblegum.yaml.example` — add anthropic example config block

### Design
```python
class AnthropicProvider(ModelProvider):
    provider_name = "anthropic"
    # Uses anthropic Python SDK: pip install anthropic
    # Reads ANTHROPIC_API_KEY from env
    # Sends messages=[{"role": "user", "content": prompt}]
    # system= maps to top-level system parameter
    # response_format="json" → adds "Return only JSON." to system prompt
    #   (Anthropic does not have JSON mode; we prompt-engineer it)
    # Supports claude-opus-4-8, claude-sonnet-4-6, claude-haiku-4-5
```

### Config (bubblegum.yaml)
```yaml
ai:
  enabled: true
  provider: anthropic
  model: claude-haiku-4-5-20251001   # cheapest, fast, good for UI grounding
```

### Test plan
- Unit: mock anthropic SDK, assert message format + system prompt handling
- Unit: assert JSON response_format adds instruction to system prompt
- Unit: assert token counts and latency are logged via `_log_call()`
- Integration: (marked `@pytest.mark.llm`) real call with `ANTHROPIC_API_KEY`

---

## 2. Session Class

**Why**: The current API requires `page=page` on every call. Real test scripts look like:
```python
# Current — noisy
await act("Click Login",           page=page, channel="web")
await act('Enter "x" into Email',  page=page, channel="web")
await verify("Dashboard visible",  page=page, channel="web")
```
A Session holds the channel + driver/page once and exposes `act/verify/extract` directly.

### Target API
```python
async with BubblegumSession.web(page) as s:
    await s.act("Click Login")
    await s.act('Enter "tomsmith" into Username')
    await s.act('Enter "secret" into Password')
    await s.verify("Secure Area visible")
    value = await s.extract("Get flash message")
    print(s.summary())   # pass/fail counts, total duration
```

### Files to create/change
- `bubblegum/session.py` — new `BubblegumSession` class
- `bubblegum/__init__.py` — export `BubblegumSession`
- `examples/test_real_web.py` — add session-based version of the login test

### Design
```python
class BubblegumSession:
    def __init__(self, channel, page=None, driver=None, config=None): ...

    @classmethod
    def web(cls, page, **kwargs) -> "BubblegumSession": ...

    @classmethod
    def mobile(cls, driver, **kwargs) -> "BubblegumSession": ...

    async def act(self, instruction, **kwargs) -> StepResult: ...
    async def verify(self, instruction, **kwargs) -> StepResult: ...
    async def extract(self, instruction, **kwargs) -> StepResult: ...
    async def recover(self, failed_selector, intent, **kwargs) -> StepResult: ...

    def summary(self) -> dict: ...           # {total, passed, failed, recovered}
    def results(self) -> list[StepResult]: ...
    def assert_all_passed(self) -> None: ...  # raises AssertionError on any failure

    # context manager
    async def __aenter__(self): return self
    async def __aexit__(self, *_): ...        # close/cleanup hooks
```

### Test plan
- Unit: Session.web() wires channel="web" and passes page through
- Unit: results accumulate across multiple act() calls
- Unit: assert_all_passed() raises if any result is failed
- Unit: summary() returns correct counts
- Integration: fake adapter end-to-end through Session

---

## 3. `dry_run=True` Mode

**Why**: Teams nervous about AI-driven execution need to see "what would it click?" before trusting it with real actions. Essential for onboarding.

### Target API
```python
result = await act("Click Login", page=page, dry_run=True)
# → StepResult(status="dry_run", target=<resolved>, confidence=0.96)
# No browser interaction happens — element identified but not clicked.

# Or via Session:
async with BubblegumSession.web(page, dry_run=True) as s:
    await s.act("Click Login")      # resolves only
    await s.act('Enter "x" into Username')  # resolves only
    s.print_plan()                  # prints the full resolution plan
```

### Files to change
- `bubblegum/core/schemas.py` — add `dry_run: bool = False` to `ExecutionOptions`; add `"dry_run"` to `StepResult.status` literal
- `bubblegum/core/sdk.py` — after ground(), if `dry_run=True`, skip `adapter.execute()` and return `status="dry_run"`
- `bubblegum/core/planner/intent.py` — pass `dry_run` through `build_options()`
- `bubblegum/session.py` — Session-level `dry_run=True` flag sets it on every call

### Test plan
- Unit: dry_run=True returns status="dry_run" without calling adapter.execute()
- Unit: target and confidence are populated in dry_run result
- Unit: dry_run result has no artifacts (no screenshot)
- Unit: dry_run respects resolver chain normally (full resolution runs)

---

## 4. CI Memory Cache Export / Import

**Why**: The SQLite self-healing cache is wiped on every CI run (ephemeral containers). Without persistence, the memory resolver never gets a chance to work in CI, which is exactly where you want it most.

### Target API (CLI + Python)
```bash
# In CI "save cache" step:
bubblegum cache export --output .bubblegum-cache.json

# In CI "restore cache" step (before tests):
bubblegum cache import --input .bubblegum-cache.json

# Or via GitHub Actions cache key:
# - uses: actions/cache@v4
#   with:
#     path: .bubblegum/memory.db
#     key: bubblegum-memory-${{ runner.os }}-${{ hashFiles('tests/**') }}
```

```python
# Python API
from bubblegum.core.memory.layer import MemoryLayer

layer = MemoryLayer()
layer.export(".bubblegum-cache.json")   # → JSON file (portable, diffable)
layer.import_from(".bubblegum-cache.json")
```

### Files to change
- `bubblegum/core/memory/layer.py` — add `export(path)` and `import_from(path)` methods
- `bubblegum/cli.py` — new (or extend existing) CLI: `bubblegum cache export/import/stats`
- `pyproject.toml` — register `bubblegum` console script entry point
- `docs/ci.md` — GitHub Actions snippet showing the cache step pattern

### Export format (JSON, human-readable)
```json
{
  "version": 1,
  "exported_at": "2026-06-02T10:00:00Z",
  "entries": [
    {
      "screen_signature": "sha256:abc...",
      "step_hash": "sha256:def...",
      "ref": "role=button[name=\"Login\"]",
      "resolver_name": "accessibility_tree",
      "confidence": 0.96,
      "success_count": 5,
      "failure_count": 0,
      "last_used": "2026-06-02T09:55:00Z"
    }
  ]
}
```

### Test plan
- Unit: export() writes valid JSON with correct schema
- Unit: import_from() loads entries into SQLite
- Unit: import is idempotent (re-importing same data doesn't duplicate)
- Unit: import merges correctly (higher success_count wins on conflict)
- Unit: CLI `bubblegum cache export` writes file; `import` reads it back

---

## Implementation Order (recommended)

| # | Item | Effort | Value |
|---|------|--------|-------|
| 1 | AnthropicProvider | Small (1–2 hrs) | High — unlocks Claude for grounding |
| 2 | `dry_run=True` | Small (1–2 hrs) | High — adoption blocker for risk-averse teams |
| 3 | Session class | Medium (3–4 hrs) | High — biggest DX improvement |
| 4 | CI cache export/import | Medium (3–4 hrs) | Medium — valuable but lower urgency |

Start with 1 + 2 (both small, high value), then 3, then 4.
