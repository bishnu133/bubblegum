# Acme Notes — the "first 60 seconds" sample app

A minimal three-page web app (login → dashboard → settings) used to show
what a Bubblegum test looks like with **zero selectors**. Pages are plain
HTML + a few lines of JS — no backend, no bundler.

| Page | What it demonstrates |
|---|---|
| `pages/login.html` | typing into labelled fields, button click + real navigation, error state |
| `pages/dashboard.html` | text verification, link navigation |
| `pages/settings.html` | checkbox, native select, in-page button + status text |

Demo credentials: `tester` / `bubblegum!`

## Run the standalone flow

```bash
pip install -e ".[web,test]"
python -m playwright install chromium
python examples/web/real_local/run_example.py            # headless
python examples/web/real_local/run_example.py --headed   # watch it
```

## Use it from pytest

The plugin ships a session-scoped `sample_app` fixture that serves these
pages and yields the base URL:

```python
import pytest

pytestmark = [pytest.mark.bubblegum, pytest.mark.asyncio]

async def test_login(bubblegum_web, sample_app):
    await bubblegum_web.goto(f"{sample_app}/login.html")
    await bubblegum_web.act('Enter "tester" into Username')
    await bubblegum_web.act('Enter "bubblegum!" into Password')
    await bubblegum_web.act("Click Sign in")
    assert await bubblegum_web.is_visible("Dashboard")
    bubblegum_web.assert_all_passed()
```

See `docs/getting-started-for-testers.md` for the full walkthrough.
