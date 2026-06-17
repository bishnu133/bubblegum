// Smoke test for the CommonJS build: a plain `require()` (as used by Jest's
// default runtime, ts-node in CJS mode, or any CommonJS script) must resolve
// the package and expose the public surface. This guards the dual-build wiring
// (exports "require" condition + dist/cjs "type": "commonjs" marker).
const { test } = require("node:test");
const assert = require("node:assert/strict");

const pkg = require("../dist/cjs/index.js");

test("CJS require() exposes the public API", () => {
  assert.equal(typeof pkg.Bubblegum, "function");
  assert.equal(typeof pkg.BridgeClient, "function");
  assert.equal(typeof pkg.BridgeError, "function");
  assert.equal(typeof pkg.spawnBridgeTransport, "function");
  assert.equal(typeof pkg.PROTOCOL_VERSION, "number");
});
