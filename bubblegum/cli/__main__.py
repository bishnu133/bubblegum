"""Enable ``python -m bubblegum.cli`` alongside the ``bubblegum`` console script."""

from bubblegum.cli import main

raise SystemExit(main())
