"""
bubblegum/core/repl/evaluate.py
===============================
Evaluate a parsed :class:`ReplCommand` against a live session and render the
outcome for printing (A2).

``evaluate`` is the REPL's single execution surface — it drives ``act`` /
``verify`` / ``extract`` / ``explain`` / ``goto`` on a duck-typed session
(BubblegumSession in practice) and returns a human-readable line reporting the
resolved target, resolver, and confidence. The CLI loop only reads input lines
and prints what this returns; the browser/driver wiring lives in
``bubblegum.cli.repl``.
"""

from __future__ import annotations

HELP_TEXT = """\
Bubblegum REPL — type a natural-language step and press Enter.

  Click Login                 run an action (bare NL is treated as act)
  act("Click Login")          same, explicit verb form
  verify("Secure Area visible")   assert an expected state
  extract("Get flash message")    read text from a resolved element
  explain("Click Login")      show why a step resolves (ranked candidates)
  dry("Click Login")          resolve only — preview the target, do not act

Meta commands:
  :dry [on|off]               toggle resolve-only mode (no on/off = flip)
  :open <url>                 navigate (web only)
  :explain <step>             rationale for a step
  :help                       show this help
  :quit                       exit (Ctrl-D also works)
"""

_STATUS_ICON = {
    "passed": "✓",
    "recovered": "✓",
    "dry_run": "○",
    "failed": "✗",
    "skipped": "—",
}


def format_result(result, *, resolve_only: bool = False) -> str:
    """Render a StepResult into a one-or-two line REPL report.

    Reports status, the resolved ref, resolver name and confidence; appends an
    error message or an extracted value when present.
    """
    icon = _STATUS_ICON.get(result.status, "?")
    head = "would resolve" if resolve_only and result.status == "dry_run" else result.status
    if result.target is not None:
        line = (
            f"{icon} {head}  {result.target.ref}  "
            f"({result.target.resolver_name}, conf={result.confidence:.2f})"
        )
        extracted = result.target.metadata.get("extracted_value")
        if extracted is not None:
            line += f"\n    value: {extracted!r}"
    else:
        line = f"{icon} {head}"
    if result.error is not None:
        line += f"\n    {result.error.message}"
    return line


async def evaluate(session, command, *, dry_run: bool = False) -> str:
    """Execute a REPL command against ``session`` and return printable output.

    ``dry_run`` is the session-wide resolve-only mode; a command may override it
    (``dry(...)`` forces resolve-only). ``help`` / ``quit`` / ``empty`` /
    ``toggle_dry`` are handled by the loop, not here.
    """
    resolve_only = command.dry_override if command.dry_override is not None else dry_run
    kind = command.kind

    try:
        if kind == "act":
            result = await session.act(command.text, dry_run=resolve_only)
            return format_result(result, resolve_only=resolve_only)
        if kind == "verify":
            result = await session.verify(command.text)
            return format_result(result, resolve_only=resolve_only)
        if kind == "extract":
            result = await session.extract(command.text)
            return format_result(result, resolve_only=resolve_only)
        if kind == "explain":
            return await session.explain(command.text, print_output=False)
        if kind == "goto":
            await session.goto(command.text)
            return f"→ navigated to {command.text}"
        if kind == "unknown":
            return f"✗ {command.error or 'unknown command'}"
    except NotImplementedError as exc:
        return f"✗ not supported here: {exc}"
    except Exception as exc:  # noqa: BLE001 — a bad step must not kill the REPL
        return f"✗ error: {exc}"

    return f"✗ unhandled command kind {kind!r}"
