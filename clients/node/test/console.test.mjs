import { test } from "node:test";
import assert from "node:assert/strict";
import { formatStepLine } from "../dist/esm/index.js";

const mk = (over = {}) => ({
  status: "passed", action: "Click Save",
  target: { ref: "#x", confidence: 0.9, resolver_name: "accessibility_tree", metadata: {} },
  confidence: 0.9, duration_ms: 120, error: null, ...over,
});

test("formatStepLine: plain (no color) shows status, action, resolver, timing", () => {
  const line = formatStepLine(mk(), { color: false });
  assert.match(line, /✔ PASS/);
  assert.match(line, /Click Save/);
  assert.match(line, /accessibility_tree · 0\.90 · 120ms/);
  assert.ok(!line.includes("\x1b["), "must not contain ANSI when color is off");
});

test("formatStepLine: recovered is flagged as self-healed", () => {
  const line = formatStepLine(mk({ status: "recovered" }), { color: false });
  assert.match(line, /✚ HEAL/);
  assert.match(line, /\(self-healed\)/);
});

test("formatStepLine: fallback selector is flagged", () => {
  const line = formatStepLine(
    mk({ target: { ref: "#x", confidence: 0.5, resolver_name: "fallback_selector", metadata: { fallback_selector_used: true } } }),
    { color: false },
  );
  assert.match(line, /⚠ fallback selector/);
});

test("formatStepLine: failed shows the error on a second line", () => {
  const line = formatStepLine(
    mk({ status: "failed", error: { error_type: "ResolutionFailedError", message: "no candidate" } }),
    { color: false },
  );
  assert.match(line, /✖ FAIL/);
  assert.match(line, /↳ ResolutionFailedError: no candidate/);
});

test("formatStepLine: long action is truncated to width", () => {
  const line = formatStepLine(mk({ action: "x".repeat(200) }), { color: false, width: 20, detail: false });
  assert.ok(line.includes("…"));
});
