// Browser/Python-free tests: drive the client + session against an in-memory
// mock transport that auto-responds, exercising JSON-RPC framing, id
// correlation, error mapping, protocol negotiation, and the session proxies.
//
// Run after build (`npm test` builds first): imports the compiled dist.
import { test } from "node:test";
import assert from "node:assert/strict";

import { BridgeClient, Bubblegum, BridgeError } from "../dist/esm/index.js";

/** A Transport that records sent lines and auto-replies via a method->handler map. */
function makeMock(handlers = {}) {
  let lineCb = () => {};
  let closeCb = () => {};
  const sent = [];
  const transport = {
    send(line) {
      sent.push(line);
      const msg = JSON.parse(line);
      if (msg.id == null) return;
      queueMicrotask(() => {
        const handler = handlers[msg.method];
        if (!handler) {
          lineCb(JSON.stringify({
            jsonrpc: "2.0",
            id: msg.id,
            error: { code: -32601, message: `method not found: ${msg.method}` },
          }));
          return;
        }
        const out = handler(msg.params ?? {});
        const body = out && out.__error
          ? { jsonrpc: "2.0", id: msg.id, error: out.__error }
          : { jsonrpc: "2.0", id: msg.id, result: out };
        lineCb(JSON.stringify(body));
      });
    },
    onLine(cb) { lineCb = cb; },
    onClose(cb) { closeCb = cb; },
    async close() { closeCb(); },
  };
  return { transport, sent, methods: () => sent.map((s) => JSON.parse(s)) };
}

const HANDSHAKE = () => ({ engine_version: "0.0.6a0", protocol_version: 1, capabilities: ["act", "channel.web"] });

test("request frames JSON-RPC 2.0 and resolves the result", async () => {
  const m = makeMock({ ping: () => ({ ok: true }) });
  const client = new BridgeClient({ transport: m.transport });
  const res = await client.request("ping", { x: 1 });
  assert.deepEqual(res, { ok: true });
  const req = m.methods()[0];
  assert.equal(req.jsonrpc, "2.0");
  assert.equal(req.method, "ping");
  assert.deepEqual(req.params, { x: 1 });
  assert.equal(typeof req.id, "number");
});

test("an error response rejects with a BridgeError carrying the code", async () => {
  const m = makeMock({ act: () => ({ __error: { code: -32001, message: "no open session" } }) });
  const client = new BridgeClient({ transport: m.transport });
  await assert.rejects(
    client.request("act"),
    (e) => e instanceof BridgeError && e.code === -32001 && /no open session/.test(e.message),
  );
});

test("handshake rejects an unsupported protocol version", async () => {
  const m = makeMock({ handshake: () => ({ engine_version: "9.9", protocol_version: 999, capabilities: [] }) });
  const client = new BridgeClient({ transport: m.transport });
  await assert.rejects(client.handshake(), (e) => e instanceof BridgeError);
});

test("handshake stores info and exposes capabilities", async () => {
  const m = makeMock({ handshake: HANDSHAKE });
  const client = new BridgeClient({ transport: m.transport });
  const hs = await client.handshake();
  assert.equal(hs.protocol_version, 1);
  assert.ok(client.hasCapability("act"));
  assert.equal(client.hasCapability("nope"), false);
});

test("Bubblegum.launch opens an engine-owned session and act() proxies it", async () => {
  const m = makeMock({
    handshake: HANDSHAKE,
    "session.open": (p) => {
      assert.equal(p.channel, "web");
      assert.equal(p.url, "http://x");
      return { session_id: "sid-1" };
    },
    act: (p) => ({ status: "passed", action: p.instruction, target: null, confidence: 0.9, duration_ms: 1 }),
  });
  const bg = await Bubblegum.launch({ transport: m.transport, url: "http://x" });
  const r = await bg.act("Click Login");
  assert.equal(r.status, "passed");
  assert.equal(r.action, "Click Login");
  const actReq = m.methods().find((x) => x.method === "act");
  assert.equal(actReq.params.session_id, "sid-1");
  assert.equal(actReq.params.instruction, "Click Login");
});

test("recover maps camelCase args to the wire snake_case", async () => {
  let captured;
  const m = makeMock({
    handshake: HANDSHAKE,
    "session.open": () => ({ session_id: "s" }),
    recover: (p) => {
      captured = p;
      return { status: "recovered", action: p.intent, target: null, confidence: 1, duration_ms: 1 };
    },
  });
  const bg = await Bubblegum.launch({ transport: m.transport });
  const r = await bg.recover({ failedSelector: "#old", intent: "Click Login" });
  assert.equal(r.status, "recovered");
  assert.equal(captured.failed_selector, "#old");
  assert.equal(captured.intent, "Click Login");
});

test("state probes unwrap the {value} envelope", async () => {
  const m = makeMock({
    handshake: HANDSHAKE,
    "session.open": () => ({ session_id: "s" }),
    is_visible: () => ({ value: true }),
    selected_value: () => ({ value: "FR" }),
  });
  const bg = await Bubblegum.launch({ transport: m.transport });
  assert.equal(await bg.isVisible("Welcome"), true);
  assert.equal(await bg.selectedValue("Country"), "FR");
});

test("attach() sends cdp_endpoint + page_index when the engine supports it", async () => {
  let openParams;
  const m = makeMock({
    handshake: () => ({ engine_version: "0.0.6a0", protocol_version: 1, capabilities: ["act", "channel.web.cdp"] }),
    "session.open": (p) => {
      openParams = p;
      return { session_id: "sid-cdp" };
    },
    act: (p) => ({ status: "passed", action: p.instruction, target: null, confidence: 1, duration_ms: 1 }),
  });
  const bg = await Bubblegum.attach({ transport: m.transport, cdpEndpoint: "http://localhost:9222", pageIndex: 1 });
  await bg.act("Click Login");
  assert.equal(openParams.channel, "web");
  assert.equal(openParams.cdp_endpoint, "http://localhost:9222");
  assert.equal(openParams.page_index, 1);
});

test("attach() rejects when the engine lacks the channel.web.cdp capability", async () => {
  const m = makeMock({
    handshake: () => ({ engine_version: "0.0.5a0", protocol_version: 1, capabilities: ["act"] }), // no channel.web.cdp
    "session.open": () => ({ session_id: "x" }),
  });
  await assert.rejects(
    Bubblegum.attach({ transport: m.transport, cdpEndpoint: "http://localhost:9222" }),
    (e) => e instanceof BridgeError && /CDP attach/.test(e.message),
  );
});

test("attachMobile() sends existing_session_id on the mobile channel when supported", async () => {
  let openParams;
  const m = makeMock({
    handshake: () => ({ engine_version: "0.0.6a0", protocol_version: 1, capabilities: ["act", "channel.mobile.attach"] }),
    "session.open": (p) => {
      openParams = p;
      return { session_id: "sid-mob" };
    },
    act: (p) => ({ status: "passed", action: p.instruction, target: null, confidence: 1, duration_ms: 1 }),
  });
  const bg = await Bubblegum.attachMobile({
    transport: m.transport,
    appiumUrl: "http://host/wd/hub",
    existingSessionId: "live-42",
    capabilities: { platformName: "iOS" },
  });
  await bg.act("Tap View daily summary");
  assert.equal(openParams.channel, "mobile");
  assert.equal(openParams.appium_url, "http://host/wd/hub");
  assert.equal(openParams.existing_session_id, "live-42");
  assert.deepEqual(openParams.capabilities, { platformName: "iOS" });
});

test("attachMobile() rejects when the engine lacks the channel.mobile.attach capability", async () => {
  const m = makeMock({
    handshake: () => ({ engine_version: "0.0.5a0", protocol_version: 1, capabilities: ["act", "channel.mobile"] }), // no attach
    "session.open": () => ({ session_id: "x" }),
  });
  await assert.rejects(
    Bubblegum.attachMobile({ transport: m.transport, appiumUrl: "http://h", existingSessionId: "s" }),
    (e) => e instanceof BridgeError && /channel\.mobile\.attach/.test(e.message),
  );
});

test("report() maps options to report.write and resolves written paths", async () => {
  let captured;
  const m = makeMock({
    handshake: () => ({ engine_version: "0.0.6", protocol_version: 1, capabilities: ["act", "report.write"] }),
    "session.open": () => ({ session_id: "s" }),
    "report.write": (p) => {
      captured = p;
      return { written: { html: "/abs/run.html", allure: "/abs/allure-results" }, steps: 3 };
    },
  });
  const bg = await Bubblegum.launch({ transport: m.transport });
  const r = await bg.report({ html: "run.html", allure: true, title: "My Run", suiteName: "h365" });
  assert.equal(r.steps, 3);
  assert.equal(r.written.html, "/abs/run.html");
  // string path passes through; `true` becomes the default dir name; camelCase -> snake_case.
  assert.equal(captured.html, "run.html");
  assert.equal(captured.allure, "allure-results");
  assert.equal(captured.title, "My Run");
  assert.equal(captured.suite_name, "h365");
  assert.equal(captured.session_id, "s");
});

test("report() throws when the engine lacks the report.write capability", async () => {
  const m = makeMock({
    handshake: HANDSHAKE, // no report.write
    "session.open": () => ({ session_id: "s" }),
  });
  const bg = await Bubblegum.launch({ transport: m.transport });
  await assert.throws(
    () => bg.report({ html: true }),
    (e) => e instanceof BridgeError && /report generation/.test(e.message),
  );
});

test("close() closes the session then the bridge", async () => {
  const m = makeMock({
    handshake: HANDSHAKE,
    "session.open": () => ({ session_id: "s" }),
    "session.close": () => ({ closed: true }),
  });
  const bg = await Bubblegum.launch({ transport: m.transport });
  await bg.close();
  assert.ok(m.methods().some((x) => x.method === "session.close"));
});

test("verifyTable() forwards assertion_type=table with columns/row/cell", async () => {
  const m = makeMock({
    handshake: HANDSHAKE,
    "session.open": () => ({ session_id: "sid-t" }),
    verify: (p) => ({
      status: "passed", action: p.instruction, target: null,
      confidence: 1, duration_ms: 1, __opts: p.options,
    }),
  });
  const bg = await Bubblegum.launch({ transport: m.transport, url: "http://x" });
  await bg.verifyTable({
    columns: ["PPHID", "Account Status"],
    row: { Name: "Bishnu Test Account" },
    cell: { "Account Status": "Active" },
    timeoutMs: 2000,
  });
  const req = m.methods().find((x) => x.method === "verify");
  assert.equal(req.params.options.assertion_type, "table");
  assert.deepEqual(req.params.options.columns, ["PPHID", "Account Status"]);
  assert.deepEqual(req.params.options.row, { Name: "Bishnu Test Account" });
  assert.deepEqual(req.params.options.cell, { "Account Status": "Active" });
  assert.equal(req.params.options.timeout_ms, 2000);
});

test("clickInTable() forwards column + row (index word) for a cell click", async () => {
  const m = makeMock({
    handshake: HANDSHAKE,
    "session.open": () => ({ session_id: "sid-c" }),
    act: (p) => ({ status: "passed", action: p.instruction, target: null, confidence: 1, duration_ms: 1 }),
  });
  const bg = await Bubblegum.launch({ transport: m.transport, url: "http://x" });
  await bg.clickInTable({ column: "PPHID", row: "first" });
  const req = m.methods().find((x) => x.method === "act");
  assert.equal(req.params.options.action_type, "click");
  assert.equal(req.params.options.column, "PPHID");
  assert.equal(req.params.options.row, "first");
});

test("clickInTable() forwards rowMatch as row_match", async () => {
  const m = makeMock({
    handshake: HANDSHAKE,
    "session.open": () => ({ session_id: "sid-c2" }),
    act: (p) => ({ status: "passed", action: p.instruction, target: null, confidence: 1, duration_ms: 1 }),
  });
  const bg = await Bubblegum.launch({ transport: m.transport, url: "http://x" });
  await bg.clickInTable({ column: "PPHID", rowMatch: { Name: "Bishnu Test Account" } });
  const req = m.methods().find((x) => x.method === "act");
  assert.deepEqual(req.params.options.row_match, { Name: "Bishnu Test Account" });
  assert.equal(req.params.options.row, undefined);
});

test("clickLink() forwards link_text", async () => {
  const m = makeMock({
    handshake: HANDSHAKE,
    "session.open": () => ({ session_id: "sid-l" }),
    act: (p) => ({ status: "passed", action: p.instruction, target: null, confidence: 1, duration_ms: 1 }),
  });
  const bg = await Bubblegum.launch({ transport: m.transport, url: "http://x" });
  await bg.clickLink("9ca87fc7-bacc", { exact: true });
  const req = m.methods().find((x) => x.method === "act");
  assert.equal(req.params.options.action_type, "click");
  assert.equal(req.params.options.link_text, "9ca87fc7-bacc");
  assert.equal(req.params.options.exact, true);
});

test("preflight() dry-runs each step and reports ok/failed without executing", async () => {
  const m = makeMock({
    handshake: HANDSHAKE,
    "session.open": () => ({ session_id: "sid-pf" }),
    act: (p) => {
      assert.equal(p.options.dry_run, true); // never executes
      if (p.instruction.includes("Bad")) {
        return { status: "failed", action: p.instruction, target: null, confidence: 0,
                 duration_ms: 1, error: { error_type: "LowConfidenceError", message: "no match" } };
      }
      return { status: "dry_run", action: p.instruction,
               target: { ref: "role=button", confidence: 0.9, resolver_name: "accessibility_tree" },
               confidence: 0.9, duration_ms: 1 };
    },
  });
  const bg = await Bubblegum.launch({ transport: m.transport, url: "http://x" });
  const report = await bg.preflight([
    'Click the "Update account status" button',
    { instruction: "click cell", options: { column: "PPHID", row: "first" } },
    "Click the Bad thing",
  ]);
  assert.equal(report.length, 3);
  assert.equal(report[0].ok, true);
  assert.equal(report[0].resolver, "accessibility_tree");
  assert.equal(report[1].ok, true);
  assert.equal(report[2].ok, false);
  assert.equal(report[2].status, "failed");
  assert.match(report[2].error, /no match/);
  // The table step forwarded its structured options alongside dry_run.
  const cellReq = m.methods().find((x) => x.method === "act" && x.params.options.column === "PPHID");
  assert.equal(cellReq.params.options.dry_run, true);
});
