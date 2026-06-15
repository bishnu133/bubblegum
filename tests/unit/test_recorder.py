"""Unit tests for the recorder / codegen core (A1).

Browser-free: exercises event normalization, coalescing, NL-label derivation
(with round-trip through the parser), script emission, the ActionRecorder
binding, and CLI argument parsing.
"""

from __future__ import annotations

import pytest

from bubblegum.core.parser.instruction import decompose
from bubblegum.core.recorder import (
    ActionRecorder,
    RecordedAction,
    RecordedStep,
    coalesce_actions,
    derive_steps,
    emit_script,
    normalize_event,
)
from bubblegum.core.recorder.codegen import action_to_step


# ---------------------------------------------------------------------------
# normalize_event
# ---------------------------------------------------------------------------


def test_normalize_event_basic_click():
    action = normalize_event(
        {"action": "click", "role": "Button", "name": " Login ", "tag": "BUTTON",
         "fallback_ref": 'role=button[name="Login"]'}
    )
    assert action == RecordedAction(
        action="click", role="button", name="Login", value=None,
        tag="button", fallback_ref='role=button[name="Login"]',
    )


def test_normalize_event_drops_unknown_action():
    assert normalize_event({"action": "hover", "name": "x"}) is None
    assert normalize_event({"name": "x"}) is None
    assert normalize_event("not a dict") is None


def test_normalize_event_collapses_and_caps_name():
    raw = {"action": "click", "name": "  Sign\n\n  In  now  "}
    assert normalize_event(raw).name == "Sign In now"

    long_name = "a " * 200
    capped = normalize_event({"action": "click", "name": long_name}).name
    assert len(capped) <= 120


def test_normalize_event_coerces_value_and_blank_ref():
    a = normalize_event({"action": "type", "name": "Qty", "value": 5, "fallback_ref": "   "})
    assert a.value == "5"
    assert a.fallback_ref is None


# ---------------------------------------------------------------------------
# coalesce_actions
# ---------------------------------------------------------------------------


def test_coalesce_merges_consecutive_type_on_same_field():
    raw = [
        {"action": "type", "name": "Username", "value": "to", "fallback_ref": "#user"},
        {"action": "type", "name": "Username", "value": "tomsmith", "fallback_ref": "#user"},
        {"action": "click", "name": "Login", "fallback_ref": "#login"},
    ]
    actions = coalesce_actions(raw)
    assert [a.action for a in actions] == ["type", "click"]
    assert actions[0].value == "tomsmith"


def test_coalesce_keeps_distinct_fields_separate():
    raw = [
        {"action": "type", "name": "Username", "value": "tom", "fallback_ref": "#user"},
        {"action": "type", "name": "Password", "value": "pw", "fallback_ref": "#pass"},
    ]
    actions = coalesce_actions(raw)
    assert [a.name for a in actions] == ["Username", "Password"]


def test_coalesce_skips_invalid_events():
    raw = [{"action": "scrollz"}, {"action": "click", "name": "Go"}]
    assert [a.name for a in coalesce_actions(raw)] == ["Go"]


# ---------------------------------------------------------------------------
# codegen / derive_steps — with parser round-trip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "action,expected_instruction,expected_type,expected_target,expected_value",
    [
        (RecordedAction("click", role="button", name="Login"),
         "Click Login", "click", "Login", None),
        (RecordedAction("type", role="textbox", name="Username", value="tomsmith"),
         'Enter "tomsmith" into Username', "type", "Username", "tomsmith"),
        (RecordedAction("select", role="combobox", name="Country", value="France"),
         'Select "France" from Country', "select", "Country", "France"),
        (RecordedAction("check", role="checkbox", name="Newsletter"),
         "Check Newsletter", "check", "Newsletter", None),
        (RecordedAction("uncheck", role="checkbox", name="Marketing"),
         "Uncheck Marketing", "uncheck", "Marketing", None),
    ],
)
def test_derive_step_roundtrips_through_parser(
    action, expected_instruction, expected_type, expected_target, expected_value
):
    step = action_to_step(action)
    assert step.instruction == expected_instruction

    # The emitted NL must parse back to the action the recorder observed.
    parsed = decompose(step.instruction)
    assert parsed.action_type == expected_type
    assert parsed.target_phrase == expected_target
    if expected_value is not None:
        assert parsed.input_value == expected_value


def test_derive_step_skips_nameless_action():
    step = action_to_step(RecordedAction("click", role="button", name=""))
    assert step.instruction is None
    assert "no accessible name" in step.skipped_reason


def test_derive_steps_preserves_order_and_fallback():
    actions = [
        RecordedAction("type", name="Email", value="a@b.com", fallback_ref="#email"),
        RecordedAction("click", name="Submit", fallback_ref="#submit"),
    ]
    steps = derive_steps(actions)
    assert steps[0].fallback_ref == "#email"
    assert steps[1].instruction == "Click Submit"


# ---------------------------------------------------------------------------
# emit_script
# ---------------------------------------------------------------------------


def test_emit_script_is_valid_python_with_steps_and_comments():
    steps = [
        RecordedStep('Enter "tom" into Username', "#user"),
        RecordedStep("Click Login", 'role=button[name="Login"]'),
        RecordedStep(None, None, skipped_reason="click target with no accessible name"),
    ]
    src = emit_script(steps, "https://example.com/login", headless=True)

    # Compiles as valid Python.
    compile(src, "<emitted>", "exec")

    assert 'await s.act(\'Enter "tom" into Username\')  # fallback: #user' in src
    assert 'await s.act(\'Click Login\')  # fallback: role=button[name="Login"]' in src
    assert "# skipped: click target with no accessible name" in src
    assert "https://example.com/login" in src
    assert "s.assert_all_passed()" in src
    assert "headless=True" in src


def test_emit_script_handles_no_actionable_steps():
    src = emit_script([RecordedStep(None, None, skipped_reason="nope")], "https://x.test")
    compile(src, "<emitted>", "exec")
    assert "no actionable steps were recorded" in src


def test_emit_script_emit_headed():
    src = emit_script([RecordedStep("Click Go", None)], "https://x.test", headless=False)
    assert "headless=False" in src


# ---------------------------------------------------------------------------
# ActionRecorder
# ---------------------------------------------------------------------------


def test_action_recorder_collects_and_derives():
    rec = ActionRecorder()
    rec._on_binding({"source": "page"}, {"action": "click", "name": "Login", "fallback_ref": "#l"})
    rec.record_raw({"action": "type", "name": "User", "value": "tom"})
    rec.record_raw("ignored-non-dict")

    assert len(rec.raw_events) == 2
    steps = rec.steps()
    # Events are kept in capture order: click first, then type.
    assert [s.instruction for s in steps] == ["Click Login", 'Enter "tom" into User']


@pytest.mark.asyncio
async def test_action_recorder_attach_wires_binding_and_script():
    class FakeContext:
        def __init__(self):
            self.binding = None
            self.scripts = []

        async def expose_binding(self, name, fn):
            self.binding = (name, fn)

        async def add_init_script(self, script):
            self.scripts.append(script)

    rec = ActionRecorder()
    ctx = FakeContext()
    await rec.attach(ctx)

    assert ctx.binding[0] == "__bubblegum_record__"
    assert ctx.scripts and "addEventListener" in ctx.scripts[0]


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------


def test_cli_parser_parses_record_command():
    from bubblegum.cli import build_parser

    args = build_parser().parse_args(["record", "--url", "https://x.test", "--out", "flow.py"])
    assert args.command == "record"
    assert args.url == "https://x.test"
    assert args.out == "flow.py"
    assert args.headless is False
    assert args.emit_headed is False


def test_cli_parser_record_requires_url_and_out():
    from bubblegum.cli import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(["record", "--url", "https://x.test"])


def test_cli_main_dispatches_to_run_record(monkeypatch):
    import bubblegum.cli.record as record_mod

    captured = {}

    def fake_run_record(*, url, out, headless, emit_headless):
        captured.update(url=url, out=out, headless=headless, emit_headless=emit_headless)
        return 0

    monkeypatch.setattr(record_mod, "run_record", fake_run_record)

    from bubblegum.cli import main

    code = main(["record", "--url", "https://x.test", "--out", "flow.py", "--emit-headed"])
    assert code == 0
    assert captured == {
        "url": "https://x.test", "out": "flow.py", "headless": False, "emit_headless": False,
    }


def test_cli_main_no_command_prints_help_and_returns_nonzero(capsys):
    from bubblegum.cli import main

    code = main([])
    assert code == 1
    assert "record" in capsys.readouterr().out
