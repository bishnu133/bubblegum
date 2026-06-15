/**
 * @bubblegum-ai/node — Node/TypeScript client for the Bubblegum engine.
 *
 * Drives AI-powered, natural-language Playwright/Appium test steps from JS/TS by
 * spawning the Python `bubblegum bridge` and speaking its JSON-RPC protocol. The
 * Python engine stays the single source of truth for grounding; this package is
 * a thin, typed proxy. See ../../docs/distribution-npm-and-pypi.md.
 */

export { Bubblegum } from "./session.js";
export type { Channel, LaunchOptions, RecoverArgs } from "./session.js";

export { BridgeClient, spawnBridgeTransport } from "./client.js";
export type { Transport, SpawnOptions, BridgeClientOptions } from "./client.js";

export { BridgeError } from "./errors.js";

export {
  PROTOCOL_VERSION,
  SUPPORTED_PROTOCOL_VERSIONS,
  ErrorCodes,
} from "./protocol.js";
export type { Handshake, JsonRpcResponse } from "./protocol.js";

export type {
  StepResult,
  StepStatus,
  ResolvedTarget,
  ErrorInfo,
  SessionSummary,
  StepOptions,
} from "./types.js";
