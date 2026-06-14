"""Interactive REPL / live-try mode (A2).

Pure, browser-free pieces shared by the ``bubblegum repl`` CLI:
  - ``parse_repl_line`` / ``ReplCommand``  the line grammar
  - ``evaluate``                            run a command against a live session
  - ``format_result`` / ``HELP_TEXT``       rendering helpers
"""

from bubblegum.core.repl.commands import ReplCommand, parse_repl_line
from bubblegum.core.repl.evaluate import HELP_TEXT, evaluate, format_result

__all__ = [
    "ReplCommand",
    "parse_repl_line",
    "evaluate",
    "format_result",
    "HELP_TEXT",
]
