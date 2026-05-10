from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "smoke_examples.py"
spec = importlib.util.spec_from_file_location("smoke_examples", MODULE_PATH)
smoke_examples = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(smoke_examples)


def test_planned_infra_free_commands_only() -> None:
    commands = smoke_examples.planned_infra_free_commands()
    assert len(commands) == 2
    assert commands[0][1] == "examples/ocr_callable_hydration_example.py"
    assert commands[1][1] == "examples/report_artifacts_example.py"


def test_manual_commands_include_playwright_appium_openai() -> None:
    manual = smoke_examples.MANUAL_COMMANDS
    assert "python -m playwright install chromium" in manual
    assert "python examples/appium_quickstart.py" in manual
    assert "python examples/openai_vision_provider_manual_example.py" in manual


def test_dry_run_executes_nothing(monkeypatch) -> None:
    called = []

    def _run(*_args, **_kwargs):
        called.append(True)
        raise AssertionError("subprocess.run should not be called in dry-run")

    monkeypatch.setattr(smoke_examples.subprocess, "run", _run)
    rc = smoke_examples.main(["--dry-run"])
    assert rc == 0
    assert called == []


def test_failure_exit_when_infra_free_command_fails(monkeypatch) -> None:
    class _Completed:
        def __init__(self, returncode: int):
            self.returncode = returncode

    state = {"count": 0}

    def _run(*_args, **_kwargs):
        state["count"] += 1
        return _Completed(1 if state["count"] == 2 else 0)

    monkeypatch.setattr(smoke_examples.subprocess, "run", _run)
    rc = smoke_examples.main([])
    assert rc == 1
