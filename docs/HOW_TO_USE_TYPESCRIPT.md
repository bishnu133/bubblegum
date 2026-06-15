# How to Use Bubblegum — TypeScript / JavaScript (`@bubblegum-ai/node`)

This is the **copy‑paste how‑to guide for JS/TS projects**. If your automation is
written in TypeScript or JavaScript (e.g. a Playwright suite), you can drive the
same AI‑powered, natural‑language, self‑healing steps from Node using the
**`@bubblegum-ai/node`** client — `await bg.act("Click Login")`.

> **How it works (and why you still need Python).** Bubblegum's engine — the
> tiered resolver chain, ranking, self‑healing, memory, vision/OCR — lives in
> **one Python package**, so it never drifts between languages. The npm client is
> a thin, typed layer that **spawns the Python engine** (`python -m
> bubblegum.bridge`) and talks to it over a small JSON‑RPC protocol. You get the
> exact same behavior and the exact same `StepResult` as the Python SDK. See
> [`distribution-npm-and-pypi.md`](distribution-npm-and-pypi.md) and
> [`bridge-protocol.md`](bridge-protocol.md).
>
> Python users / the Playwright (Python) and Appium guides:
> [`HOW_TO_USE_WEB.md`](HOW_TO_USE_WEB.md) · [`HOW_TO_USE_MOBILE.md`](HOW_TO_USE_MOBILE.md).

## Contents

- [Prerequisites](#prerequisites)
- [Install](#install)
- [Hello, Bubblegum (Node)](#hello-bubblegum-node)
- [The four primitives](#the-four-primitives)
- [`StepResult` — what you get back](#stepresult--what-you-get-back)
- [Per‑call options](#percall-options)
- [Attach to your own Playwright browser (CDP)](#attach-to-your-own-playwright-browser-cdp)
- [Use inside `@playwright/test`](#use-inside-playwrighttest)
- [Mobile (Appium)](#mobile-appium)
- [Heal a stale selector](#heal-a-stale-selector)
- [Error handling](#error-handling)
- [Compatibility & versioning](#compatibility--versioning)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

The client launches the engine as a child process, so **Python must be available**
on the machine running your tests (CI included):

```bash
# 1) the engine (+ Playwright for the web channel)
pip install "bubblegum-ai[web]"
python -m playwright install chromium

# 2) Node 18+ for the client
node --version
```

Sanity‑check the bridge is runnable (it waits for JSON‑RPC on stdin; Ctrl‑D to exit):

```bash
python -m bubblegum.bridge
```

> For mobile: `pip install "bubblegum-ai[mobile]"` plus a running Appium server +
> device. For Claude/LLM grounding: `pip install "bubblegum-ai[anthropic]"`.

---

## Install

```bash
npm install @bubblegum-ai/node
```

---

## Hello, Bubblegum (Node)

The simplest mode is **engine‑owned**: `launch()` spawns the bridge and opens a
browser inside the engine for you.

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

`launch()` spawns the engine, negotiates the protocol (`handshake`), and opens an
engine‑owned session. Every method returns the same `StepResult` shape as the
Python SDK.

> Prefer to drive **your own** browser (the one your Playwright test already
> opened)? See [CDP attach](#attach-to-your-own-playwright-browser-cdp) — that's
> the mode most existing TS suites want.

---

## The four primitives

```ts
await bg.act("Click Login");                       // perform an action
await bg.verify("Dashboard is visible");           // assert a state
const e = await bg.extract("Get the order total"); // read text
await bg.recover({ failedSelector: "#old", intent: "Click Login" }); // heal a stale selector
```

The natural‑language grammar is identical to the Python guides — `Click X`,
`Enter "v" into Field`, `Select "v" from Field`, `Check X`, `Scroll to X`, etc.
(see [`HOW_TO_USE_WEB.md`](HOW_TO_USE_WEB.md#naturallanguage-grammar)).

`extract` returns the text under `target.metadata.extracted_value`:

```ts
const r = await bg.extract("Get the flash message");
console.log(r.target?.metadata?.extracted_value);
```

State probes return plain values:

```ts
await bg.isVisible("Welcome banner");   // boolean
await bg.isChecked("Newsletter");       // boolean
await bg.selectedValue("Country");      // string, e.g. "FR"
```

---

## `StepResult` — what you get back

The same contract as the Python SDK, fully typed:

```ts
import type { StepResult } from "@bubblegum-ai/node";

const r: StepResult = await bg.act("Click Login");
r.status;                 // "passed" | "recovered" | "failed" | "dry_run" | "skipped"
r.target?.ref;            // the locator Bubblegum resolved
r.target?.resolver_name;  // which tier won: accessibility_tree / fuzzy_text / memory_cache / ...
r.confidence;             // 0.0–1.0
r.error?.message;         // when status === "failed"
```

`"recovered"` means the original label/selector drifted but Bubblegum healed it —
surface it in CI so your team knows which steps to de‑brittle.

---

## Per‑call options

The optional second argument is forwarded verbatim to the engine — the same
options documented in the Python how‑to (`timeout_ms`, `selector`, `action_type`,
`value`, `assertion_type`, `expected_value`, `max_cost_level`, `nav_wait_ms`,
`resolve_retries`, …):

```ts
await bg.act("Submit", { action_type: "click", timeout_ms: 5000 });
await bg.act("Set quantity", { action_type: "type", value: "5", selector: "#qty" });
await bg.verify("login call succeeded", {
  assertion_type: "network",
  expected_value: "POST /api/login 200",
});
```

---

## Attach to your own Playwright browser (CDP)

Most existing TS Playwright suites already have a `Browser`/`Page`. Instead of
letting the engine launch its own Chromium, point it at **your** browser over the
Chrome DevTools Protocol, so the engine and your test drive **one shared browser**.

Launch Chromium with a remote‑debugging port, then `attach`:

```ts
import { chromium } from "@playwright/test";
import { Bubblegum } from "@bubblegum-ai/node";

const browser = await chromium.launch({ args: ["--remote-debugging-port=9222"] });
const page = await browser.newPage();
await page.goto("https://example.com/login");

const bg = await Bubblegum.attach({ cdpEndpoint: "http://localhost:9222" });
try {
  await bg.act('Enter "tom" into Username');
  await bg.act("Click Login");          // drives the page YOU opened
  await bg.verify("Dashboard is visible");
} finally {
  await bg.close();                     // disconnects; your browser keeps running
}
```

- The engine attaches to an existing page (`pageIndex`, default `0`) and **never
  creates or closes your browser/page**.
- Requires Bubblegum ≥ `0.0.6` (the engine advertises a `channel.web.cdp`
  capability); `attach()` throws a clear error against an older engine.
- CDP attach is **Chromium‑only**.

---

## Use inside `@playwright/test`

A small fixture makes Bubblegum available to every test, sharing the test's page
via CDP:

```ts
// fixtures.ts
import { test as base, chromium, type Browser } from "@playwright/test";
import { Bubblegum } from "@bubblegum-ai/node";

export const test = base.extend<{ bg: Bubblegum }>({
  bg: async ({}, use) => {
    const browser: Browser = await chromium.launch({ args: ["--remote-debugging-port=9222"] });
    const page = await browser.newPage();
    const bg = await Bubblegum.attach({ cdpEndpoint: "http://localhost:9222" });
    // expose the page too if your test wants to navigate directly:
    (bg as any).page = page;
    await use(bg);
    await bg.close();
    await browser.close();
  },
});
```

```ts
// login.spec.ts
import { test } from "./fixtures";

test("login heals a renamed button", async ({ bg }) => {
  await (bg as any).page.goto("https://example.com/login");
  await bg.act('Enter "tom" into Username');
  await bg.act("Click Login");                 // passes even if it now says "Sign In"
  const r = await bg.verify("Dashboard is visible");
  test.expect(["passed", "recovered"]).toContain(r.status);
});
```

> This is a minimal pattern — pick a free debugging port per worker if you
> parallelize. A turnkey Playwright fixture is on the roadmap.

---

## Mobile (Appium)

```ts
const bg = await Bubblegum.launch({
  channel: "mobile",
  appiumUrl: "http://127.0.0.1:4723",
  capabilities: { platformName: "Android", "appium:app": "/path/to/app.apk" },
});
try {
  await bg.act('Enter "tom" into Username');
  await bg.act("Tap Login");
  await bg.verify("Welcome");
} finally {
  await bg.close();
}
```

Mobile actions are `tap` / `type` / `scroll` / `swipe` — see the mobile grammar
in [`HOW_TO_USE_MOBILE.md`](HOW_TO_USE_MOBILE.md).

---

## Heal a stale selector

The lowest‑friction adoption path — drop Bubblegum into a legacy test only where a
selector breaks:

```ts
// old: await page.click("#login-btn");   // selector now stale
const r = await bg.recover({ failedSelector: "#login-btn", intent: "Click Login" });
// r.status === "recovered" when Bubblegum healed it
```

---

## Error handling

Engine/transport failures surface as a typed `BridgeError` carrying the JSON‑RPC
code; a *step* that fails comes back as a `StepResult` with `status: "failed"`
(not a throw), mirroring the Python SDK.

```ts
import { BridgeError } from "@bubblegum-ai/node";

try {
  const r = await bg.act("Click the Frobnicate button");
  if (r.status === "failed") console.error(r.error?.message);
} catch (err) {
  if (err instanceof BridgeError) console.error(`bridge error ${err.code}: ${err.message}`);
}
```

---

## Compatibility & versioning

- The client negotiates with the engine on `launch()`/`attach()` via `handshake`
  and **refuses to start against a protocol version it doesn't support**, telling
  you to upgrade — newer engines keep serving older clients (additive‑first).
- Install a **matching `bubblegum-ai`**: the npm package's major/minor track the
  engine. `@bubblegum-ai/node@0.0.6-*` expects `bubblegum-ai >= 0.0.6`.
- Pin both in CI for reproducible runs.

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `spawn python ENOENT` / bridge won't start | Python isn't on `PATH`. Install it, or pass `{ spawn: { command: "python3" } }` to `launch`/`attach`. |
| `web channel needs Playwright` | `pip install "bubblegum-ai[web]"` and `python -m playwright install chromium`. |
| `this engine does not support CDP attach` | The engine is older than `0.0.6`. Upgrade: `pip install -U bubblegum-ai`. |
| `no existing page on the CDP endpoint` | Open a page in your browser (e.g. `browser.newPage()`) before `attach()`, or check `pageIndex`. |
| `protocol vN is not supported` | Client/engine mismatch — upgrade `@bubblegum-ai/node` (or the engine) so they align. |
| mobile: `mobile session needs 'appium_url'` | Pass `appiumUrl` (and `capabilities`) to `launch({ channel: "mobile", ... })`. |

For the raw wire protocol (methods, params, error codes), see
[`bridge-protocol.md`](bridge-protocol.md). For the client API surface, see the
package README at `clients/node/README.md`.
