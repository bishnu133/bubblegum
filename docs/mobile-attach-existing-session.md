# Mobile: attach Bubblegum to an Appium session your test already drives

Drop Bubblegum into **one step** of an existing WebdriverIO + Appium test (local
or on a cloud device farm) as a try/catch fallback: when a normal locator fails,
Bubblegum finds the element by its visible text and taps it — no locator
maintenance. This works on iOS as well as Android.

Requires **bubblegum-ai `0.0.6a56`+** (engine) and **`@bubblegum-ai/node`
`0.0.6-alpha.11`+** (TS client).

> All values below (hosts, labels, file names) are **placeholders** — replace
> them with your own. Nothing here is app-specific.

---

## Why two features are involved

1. **iOS grounding.** The mobile resolver reads XCUITest attributes
   (`label` / `name` / `value` / `type`) and matches them the same way it does
   Android's, so `act("Tap Continue")` resolves an element by its visible label.
   This helps the common React-Native-iOS case where a `testID` does not survive
   as a usable iOS locator but the visible label does.

2. **Attach to an existing session.** Cloud device farms typically allow **one
   Appium session per device**. Your test already holds it, so Bubblegum cannot
   open a second one — it must *reuse* your session by id.
   `attachMobile()` does that and **never quits your session** (your test keeps
   ownership of teardown).

Both run **on-device via the XML hierarchy — no screenshot or UI text leaves the
machine**, so nothing is sent to an external service. The AI tier only engages
if you explicitly configure a provider; leave it off to keep everything local.

---

## Setup (local, no CI/Docker changes)

The Node client spawns a small Python "engine" over stdio; install both on the
machine that runs the test.

```bash
# Python engine (3.11+), with the Appium client
pip install "bubblegum-ai[mobile]==0.0.6a57"

# TS client, in your WebdriverIO project
npm install @bubblegum-ai/node@0.0.6-alpha.11
```

By default the client spawns the engine as `python -m bubblegum.bridge`, so if
that `python` has `bubblegum-ai` installed, no extra config is needed. For a
specific interpreter (venv/pyenv), pass the `spawn` option shown below.

---

## Pattern 1 — a single flaky step (try/catch)

```ts
import { Bubblegum } from "@bubblegum-ai/node";

try {
  // Your existing step — unchanged; still the fast path when the locator works.
  await (await locators.someButton).click();
} catch (err) {
  const bg = await Bubblegum.attachMobile({
    appiumUrl: "https://appium.example.com/wd/hub", // your Appium/cloud hub
    existingSessionId: browser.sessionId,            // reuse THIS running session
    capabilities: { platformName: "iOS" },
    // Only if the engine isn't the default `python` on PATH:
    // spawn: { command: "/path/to/venv/bin/python", args: ["-m", "bubblegum.bridge"] },
  });
  try {
    const r = await bg.act("Tap Continue");          // use the visible wording
    if (r.status !== "passed" && r.status !== "recovered") {
      throw new Error(`Bubblegum could not tap it: ${r.error?.message ?? r.status}`);
    }
  } finally {
    await bg.close(); // closes the engine wrapper only — your session stays up
  }
}
```

Notes:
- `browser.sessionId` and the Appium URL come from your live session; adjust the
  URL to however your `browser` is configured.
- Use the **on-screen wording** in `act(...)`, not a testID — that is the point.

---

## Pattern 2 — optional dialogs (e.g. an OS permission "Allow" popup)

System permission alerts are *optional* (may not appear) and often have a
lookalike button next to the one you want (e.g. "Allow" beside "Don't Allow", both
containing "allow"). Two things make this safe:

- **Only act if it's on screen.** `preflight()` is a dry-run resolve that executes
  nothing.
- **Exact label wins.** As of engine `0.0.6a57`, an exact "Allow" outranks a
  partial "Don't Allow", so `act("Tap Allow")` never taps deny.

Because a permission alert is a **system (springboard) alert**, make sure your
WDA session surfaces it in the page source (the XCUITest default). If your caps
set `autoAcceptAlerts` / `autoDismissAlerts`, the OS handles the alert before any
locator can see it — turn those off for this to apply.

```ts
// Tap by visible text only if present. Returns whether it tapped.
async function tapIfPresent(bg: Bubblegum, phrase: string): Promise<boolean> {
  const [pf] = await bg.preflight([`Tap ${phrase}`]); // resolve-only, no tap
  if (!pf.ok) return false;                            // not on screen
  const r = await bg.act(`Tap ${phrase}`);
  return r.status === "passed" || r.status === "recovered";
}

async function handlePermissions(browser) {
  if (!browser.isIOS) return;
  const bg = await Bubblegum.attachMobile({
    appiumUrl: "https://appium.example.com/wd/hub",
    existingSessionId: browser.sessionId,
    capabilities: { platformName: "iOS" },
  });
  try {
    while (await tapIfPresent(bg, "Allow")) { await browser.pause(300); } // repeat prompts
    await tapIfPresent(bg, "OK");
  } finally {
    await bg.close();
  }
}
```

---

## How to tell it worked

`act(...)` returns a `StepResult`:

- `status: "passed"` → resolved and tapped. `r.target.ref` shows the XPath used
  (e.g. `//XCUIElementTypeButton[@label='Continue']`) and `r.target.resolver_name`
  is `appium_hierarchy`.
- `status: "failed"` → no match; `r.error.message` explains why. Try the exact
  visible label, or `bg.preflight(["Tap Continue"])` to inspect candidates.

---

## Scope / caveats

- Wire one step first; once you trust it, the same `attachMobile()` handle can
  drive other steps in the same test.
- The attach reuses your session by intercepting Appium's `newSession`; it is
  marked experimental. If a provider proxies Appium unusually and attach fails,
  capture the error and fall back to your original failure so the test still
  reports honestly.
- No AI/LLM is used unless you configure a provider.
