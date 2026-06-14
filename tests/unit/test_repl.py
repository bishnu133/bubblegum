"""Unit tests for the REPL / live-try core (A2).

Browser-free: line grammar, command evaluation against a fake session, result
formatting, the read-eval-print loop (driven by a scripted line reader), and
CLI argument parsing.
"""

from __future__ import annotations

import pytest

from bubblegum.cli.repl import repl_loop
from bubblegum.core.repl import ReplCommand, evaluate, format_result, parse_repl_line
from bubblegum.core.schemas import ErrorInfo, ResolvedTarget, StepResult


# ---------------------------------------------------------------------------
# parse_repl_line
# ---------------------------------------------------------------------------


def test_parse_bare_line_is_act():
    cmd = parse_repl_line("Click Login")
    assert cmd == ReplCommand(kind="act", text="Click Login")


@pytest.mark.parametrize(
    "line,kind,text,dry",
    [
        ('act("Click Login")', "act", "Click Login", None),
        ("verify('Secure Area visible')", "verify", "Secure Area visible", None),
        ('extract("Get flash message")', "extract", "Get flash message", None),
        ('explain("Click Login")', "explain", "Click Login", None),
        ('dry("Click Login")', "act", "Click Login", True),
        ("act(Click Login)", "act", "Click Login", None),  # unquoted arg
    ],
)
def test_parse_verb_call_forms(line, kind, text, dry):
    cmd = parse_repl_line(line)
    assert (cmd.kind, cmd.text, cmd.dry_override) == (kind, text, dry)


def test_parse_meta_commands():
    assert parse_repl_line(":quit").kind == "quit"
    assert parse_repl_line(":q").kind == "quit"
    assert parse_repl_line(":help").kind == "help"
    assert parse_repl_line(":").kind == "help"
    assert parse_repl_line(":dry on") == ReplCommand(kind="toggle_dry", text="on")
    assert parse_repl_line(":dry") == ReplCommand(kind="toggle_dry", text="")
    assert parse_repl_line(":open https://x.test") == ReplCommand(kind="goto", text="https://x.test")
    assert parse_repl_line(":explain Click Login") == ReplCommand(kind="explain", text="Click Login")


def test_parse_empty_and_unknown():
    assert parse_repl_line("   ").kind == "empty"
    assert parse_repl_line(":nope").kind == "unknown"
    assert parse_repl_line(":open").kind == "unknown"
    assert parse_repl_line("act()").kind == "unknown"


# ---------------------------------------------------------------------------
# format_result
# ---------------------------------------------------------------------------


def _passed(ref="role=button[name=\"Login\"]", resolver="exact_text", conf=0.95):
    return StepResult(
        status="passed",
        action="Click Login",
        target=ResolvedTarget(ref=ref, confidence=conf, resolver_name=resolver),
        confidence=conf,
    )


def test_format_passed_reports_ref_resolver_confidence():
    out = format_result(_passed())
    assert "✓ passed" in out
    assert 'role=button[name="Login"]' in out
    assert "exact_text" in out
    assert "conf=0.95" in out


def test_format_dry_run_says_would_resolve():
    r = StepResult(
        status="dry_run", action="Click Login",
        target=ResolvedTarget(ref="role=button", confidence=0.9, resolver_name="exact_text"),
        confidence=0.9,
    )
    assert "would resolve" in format_result(r, resolve_only=True)


def test_format_failed_shows_error():
    r = StepResult(
        status="failed", action="Click Nope", confidence=0.0,
        error=ErrorInfo(error_type="ResolutionFailedError", message="no candidates"),
    )
    out = format_result(r)
    assert "✗ failed" in out
    assert "no candidates" in out


def test_format_extract_shows_value():
    r = StepResult(
        status="passed", action="Get flash",
        target=ResolvedTarget(
            ref="text=Hi", confidence=1.0, resolver_name="exact_text",
            metadata={"extracted_value": "Hello"},
        ),
        confidence=1.0,
    )
    assert "value: 'Hello'" in format_result(r)


# ---------------------------------------------------------------------------
# evaluate (against a fake session)
# ---------------------------------------------------------------------------


class FakeSession:
    def __init__(self):
        self.calls = []

    async def act(self, instruction, **kwargs):
        self.calls.append(("act", instruction, kwargs))
        return _passed()

    async def verify(self, instruction, **kwargs):
        self.calls.append(("verify", instruction, kwargs))
        return _passed(resolver="exact_text")

    async def extract(self, instruction, **kwargs):
        self.calls.append(("extract", instruction, kwargs))
        return StepResult(
            status="passed", action=instruction,
            target=ResolvedTarget(
                ref="text=x", confidence=1.0, resolver_name="exact_text",
                metadata={"extracted_value": "v"},
            ),
            confidence=1.0,
        )

    async def explain(self, instruction, *, print_output=True, **kwargs):
        self.calls.append(("explain", instruction, kwargs))
        return f"EXPLANATION for {instruction}"

    async def goto(self, url, **kwargs):
        self.calls.append(("goto", url, kwargs))


@pytest.mark.asyncio
async def test_evaluate_act_executes_and_reports_resolver():
    s = FakeSession()
    out = await evaluate(s, parse_repl_line("Click Login"))
    assert s.calls[0][0] == "act"
    assert s.calls[0][2]["dry_run"] is False
    assert "exact_text" in out  # resolver surfaced


@pytest.mark.asyncio
async def test_evaluate_dry_override_forces_resolve_only():
    s = FakeSession()
    await evaluate(s, parse_repl_line('dry("Click Login")'), dry_run=False)
    assert s.calls[0][2]["dry_run"] is True


@pytest.mark.asyncio
async def test_evaluate_session_dry_run_propagates_to_act():
    s = FakeSession()
    await evaluate(s, parse_repl_line("Click Login"), dry_run=True)
    assert s.calls[0][2]["dry_run"] is True


@pytest.mark.asyncio
async def test_evaluate_explain_returns_rationale():
    s = FakeSession()
    out = await evaluate(s, parse_repl_line('explain("Click Login")'))
    assert out == "EXPLANATION for Click Login"


@pytest.mark.asyncio
async def test_evaluate_goto_navigates():
    s = FakeSession()
    out = await evaluate(s, parse_repl_line(":open https://x.test"))
    assert s.calls[0] == ("goto", "https://x.test", {})
    assert "navigated to https://x.test" in out


@pytest.mark.asyncio
async def test_evaluate_catches_step_errors():
    class Boom(FakeSession):
        async def act(self, instruction, **kwargs):
            raise RuntimeError("kaboom")

    out = await evaluate(Boom(), parse_repl_line("Click Login"))
    assert "✗ error: kaboom" in out


@pytest.mark.asyncio
async def test_evaluate_unknown_reports_error():
    out = await evaluate(FakeSession(), parse_repl_line(":nope"))
    assert out.startswith("✗")


# ---------------------------------------------------------------------------
# repl_loop
# ---------------------------------------------------------------------------


def _scripted_reader(lines):
    it = iter(lines)

    async def read(_prompt):
        try:
            return next(it)
        except StopIteration:
            return None  # EOF

    return read


@pytest.mark.asyncio
async def test_repl_loop_runs_steps_help_toggle_and_quits():
    s = FakeSession()
    out_lines: list[str] = []

    await repl_loop(
        s,
        read_line=_scripted_reader(["Click Login", ":dry on", "Click Login", ":help", ":quit", "ignored"]),
        emit=out_lines.append,
    )

    # Two act calls ran; second was resolve-only after :dry on.
    act_calls = [c for c in s.calls if c[0] == "act"]
    assert len(act_calls) == 2
    assert act_calls[0][2]["dry_run"] is False
    assert act_calls[1][2]["dry_run"] is True
    # :quit stopped the loop before the trailing line.
    assert any("resolve-only mode is ON" in line for line in out_lines)


@pytest.mark.asyncio
async def test_repl_loop_stops_on_eof():
    s = FakeSession()
    await repl_loop(s, read_line=_scripted_reader([]), emit=lambda _l: None)
    assert s.calls == []


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------


def test_cli_parses_repl_web():
    from bubblegum.cli import build_parser

    args = build_parser().parse_args(["repl", "--url", "https://x.test", "--dry-run"])
    assert args.command == "repl"
    assert args.url == "https://x.test"
    assert args.dry_run is True


def test_cli_repl_requires_a_target(capsys):
    from bubblegum.cli import main

    with pytest.raises(SystemExit):
        main(["repl"])
    assert "requires --url" in capsys.readouterr().err


def test_cli_main_dispatches_to_run_repl(monkeypatch):
    import bubblegum.cli.repl as repl_mod

    captured = {}
    monkeypatch.setattr(repl_mod, "run_repl", lambda **kw: captured.update(kw) or 0)

    from bubblegum.cli import main

    code = main(["repl", "--appium-url", "http://127.0.0.1:4723", "--caps", "{}"])
    assert code == 0
    assert captured["appium_url"] == "http://127.0.0.1:4723"
    assert captured["caps"] == "{}"
    assert captured["url"] is None
