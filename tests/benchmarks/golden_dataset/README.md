# Bubblegum Golden Benchmark Dataset

Phase 0 scaffold — 100-scenario target composition:

| Category | Target | File |
|---|---|---|
| web_standard | 50 scenarios | web_standard/scenarios.json |
| broken_selectors | 20 scenarios | broken_selectors/scenarios.json |
| changed_labels | 10 scenarios | changed_labels/scenarios.json |
| duplicate_labels | 10 scenarios | duplicate_labels/scenarios.json |
| dynamic_overlays | 10 scenarios | dynamic_overlays/scenarios.json |

## Metrics tracked per run
- Deterministic success rate (Tier 1-2 resolver win rate)
- AI recovery success rate (Tier 3 resolver win rate)
- False positive rate (wrong element selected)
- Ambiguous target rate (AmbiguousTargetError frequency)
- Average step latency per resolver (ms)
- Model calls per scenario (cost proxy)
- Cost per test run (USD estimate via token counting)
- Resolver win distribution by action type

## Adding scenarios
Each scenarios.json is a list of scenario objects.
Required fields: id, instruction, channel, action_type.
See existing entries for optional fields (failed_selector, expected_resolver, expected_error).