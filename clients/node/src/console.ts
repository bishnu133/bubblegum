/**
 * Modern, dependency-free console output for Bubblegum runs.
 *
 * The engine returns a {@link StepResult} for every act/verify; this module
 * turns that into a clean, colorized one-line status you can print from your
 * test helper, plus a {@link RunConsole} that tracks a run and prints an
 * enterprise-style header/summary. No external libraries — ANSI only, and it
 * auto-disables color for non-TTY / `NO_COLOR` so CI logs stay clean.
 *
 * ```ts
 * import { RunConsole } from "@bubblegum-ai/node";
 * const out = new RunConsole("Workout Creation");
 * out.step(await bg.act("Click Save"));
 * out.step(await bg.verify('status is "In Draft"'));
 * out.summary();
 * ```
 */
import { StepResult, StepStatus } from "./types.js";

const ANSI = {
  reset: "\x1b[0m", bold: "\x1b[1m", dim: "\x1b[2m",
  green: "\x1b[32m", red: "\x1b[31m", amber: "\x1b[33m",
  gray: "\x1b[90m", blue: "\x1b[34m", magenta: "\x1b[35m", cyan: "\x1b[36m",
};

function colorEnabled(opt?: boolean): boolean {
  if (typeof opt === "boolean") return opt;
  const env = typeof process !== "undefined" ? process.env : {};
  if (env.NO_COLOR) return false;
  if (env.FORCE_COLOR) return true;
  return !!(typeof process !== "undefined" && process.stdout && (process.stdout as { isTTY?: boolean }).isTTY);
}

/** Per-status glyph + label + color. */
const STATUS_STYLE: Record<StepStatus, { icon: string; label: string; color: keyof typeof ANSI }> = {
  passed: { icon: "✔", label: "PASS", color: "green" },
  recovered: { icon: "✚", label: "HEAL", color: "amber" },
  failed: { icon: "✖", label: "FAIL", color: "red" },
  skipped: { icon: "○", label: "SKIP", color: "gray" },
  dry_run: { icon: "◇", label: "PLAN", color: "blue" },
};

export interface ConsoleOptions {
  /** Force color on/off. Default: auto (TTY and not NO_COLOR). */
  color?: boolean;
  /** Width the action text is padded to. Default 48. */
  width?: number;
  /** Include the resolver name + confidence. Default true. */
  detail?: boolean;
}

function paint(s: string, color: keyof typeof ANSI, on: boolean): string {
  return on ? `${ANSI[color]}${s}${ANSI.reset}` : s;
}

function fallbackUsed(r: StepResult): boolean {
  const m = (r.target && (r.target.metadata as Record<string, unknown> | undefined)) || {};
  return r.target?.resolver_name === "fallback_selector" || m.fallback_selector_used === true;
}

/** Render a single step as a formatted, optionally-colorized line. */
export function formatStepLine(result: StepResult, opts: ConsoleOptions = {}): string {
  const on = colorEnabled(opts.color);
  const width = opts.width ?? 48;
  const detail = opts.detail ?? true;
  const st = STATUS_STYLE[result.status] ?? STATUS_STYLE.skipped;

  const badge = paint(`${st.icon} ${st.label}`, st.color, on);
  const action = (result.action || "").replace(/\s+/g, " ").trim();
  const actionCol = action.length > width ? action.slice(0, width - 1) + "…" : action.padEnd(width);

  const parts = [badge, "  ", actionCol];
  if (detail) {
    const resolver = result.target?.resolver_name ?? "—";
    const conf = typeof result.confidence === "number" ? result.confidence.toFixed(2) : "—";
    const ms = `${Math.round(result.duration_ms || 0)}ms`;
    parts.push(paint(`  ${resolver} · ${conf} · ${ms}`, "gray", on));
  }
  if (result.status === "recovered") parts.push(paint("  (self-healed)", "amber", on));
  if (fallbackUsed(result)) parts.push(paint("  ⚠ fallback selector", "magenta", on));

  let line = parts.join("");
  if (result.status === "failed" && result.error) {
    const err = `${result.error.error_type}: ${result.error.message}`;
    line += "\n" + paint(`         ↳ ${err}`, "red", on);
  }
  return line;
}

/** Print a single step line (convenience over {@link formatStepLine}). */
export function logStep(result: StepResult, opts: ConsoleOptions = {}): void {
  // eslint-disable-next-line no-console
  console.log(formatStepLine(result, opts));
}

/**
 * A small run tracker: prints a header, one line per step, and an
 * enterprise-style summary with counts, pass rate and elapsed time.
 */
export class RunConsole {
  private counts: Record<StepStatus, number> = {
    passed: 0, failed: 0, recovered: 0, skipped: 0, dry_run: 0,
  };
  private fallbacks = 0;
  private started = Date.now();
  private on: boolean;

  constructor(private title = "Bubblegum Run", private opts: ConsoleOptions = {}) {
    this.on = colorEnabled(opts.color);
    this.banner();
  }

  private write(s: string) {
    // eslint-disable-next-line no-console
    console.log(s);
  }

  private banner() {
    const bar = "─".repeat(Math.max(8, this.title.length + 4));
    this.write("");
    this.write(paint(`┌${bar}┐`, "cyan", this.on));
    this.write(paint(`│  ${this.title}  │`, "cyan", this.on) + paint("  bubblegum", "gray", this.on));
    this.write(paint(`└${bar}┘`, "cyan", this.on));
  }

  /** A labelled section divider between logical groups of steps. */
  section(name: string) {
    this.write("");
    this.write(paint(`▸ ${name}`, "bold", this.on));
  }

  /** Record and print one step. Returns the same result for chaining. */
  step(result: StepResult): StepResult {
    this.counts[result.status] = (this.counts[result.status] ?? 0) + 1;
    if (fallbackUsed(result)) this.fallbacks += 1;
    this.write("  " + formatStepLine(result, this.opts));
    return result;
  }

  /** Print the run summary footer. */
  summary() {
    const total = Object.values(this.counts).reduce((a, b) => a + b, 0);
    const done = total - this.counts.skipped;
    const rate = done ? Math.round((this.counts.passed + this.counts.recovered) / done * 100) : 0;
    const secs = ((Date.now() - this.started) / 1000).toFixed(1);
    const ok = this.counts.failed === 0;

    const chip = (label: string, n: number, color: keyof typeof ANSI) =>
      n > 0 ? paint(`${label} ${n}`, color, this.on) : paint(`${label} ${n}`, "gray", this.on);

    this.write("");
    this.write(paint("─".repeat(56), "gray", this.on));
    this.write([
      chip("✔", this.counts.passed, "green"),
      chip("✚", this.counts.recovered, "amber"),
      this.fallbacks ? paint(`⚠ ${this.fallbacks}`, "magenta", this.on) : "",
      chip("✖", this.counts.failed, "red"),
      chip("○", this.counts.skipped, "gray"),
      paint(`· ${rate}% pass · ${secs}s`, "gray", this.on),
    ].filter(Boolean).join("   "));
    this.write(
      ok
        ? paint(`  ${this.title}: ALL PASSED`, "green", this.on)
        : paint(`  ${this.title}: ${this.counts.failed} FAILED`, "red", this.on),
    );
    this.write("");
  }
}
