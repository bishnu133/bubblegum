"""
bubblegum/convert/scaffold.py
=============================
Scaffold the shared TypeScript harness that generated smart-tests import.

``bubblegum convert --init`` writes these once into the output directory so a
new project is self-contained:

    <out>/helpers/engine.ts      launch browser + CDP-attach the engine
    <out>/helpers/actions.ts     act / observe / verify wrappers (log + throw)
    <out>/helpers/reporter.ts    generateReports() — html/json/junit/allure
    <out>/flows/login.flow.ts    reusable loginFlow(engine, page, credentials)
    <out>/.env.bubblegum.local.example   env template

These mirror the user's proven ``smart-tests`` harness. Existing files are never
overwritten — the scaffold is additive so hand-tuned helpers are safe.
"""

from __future__ import annotations

from pathlib import Path

ENGINE_TS = """\
/**
 * Engine helper — abstracts browser launch, CDP attachment, and AI engine lifecycle.
 * Keeps test scripts agnostic of the underlying AI library.
 */
import { chromium, type Browser, type Page } from '@playwright/test';
import { Bubblegum } from '@bubblegum-ai/node';

export interface EngineConfig {
  headless?: boolean;
  cdpPort?: number;
  pythonPath?: string;
  viewport?: { width: number; height: number };
}

export interface EngineContext {
  browser: Browser;
  page: Page;
  engine: Bubblegum;
}

const DEFAULT_CONFIG: Required<EngineConfig> = {
  headless: process.env.HEADLESS !== 'false',
  cdpPort: Number(process.env.CDP_PORT ?? 9222),
  pythonPath: process.env.BUBBLEGUM_PYTHON ?? 'python3',
  viewport: { width: 1440, height: 900 },
};

/** Launches a browser with CDP and attaches the AI engine. */
export async function initEngine(
  config: Partial<EngineConfig> = {}
): Promise<EngineContext> {
  const cfg = { ...DEFAULT_CONFIG, ...config };

  const browser = await chromium.launch({
    headless: cfg.headless,
    args: [`--remote-debugging-port=${cfg.cdpPort}`],
  });

  const page = await browser.newPage({
    ignoreHTTPSErrors: true,
    viewport: cfg.viewport,
  });

  const engine = await Bubblegum.attach({
    cdpEndpoint: `http://localhost:${cfg.cdpPort}`,
    spawn: { command: cfg.pythonPath },
  });

  return { browser, page, engine };
}

/** Gracefully shuts down the engine and browser. Safe to call twice. */
export async function teardownEngine(ctx: EngineContext): Promise<void> {
  try {
    await ctx.engine.close();
  } catch {
    // engine may already be closed
  }
  try {
    await ctx.browser.close();
  } catch {
    // browser may already be closed
  }
}
"""

ACTIONS_TS = """\
/**
 * Action helpers — thin wrappers around the AI engine's act/observe/verify methods.
 * Provides consistent logging and error handling across all test flows.
 */
import { Bubblegum } from '@bubblegum-ai/node';

/** Observe (dry-run): resolve an element WITHOUT acting on it. */
export async function observe(
  engine: Bubblegum,
  phrase: string
): Promise<string | null> {
  const r = await engine.act(phrase, { dry_run: true });
  console.log(
    `observe "${phrase}" -> ${r.status}  ref=${r.target?.ref}  conf=${r.confidence}`
  );
  return r.target?.ref ?? null;
}

/** Act: perform an action (click, type, select, upload) with logging. Throws on failure. */
export async function act(
  engine: Bubblegum,
  phrase: string,
  options?: Record<string, unknown>
) {
  const r = await engine.act(phrase, options);
  console.log(
    `act "${phrase}" -> ${r.status}  (${r.target?.resolver_name}, conf ${r.confidence})`
  );
  if (r.status === 'failed') {
    throw new Error(`Step failed: "${phrase}" — ${r.error?.message}`);
  }
  return r;
}

/** Verify: assert a condition on the page. Throws if the assertion does not hold. */
export async function verify(engine: Bubblegum, phrase: string) {
  const r = await engine.verify(phrase);
  console.log(`verify "${phrase}" -> ${r.status}  (conf ${r.confidence})`);
  if (!['passed', 'recovered'].includes(r.status)) {
    throw new Error(
      `Verification failed: "${phrase}" — ${r.error?.message ?? r.status}`
    );
  }
  return r;
}
"""

REPORTER_TS = """\
/**
 * Reporter helper — generates test reports in multiple formats.
 * Centralizes report configuration so individual tests stay clean.
 */
import { Bubblegum } from '@bubblegum-ai/node';

export interface ReportConfig {
  reportDir?: string;
  title?: string;
  suiteName?: string;
}

const DEFAULT_REPORT_CONFIG: Required<ReportConfig> = {
  reportDir: process.env.REPORT_DIR ?? 'reports',
  title: 'Smart Tests',
  suiteName: 'smart-tests',
};

/** Generates HTML, JSON, JUnit XML, and Allure reports. Call BEFORE engine.close(). */
export async function generateReports(
  engine: Bubblegum,
  config: Partial<ReportConfig> = {}
) {
  const cfg = { ...DEFAULT_REPORT_CONFIG, ...config };

  try {
    const out = await engine.report({
      html: `${cfg.reportDir}/bubblegum-report.html`,
      allure: `${cfg.reportDir}/allure-results`,
      junit: `${cfg.reportDir}/junit.xml`,
      json: `${cfg.reportDir}/bubblegum-report.json`,
      title: cfg.title,
      suiteName: cfg.suiteName,
    });

    console.log(`\\nReports written (${out.steps} steps):`);
    for (const [fmt, filePath] of Object.entries(out.written)) {
      console.log(`  ${fmt.padEnd(7)} ${filePath}`);
    }
    return out;
  } catch (err) {
    console.error('Report generation failed:', err);
    throw err;
  }
}
"""

LOGIN_FLOW_TS = """\
/**
 * Login flow — reusable login steps for any test that needs authentication.
 * Adjust the field phrases to match your app's login screen if they differ.
 */
import type { Page } from '@playwright/test';
import type { Bubblegum } from '@bubblegum-ai/node';
import { act } from '../helpers/actions';

export interface LoginCredentials {
  username: string;
  password: string;
}

/** Performs login. Assumes the page is already on the login screen. */
export async function loginFlow(
  engine: Bubblegum,
  page: Page,
  credentials: LoginCredentials
): Promise<void> {
  await act(engine, `Enter "${credentials.username}" into Username`);
  await act(engine, `Enter "${credentials.password}" into Password`);
  await act(engine, 'Click Sign In');

  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(3000);
  console.log('Login completed successfully');
}
"""

ENV_EXAMPLE = """\
# Copy to `.env.bubblegum.local` and fill in. Never commit real secrets.
HEADLESS=false
CDP_PORT=9222
BUBBLEGUM_PYTHON=python3
REPORT_DIR=reports

# App under test + login (used by the generated .test.mts files).
APP_URL=https://your-app.example.com
APP_USER=
APP_PASS=
"""

# name (relative to out dir) -> content. Written only if absent.
_HARNESS_FILES: dict[str, str] = {
    "helpers/engine.ts": ENGINE_TS,
    "helpers/actions.ts": ACTIONS_TS,
    "helpers/reporter.ts": REPORTER_TS,
    "flows/login.flow.ts": LOGIN_FLOW_TS,
    ".env.bubblegum.local.example": ENV_EXAMPLE,
}


def scaffold_harness(out_dir: str | Path) -> list[str]:
    """Write the shared harness into ``out_dir``. Returns paths actually written.

    Existing files are left untouched so hand-edits are never clobbered.
    """
    root = Path(out_dir)
    written: list[str] = []
    for rel, content in _HARNESS_FILES.items():
        target = root / rel
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(str(target))
    return written
