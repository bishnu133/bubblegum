/**
 * login.spec.ts — demo of @bubblegum-ai/node inside @playwright/test, using CDP
 * attach so the engine drives the SAME browser your test opened.
 *
 * Prerequisites:
 *   npm i -D @playwright/test
 *   npm i @bubblegum-ai/node
 *   pip install "bubblegum-ai[web]" && python -m playwright install chromium
 *
 * Run:
 *   npx playwright test login.spec.ts
 *
 * Notes:
 * - We launch a Chromium with a fixed remote-debugging port and `attach` to it.
 *   If you run tests in parallel, give each worker a unique port (see PORT).
 * - The engine attaches to the page you already opened and never closes it.
 */
import { test, expect, chromium, type Browser } from "@playwright/test";
import { Bubblegum } from "@bubblegum-ai/node";

const PORT = 9222; // unique per worker if you parallelize: 9222 + test.info().workerIndex

test("login heals a renamed button", async () => {
  const browser: Browser = await chromium.launch({
    args: [`--remote-debugging-port=${PORT}`],
  });
  const page = await browser.newPage();
  await page.goto("https://the-internet.herokuapp.com/login");

  const bg = await Bubblegum.attach({ cdpEndpoint: `http://localhost:${PORT}` });
  try {
    await bg.act('Enter "tomsmith" into Username');
    await bg.act('Enter "SuperSecretPassword!" into Password');

    // The button is labelled "Login"; Bubblegum heals "Sign in" -> "Login".
    const click = await bg.act("Click Sign in");
    expect(["passed", "recovered"]).toContain(click.status);

    const verify = await bg.verify("You logged into a secure area");
    expect(["passed", "recovered"]).toContain(verify.status);

    // The page object is still yours — mix Bubblegum and raw Playwright freely.
    await expect(page).toHaveURL(/secure/);
  } finally {
    await bg.close();      // disconnects the engine; your browser stays up
    await browser.close(); // you own the browser lifecycle
  }
});
