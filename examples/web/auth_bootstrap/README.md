# API auth bootstrap example (W1)

Skip the slow, flaky UI login. Pass an async `bootstrap` callable to
`BubblegumSession.web(page, bootstrap=...)`: it runs once on session entry,
receives the Playwright `page`, and establishes authenticated state via API
(cookies / `localStorage` / token). Your test starts already authenticated.

```python
async def login(page):
    token = await get_token_via_api("tester", "pw!")   # your real login call
    await page.context.add_cookies(
        [{"name": "session", "value": token, "url": "https://your-app.test"}]
    )

async with BubblegumSession.web(page, bootstrap=login) as s:
    await s.goto("https://your-app.test/dashboard")     # already authed
    await s.verify("Dashboard is visible")
    s.assert_all_passed()
```

Run the runnable demo:

```bash
pip install -e ".[web]" && python -m playwright install chromium
python examples/web/auth_bootstrap/run_example.py --url https://your-app.test \
    --authed-path /dashboard --expect-text Dashboard
```

Bubblegum stays provider-agnostic — you supply the API call. On mobile, pass
`bootstrap` to `BubblegumSession.mobile(driver, bootstrap=...)` and deep-link or
inject a token via the `driver` instead.
