# Mobile network-condition simulation (M6)

Test how an app behaves on a flaky connection — offline, airplane mode, or a
throttled 2G/3G link — by saying so in plain language. Like the M2 system
verbs, these are **device-level** actions with no UI element to ground: Bubblegum
recognizes them and routes them straight to the Appium driver before grounding.

```python
await s.act("go offline")            # cut all connectivity
await s.act("simulate 3g network")   # throttle to a 3G profile (emulator)
await s.act("go online")             # restore wifi + data
```

## Recognized verbs

### Connectivity (real devices + emulators)

Driven via Android `mobile: setConnectivity`.

| Say                                            | Effect |
| ---------------------------------------------- | ------ |
| `go offline` / `simulate no network` / `disconnect` | wifi off, data off, airplane on |
| `go online` / `restore network` / `reconnect`  | wifi on, data on, airplane off |
| `enable airplane mode` / `turn off flight mode`| airplane on / off |
| `turn on wifi` / `turn off wi-fi`              | wifi on / off |
| `enable data` / `turn off mobile data`         | mobile data on / off |

### Speed profiles (Android emulator only)

Mapped to the emulator `netspeed` tokens via `mobile: networkSpeed`.

| Say                                      | Profile token |
| ---------------------------------------- | ------------- |
| `simulate 2g network` / `simulate slow network` | `gsm` |
| `throttle network to edge`               | `edge` |
| `simulate 3g network`                    | `umts` |
| `set network to hsdpa`                   | `hsdpa` |
| `simulate 4g network` / `simulate lte`   | `lte` |
| `simulate 5g network` / `set network speed to full` | `full` (unthrottled) |

## Scope & honesty

- **Connectivity** is supported on real Android devices and emulators.
- **Speed throttling** is an **Android-emulator** capability (the emulator's
  network shaper). On a real device or iOS it isn't drivable through Appium, so
  the step fails with a clear message rather than silently doing nothing.
- **iOS** cannot toggle radios reliably through XCUITest, so connectivity verbs
  raise on iOS — reported honestly, not worked around.

## Parsing

Detection is **start-anchored** so real UI controls aren't hijacked: "Click the
Wi-Fi settings row" or "Verify airplane mode banner is visible" go through
normal grounding, not the network path. Anything ambiguous returns to grounding.

## Internals

- NL parsing: `bubblegum/core/mobile/network_conditions.py`
  (`parse_network_condition` → a `SystemAction` reusing the M2 type).
- Routing: `sdk.act` checks `parse_system_action` then `parse_network_condition`
  for mobile steps before grounding.
- Execution: `AppiumAdapter.execute_system_action` → `_apply_connectivity` /
  `_apply_network_speed`.
