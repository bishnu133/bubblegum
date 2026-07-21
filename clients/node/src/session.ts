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

/** One step's outcome from {@link Bubblegum.preflight}. */
export interface PreflightResult {
  instruction: string;
  /** Engine status: "dry_run" when it resolved, "failed" when it didn't. */
  status: StepResult["status"];
  /** True when the step resolved to a target (dry_run / passed / recovered). */
  ok: boolean;
  confidence: number;
  resolver: string | null;
  ref: string | null;
  error: string | null;
}

/** Arguments for {@link Bubblegum.clickInTable}. */
export interface TableCellTarget {
  /** Column header that identifies the cell. */
  column: string;
  /** Row selector: 1-based index, -1 = last, or a word like "first" / "last". */
  row?: number | string;
  /** Locate the row by another column's value instead of an index (e.g. a DB key). */
  rowMatch?: Record<string, string>;
  /** Per-call timeout. */
  timeoutMs?: number;
}

/** Arguments for {@link Bubblegum.verifyTable}. */
export interface TableAssertion {
  /** Column headers that must all be present. */
  columns?: string[];
  /** Column -> value used to locate the row(s) (e.g. a key sourced from a DB). */
  row?: Record<string, string>;
  /** Column -> expected value asserted in the matched row(s). */
  cell?: Record<string, string>;
  /** Optional human-readable step label for the report. */
  description?: string;
  /** Per-call timeout; the assertion polls the table until it holds or this elapses. */
  timeoutMs?: number;
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

  /**
   * Dry-run a list of steps against the *current* page and report whether each
   * one resolves — without executing anything. Lets you validate a script (or a
   * page's worth of steps) in one batch instead of discovering failures one run
   * at a time.
   *
   * Because nothing executes, steps are all checked against the page as it is
   * now (no navigation between them) — so call it once per page (e.g. after
   * landing on each screen) with that screen's steps.
   *
   * @example
   * const report = await bg.preflight([
   *   'Select "Active" from the Participant status dropdown',
   *   'Select "Change of mind" from the Reason dropdown',
   *   'Click the Submit button',
   * ]);
   * console.table(report);            // see status / confidence / resolver per step
   * if (report.some(r => !r.ok)) throw new Error("preflight found unresolved steps");
   */
  async preflight(
    steps: Array<string | { instruction: string; options?: StepOptions }>,
    options?: StepOptions,
  ): Promise<PreflightResult[]> {
    const out: PreflightResult[] = [];
    for (const step of steps) {
      const instruction = typeof step === "string" ? step : step.instruction;
      const perStep = typeof step === "string" ? undefined : step.options;
      const r = await this.act(instruction, { ...options, ...perStep, dry_run: true });
      out.push({
        instruction,
        status: r.status,
        ok: r.status === "dry_run" || r.status === "passed" || r.status === "recovered",
        confidence: r.confidence,
        resolver: r.target?.resolver_name ?? null,
        ref: r.target?.ref ?? null,
        error: r.error?.message ?? null,
      });
    }
    return out;
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

  /**
   * Click an element inside a table cell, addressed by column + row.
   *
   * The cell's clickable child (a link / button) is clicked when present — ideal
   * when the visible text is dynamic (a UUID, a DB id) and so can't be named.
   *
   * @example
   * await bg.clickInTable({ column: "PPHID", row: "first" });
   * await bg.clickInTable({ column: "PPHID", rowMatch: { Name: dbName } });
   */
  clickInTable(spec: TableCellTarget): Promise<StepResult> {
    const { column, row, rowMatch, timeoutMs } = spec;
    const options: StepOptions = { action_type: "click", column };
    if (rowMatch) options.row_match = rowMatch;
    else if (row !== undefined) options.row = row;
    if (timeoutMs !== undefined) options.timeout_ms = timeoutMs;
    return this.act(`click the ${column} cell`, options);
  }

  /**
   * Click a link by its text (exact, then case-insensitive, then substring).
   * Handy when the link label is a dynamic value pulled from a DB.
   */
  clickLink(text: string, options?: { exact?: boolean; timeoutMs?: number }): Promise<StepResult> {
    const opts: StepOptions = { action_type: "click", link_text: text };
    if (options?.exact !== undefined) opts.exact = options.exact;
    if (options?.timeoutMs !== undefined) opts.timeout_ms = options.timeoutMs;
    return this.act(`click the link "${text}"`, opts);
  }

  /**
   * Assert columns / cell values in a data table (Ant Design / native / ARIA).
   *
   * - `columns`: header names that must all be present.
   * - `row`: column -> value used to locate the row(s) (e.g. a key from your DB).
   * - `cell`: column -> expected value asserted in the matched row(s).
   *
   * At least one of `columns` / `cell` should be provided. Matching is
   * whitespace-normalised, case-insensitive, and tolerates a value rendered
   * inside a badge (expected is matched as a substring of the cell).
   *
   * @example
   * await bg.verifyTable({ columns: ["PPHID", "Account Status", "Profile Status"] });
   * await bg.verifyTable({ row: { Name: dbName }, cell: { "Account Status": dbStatus } });
   */
  verifyTable(spec: TableAssertion): Promise<StepResult> {
    const { description, timeoutMs, ...rest } = spec;
    const options: StepOptions = { assertion_type: "table", ...rest };
    if (timeoutMs !== undefined) options.timeout_ms = timeoutMs;
    return this.verify(description ?? "table assertion", options);
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
    const summary = resolve(opts.summary, "bubblegum-summary.html");
    if (html) params.html = html;
    if (json) params.json = json;
    if (junit) params.junit = junit;
    if (allure) params.allure = allure;
    if (summary) params.summary = summary;
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
