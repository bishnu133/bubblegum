# Bubblegum Bridge Protocol (v1)

The **bridge** exposes the Python engine over **JSON-RPC 2.0** so non-Python
clients — most importantly the planned `@bubblegum-ai/node` npm package — can
drive the same four primitives (`act` / `verify` / `extract` / `recover`) without
re-implementing the grounding engine. This is the server side of the
dual-distribution plan in `distribution-npm-and-pypi.md`.

> **Status:** `0.1.0` slice — stdio transport, engine-owned sessions. The Node
> client and client-owned (CDP-attach) browser model are subsequent slices.

## Running it

```bash
bubblegum bridge          # serve JSON-RPC over stdio
python -m bubblegum.bridge
```

The bridge reads **one JSON-RPC request per line** on stdin and writes **one
response per line** to stdout. It is designed to be spawned as a child process by
a client and spoken to over the pipe.

## Transport & framing

- **JSON-RPC 2.0**, newline-delimited (one compact JSON object per line).
- Requests with an `id` get exactly one response; **notifications** (no `id`)
  get none.
- A malformed line yields a `-32700` parse-error response with `id: null`; the
  loop keeps running.
- A handler error never crashes the process — it becomes a JSON-RPC error object.

## Version negotiation

Call `handshake` first. The engine reports its `protocol_version` and the full
`capabilities` list. **Feature-detect on capabilities**, not on the raw version
number — that is what lets a newer engine keep serving an older client and lets
new features ship additively at higher versions.

```json
→ {"jsonrpc":"2.0","id":1,"method":"handshake"}
← {"jsonrpc":"2.0","id":1,"result":{
     "engine_version":"0.0.5a0","protocol_version":1,
     "capabilities":["session.open","session.close","act","verify","extract",
                     "recover","explain","state_probes","summary",
                     "configure_runtime","channel.web","channel.mobile"]}}
```

`PROTOCOL_VERSION` is bumped **additively**: new methods / optional fields raise
it, but every previously shipped method keeps working.

## Sessions

The wire cannot carry a live Playwright `Page` or Appium `WebDriver`, so the
**engine owns the runtime handle**. Open a session, then pass its `session_id` on
every subsequent call.

```json
→ {"jsonrpc":"2.0","id":2,"method":"session.open",
   "params":{"channel":"web","url":"https://example.com/login","headless":true}}
← {"jsonrpc":"2.0","id":2,"result":{"session_id":"a1b2c3..."}}
```

`session.open` params:

| param | channel | meaning |
| --- | --- | --- |
| `channel` | both | `"web"` (default) or `"mobile"` |
| `url` | web | optional start URL to navigate to |
| `headless` | web | default `true` |
| `dry_run` | both | resolve-only, never execute |
| `appium_url` | mobile | Appium server URL (required for mobile) |
| `capabilities` | mobile | Appium capabilities object |

Close with `session.close` (`{"session_id": ...}` → `{"closed": true}`). The
process tears down any still-open sessions on exit.

## Methods

All take a params **object**; all primitive results are the engine's
`StepResult` serialized as JSON (`status`, `action`, `target`, `confidence`,
`traces`, `error`, …) — identical to the Python SDK.

| Method | Params | Result |
| --- | --- | --- |
| `handshake` | — | `{engine_version, protocol_version, capabilities[]}` |
| `session.open` | see table above | `{session_id}` |
| `session.close` | `{session_id}` | `{closed: true}` |
| `act` | `{session_id, instruction, options?}` | `StepResult` |
| `verify` | `{session_id, instruction, options?}` | `StepResult` |
| `extract` | `{session_id, instruction, options?}` | `StepResult` (value in `target.metadata.extracted_value`) |
| `recover` | `{session_id, failed_selector, intent, options?}` | `StepResult` |
| `explain` | `{session_id, instruction}` | `{explanation: string}` |
| `is_visible` | `{session_id, target}` | `{value: bool}` |
| `is_checked` | `{session_id, target}` | `{value: bool}` |
| `selected_value` | `{session_id, target}` | `{value: string}` |
| `summary` | `{session_id}` | `{total, passed, failed, ...}` |
| `configure_runtime` | `{config_path?}` | `{ok: true}` |

`options` is forwarded verbatim to the SDK as keyword arguments — the same
per-call kwargs documented in the how-to guides (`timeout_ms`, `selector`,
`action_type`, `value`, `assertion_type`, `expected_value`, `max_cost_level`,
`nav_wait_ms`, `resolve_retries`, …).

### Example: act

```json
→ {"jsonrpc":"2.0","id":3,"method":"act",
   "params":{"session_id":"a1b2c3...","instruction":"Click Login"}}
← {"jsonrpc":"2.0","id":3,"result":{
     "status":"passed","action":"Click Login",
     "target":{"ref":"role=button[name='Login']","confidence":0.93,
               "resolver_name":"accessibility_tree"},
     "confidence":0.93,"duration_ms":42,"traces":[...]}}
```

## Error codes

| Code | Meaning |
| --- | --- |
| `-32700` | Parse error (malformed JSON) |
| `-32600` | Invalid request (not JSON-RPC 2.0) |
| `-32601` | Method not found |
| `-32602` | Invalid params (missing/typed wrong) |
| `-32603` | Internal error (unexpected engine exception) |
| `-32001` | Session not found |
| `-32002` | Engine error |
| `-32003` | Unsupported (e.g. channel dependency not installed) |

## Architecture (where the code lives)

| Module | Responsibility |
| --- | --- |
| `bubblegum/bridge/protocol.py` | `PROTOCOL_VERSION`, capabilities, JSON-RPC framing, error codes — pure, no I/O |
| `bubblegum/bridge/server.py` | `BridgeServer` dispatch + `serve` / `serve_stdio` loop |
| `bubblegum/bridge/sessions.py` | `SessionManager` + injectable session factory (engine-owned Playwright/Appium) |
| `bubblegum/bridge/handlers.py` | One coroutine per method; thin adapter onto `BubblegumSession` / SDK |
| `bubblegum/cli/bridge.py` | `bubblegum bridge` process entry point |

The handlers contain **no grounding logic** — they call the existing
`BubblegumSession` / `bubblegum.core.sdk`, so the bridge and the Python SDK share
one engine and one `StepResult` shape. Unit coverage drives
`BridgeServer.handle_message` with a fake session factory (no browser/device):
`tests/unit/test_bridge.py`.
