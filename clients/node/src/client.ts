import { spawn } from "node:child_process";
import { createInterface } from "node:readline";

import { BridgeError } from "./errors.js";
import {
  ErrorCodes,
  Handshake,
  JsonRpcResponse,
  SUPPORTED_PROTOCOL_VERSIONS,
  isErrorResponse,
} from "./protocol.js";

/**
 * A line-oriented duplex link to the bridge. The default implementation spawns
 * the Python `bubblegum bridge` process, but it is an interface so tests (and
 * future transports — e.g. a long-lived daemon socket) can inject their own.
 */
export interface Transport {
  /** Write one newline-delimited JSON-RPC message. */
  send(line: string): void;
  /** Register the handler for each inbound line. */
  onLine(cb: (line: string) => void): void;
  /** Register the handler invoked when the link closes (optionally with an error). */
  onClose(cb: (err?: Error) => void): void;
  /** Tear the link down. */
  close(): Promise<void>;
}

export interface SpawnOptions {
  /** Executable to launch (default: `python`). */
  command?: string;
  /** Args (default: `["-m", "bubblegum.bridge"]`). */
  args?: string[];
  cwd?: string;
  env?: NodeJS.ProcessEnv;
}

/** Spawn the Python bridge as a child process and frame JSON-RPC over its stdio. */
export function spawnBridgeTransport(opts: SpawnOptions = {}): Transport {
  const command = opts.command ?? "python";
  const args = opts.args ?? ["-m", "bubblegum.bridge"];
  const child = spawn(command, args, {
    cwd: opts.cwd,
    env: opts.env,
    stdio: ["pipe", "pipe", "inherit"], // engine logs/errors pass through to our stderr
  });
  const rl = createInterface({ input: child.stdout! });

  return {
    send(line: string): void {
      child.stdin!.write(line + "\n");
    },
    onLine(cb: (line: string) => void): void {
      rl.on("line", cb);
    },
    onClose(cb: (err?: Error) => void): void {
      child.on("error", (err) => cb(err));
      child.on("exit", () => cb());
    },
    async close(): Promise<void> {
      rl.close();
      child.stdin!.end();
      if (child.exitCode === null) child.kill();
    },
  };
}

interface Pending {
  resolve: (value: unknown) => void;
  reject: (err: Error) => void;
}

export interface BridgeClientOptions {
  /** Inject a transport (tests/daemon). When omitted, a Python bridge is spawned. */
  transport?: Transport;
  /** Spawn options for the default transport. Ignored when `transport` is given. */
  spawn?: SpawnOptions;
}

/**
 * Low-level JSON-RPC client over a {@link Transport}: assigns request ids,
 * correlates responses, surfaces engine errors as {@link BridgeError}, and
 * negotiates the protocol version via {@link BridgeClient.handshake}.
 */
export class BridgeClient {
  private readonly transport: Transport;
  private readonly pending = new Map<number, Pending>();
  private nextId = 1;
  private closed = false;
  /** Populated after a successful {@link handshake}. */
  handshakeInfo?: Handshake;

  constructor(opts: BridgeClientOptions = {}) {
    this.transport = opts.transport ?? spawnBridgeTransport(opts.spawn);
    this.transport.onLine((line) => this.onLine(line));
    this.transport.onClose((err) => this.onClose(err));
  }

  private onLine(line: string): void {
    const trimmed = line.trim();
    if (!trimmed) return;
    let msg: JsonRpcResponse;
    try {
      msg = JSON.parse(trimmed) as JsonRpcResponse;
    } catch {
      return; // ignore non-JSON noise on the channel
    }
    if (typeof msg.id !== "number") return; // we only issue numeric ids
    const pending = this.pending.get(msg.id);
    if (!pending) return;
    this.pending.delete(msg.id);
    if (isErrorResponse(msg)) {
      pending.reject(new BridgeError(msg.error.code, msg.error.message, msg.error.data));
    } else {
      pending.resolve(msg.result);
    }
  }

  private onClose(err?: Error): void {
    this.closed = true;
    const reason = err ?? new BridgeError(ErrorCodes.InternalError, "bridge connection closed");
    for (const [, pending] of this.pending) pending.reject(reason);
    this.pending.clear();
  }

  /** Issue a request and resolve with its `result` (or reject with a {@link BridgeError}). */
  request<T = unknown>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    if (this.closed) {
      return Promise.reject(new BridgeError(ErrorCodes.InternalError, "bridge is closed"));
    }
    const id = this.nextId++;
    const payload = { jsonrpc: "2.0" as const, id, method, params };
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve: resolve as (v: unknown) => void, reject });
      this.transport.send(JSON.stringify(payload));
    });
  }

  /** Negotiate with the engine; throws if its protocol version is unsupported. */
  async handshake(): Promise<Handshake> {
    const info = await this.request<Handshake>("handshake");
    if (!(SUPPORTED_PROTOCOL_VERSIONS as readonly number[]).includes(info.protocol_version)) {
      throw new BridgeError(
        ErrorCodes.Unsupported,
        `engine protocol v${info.protocol_version} is not supported by this client ` +
          `(supports: ${SUPPORTED_PROTOCOL_VERSIONS.join(", ")}). Upgrade @bubblegum-ai/node.`,
      );
    }
    this.handshakeInfo = info;
    return info;
  }

  /** True if the engine advertised the given capability in its handshake. */
  hasCapability(name: string): boolean {
    return this.handshakeInfo?.capabilities.includes(name) ?? false;
  }

  async close(): Promise<void> {
    await this.transport.close();
    this.onClose();
  }
}
