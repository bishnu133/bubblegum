// demo-engine-owned.mjs — the quickest way to try @bubblegum-ai/node.
//
// The engine launches its own browser (no Playwright Test, no CDP). Run:
//   npm install @bubblegum-ai/node
//   pip install "bubblegum-ai[web]" && python -m playwright install chromium
//   node demo-engine-owned.mjs
//
// Demonstrates: natural-language steps + self-healing. The button on the demo
// site says "Login"; try changing "Click Login" to "Click Sign in" and the
// fuzzy tier still heals it (status becomes "recovered").

import { Bubblegum } from "@bubblegum-ai/node";

const bg = await Bubblegum.launch({
  url: "https://the-internet.herokuapp.com/login",
  headless: true, // set false to watch it
});

try {
  await bg.act('Enter "tomsmith" into Username');
  await bg.act('Enter "SuperSecretPassword!" into Password');
  await bg.act("Click Login");

  const r = await bg.verify("You logged into a secure area");
  console.log(`verify -> ${r.status} (confidence ${r.confidence})`);

  const msg = await bg.extract("Get the flash message");
  console.log("flash:", msg.target?.metadata?.extracted_value?.trim());

  console.log("summary:", bg.summary ? await bg.summary() : "(n/a)");
} finally {
  await bg.close();
}
