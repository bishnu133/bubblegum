# Distribution Strategy — PyPI + npm (and future enhancements)

This document answers three questions:

1. We plan to ship Bubblegum on **PyPI**. Can we *also* ship it on **npm** so
   teams whose automation is TypeScript/JavaScript + Playwright can use it?
2. If yes, **what is our approach** — concretely, what do we build and publish?
3. Once published, how do we **ship future enhancements** safely, at higher
   versions, without breaking the people already depending on us?

**Short answer:** Yes. We keep **one Python engine** as the single source of
truth, expose it over a tiny stable **JSON‑RPC protocol**, and publish a **thin
Node/TypeScript client** to npm that drives the same four primitives. The two
packages are version‑aligned through a shared **protocol version**, and we grow
the product with **SemVer + additive‑first protocol changes** so old clients keep
working against newer engines.

---

## 1. Can we do it? — Yes, with the right architecture

The thing that makes Bubblegum valuable is the **engine**: the tiered resolver
chain, candidate ranking, confidence scoring, self‑healing, memory cache, vision/
OCR plumbing, parser/planner, and the privacy/cost gates. That engine is a large,
maturing Python codebase (`bubblegum/core/**`). Re‑implementing it in TypeScript
would mean maintaining **two** copies of grounding logic that must stay
bit‑for‑bit equivalent forever — every resolver fix, every threshold tweak, every
benchmark would have to land twice. That is the trap to avoid.

So the design goal is: **write the engine once, consume it from anywhere.**

### Options considered

| Option | What it is | Verdict |
| --- | --- | --- |
| **A. Full TS port** | Re‑implement the whole engine in TypeScript. | ❌ Rejected for now. Doubles maintenance, guarantees drift, and the AI/vision/OCR/Appium/Playwright surface is huge. Only revisit for a small, frozen, deterministic subset (see Phase 3). |
| **B. Thin TS client + Python engine sidecar** ⭐ | npm package spawns the Python engine as a child process and talks to it over a small JSON‑RPC protocol (stdio or local socket). | ✅ **Recommended.** 100% engine reuse, ships fast, one place to fix bugs. Cost: Python must be present in the user's environment. |
| **C. Hosted/remote engine** | Engine runs as a service; clients call it over the network. | ➖ Possible later for cloud/SaaS, but adds latency, auth, and data‑egress concerns for DOM/screenshots. Not the default for a local test runner. |

We go with **Option B** as the v0.x path, and keep the door open to a **native TS
fast‑path** (Option A, scoped) once the protocol is stable.

> **Why a Node user tolerates a Python dependency:** Playwright itself already
> ships both a Node and a Python binding around the same browser protocol. Asking
> a TS team to have a Python runtime available for the Bubblegum engine is the
> same shape of dependency, and it is far cheaper than us maintaining two engines.
> We make it painless with auto‑provisioning (see "Runtime bootstrap" below).

---

## 2. The approach — what we actually build

```
┌──────────────────────────────────────────────────────────────────────┐
│  TS/JS test process (Playwright)                                       │
│                                                                        │
│   import { act, verify, extract, recover } from "@bubblegum-ai/node";  │
│   const bg = await Bubblegum.web(page);                                │
│   await bg.act("Click Login");        ──────────┐                      │
│                                                  │ JSON-RPC             │
└──────────────────────────────────────────────────┼─────────────────────┘
                                                   │ (stdio / local socket)
                                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│  bubblegum-engine  (Python, the existing package)                      │
│                                                                        │
│   bubblegum.bridge  →  GroundingEngine / resolvers / memory / vision   │
│   drives Playwright (web) or Appium (mobile) and returns StepResult    │
└──────────────────────────────────────────────────────────────────────┘
```

There are two deliverables that did **not** exist before:

### 2a. A bridge server in the Python package (new module)

Add `bubblegum/bridge/` exposing the public primitives over JSON‑RPC:

- **Transport:** newline‑delimited JSON‑RPC 2.0 over **stdio** (default, zero
  ports, easiest for a spawned child) with an optional **local TCP/Unix‑socket**
  mode for debugging.
- **Methods (1:1 with the SDK):** `session.open`, `session.close`, `act`,
  `verify`, `extract`, `recover`, `explain`, `is_visible`, `is_checked`,
  `selected_value`, `configure_runtime`, `handshake`.
- **`handshake`** returns `{ engine_version, protocol_version, capabilities[] }`
  so the client can negotiate (see §3).
- **Entry point:** `bubblegum bridge` CLI subcommand (sits beside the existing
  `record` / `repl` subcommands) and `python -m bubblegum.bridge`.
- **Returns** the existing `StepResult` serialized as JSON — it is already a
  Pydantic model, so `.model_dump(mode="json")` gives a stable wire shape for
  free. Reuse the same dict in HTML/JSON reports.

The bridge is a **thin adapter** — it does no grounding itself; it calls
`bubblegum.core.sdk.act/verify/extract/recover` and serializes the result. That
keeps all behavior in one place.

> **Who owns the browser/driver?** Two supported models:
> - **Engine‑owned (default):** the client asks the engine to launch
>   Playwright/Appium; the engine drives it end‑to‑end. Simplest, full feature
>   parity, but the page lives in the Python process.
> - **Client‑owned (advanced):** the TS test already has a Playwright `Page`. The
>   client passes a **CDP endpoint / browser‑ws‑endpoint** in `session.open`, and
>   the engine attaches Playwright‑Python to that same browser over CDP, so the
>   TS test and the engine share one browser. This is the model that makes
>   Bubblegum feel native inside an existing TS Playwright suite.
>
> We ship engine‑owned first (works immediately) and add client‑owned CDP attach
> as a fast follow, because that is the integration TS teams will actually want.

### 2b. A Node/TypeScript client (new npm package)

Publish **`@bubblegum-ai/node`** (scoped) — a small, typed wrapper:

- Spawns/locates the Python engine, performs the `handshake`, and proxies the
  primitives with the **same names and semantics** as the Python SDK.
- Ships full **TypeScript types** generated from the Pydantic schemas (one source
  of truth — export JSON Schema from Pydantic, codegen `.d.ts`), so `StepResult`,
  `ResolvedTarget`, etc. are typed identically on both sides.
- Mirrors the ergonomic surface: `Bubblegum.web(page)` / `Bubblegum.mobile(driver)`,
  `bg.act/verify/extract/recover`, `assertAllPassed()`, `summary()`.
- **Runtime bootstrap:** on first use, detect a usable Python (≥3.11) and the
  `bubblegum-ai` package; if missing, either (a) auto‑create a managed venv and
  `pip install bubblegum-ai==<pinned>`, or (b) print one clear remediation line.
  Pin the engine version the npm package was built against.

Example target API (intentionally parallel to the Python guide):

```ts
import { test } from "@playwright/test";
import { Bubblegum } from "@bubblegum-ai/node";

test("login", async ({ page }) => {
  const bg = await Bubblegum.web(page);            // attaches the engine to this page
  await bg.act('Enter "tomsmith" into Username');
  await bg.act('Enter "SuperSecretPassword!" into Password');
  await bg.act("Click Login");
  await bg.verify("You logged into a secure area");
  bg.assertAllPassed();
});
```

The same `recover()` adoption path works for legacy TS tests:

```ts
// old: await page.click("#login-btn");   // selector now stale
const r = await bg.recover({ failedSelector: "#login-btn", intent: "Click Login" });
// r.status === "recovered" when Bubblegum healed it
```

### What we are NOT doing (yet)

- Not re‑implementing resolvers/grounding in TS.
- Not requiring a network service or API keys for the bridge itself (the engine
  still only calls a model provider when the AI tier is opted in, exactly as today).
- Not changing any existing Python public API — the bridge is purely additive.

---

## 3. Shipping future enhancements (versioning that won't bite us)

We version **three things**, and keep them honest:

| Artifact | Versioning | Example |
| --- | --- | --- |
| **Engine** (`bubblegum-ai` on PyPI) | SemVer | `1.4.0` |
| **Node client** (`@bubblegum-ai/node` on npm) | SemVer, **major aligned** with the engine | `1.4.x` |
| **Bridge protocol** (`PROTOCOL_VERSION`) | Integer, **additive‑first** | `3` |

### Rule 1 — SemVer, and the public contract is the four primitives + `StepResult`

- **MAJOR** (`2.0.0`): a breaking change to a primitive's signature, the
  `StepResult` shape, config keys, or the protocol in a non‑backward‑compatible
  way.
- **MINOR** (`1.4.0`): new resolvers, new actions, new `assertion_type`s, new
  optional kwargs/fields, new protocol methods. **Additive only.**
- **PATCH** (`1.4.1`): bug fixes, accuracy/ranking tuning, doc fixes — no
  surface change.

Today the engine is `0.0.5a0` (alpha, pre‑1.0), so the `0.x` "anything may move"
rule applies and lets us iterate. **`1.0.0` is the moment we freeze the four
primitives + `StepResult` as a contract** — that is the version to cut once the
bridge protocol and the npm client have shipped and stabilized.

### Rule 2 — the protocol negotiates, so old clients keep working

`handshake` exchanges `protocol_version` and a `capabilities[]` list. The client
asks for what it needs; the engine answers with what it supports:

- **Additive change** (new method, new optional field) → bump
  `PROTOCOL_VERSION`, advertise a new capability flag, but keep every old method/
  field working. An old client simply doesn't call the new method. → **engine
  MINOR**, no client change required.
- **Deprecation** → keep the old method for **at least one MAJOR**, return a
  `deprecation` warning field, document the replacement.
- **Breaking change** → only at an engine MAJOR; the client refuses to start with
  a crisp "engine X needs client ≥ Y" message instead of misbehaving.

This is the key to "update the package with new implementation later": new engine
features ride in as **new capabilities behind the handshake**, so a v1.4 engine
serves both a v1.4 client and an old v1.1 client. We never strand a user mid‑suite.

### Rule 3 — version skew is detected, never silently wrong

The client pins a **compatible engine range** (`bubblegum-ai >=1.4,<2`). On
`handshake` it checks `protocol_version` is in range and fails fast with a clear
upgrade instruction otherwise. The auto‑bootstrap installs the pinned engine to
avoid skew in the common case.

### Forward‑looking release ladder (illustrative)

| Version | Theme | Notes |
| --- | --- | --- |
| `0.0.5‑alpha` | Current | Engine only, GitHub pre‑release distribution. |
| `0.1.0` | **PyPI publish + bridge MVP** | Publish `bubblegum-ai` to PyPI; land `bubblegum/bridge` (stdio JSON‑RPC), `bubblegum bridge` CLI, `PROTOCOL_VERSION = 1`. No SDK breakage. |
| `0.2.0` | **npm client MVP** | Publish `@bubblegum-ai/node` (engine‑owned browser), generated TS types, parity test suite (same scenarios drive both bindings). |
| `0.3.0` | **Client‑owned CDP attach** | TS test shares its own Playwright `Page` with the engine over CDP — the "feels native" integration. `PROTOCOL_VERSION = 2`. |
| `0.4.0` | **Mobile over the bridge** | Appium driver handle/endpoint passed across the bridge; mobile parity for Node. |
| `1.0.0` | **Stable contract** | Freeze the four primitives + `StepResult` + protocol. Dual PyPI+npm release becomes the supported, semver‑guaranteed surface. |
| `1.x` | **Enhancements, additive** | New resolvers/actions/assertions ship as MINORs behind capability flags; both bindings benefit with zero re‑port. |
| `2.0.0` | **Next major** | Only if/when a breaking change is genuinely required; one MAJOR of deprecation runway precedes it. |
| *(later, optional)* | **Phase 3 native TS fast‑path** | Re‑implement *only* the frozen deterministic tiers (exact/fuzzy text, memory cache) in TS for zero‑Python installs, gated behind the same protocol/contract so behavior stays identical. AI/vision/OCR/mobile continue to route to the engine. |

### Release mechanics (dual publish)

- **Single source version** read from `pyproject.toml`; the npm `package.json`
  major/minor are kept in lockstep by a release script (a `version-check` CI gate
  fails the build if they diverge).
- **CI tags drive both publishes:** a `vX.Y.Z` tag runs
  `python -m build && twine upload` (PyPI, via `publish-check.yml`) **and**
  `npm publish` for `@bubblegum-ai/node`. Both behind the existing pre‑release
  gates (`scripts/validate_package.py`, benchmarks) plus a **cross‑binding parity
  job** that runs the same scenario set through Python and Node and diffs the
  `StepResult`s.
- **CHANGELOG** gets one entry per release noting engine + client + protocol
  versions and any new capability flags.
- Pre‑1.0 we can publish under npm `next`/PyPI pre‑release tags and TestPyPI to
  de‑risk, exactly as the current `RELEASE_CHECKLIST.md` already anticipates for
  PyPI.

---

## Summary

- **Yes**, we can serve Python *and* TS/JS users from one product.
- **How:** keep the Python engine as the single source of truth, expose it over a
  tiny JSON‑RPC bridge, and publish a thin, typed Node client to npm that drives
  the same four primitives. Avoid a second engine.
- **Future‑proofing:** SemVer with a frozen primitive/`StepResult` contract at
  `1.0`, plus an **additive‑first, capability‑negotiated protocol** so newer
  engines keep serving older clients — new implementation lands as new
  capabilities at higher MINOR/MAJOR versions without breaking anyone.

> This is a design/strategy document. No engine code changes ship with it; the
> bridge module and npm client are scoped as the `0.1.0`/`0.2.0` slices above.
