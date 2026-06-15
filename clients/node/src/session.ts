import { BridgeClient, BridgeClientOptions } from "./client.js";
import { SessionSummary, StepOptions, StepResult } from "./types.js";

export type Channel = "web" | "mobile";

export interface LaunchOptions extends BridgeClientOptions {
  /** "web" (default) or "mobile". */
  channel?: Channel;
  /** Web: start URL to open. */
  url?: string;
  /** Web: run headless (default true). */
  headless?: boolean;
  /** Resolve-only — never execute. */
  dryRun?: boolean;
  /** Mobile: Appium server URL (required for the mobile channel). */
  appiumUrl?: string;
  /** Mobile: Appium capabilities. */
  capabilities?: Record<string, unknown>;
}

export interface RecoverArgs {
  failedSelector: string;
  intent: string;
  options?: StepOptions;
}

/**
 * The ergonomic, engine-owned session. `launch()` spawns the bridge, negotiates
 * the protocol, and opens a session whose Playwright/Appium handle lives inside
 * the Python engine; every call here is a thin proxy to the same four primitives
 * the Python SDK exposes, returning the identical `StepResult` shape.
 *
 * ```ts
 * const bg = await Bubblegum.launch({ url: "https://example.com/login" });
 * try {
 *   await bg.act('Enter "tom" into Username');
 *   await bg.act("Click Login");
 *   await bg.verify("Dashboard is visible");
 * } finally {
 *   await bg.close();
 * }
 * ```
 */
export class Bubblegum {
  private constructor(
    private readonly client: BridgeClient,
    private readonly sessionId: string,
  ) {}

  /** Spawn the bridge, handshake, and open an engine-owned session. */
  static async launch(opts: LaunchOptions = {}): Promise<Bubblegum> {
    const client = new BridgeClient(opts);
    try {
      await client.handshake();
      const { session_id } = await client.request<{ session_id: string }>("session.open", {
        channel: opts.channel ?? "web",
        url: opts.url,
        headless: opts.headless ?? true,
        dry_run: opts.dryRun ?? false,
        appium_url: opts.appiumUrl,
        capabilities: opts.capabilities,
      });
      return new Bubblegum(client, session_id);
    } catch (err) {
      await client.close();
      throw err;
    }
  }

  /** The bridge client (for advanced use / capability checks). */
  get bridge(): BridgeClient {
    return this.client;
  }

  act(instruction: string, options?: StepOptions): Promise<StepResult> {
    return this.client.request<StepResult>("act", {
      session_id: this.sessionId,
      instruction,
      options,
    });
  }

  verify(instruction: string, options?: StepOptions): Promise<StepResult> {
    return this.client.request<StepResult>("verify", {
      session_id: this.sessionId,
      instruction,
      options,
    });
  }

  extract(instruction: string, options?: StepOptions): Promise<StepResult> {
    return this.client.request<StepResult>("extract", {
      session_id: this.sessionId,
      instruction,
      options,
    });
  }

  recover(args: RecoverArgs): Promise<StepResult> {
    return this.client.request<StepResult>("recover", {
      session_id: this.sessionId,
      failed_selector: args.failedSelector,
      intent: args.intent,
      options: args.options,
    });
  }

  async isVisible(target: string): Promise<boolean> {
    const r = await this.client.request<{ value: boolean }>("is_visible", {
      session_id: this.sessionId,
      target,
    });
    return r.value;
  }

  async isChecked(target: string): Promise<boolean> {
    const r = await this.client.request<{ value: boolean }>("is_checked", {
      session_id: this.sessionId,
      target,
    });
    return r.value;
  }

  async selectedValue(target: string): Promise<string> {
    const r = await this.client.request<{ value: string }>("selected_value", {
      session_id: this.sessionId,
      target,
    });
    return r.value;
  }

  async explain(instruction: string): Promise<string> {
    const r = await this.client.request<{ explanation: string }>("explain", {
      session_id: this.sessionId,
      instruction,
    });
    return r.explanation;
  }

  summary(): Promise<SessionSummary> {
    return this.client.request<SessionSummary>("summary", { session_id: this.sessionId });
  }

  /** Close the engine session and tear down the bridge process. */
  async close(): Promise<void> {
    try {
      await this.client.request("session.close", { session_id: this.sessionId });
    } finally {
      await this.client.close();
    }
  }
}
