"""Enable ``python -m bubblegum.bridge`` alongside the ``bubblegum bridge`` command."""

from bubblegum.cli.bridge import run_bridge

raise SystemExit(run_bridge())
