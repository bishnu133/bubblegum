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
