# @bubblegum-ai/node

Node/TypeScript client for [**Bubblegum**](https://github.com/bishnu133/bubblegum) —
drive AI-powered, natural-language Playwright/Appium test steps from JS/TS.

> **Status: alpha scaffold (`0.2.0` slice).** This is a thin, typed client that
> spawns the Python **bubblegum bridge** and speaks its JSON-RPC protocol. The
> Python engine stays the single source of truth for grounding/self-healing — we
> do **not** re-implement it in TypeScript. See
> [`docs/distribution-npm-and-pypi.md`](../../docs/distribution-npm-and-pypi.md)
> and [`docs/bridge-protocol.md`](../../docs/bridge-protocol.md).

## Prerequisites

The client launches the engine as a child process, so a Python engine must be
importable on the machine running your tests:

```bash
pip install "bubblegum-ai[web]"        # the engine + Playwright
python -m playwright install chromium  # one-time browser download
# (mobile: pip install "bubblegum-ai[mobile]" + a running Appium server/device)
```

Confirm the bridge is runnable:

```bash
python -m bubblegum.bridge   # should wait for JSON-RPC on stdin (Ctrl-D to exit)
```

## Install

```bash
npm install @bubblegum-ai/node
```

## Quick start

```ts
import { Bubblegum } from "@bubblegum-ai/node";

const bg = await Bubblegum.launch({ url: "https://the-internet.herokuapp.com/login" });
try {
  await bg.act('Enter "tomsmith" into Username');
  await bg.act('Enter "SuperSecretPassword!" into Password');
  await bg.act("Click Login");
  const r = await bg.verify("You logged into a secure area");
  console.log(r.status); // "passed" | "recovered" | "failed"
} finally {
  await bg.close();
}
```

`launch()` spawns the bridge, negotiates the protocol via `handshake`, and opens
an **engine-owned** session (the Playwright `Page` / Appium driver lives in the
Python process). Every method returns the same `StepResult` shape as the Python
SDK.

### Heal a stale selector (adoption path)

```ts
// old: await page.click("#login-btn");   // selector now stale
const r = await bg.recover({ failedSelector: "#login-btn", intent: "Click Login" });
// r.status === "recovered" when Bubblegum healed it
```

### Mobile

```ts
const bg = await Bubblegum.launch({
  channel: "mobile",
  appiumUrl: "http://127.0.0.1:4723",
  capabilities: { platformName: "Android", "appium:app": "/path/to/app.apk" },
});
await bg.act("Tap Login");
```

### Attach to your own browser (CDP, client-owned)

Instead of letting the engine launch its own Chromium, point it at the browser
**your** Playwright test already drives, over the Chrome DevTools Protocol. Launch
Chromium with a remote-debugging port, then `attach`:

```ts
import { chromium } from "@playwright/test";
import { Bubblegum } from "@bubblegum-ai/node";

const browser = await chromium.launch({ args: ["--remote-debugging-port=9222"] });
const page = await browser.newPage();
await page.goto("https://example.com/login");

const bg = await Bubblegum.attach({ cdpEndpoint: "http://localhost:9222" });
await bg.act("Click Login");   // drives the page you just opened
await bg.close();              // disconnects; your browser keeps running
```

The engine attaches to an existing page (`pageIndex`, default 0) and never
creates or closes your browser/page. Requires the engine to advertise the
`channel.web.cdp` capability (Bubblegum ≥ 0.0.6); `attach()` throws a clear error
otherwise. CDP attach is Chromium-only.

## API

| Method | Returns | Notes |
| --- | --- | --- |
| `Bubblegum.launch(opts)` | `Promise<Bubblegum>` | spawn + handshake + `session.open` |
| `bg.act(instruction, options?)` | `Promise<StepResult>` | |
| `bg.verify(instruction, options?)` | `Promise<StepResult>` | |
| `bg.extract(instruction, options?)` | `Promise<StepResult>` | value in `target.metadata.extracted_value` |
| `bg.recover({ failedSelector, intent, options? })` | `Promise<StepResult>` | |
| `bg.isVisible / isChecked / selectedValue(target)` | `Promise<boolean \| string>` | |
| `bg.explain(instruction)` | `Promise<string>` | dry-run rationale |
| `bg.summary()` | `Promise<SessionSummary>` | |
| `bg.close()` | `Promise<void>` | closes the session + bridge |

`options` is forwarded verbatim to the engine (`timeout_ms`, `selector`,
`action_type`, `value`, `assertion_type`, `expected_value`, `max_cost_level`, …),
matching the Python how-to guides.

### Advanced: `BridgeClient`

`Bubblegum` wraps a lower-level `BridgeClient` (`bg.bridge`) that you can use
directly, or with an injected `Transport` (e.g. for tests or a future daemon
socket). See `src/client.ts`.

## Versioning

The client pins to a compatible engine. It refuses to start against a
`protocol_version` it doesn't support and tells you to upgrade — newer engines
keep serving older clients (additive-first). This package's major/minor track the
engine; install a matching `bubblegum-ai`.

## Develop

```bash
npm install
npm run build      # tsc -> dist/
npm test           # build + node:test (no Python needed; mock transport)
npm run typecheck
```

## Not yet (roadmap)

- Auto-bootstrap of a managed Python venv when the engine isn't found.
- Published to npm + dual-publish CI alongside PyPI.
