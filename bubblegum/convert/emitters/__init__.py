"""Code emitters: Canonical IR → smart-tests TypeScript (default) / .feature / pytest-bdd."""

from bubblegum.convert.emitters.feature import emit_feature_file
from bubblegum.convert.emitters.python_bdd import emit_python_steps
from bubblegum.convert.emitters.ts_smart import emit_flow_file, emit_test_file

__all__ = [
    "emit_flow_file",
    "emit_test_file",
    "emit_feature_file",
    "emit_python_steps",
]
