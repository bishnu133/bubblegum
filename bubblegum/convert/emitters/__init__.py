"""Code emitters: Canonical IR → .feature / .py / .ts scaffolds."""

from bubblegum.convert.emitters.feature import emit_feature_file
from bubblegum.convert.emitters.python_bdd import emit_python_steps
from bubblegum.convert.emitters.typescript_bdd import emit_typescript_steps

__all__ = ["emit_feature_file", "emit_python_steps", "emit_typescript_steps"]
