# Simple Login Example (Web)

This example is configured for a **real public demo app** so testers can validate local Bubblegum web behavior without private credentials.

## App
- Name: The Internet (Herokuapp demo)
- URL: https://the-internet.herokuapp.com/login
- Public demo credentials:
  - Username: `tomsmith`
  - Password: `SuperSecretPassword!`

## Files
- `bubblegum.yaml`: Web runtime configuration for this demo app.
- `test_login.feature`: Happy-path and negative-path login scenarios.

## Local setup (editable install)
From repo root:

```bash
python -m pip install -e .
```

No PyPI install is required for local validation.

## Validation notes
At Phase 22B, this folder contains runnable-like scenario assets, but there is no dedicated feature runner wired to execute this `.feature` file directly via Bubblegum CLI in this repo state. If your environment has a custom runner, point it to this folder and capture reports under `reports/web-simple-login`.
