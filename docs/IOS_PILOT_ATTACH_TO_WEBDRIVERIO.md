# iOS pilot — resolve a flaky click with Bubblegum, inside your WebdriverIO test

This guide shows how to drop Bubblegum into **one step** of an existing
WebdriverIO + Appium test (running on a cloud device such as pCloudy) as a
try/catch fallback: when your normal locator click fails, Bubblegum finds the
element by its human text and taps it — no locator maintenance.

It targets the reported case: `viewMyDailySummaryV2.click()` works on Android
but throws on iOS because the React-Native `testID` does not survive as a usable
iOS locator (XCUITest surfaces the visible **label** as the element `name`, not
the testID).

Requires **bubblegum-ai `0.0.6a56`+** (engine) and **`@bubblegum-ai/node`
`0.0.6-alpha.11`+** (TS client), which add iOS grounding and attach-to-existing
Appium session.

---

## Why this needs two Bubblegum features (both new in a56)

1. **iOS grounding.** Until a56, the mobile resolver read only Android
   attributes, so "find by text" returned nothing on iOS. a56 reads XCUITest
   `label` / `name` / `value` / `type` and matches the same way it does on
   Android. So `act("Tap View daily summary")` resolves the button by its
   visible label.

2. **Attach to your existing session.** pCloudy allows **one Appium session per
   device**. Your WebdriverIO test already holds it, so Bubblegum cannot open a
   second one — it must *reuse* your session by id. `attachMobile()` does exactly
   that and never quits your session (your test still owns teardown).

Both run **on-device via the XML hierarchy — no screenshot or UI text leaves the
machine**, so this pilot does not send anything to an external LLM. That keeps it
inside your data-residency constraint. (The AI tier only engages if you
explicitly configure a provider; leave it off for this pilot.)

---

## One-time setup (local, no CI/Docker changes)

Bubblegum's Node client spawns a small Python "engine" over stdio. You need both
installed on the machine that runs the test.

```bash
# 1. Python engine (3.11+). Installs the Appium client too.
pip install "bubblegum-ai[mobile]==0.0.6a56"
# ...or straight from the branch while piloting:
# pip install "git+https://github.com/bishnu133/bubblegum.git@claude/ai-automation-improvements-5a76d8#egg=bubblegum-ai[mobile]"

# 2. TS client, in your WebdriverIO project
npm install @bubblegum-ai/node@0.0.6-alpha.11
```

By default the Node client spawns the engine as `python -m bubblegum.bridge`, so
if the same `python` on your PATH has `bubblegum-ai` installed, **no extra config
is needed**. If your engine lives under a specific interpreter (venv, pyenv),
tell the client which command to spawn via the `spawn` option (see below).

> The engine talks to the **same Appium/pCloudy endpoint** your WDIO test uses,
> reusing your session id — it does not connect to the device directly.

---

## The code change — wrap just line 95

In `meallogV2.ts`, replace the single click with a try/catch that falls back to
Bubblegum only when the normal click fails:

```ts
import { Bubblegum } from "@bubblegum-ai/node";

// ... existing meallog code ...

try {
  // Your existing step — unchanged. Still the fast path on Android and
  // whenever the iOS locator happens to work.
  await (await meallogLocators.viewMyDailySummaryV2).click();
} catch (err) {
  // Fallback: let Bubblegum find & tap it by its visible text.
  const bg = await Bubblegum.attachMobile({
    appiumUrl: browser.options.path
      ? `${browser.options.protocol}://${browser.options.hostname}:${browser.options.port}${browser.options.path}`
      : "https://ship-hats.pcloudy.com/appiumcloud/wd/hub",
    existingSessionId: browser.sessionId,          // reuse THIS running session
    capabilities: { platformName: "iOS" },
    // Only if the engine isn't the default `python` on PATH:
    // spawn: { command: "/path/to/venv/bin/python", args: ["-m", "bubblegum.bridge"] },
  });
  try {
    const r = await bg.act("Tap View daily summary");
    if (r.status !== "passed" && r.status !== "recovered") {
      throw new Error(`Bubblegum could not tap it: ${r.error?.message ?? r.status}`);
    }
  } finally {
    await bg.close();   // closes the engine wrapper only — your session stays up
  }
}
```

Notes:
- `browser.sessionId` and the Appium URL come from your live WebdriverIO
  session; adjust the URL expression to however your `browser` is configured
  (the hard-coded pCloudy hub is a safe fallback).
- Use the **on-screen wording** in `act(...)` ("View daily summary"), not the
  testID. That is the whole point — you match what a user sees.
- Keep your `capabilities` minimal here; `platformName: "iOS"` is enough for the
  attach to pick the right automation.

---

## How to tell it worked

`act(...)` returns a `StepResult`:

- `status: "passed"` → Bubblegum resolved and tapped it. `r.target.ref` shows the
  XPath it used (e.g. `//XCUIElementTypeButton[@label='View daily summary']`) and
  `r.target.resolver_name` will be `appium_hierarchy`.
- `status: "failed"` → it could not find a match; `r.error.message` explains why.
  Try `bg.act("...")` with the exact visible label, or run
  `await bg.preflight(["Tap View daily summary"])` to see the candidates without
  executing.

---

## Pattern 2 — optional dialogs (iOS permission "Allow" popup)

Permission alerts (`"H365+ UAT" Would Like to Send You Notifications` → **Allow**)
are *optional*: they may or may not appear, and there is a lookalike **Don't
Allow** right next to Allow. Two things make this safe:

- **Only act if it's on screen.** Use `preflight()` (a dry-run resolve that
  executes nothing) to check presence, then `act()`.
- **Exact label wins.** As of engine `0.0.6a57` the resolver prefers the exact
  "Allow" over the partial "Don't Allow", so `act("Tap Allow")` never taps deny.

Because the permission alert is a **system (springboard) alert**, make sure your
WebdriverIO/WDA session surfaces it in the page source (the default for the
XCUITest driver). If your caps set `autoAcceptAlerts`/`autoDismissAlerts`, the OS
handles the alert before any locator — including Bubblegum — can see it; turn
those off for this to apply.

Refactor `handleiOSPermissions()` to reuse **one** attached handle (cheaper than
attaching per check):

```ts
// Helper: tap by visible text only if it's present. Returns whether it tapped.
async function tapIfPresent(bg: Bubblegum, phrase: string): Promise<boolean> {
  const [pf] = await bg.preflight([`Tap ${phrase}`]);   // resolve-only, no tap
  if (!pf.ok) return false;                              // not on screen
  const r = await bg.act(`Tap ${phrase}`);
  return r.status === "passed" || r.status === "recovered";
}

async handleiOSPermissions() {
  if (!driver.isIOS) return;
  const bg = await Bubblegum.attachMobile({
    appiumUrl: "https://ship-hats.pcloudy.com/appiumcloud/wd/hub",
    existingSessionId: browser.sessionId,
    capabilities: { platformName: "iOS" },
  });
  try {
    // Handles the notifications alert (and any repeat prompts) + a trailing OK.
    while (await tapIfPresent(bg, "Allow")) { await driver.pause(300); }
    await tapIfPresent(bg, "OK");
  } finally {
    await bg.close();
  }
}
```

This keeps your existing `userLocators.allowButton` predicate as the fast path if
you prefer try/catch instead — the same `tapIfPresent(bg, "Allow")` works as the
`catch` fallback exactly like Pattern 1.

## Scope / caveats for the pilot

- This wires **one step**. Once you trust it, the same `attachMobile()` handle
  can drive other flaky steps in the same test.
- The attach reuses your session by intercepting Appium's `newSession`; it is
  marked experimental. If your cloud provider proxies Appium in an unusual way
  and the attach fails, capture the error and fall back to your original failure
  so the test still reports honestly.
- No AI/LLM is used unless you configure a provider — leave it unset to keep
  everything on-device for data residency.
