# Mobile Local Testing Runbook (0.0.6a70–a75)

A dead-simple, copy‑paste guide to validate the new mobile features on your own
machine — **Android emulator first, then iOS simulator** — before moving to a
device farm. Everything here is plain‑English steps; no selectors, no per‑app
configuration.

## What you are validating

| Feature (version) | What to check it does |
|---|---|
| Scroll‑to‑find (a70) | `Tap "…"` finds a control that starts **below the fold** |
| Offline OCR (a71) | Grounds by on‑screen **pixels** — no cloud, works offline |
| Flutter/canvas routing (a72) | `Tap "…"` works on a **Flutter / game / canvas** screen |
| OCR verify/extract (a73) | `verify`/`extract` read a **canvas** screen's text |
| Readiness & resilience (a74) | Waits out **spinners**; clean error on **ANR/crash** |
| Hierarchy compaction (a75) | Faster grounding on **complex** screens (no behaviour change) |

---

## 0) One‑time tooling (both platforms)

```bash
# Node + Appium 2 (the automation server both platforms talk to)
npm i -g appium
appium driver install uiautomator2      # Android
# (iOS driver is installed in the iOS section — needs a Mac)

# Python 3.11+ and the Bubblegum engine with mobile + offline‑OCR support
python -m venv .venv-bubblegum
source .venv-bubblegum/bin/activate
pip install -U "bubblegum-ai[mobile,localvision]==0.0.6a75"
#   [mobile]      -> Appium-Python-Client
#   [localvision] -> RapidOCR (offline OCR) + Pillow  (this is the a71 backend)

# If you drive Bubblegum from TypeScript, also point it at this interpreter:
export BUBBLEGUM_PYTHON="$(pwd)/.venv-bubblegum/bin/python"
```

> The offline‑OCR model downloads once on first use (a few MB, bundled with
> RapidOCR). After that it runs fully offline.

Turn the new grounding on with a tiny `bubblegum.yaml` in your test folder:

```yaml
grounding:
  enable_vision: true          # turn on screenshot grounding
  vision_backend: rapidocr     # the offline, on-device OCR backend (a71)
  # These are ON by default — listed here only so you know the knobs:
  scroll_to_find: true         # a70
  canvas_auto_route: true      # a72
  mobile_hierarchy_compaction: true  # a75
```

That's the whole configuration. Nothing app‑specific.

---

## 1) Android — local emulator (works on macOS / Linux / Windows)

```bash
# a) Install Android Studio (or just the cmdline-tools) and set ANDROID_HOME.
#    Then create + boot an emulator:
sdkmanager "system-images;android-34;google_apis;x86_64"
avdmanager create avd -n bg_pixel -k "system-images;android-34;google_apis;x86_64" -d pixel_7
emulator -avd bg_pixel -no-snapshot -gpu swiftshader_indirect &
adb wait-for-device

# b) Start Appium (leave it running in its own terminal)
appium --address 127.0.0.1 --port 4723

# c) Install the app you want to test (or point caps at appPackage/appActivity)
adb install /path/to/app-debug.apk
```

Now run the smoke script from section 4 with these env vars:

```bash
export BUBBLEGUM_REAL_ENV=1
export BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723
export BUBBLEGUM_ANDROID_APP=/path/to/app-debug.apk
python mobile_smoke.py android
```

---

## 2) iOS — local simulator (macOS only)

```bash
# a) Install Xcode + Command Line Tools, then the Appium iOS driver:
appium driver install xcuitest
brew install carthage        # WebDriverAgent builds on first run

# b) Boot a simulator
xcrun simctl list devices
xcrun simctl boot "iPhone 15"
open -a Simulator

# c) Appium (same server handles both platforms)
appium --address 127.0.0.1 --port 4723
```

Run the smoke script:

```bash
export BUBBLEGUM_REAL_ENV=1
export BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723
export BUBBLEGUM_IOS_APP=/path/to/YourApp.app     # a simulator .app build
python mobile_smoke.py ios
```

> Note: network‑condition simulation (throttling/airplane) is Android‑only by
> design; on iOS it reports that honestly. Everything else — grounding,
> gestures, OCR/canvas, readiness — is validated on the simulator.

---

## 3) Which sample apps to use (per technology)

You want three kinds of screens so every new path is exercised. Any open,
license‑clean app works — suggestions:

| Screen type | Suggested app | Proves |
|---|---|---|
| **Native, long/scrollable** | Android **ApiDemos**, or your own app's settings/form | scroll‑to‑find (a70), compaction (a75) |
| **Native, simple** | any login/form screen | hierarchy grounding still precise |
| **Hybrid (WebView)** | any app wrapping a web page | WebView path unaffected |
| **Flutter / canvas / game** | the Flutter **gallery**/counter demo, or any game menu | OCR + canvas routing (a71/a72/a73) |

Keep the builds handy as `.apk` (Android) and `.app` (iOS simulator).

---

## 4) The smoke script (`mobile_smoke.py`)

Save this next to your `bubblegum.yaml`. It drives each feature with **plain
English** and prints PASS/FAIL per step. Replace the quoted labels with real
on‑screen text from your app.

```python
import os, sys, asyncio
from bubblegum import Bubblegum   # ergonomic wrapper over act/verify/extract

PLATFORM = (sys.argv[1] if len(sys.argv) > 1 else "android").lower()

CAPS = {
    "android": {
        "platformName": "Android",
        "appium:automationName": "UiAutomator2",
        "appium:app": os.environ["BUBBLEGUM_ANDROID_APP"],
        "appium:newCommandTimeout": 120,
    },
    "ios": {
        "platformName": "iOS",
        "appium:automationName": "XCUITest",
        "appium:app": os.environ["BUBBLEGUM_IOS_APP"],
        "appium:newCommandTimeout": 120,
    },
}[PLATFORM]

async def main():
    bg = await Bubblegum.open_mobile(
        appium_url=os.environ["BUBBLEGUM_APPIUM_SERVER_URL"],
        capabilities=CAPS,
    )
    try:
        # --- native + scroll-to-find (a70) ---------------------------------
        await bg.act('Tap "Settings"')                 # normal hierarchy grounding
        await bg.act('Tap "About"')                    # a70: works even if below the fold
        await bg.verify('the screen shows "Version"')  # native text_visible

        # --- canvas / Flutter (a71 + a72 + a73) ----------------------------
        # On a Flutter/game screen these route to offline OCR automatically:
        await bg.act('Tap "Play"')                     # a72: OCR + coordinate tap
        await bg.verify('the screen shows "Level 1"')  # a73: OCR text check
        score = await bg.extract('Get the score')      # a73: OCR text read
        print("extracted:", score)

        print("\n✅ smoke complete")
    finally:
        await bg.close()

asyncio.run(main())
```

> The exact `Bubblegum.open_mobile(...)` entry point matches the mobile quickstart
> in `docs/HOW_TO_USE_MOBILE.md`; if your project uses the pytest
> `bubblegum_mobile` fixture instead, drop these same `bg.act/verify/extract`
> lines into a test and run with `--bubblegum-capabilities`.

---

## 5) How to read the results

- **PASS** = the step found and acted on the element with plain English and no
  selector. That's the whole point.
- Each step's report metadata tells you **which path** resolved it:
  - `scroll_to_find` → the target was found after scrolling (a70)
  - `source: "canvas_vision"` / `canvas_ocr` → resolved by OCR on a self‑drawn
    screen (a71/a72/a73)
  - `coordinate_point` → tapped by coordinate (canvas fallback)
  - `readiness.blocker: anr|crash` on a failure → the app was wedged (a74),
    not a Bubblegum miss
- On a **Flutter** screen with vision off you'll see a clear log line:
  *"screen routed to vision but vision_backend_not_configured"* — that's your cue
  the `bubblegum.yaml` above isn't being picked up.

---

## 6) Quick troubleshooting

| Symptom | Fix |
|---|---|
| `RapidOCR is not installed` in logs | `pip install "bubblegum-ai[localvision]"` in the **same** venv Appium‑bridge uses (`BUBBLEGUM_PYTHON`) |
| Flutter step fails, log says *routed to vision but not configured* | add the `bubblegum.yaml` (`enable_vision: true`, `vision_backend: rapidocr`) next to where you run the test |
| Every step waits ~5s then proceeds | the screen has a permanent progress bar; lower `grounding.stability_timeout_ms` or set `stability_wait_enabled: false` |
| `AppNotReadyError` | the app genuinely crashed / ANR'd — relaunch it; this is a74 reporting the truth |
| Appium can't create session | check the emulator/simulator is booted (`adb devices` / `xcrun simctl list`) and the app path is correct |

---

## 7) After local passes → device farm (next phase, M‑F)

The **same** `bg.act/verify/extract` steps run on pCloudy / BrowserStack by
swapping the driver construction for `create_cloud_appium_driver(provider=…)` and
setting `BUBBLEGUM_CLOUD_*` credentials — offline OCR runs on the **runner**, so
only the screenshot travels back over the wire. We'll wire up that matrix
(native + hybrid + Flutter × Android + iOS × pCloudy + BrowserStack) in the M‑F
slice once local is green.
