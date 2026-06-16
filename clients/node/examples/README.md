# `@bubblegum-ai/node` — demo files

Copy these into your project to try Bubblegum from TS/JS. Full guide:
[`docs/HOW_TO_USE_TYPESCRIPT.md`](../../../docs/HOW_TO_USE_TYPESCRIPT.md).

## Prerequisites (both demos)

The client spawns the Python engine, so Python must be available:

```bash
pip install "bubblegum-ai[web]"
python -m playwright install chromium
node --version   # 18+
```

> Behind a corporate npm registry (e.g. Nexus)? Point the scope at public npm:
> `npm config set @bubblegum-ai:registry https://registry.npmjs.org/`

## 1. Quickest try — engine-owned (`demo-engine-owned.mjs`)

The engine launches its own browser. No Playwright Test needed.

```bash
npm install @bubblegum-ai/node
node demo-engine-owned.mjs
```

You should see the login succeed and the flash message printed. Try changing
`"Click Login"` to `"Click Sign in"` — it still passes, marked `recovered`
(self-healing).

## 2. Inside your Playwright suite — CDP attach (`login.spec.ts`)

The engine drives the **same** browser your test opened, over CDP.

```bash
npm i -D @playwright/test
npm i @bubblegum-ai/node
npx playwright test login.spec.ts
```

This is the pattern to adopt in a real TS Playwright project: keep your `page`,
let Bubblegum resolve/heal steps, and mix raw Playwright calls freely.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `spawn python ENOENT` | Python not on `PATH`; or pass `{ spawn: { command: "python3" } }` to `launch`/`attach`. |
| `web channel needs Playwright` | `pip install "bubblegum-ai[web]" && python -m playwright install chromium`. |
| `this engine does not support CDP attach` | Engine < 0.0.6 — `pip install -U bubblegum-ai`. |
| `404` installing from npm | Corporate registry — set the scoped registry (above), or `--registry=https://registry.npmjs.org/`. |

Hit something else? Paste the error and we'll fix it.
