# Device cloud integration (M5)

Run the same Bubblegum mobile test on a local Appium server or on a real-device
cloud — **BrowserStack, Sauce Labs, LambdaTest, or pCloudy** — by naming the
provider. Bubblegum builds the right W3C capabilities (each cloud nests
credentials and run metadata under its own vendor namespace) and points Appium
at the provider's hub URL.

Pure capability building lives in `bubblegum/testing/cloud.py`; it is
Appium-free and unit-testable without a device or a cloud account.

## Supported providers

| Provider       | `--bubblegum-cloud-provider` | Capability namespace | Default hub URL |
| -------------- | ---------------------------- | -------------------- | --------------- |
| BrowserStack   | `browserstack`               | `bstack:options`     | `https://hub.browserstack.com/wd/hub` |
| Sauce Labs     | `saucelabs`                  | `sauce:options`      | `https://ondemand.us-west-1.saucelabs.com/wd/hub` |
| LambdaTest     | `lambdatest`                 | `LT:Options`         | `https://mobile-hub.lambdatest.com/wd/hub` |
| pCloudy        | `pcloudy`                    | `pCloudy_Options`    | `https://device.pcloudy.com/appiumcloud/wd/hub` |
| Generic (W3C)  | `generic`                    | `appium:options`     | *(none — supply a URL)* |

## Credentials

Credentials are never baked into code. They are resolved in this order:

1. explicit `username=` / `access_key=` arguments,
2. `BUBBLEGUM_CLOUD_USERNAME` / `BUBBLEGUM_CLOUD_ACCESS_KEY` (provider-agnostic),
3. the provider's own conventional env vars — `BROWSERSTACK_USERNAME` /
   `BROWSERSTACK_ACCESS_KEY`, `SAUCE_USERNAME` / `SAUCE_ACCESS_KEY`,
   `LT_USERNAME` / `LT_ACCESS_KEY`, `PCLOUDY_USERNAME` / `PCLOUDY_API_KEY`.

So a CI job that already exports `SAUCE_USERNAME`/`SAUCE_ACCESS_KEY` works with
no extra configuration.

## With the `bubblegum_mobile` pytest fixture

Add `--bubblegum-cloud-provider` to the existing mobile flags. Your
`--bubblegum-capabilities` JSON supplies the device + app; the provider
namespace and credentials are merged in automatically, and the hub URL defaults
to the provider's (override with `--bubblegum-appium-url`).

```bash
export BUBBLEGUM_CLOUD_USERNAME=...        # or BROWSERSTACK_USERNAME, etc.
export BUBBLEGUM_CLOUD_ACCESS_KEY=...

pytest tests/mobile \
  --bubblegum-cloud-provider browserstack \
  --bubblegum-capabilities '{"platformName":"Android","appium:deviceName":"Google Pixel 8","appium:app":"bs://<app-id>"}'
```

## Programmatic use

Build capabilities and a driver directly — handy outside pytest:

```python
from bubblegum.testing.cloud import build_cloud_capabilities, cloud_hub_url
from bubblegum.testing.appium_driver import create_appium_driver, create_cloud_appium_driver

# Build full caps from scratch:
caps = build_cloud_capabilities(
    provider="lambdatest",
    platform="android",
    device_name="Galaxy S23",
    app="lt://APP123",
    session_name="Login smoke",
    build_name="CI #128",
)                                   # credentials from env if omitted
driver = create_appium_driver(cloud_hub_url("lambdatest"), caps)

# …or cloud-ify a caps dict you already have and build the driver in one step:
driver = create_cloud_appium_driver("saucelabs", local_caps, session_name="Login smoke")
```

`build_cloud_capabilities` validates inputs and raises a clear `CloudConfigError`
on contradictions — e.g. a `bundle_id` with `platform="android"`, or no
app-launch strategy (`app` / `app_package`+`app_activity` / `bundle_id`).

## Notes

- The `generic` provider injects **no** credentials and has **no** default URL:
  pass `--bubblegum-appium-url` (or `BUBBLEGUM_CLOUD_APPIUM_URL`) and bake auth
  into your own caps. Use it for any other W3C-compliant Appium cloud.
- The real-environment cloud smoke harness
  (`tests/real_env/cloud/`) sources its provider namespaces and hub URLs from
  this same registry, so the two never drift.
