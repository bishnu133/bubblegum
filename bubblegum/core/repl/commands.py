"""
bubblegum/core/repl/commands.py
===============================
Parse a typed REPL line into a structured :class:`ReplCommand` (A2).

The REPL (``bubblegum repl``) lets a tester try NL phrasings live against a
running page/app. A line may be:

  - a bare NL step               ``Click Login``            → act
  - a verb call                  ``act("Click Login")``     → act
                                 ``verify("Secure Area visible")`` → verify
                                 ``extract("Get flash message")``  → extract
                                 ``explain("Click Login")`` → explain (A3 rationale)
                                 ``dry("Click Login")``     → act, resolve-only (one-shot)
  - a meta command               ``:help`` ``:quit`` ``:dry [on|off]``
                                 ``:open <url>`` ``:explain <step>``

Pure + browser-free so the grammar is unit-testable; the CLI loop in
``bubblegum.cli.repl`` only reads lines and prints results.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Verb-call form: name("arg") / name('arg') / name(arg)
_CALL_RE = re.compile(r"^(act|verify|extract|explain|dry)\s*\((.*)\)\s*$", re.IGNORECASE | re.DOTALL)

# Verb-call name → (command kind, dry-run override)
_CALL_KINDS: dict[str, tuple[str, bool | None]] = {
    "act": ("act", None),
    "verify": ("verify", None),
    "extract": ("extract", None),
    "explain": ("explain", None),
    "dry": ("act", True),  # one-shot resolve-only
}

_QUIT = {"q", "quit", "exit"}
_HELP = {"h", "help", "?"}


@dataclass
class ReplCommand:
    """A parsed REPL line.

    kind:         act | verify | extract | explain | goto | toggle_dry |
                  help | quit | empty | unknown
    text:         instruction / argument (e.g. the NL step or a URL)
    dry_override: per-command dry-run override (``dry(...)`` sets True), else None
    error:        message when kind == "unknown"
    """

    kind: str
    text: str = ""
    dry_override: bool | None = None
    error: str | None = None


def _unquote(arg: str) -> str:
    """Strip one layer of matching surrounding quotes from a call argument."""
    arg = arg.strip()
    if len(arg) >= 2 and arg[0] == arg[-1] and arg[0] in "\"'":
        return arg[1:-1]
    return arg


def _parse_meta(body: str) -> ReplCommand:
    """Parse a ``:`` meta command (leading colon already stripped)."""
    parts = body.strip().split(None, 1)
    if not parts:
        return ReplCommand(kind="help")
    head = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if head in _QUIT:
        return ReplCommand(kind="quit")
    if head in _HELP:
        return ReplCommand(kind="help")
    if head == "dry":
        return ReplCommand(kind="toggle_dry", text=rest.lower())
    if head in {"open", "goto", "nav"}:
        if not rest:
            return ReplCommand(kind="unknown", error=f":{head} needs a URL")
        return ReplCommand(kind="goto", text=rest)
    if head in {"explain", "why"}:
        if not rest:
            return ReplCommand(kind="unknown", error=f":{head} needs a step")
        return ReplCommand(kind="explain", text=rest)
    return ReplCommand(kind="unknown", error=f"unknown command ':{head}' (try :help)")


def parse_repl_line(line: str) -> ReplCommand:
    """Parse one REPL input line into a :class:`ReplCommand`."""
    text = (line or "").strip()
    if not text:
        return ReplCommand(kind="empty")

    if text.startswith(":"):
        return _parse_meta(text[1:])

    call = _CALL_RE.match(text)
    if call:
        kind, dry = _CALL_KINDS[call.group(1).lower()]
        arg = _unquote(call.group(2))
        if not arg:
            return ReplCommand(kind="unknown", error="empty instruction")
        return ReplCommand(kind=kind, text=arg, dry_override=dry)

    # Bare line → act on it directly.
    return ReplCommand(kind="act", text=text)
