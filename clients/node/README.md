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

### Dynamic-value tokens (dates/times + uniqueness)

For any field that needs a value computed at run time, drop a `{{ ... }}` token
into the step value instead of a literal that goes stale or collides.

**Relative dates/times** — date pickers and any date field:

```ts
await bg.act('Enter "{{today+7d|%d/%m/%Y}}" into Start date');     // -> 23/06/2026
await bg.act('Enter "{{now+2h|%d/%m/%Y %H:%M}}" into Appointment'); // -> 16/06/2026 04:00
await bg.act('Enter "{{tomorrow|%d/%m/%Y}}" into End date');
```

- **Bases:** `today`, `now`, `tomorrow`, `yesterday`.
- **Offsets (chainable, signed):** `+7d` `-3d` `+2w` `+1mo` `-1y` `+2h` `+30min` `+45s`
  (`mo` = months, `min` = minutes — spelled out so a bare `m` is never ambiguous).
- **Format:** anything after `|` is a `strftime` pattern. Defaults are
  `%Y-%m-%d` for date bases and `%Y-%m-%d %H:%M` for `now`.

**Uniqueness** — for a field whose value must differ on every run (a badge
name, an email, any create-form field with a unique constraint):

```ts
await bg.act('Enter "Badge_{{timestamp}}" into Display Name');            // -> Badge_1751558400
await bg.act('Enter "Badge_{{timestamp|%Y%m%d%H%M%S}}" into Display Name'); // -> Badge_20260703153012
await bg.act('Enter "user_{{uuid:8}}@test.com" into Email');             // -> user_3f9a1c02@test.com
await bg.act('Enter "SKU-{{random:6}}" into Code');                      // -> SKU-402913
```

- **`timestamp`** — Unix epoch **seconds**; `:ms` for milliseconds (tighter
  uniqueness in fast loops), or a `|` `strftime` for a readable stamp such as
  `{{timestamp|%Y%m%d%H%M%S}}`.
- **`uuid`** — a random UUID hex string (32 chars); `:N` keeps the first `N`
  chars, e.g. `{{uuid:8}}`. Unique regardless of the clock.
- **`random`** — a run of random digits, default 6; `:N` for `N` digits.

Token-free values (and any `{{...}}` that isn't a recognised expression) are
passed through unchanged, so existing literal steps are unaffected. Expansion
happens engine-side, so it works identically for web, mobile, and CDP attach.

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
| `bg.report(opts)` | `Promise<ReportResult>` | write Allure/HTML/JSON/JUnit from the run |
| `bg.close()` | `Promise<void>` | closes the session + bridge |

`options` is forwarded verbatim to the engine (`timeout_ms`, `selector`,
`action_type`, `value`, `assertion_type`, `expected_value`, `max_cost_level`, …),
matching the Python how-to guides.

### Reports (Allure / HTML / JSON / JUnit)

The engine remembers every step a session runs, so you can emit the same reports
the Python/pytest path produces — no pytest required. Call `bg.report(...)` once
near the end (in a `finally`, before `close()`):

```ts
try {
  await bg.act('Enter "tom" into Username');
  await bg.act("Click Login");
  await bg.verify("Dashboard is visible");
} finally {
  await bg.report({
    html: "reports/run.html",      // single-file HTML
    allure: "allure-results",      // Allure 2 dir -> `allure serve allure-results`
    junit: "reports/junit.xml",    // CI ingestion
    json: "reports/run.json",      // machine-readable
    title: "Smoke run",
    suiteName: "h365-portal",
  });
  await bg.close();
}
```

Each format is optional; pass `true` instead of a path to use the default name
(`bubblegum_report.html` / `.json` / `.xml`, `allure-results/`). Paths are
resolved relative to the **engine process's working directory** (where the bridge
was spawned — normally your project root). Returns
`{ written: { html: "/abs/…", … }, steps }`. Requires the engine to advertise
`report.write` (Bubblegum ≥ 0.0.6); older engines throw a clear error.

### Advanced: `BridgeClient`

`Bubblegum` wraps a lower-level `BridgeClient` (`bg.bridge`) that you can use
directly, or with an injected `Transport` (e.g. for tests or a future daemon
socket). See `src/client.ts`.

## Versioning

The client pins to a compatible engine. It refuses to start against a
`protocol_version` it doesn't support and tells you to upgrade — newer engines
keep serving older clients (additive-first). This package's major/minor track the
engine; install a matching `bubblegum-ai`.

## Module formats (ESM + CommonJS)

This package ships **both** ES modules and CommonJS, so it works whether your
test runner loads ESM or CJS — no `.mts` rename or loader flags needed:

```ts
import { Bubblegum } from "@bubblegum-ai/node";        // ESM / TypeScript
```
```js
const { Bubblegum } = require("@bubblegum-ai/node");   // CommonJS (e.g. Jest default)
```

Node picks `dist/esm` for `import` and `dist/cjs` for `require` via the package
`exports` map; TypeScript types resolve for both.

## Develop

```bash
npm install
npm run build      # tsc -> dist/esm (ESM) + dist/cjs (CommonJS)
npm test           # build + node:test (no Python needed; mock transport)
npm run typecheck
```

## Not yet (roadmap)

- Auto-bootstrap of a managed Python venv when the engine isn't found.
- Published to npm + dual-publish CI alongside PyPI.
