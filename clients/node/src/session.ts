import { BridgeClient, BridgeClientOptions } from "./client.js";
import { BridgeError } from "./errors.js";
import { ErrorCodes } from "./protocol.js";
import { ReportOptions, ReportResult, SessionSummary, StepOptions, StepResult } from "./types.js";

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
  /**
   * Web client-owned mode: attach the engine to an existing Chromium over CDP
   * (e.g. `http://localhost:9222`) instead of launching one, so the engine
   * drives the same browser your test already controls. Requires the engine to
   * advertise the `channel.web.cdp` capability.
   */
  cdpEndpoint?: string;
  /** Which existing page to attach to when using `cdpEndpoint` (default 0). */
  pageIndex?: number;
}

/** Options for {@link Bubblegum.attach} — `cdpEndpoint` is required. */
export interface AttachOptions extends Omit<LaunchOptions, "channel"> {
  cdpEndpoint: string;
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

  /** Spawn the bridge, handshake, and open a session (engine-owned by default). */
  static async launch(opts: LaunchOptions = {}): Promise<Bubblegum> {
    const client = new BridgeClient(opts);
    try {
      await client.handshake();
      if (opts.cdpEndpoint && !client.hasCapability("channel.web.cdp")) {
        throw new BridgeError(
          ErrorCodes.Unsupported,
          "this engine does not support CDP attach (channel.web.cdp); upgrade bubblegum-ai",
        );
      }
      const { session_id } = await client.request<{ session_id: string }>("session.open", {
        channel: opts.channel ?? "web",
        url: opts.url,
        headless: opts.headless ?? true,
        dry_run: opts.dryRun ?? false,
        appium_url: opts.appiumUrl,
        capabilities: opts.capabilities,
        cdp_endpoint: opts.cdpEndpoint,
        page_index: opts.pageIndex,
      });
      return new Bubblegum(client, session_id);
    } catch (err) {
      await client.close();
      throw err;
    }
  }

  /**
   * Attach the engine to a browser your test already controls, over CDP
   * (client-owned mode). Launch your Chromium with a remote-debugging port and
   * pass its endpoint:
   *
   * ```ts
   * const browser = await chromium.launch({ args: ["--remote-debugging-port=9222"] });
   * const bg = await Bubblegum.attach({ cdpEndpoint: "http://localhost:9222" });
   * await bg.act("Click Login"); // drives the page your test opened
   * ```
   */
  static attach(opts: AttachOptions): Promise<Bubblegum> {
    return Bubblegum.launch({ ...opts, channel: "web" });
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

  /**
   * Write reports (Allure / HTML / JSON / JUnit) from every step this session
   * ran, using the engine's own reporters — the same output the Python/pytest
   * path produces. Call it once near the end of your run (e.g. in `finally`,
   * before `close()`):
   *
   * ```ts
   * await bg.report({ html: "reports/run.html", allure: "allure-results" });
   * // -> { written: { html: "/abs/...", allure: "/abs/..." }, steps: 12 }
   * ```
   */
  report(opts: ReportOptions): Promise<ReportResult> {
    if (!this.client.hasCapability("report.write")) {
      throw new BridgeError(
        ErrorCodes.Unsupported,
        "this engine does not support report generation (report.write); upgrade bubblegum-ai",
      );
    }
    const resolve = (v: string | boolean | undefined, fallback: string): string | undefined =>
      v === true ? fallback : v || undefined;

    const params: Record<string, unknown> = { session_id: this.sessionId };
    const html = resolve(opts.html, "bubblegum_report.html");
    const json = resolve(opts.json, "bubblegum_report.json");
    const junit = resolve(opts.junit, "bubblegum_report.xml");
    const allure = resolve(opts.allure, "allure-results");
    if (html) params.html = html;
    if (json) params.json = json;
    if (junit) params.junit = junit;
    if (allure) params.allure = allure;
    if (opts.title) params.title = opts.title;
    if (opts.suiteName) params.suite_name = opts.suiteName;

    return this.client.request<ReportResult>("report.write", params);
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
