/**
 * TypeScript mirror of the engine's result schemas (`bubblegum/core/schemas.py`).
 *
 * Kept intentionally close to the Pydantic models. `[key: string]: unknown`
 * index signatures let newer engine fields flow through without breaking the
 * client (additive-first), while the named fields stay strongly typed.
 */

export type StepStatus = "passed" | "failed" | "recovered" | "dry_run" | "skipped";

export interface ResolvedTarget {
  ref: string;
  confidence: number;
  resolver_name: string;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface ErrorInfo {
  error_type: string;
  message: string;
  resolver_name?: string | null;
  [key: string]: unknown;
}

export interface StepResult {
  status: StepStatus;
  action: string;
  target: ResolvedTarget | null;
  confidence: number;
  duration_ms: number;
  error?: ErrorInfo | null;
  traces?: unknown[];
  [key: string]: unknown;
}

export interface SessionSummary {
  total: number;
  passed: number;
  failed: number;
  [key: string]: unknown;
}

/** Per-call options forwarded verbatim to the engine SDK (timeout_ms, selector, …). */
export type StepOptions = Record<string, unknown>;

/**
 * Which reports to write from the session's accumulated step results.
 *
 * Each field is either an output path, or `true` to use the default name
 * (`bubblegum_report.html` / `.json` / `.xml`, and `allure-results/` for
 * Allure). Omit a field to skip that format. Paths are resolved relative to the
 * engine process's working directory.
 */
export interface ReportOptions {
  /** Single-file HTML report. */
  html?: string | boolean;
  /** Machine-readable JSON report. */
  json?: string | boolean;
  /** JUnit XML (for CI test-report ingestion). */
  junit?: string | boolean;
  /** Allure 2 results *directory* (view with `allure serve <dir>`). */
  allure?: string | boolean;
  /**
   * Cross-run suite summary HTML. Each test run upserts itself (keyed by
   * `suiteName`) into a sibling `*.json` manifest, so several independently-run
   * tests aggregate into one overview (per-test pass/fail + grand totals)
   * instead of overwriting each other. Pass a distinct `suiteName` per test.
   */
  summary?: string | boolean;
  /** Report title (HTML/JSON). */
  title?: string;
  /** Suite / test name (Allure/JUnit, and the summary manifest key). */
  suiteName?: string;
  /**
   * Header for the combined *summary* page, independent of any single test's
   * `title`. Persisted, so the last test to run no longer decides the heading.
   * Configure it once per execution (e.g. "Web Automation Summary Report");
   * defaults to a generic "Test Automation Summary Report".
   */
  summaryTitle?: string;
  /**
   * Which of the session's steps this report covers:
   *   - `"all"` (default): every step run in the session so far.
   *   - `"sinceLast"`: only the steps since the previous `report()` call, then
   *     advance the cursor. Call `report({ scope: "sinceLast", … })` after each
   *     test case to put several named tests in one file — each gets its own
   *     individual report and its own summary row.
   */
  scope?: "all" | "sinceLast";
}

/** Result of {@link Bubblegum.report}: resolved paths written, and step count. */
export interface ReportResult {
  /** Format → resolved absolute path (or directory, for Allure). */
  written: Record<string, string>;
  /** Number of steps included in the report. */
  steps: number;
}
