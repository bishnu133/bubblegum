"""
Bubblegum BDD layer.

Gives manual-QA personas Given/When/Then on top of the natural-language engine.

Two entry points:

  - `execute_step(session, text)` — a framework-agnostic dispatcher that maps a
    single Gherkin step onto a BubblegumSession call. Use it directly, or from a
    custom runner. Fully usable without pytest-bdd.

  - `bubblegum.bdd.steps` — ready-made pytest-bdd step definitions. Import it
    from your test module (or conftest) to register Given/When/Then steps that
    delegate to `execute_step`. Requires the optional `pytest-bdd` dependency
    (`pip install "bubblegum-ai[bdd]"`).
"""

from bubblegum.bdd.dispatcher import BddStepError, execute_step

__all__ = ["BddStepError", "execute_step"]
