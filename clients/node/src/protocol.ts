/**
 * Wire protocol for the Bubblegum bridge — the TypeScript mirror of
 * `bubblegum/bridge/protocol.py`. Keep these in lockstep with the Python side.
 *
 * The client negotiates against the engine via `handshake`: it feature-detects
 * on `capabilities` and refuses to run against a `protocol_version` it does not
 * support, so a newer engine can keep serving an older client (additive-first).
 */

/** Protocol versions this client speaks. v1 = the 0.1.0 bridge slice. */
export const SUPPORTED_PROTOCOL_VERSIONS = [1] as const;

/** The latest protocol version this client was written against. */
export const PROTOCOL_VERSION = 1;

/** JSON-RPC 2.0 + bridge error codes (mirror of the Python side). */
export const ErrorCodes = {
  ParseError: -32700,
  InvalidRequest: -32600,
  MethodNotFound: -32601,
  InvalidParams: -32602,
  InternalError: -32603,
  SessionNotFound: -32001,
  EngineError: -32002,
  Unsupported: -32003,
} as const;

export type JsonRpcId = number | string | null;

export interface JsonRpcRequest {
  jsonrpc: "2.0";
  id?: JsonRpcId;
  method: string;
  params?: Record<string, unknown>;
}

export interface JsonRpcSuccess {
  jsonrpc: "2.0";
  id: JsonRpcId;
  result: unknown;
}

export interface JsonRpcErrorResponse {
  jsonrpc: "2.0";
  id: JsonRpcId;
  error: { code: number; message: string; data?: unknown };
}

export type JsonRpcResponse = JsonRpcSuccess | JsonRpcErrorResponse;

export function isErrorResponse(msg: JsonRpcResponse): msg is JsonRpcErrorResponse {
  return (msg as JsonRpcErrorResponse).error !== undefined;
}

/** Result of the `handshake` method. */
export interface Handshake {
  engine_version: string;
  protocol_version: number;
  capabilities: string[];
}
