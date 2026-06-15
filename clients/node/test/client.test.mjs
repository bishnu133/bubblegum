// Browser/Python-free tests: drive the client + session against an in-memory
// mock transport that auto-responds, exercising JSON-RPC framing, id
// correlation, error mapping, protocol negotiation, and the session proxies.
//
// Run after build (`npm test` builds first): imports the compiled dist.
import { test } from "node:test";
import assert from "node:assert/strict";

import { BridgeClient, Bubblegum, BridgeError } from "../dist/index.js";

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
