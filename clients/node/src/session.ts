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
  /**
   * Mobile client-owned mode: attach the engine to an Appium session another
   * test already created, by its session id (e.g. WebdriverIO's
   * `browser.sessionId`). Cloud device farms allow only one session per device,
   * so an in-test fallback must reuse the running session rather than open a
   * new one. The engine reuses it and never quits it. Requires the engine to
   * advertise the `channel.mobile.attach` capability.
   */
  existingSessionId?: string;
}

/** Options for {@link Bubblegum.attach} — `cdpEndpoint` is required. */
export interface AttachOptions extends Omit<LaunchOptions, "channel"> {
  cdpEndpoint: string;
}

/**
 * Options for {@link Bubblegum.attachMobile} — attach to an Appium session your
 * test already drives. `appiumUrl` + `existingSessionId` are required.
 */
export interface MobileAttachOptions extends Omit<LaunchOptions, "channel" | "cdpEndpoint" | "pageIndex"> {
  appiumUrl: string;
  existingSessionId: string;
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

/** Options for {@link Bubblegum.dismissIfPresent}. */
export interface DismissOptions {
  /**
   * How many sweep rounds to perform. Each round taps every phrase currently on
   * screen; if anything was tapped, the sweep repeats to catch a follow-up
   * prompt (permission chains queue one after another). Default 3.
   */
  maxRounds?: number;
  /** Pause between rounds (ms) so the next queued dialog can render. Default 400. */
  pauseMs?: number;
  /** Per-resolve/act timeout forwarded to the engine. */
  timeoutMs?: number;
}

/** Result of {@link Bubblegum.dismissIfPresent}. */
export interface DismissResult {
  /** True if at least one popup was tapped. */
  dismissed: boolean;
  /** The visible phrases that were tapped, in tap order (may repeat across rounds). */
  tapped: string[];
  /** Number of sweep rounds actually performed. */
  rounds: number;
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
      if (opts.existingSessionId && !client.hasCapability("channel.mobile.attach")) {
        throw new BridgeError(
          ErrorCodes.Unsupported,
          "this engine does not support attaching to an existing Appium session " +
            "(channel.mobile.attach); upgrade bubblegum-ai",
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
        existing_session_id: opts.existingSessionId,
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

  /**
   * Attach the engine to a mobile (Appium) session your test already drives,
   * by its session id. Cloud device farms (pCloudy, BrowserStack, …) allow only
   * one Appium session per device, so an in-test Bubblegum fallback must reuse
   * the running session instead of opening a new one. The engine shares the
   * session and never quits it — your test keeps ownership of teardown.
   *
   * ```ts
   * // Inside a WebdriverIO test, when a normal locator click fails:
   * const bg = await Bubblegum.attachMobile({
   *   appiumUrl: "https://appium.example.com/wd/hub",
   *   existingSessionId: browser.sessionId,
   *   capabilities: { platformName: "iOS" },
   * });
   * try {
   *   await bg.act("Tap Continue");
   * } finally {
   *   await bg.close(); // closes the engine wrapper only; device session stays up
   * }
   * ```
   */
  static attachMobile(opts: MobileAttachOptions): Promise<Bubblegum> {
    return Bubblegum.launch({ ...opts, channel: "mobile" });
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

  /**
   * Tap an optional popup **by its visible text, only if it's on screen** — the
   * safe way to clear a blocking confirmation/permission dialog that may or may
   * not appear (e.g. an iOS "Allow notifications?" alert after login).
   *
   * This is the correct pattern for optional dialogs. A dialog that is *absent*
   * must not fail the flow, so you cannot key it off a locator that throws when
   * missing (WebdriverIO's `isElementPresent` returns `false` rather than
   * throwing, so a `try/catch` around it never runs your fallback). Instead this
   * helper does a resolve-only {@link preflight} first (executes nothing) and
   * taps **only** when the element is actually present.
   *
   * Pass several candidate labels to clear a *chain* of prompts in one call
   * (e.g. `["Allow", "OK", "Continue"]`). Each round taps every phrase currently
   * visible; if anything was tapped it sweeps again — because OS permission
   * prompts appear one at a time — until a round finds nothing or `maxRounds` is
   * hit. Exact labels are preferred by the engine, so `"Allow"` never taps a
   * neighbouring `"Don't Allow"`.
   *
   * It never throws for a missing dialog and never quits your session; call it
   * unconditionally right after the step the popup interrupts.
   *
   * ```ts
   * const bg = await Bubblegum.attachMobile({
   *   appiumUrl, existingSessionId: browser.sessionId,
   *   capabilities: { platformName: "iOS" },
   * });
   * try {
   *   // ...your login step ran; a permission popup may now be blocking the app.
   *   const r = await bg.dismissIfPresent(["Allow", "OK", "Continue"]);
   *   if (r.dismissed) console.log("cleared popup(s):", r.tapped.join(", "));
   *   // ...continue the flow; the app is unblocked whether or not the popup showed.
   * } finally {
   *   await bg.close();
   * }
   * ```
   */
  async dismissIfPresent(
    phrases: string | string[],
    options?: DismissOptions,
  ): Promise<DismissResult> {
    const list = typeof phrases === "string" ? [phrases] : phrases;
    const maxRounds = options?.maxRounds ?? 3;
    const pauseMs = options?.pauseMs ?? 400;
    const stepOpts: StepOptions | undefined =
      options?.timeoutMs !== undefined ? { timeout_ms: options.timeoutMs } : undefined;

    const tapped: string[] = [];
    let rounds = 0;
    for (let round = 0; round < maxRounds; round++) {
      rounds = round + 1;
      let tappedThisRound = false;
      for (const phrase of list) {
        const instruction = `Tap ${phrase}`;
        const [pf] = await this.preflight([instruction], stepOpts); // resolve-only; no tap
        if (!pf.ok) continue; // not on screen — leave it, don't fail
        const r = await this.act(instruction, stepOpts);
        if (r.status === "passed" || r.status === "recovered") {
          tapped.push(phrase);
          tappedThisRound = true;
        }
      }
      if (!tappedThisRound) break; // nothing left to clear
      if (round < maxRounds - 1 && pauseMs > 0) {
        await new Promise((resolve) => setTimeout(resolve, pauseMs));
      }
    }
    return { dismissed: tapped.length > 0, tapped, rounds };
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
   * await bg.clickInTable({ column: "RecordID", row: "first" });
   * await bg.clickInTable({ column: "RecordID", rowMatch: { Name: dbName } });
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
   * await bg.verifyTable({ columns: ["RecordID", "Account Status", "Profile Status"] });
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
