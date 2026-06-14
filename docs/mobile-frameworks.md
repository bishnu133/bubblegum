# Mobile UI framework detection (M4)

Bubblegum detects the app's **UI toolkit** so the mobile hierarchy resolver can
tune how it matches elements. Detection is heuristic and signature-based — it
reads class/package tokens from the Appium hierarchy plus the platform — and is
surfaced at `app_state["ui_framework"]` (and stamped onto each resolved
candidate's `metadata["ui_framework"]`).

This is distinct from `app_state["framework_detection"]`, which classifies the
*automation surface* (native / webview / hybrid) and the Appium driver.

## Detected frameworks

| Framework        | Signal                                                        | Confidence |
| ---------------- | ------------------------------------------------------------- | ---------- |
| `jetpack_compose`| `androidx.compose…` (`AndroidComposeView`/`ComposeView`)      | 0.9        |
| `flutter`        | `io.flutter…` / `FlutterView`                                 | 0.9        |
| `react_native`   | `com.facebook.react…`, `ReactRootView`/`ReactViewGroup`; iOS `RCTView…` | 0.9 |
| `swiftui`        | iOS `_UIHostingView` / `…HostingController` / `SwiftUI…`       | 0.8        |
| `native_android` | Android with no toolkit signature                              | 0.6        |
| `native_ios`     | iOS with no toolkit signature                                 | 0.6        |
| `unknown`        | no platform and no hierarchy signals                          | 0.0        |

## Resolution tuning

The tuning is **conservative and additive** — it never lowers a score that
worked before:

- **Compose / React Native** render tappable controls as *generic clickable*
  `View`/`ViewGroup` nodes whose label lives in `content-desc`. The resolver
  scores a clickable generic node as a real control for tap/click (role match
  `0.9` instead of the default `0.4`), so it isn't out-ranked by incidental
  `TextView`s. Native scoring is untouched.

## Known limits (reported honestly, not worked around)

- **Flutter** renders to a single canvas; the native hierarchy is **opaque**
  unless the app enables accessibility (or you drive it via the Flutter driver).
  Detection flags `flutter` and attaches `limits: ["flutter_semantics_required"]`
  + a warning, but element resolution is best-effort and may find nothing
  without accessibility enabled. The Flutter-driver path is intentionally out of
  scope for M4 (heuristic detection only).
- **SwiftUI vs UIKit**: XCUITest exposes both similarly, so a SwiftUI app
  without a clear hosting-view signature is reported as `native_ios` with an
  `ios_native_toolkit_ambiguous` warning rather than guessed.

## Verifying

- Unit tests (`tests/unit/test_ui_framework_detector.py`) cover detection across
  representative hierarchies and the resolver tuning — no device needed.
- `tests/integration/test_ui_framework_appium.py` (`--appium`) confirms the
  adapter populates `app_state["ui_framework"]` from a live device.
