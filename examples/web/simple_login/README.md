# Simple Login Example (Web)

This folder is a **sample structure** for local Bubblegum web validation.

Use it as a starting point, then replace placeholders with your real application values:
- Base URL
- Selectors/step mappings
- Username/password test data
- Expected success text (dashboard/welcome)

## Files
- `bubblegum.yaml`: Sample web config
- `test_login.feature`: Tester-readable login documentation (not executed in Phase 22C)
- `run_example.py`: Direct Bubblegum SDK execution script for login validation

## How to run (after local install)
From the Bubblegum repo root:

```bash
pip install -e .
python examples/web/simple_login/run_example.py
```

If needed, copy this folder to your own test workspace and edit it there.
