"""Tests for the rich narration."""

import io

import pytest
from rich.console import Console

from brickwright.config import Effort
from brickwright.driver import Narrator, RunReport
from brickwright.driver.narration import (
    _TOOL_LOOK,
    _call_line,
    _call_summary,
    _fmt,
    _outcome_line,
    _outcome_summary,
    _report_lines,
)
from brickwright.record import Record, Timing, Usage
from brickwright.tools.registry import _ALL_TOOLS, ToolOutcome, format_subagent_results
from brickwright.tools.subagents import SubagentResult
from brickwright.tools.testing import CheckResult
from brickwright.tools.validation import BuildDimensions, ValidationReport


@pytest.fixture
def buf() -> io.StringIO:
    """A fresh in-memory text buffer for each test."""
    return io.StringIO()


@pytest.fixture
def console(buf) -> Console:
    """A rich console writing plain text to an in-memory buffer."""
    return Console(file=buf, force_terminal=False, no_color=True, width=100)


def render(renderable, console, buf) -> str:
    """Render a rich renderable to plain text via an in-memory console."""
    console.print(renderable)
    return buf.getvalue()


def _subagent_outcome(results: list[SubagentResult]) -> ToolOutcome:
    """A dispatch_subagents outcome carrying the real serialized results JSON."""
    return ToolOutcome(format_subagent_results(results), ok=all(r.ok for r in results))


class TestLifecycle:
    """Each Narrator lifecycle hook renders the right thing."""

    def test_header_describes_unlimited_count_budgets(
        self, record, config, console, buf
    ):
        config = config.model_copy(update={"max_turns": 0, "max_validations": 0})
        Narrator(console).run_started(record, config)
        assert "unlimited turns" in buf.getvalue()
        assert "unlimited validations" in buf.getvalue()

    def test_run_started_panels_the_prompt_and_run_limits(
        self, record, config, console, buf
    ):
        config = config.model_copy(
            update={
                "model": "test/model",
                "effort": Effort.HIGH,
                "max_validations": 7,
                "max_turns": 9,
                "max_cost": 1.5,
            }
        )
        Narrator(console).run_started(record, config)
        out = buf.getvalue()
        assert "build a wall" in out  # the record's prompt is echoed
        assert "test/model" in out and "high" in out  # model + effort
        assert "7 validations" in out and "9 turns" in out  # the budget caps
        assert "$1.50" in out  # the cost cap

    def test_turn_started_rules_each_turn(self, console, buf):
        Narrator(console).turn_started(5)
        assert "turn 5" in buf.getvalue()

    def test_model_message_is_rendered_stripped(self, console, buf):
        Narrator(console).model_message("  thinking aloud  ")
        assert "thinking aloud" in buf.getvalue()

    def test_thinking_yields_a_usable_status_context(self, console, buf):
        with Narrator(console).thinking():
            pass

    def test_tool_called_names_the_tool_and_summarizes_its_arguments(
        self, console, buf
    ):
        Narrator(console).tool_called("write_build", {"content": "a\nb\nc"})
        out = buf.getvalue()
        assert "write" in out and "3 lines" in out

    def test_run_finished_summarizes_a_successful_run(self, record, console, buf):
        result = RunReport(
            done=True,
            source_sha256=record.source_sha256,
            report=ValidationReport(ok=True, source_sha256=record.source_sha256),
            validations=4,
            turns=9,
            usage=Usage(
                prompt_tokens=111,
                completion_tokens=22,
                total_tokens=133,
                cost_usd=0.1234,
            ),
            timing=Timing(
                total=12.5,
                llm=8.0,
                tools={"validate": 3.0, "read_build": 1.0},
                other=0.5,
            ),
        )
        Narrator(console).run_finished(record, result)
        out = buf.getvalue()
        assert "finished" in out and "build valid" in out
        # the labeled rows: tokens (total + in/out split), validations, turns
        assert "tokens" in out and "133" in out and "111" in out and "22" in out
        assert "validations" in out and "turns" in out
        assert "$0.1234" in out  # cost is shown when known
        # elapsed total plus the per-phase breakdown; tool times are summed into a
        # single figure (3.0 + 1.0) rather than listed per tool, to avoid clutter.
        assert "12.5s" in out
        assert all(s in out for s in ("llm 8.0", "tools 4.0", "other 0.5"))
        assert "read_build" not in out

    def test_run_finished_marks_a_done_but_invalid_run(self, record, console, buf):
        # done but the last report failed -- never the green "valid" outcome.
        result = RunReport(
            done=True,
            report=ValidationReport(ok=False),
            validations=1,
            turns=2,
            usage=Usage(),
        )
        Narrator(console).run_finished(record, result)
        out = buf.getvalue()
        assert "build invalid" in out
        assert "build valid" not in out

    def test_run_finished_omits_the_cost_row_when_cost_is_unknown(
        self, record, console, buf
    ):
        result = RunReport(
            done=True,
            report=ValidationReport(ok=True),
            validations=1,
            turns=1,
            usage=Usage(prompt_tokens=5, completion_tokens=5, total_tokens=10),
        )
        Narrator(console).run_finished(record, result)
        assert "cost" not in buf.getvalue()  # the row is dropped entirely

    def test_summary_panel_prints_the_output_dir_verbatim(self, config, tmp_path, buf):
        console = Console(file=buf, force_terminal=False, no_color=True, width=500)
        config = config.model_copy(update={"records_dir": tmp_path / "runs[/x]"})
        record = Record.create(config, prompt="x")
        result = RunReport(done=True, validations=0, turns=1, usage=Usage())
        Narrator(console).run_finished(record, result)
        assert "runs[/x]" in buf.getvalue()

    def test_summary_panel_does_not_mark_a_stalled_run_valid(
        self, record, console, buf
    ):
        # A run that stalled before finalizing is never the green "valid" outcome,
        # even if its last report happened to pass.
        result = RunReport(
            done=False,
            report=ValidationReport(ok=True),
            validations=1,
            turns=1,
            usage=Usage(),
        )
        Narrator(console).run_finished(record, result)
        out = buf.getvalue()
        assert "stalled" in out
        assert "build valid" not in out


class TestNarratorDispatch:
    """Narrator routes outcomes to the right renderer."""

    def test_tool_finished_renders_a_non_validate_outcome(self, console, buf):
        Narrator(console).tool_finished("read_build", ToolOutcome("a\nb\nc"))
        assert "3 lines" in buf.getvalue()

    def test_tool_finished_validate_with_a_report_renders_the_report(
        self, console, buf
    ):
        # A validate outcome carrying a report routes to the report renderer.
        report = ValidationReport.error("Traceback\nSyntaxError: bad")
        Narrator(console).tool_finished("validate", ToolOutcome("boom", report=report))
        out = buf.getvalue()
        assert "build failed" in out
        assert "SyntaxError: bad" in out

    def test_tool_finished_validate_renders_passing_checks(self, console, buf):
        report = ValidationReport(
            ok=True,
            checks=[
                CheckResult(name="connected", passed=True, detail=""),
                CheckResult(name="no_collisions", passed=True, detail=""),
            ],
        )
        Narrator(console).tool_finished("validate", ToolOutcome("ok", report=report))
        out = buf.getvalue()
        assert "connected" in out and "no_collisions" in out

    def test_warn_renders_a_warning_line(self, console, buf):
        Narrator(console).warn("the cost limit cannot be enforced")
        assert "cannot be enforced" in buf.getvalue()

    def test_tool_finished_validate_without_a_report_does_not_crash(self, console, buf):
        # A validate outcome carrying no report falls back to an outcome line
        # rather than trying to render a (missing) report.
        Narrator(console).tool_finished("validate", ToolOutcome("ok: validated"))
        assert "✓" in buf.getvalue()


class TestCallRendering:
    def test_write_build_summary_counts_content_lines(self):
        assert _call_summary("write_build", {"content": "a\nb\nc"}) == "3 lines"

    def test_edit_build_summary_shows_new_str_snippet(self):
        assert "abcde" in _call_summary("edit_build", {"new_str": "abcde"})

    def test_insert_build_summary_shows_the_inserted_text(self):
        assert "abcde" in _call_summary("insert_build", {"insert_text": "abcde"})

    def test_multi_edit_build_summary_counts_the_edits(self):
        args = {"edits": [{"old_str": "a", "new_str": "b"}] * 3}
        assert _call_summary("multi_edit_build", args) == "3 edits"

    def test_every_tool_has_a_look(self):
        for tool in _ALL_TOOLS:
            assert tool["function"]["name"] in _TOOL_LOOK

    def test_multi_edit_build_summary_tolerates_non_list_edits(self):
        assert _call_summary("multi_edit_build", {"edits": 5}) == "0 edits"

    def test_explore_summary_shows_the_first_line_of_code(self):
        summary = _call_summary(
            "explore", {"code": "print(model.brick_count)\nprint(x)"}
        )
        assert summary == "print(model.brick_count)"

    def test_explore_summary_truncates_a_long_first_line(self):
        summary = _call_summary("explore", {"code": "x" * 200})
        assert summary.endswith("…") and len(summary) < 200

    def test_dispatch_subagents_summary_shows_the_prompt_of_a_lone_task(self):
        summary = _call_summary(
            "dispatch_subagents", {"tasks": [{"prompt": "count the red bricks"}]}
        )
        assert summary == "count the red bricks"

    def test_dispatch_subagents_summary_counts_multiple_tasks(self):
        summary = _call_summary(
            "dispatch_subagents",
            {"tasks": [{"prompt": "a"}, {"prompt": "b"}, {"prompt": "c"}]},
        )
        assert summary == "3 subagents"

    def test_dispatch_subagents_summary_is_empty_without_tasks(self):
        assert _call_summary("dispatch_subagents", {}) == ""

    def test_other_tools_have_no_summary(self):
        assert _call_summary("validate", {}) == ""

    def test_call_line_uses_the_mapped_label_not_the_raw_tool_name(self):
        plain = _call_line("write_build", {"content": "a\nb\nc"}).plain
        assert "write_build" not in plain  # mapped to the short "write" label
        assert "write" in plain and "3 lines" in plain  # label + summary wired in


class TestOutcomeLine:
    def test_marks_success_from_the_ok_flag(self):
        line = _outcome_line("explore", ToolOutcome("Brick parts", ok=True))
        assert "✓" in line.plain

    def test_marks_failure_from_the_ok_flag(self):
        line = _outcome_line("edit_build", ToolOutcome("edit failed: x", ok=False))
        assert "✗" in line.plain


class TestOutcomeSummary:
    """A short display gloss for a non-validate tool result."""

    def test_read_build_reports_a_line_count(self):
        assert _outcome_summary("read_build", ToolOutcome("a\nb\nc")) == "3 lines"

    def test_strips_the_ok_prefix_from_a_status_string(self):
        out = ToolOutcome("ok: build.py written")
        assert _outcome_summary("write_build", out) == "build.py written"

    def test_explore_shows_a_single_short_line_of_output_verbatim(self):
        assert _outcome_summary("explore", ToolOutcome("42 bricks")) == "42 bricks"

    def test_explore_summarizes_multiline_output_by_line_count(self):
        out = ToolOutcome("a\nb\nc\nd")
        assert _outcome_summary("explore", out) == "4 lines of output"

    def test_edit_outcome_gloss_is_one_line(self):
        outcome = ToolOutcome("ok: build.py edited. Edited region:\n1: a\n2: b")
        assert _outcome_summary("edit_build", outcome) == (
            "build.py edited. Edited region:"
        )

    @pytest.mark.parametrize("tool_name", ["explore", "render", "finalize"])
    def test_tool_failures_shows_the_last_line_of_the_error(self, tool_name):
        out = ToolOutcome(
            f"{tool_name} error:\nTraceback...\nValueError: boom", ok=False
        )
        assert _outcome_summary(tool_name, out) == "ValueError: boom"

    @pytest.mark.parametrize(
        "tool_name", ["edit_build", "insert_build", "multi_edit_build", "read_build"]
    )
    def test_edit_family_failure_gloss_shows_the_first_line(self, tool_name):
        out = ToolOutcome(
            "edit failed: old_str not found.\nClosest match, lines 2-3:\n2: x",
            ok=False,
        )
        assert _outcome_summary(tool_name, out) == "edit failed: old_str not found."

    def test_dispatch_all_ok_reports_how_many_subagents_returned(self):
        out = _subagent_outcome(
            [SubagentResult(ok=True, text="a"), SubagentResult(ok=True, text="b")]
        )
        assert _outcome_summary("dispatch_subagents", out) == "2 subagents returned"

    def test_dispatch_with_a_failure_reports_the_ratio_and_reason(self):
        out = _subagent_outcome(
            [
                SubagentResult(ok=True, text="a"),
                SubagentResult(ok=False, reason="subagent crashed: boom"),
            ]
        )
        summary = _outcome_summary("dispatch_subagents", out)
        assert summary == "1/2 subagents failed — subagent crashed: boom"

    def test_dispatch_falls_back_to_the_last_line_on_unparsable_content(self):
        out = ToolOutcome(
            "dispatch_subagents failed: `tasks` must be a non-empty list", ok=False
        )
        summary = _outcome_summary("dispatch_subagents", out)
        assert summary == "dispatch_subagents failed: `tasks` must be a non-empty list"


class TestReportLines:
    """A validation report rendered as status / size / checks lines."""

    def test_shows_only_the_last_line_of_a_build_error(self, console, buf):
        report = ValidationReport.error(
            "Traceback (most recent call last):\nFile thing\nValueError: boom"
        )
        out = render(_report_lines(report), console, buf)
        assert "build failed" in out
        assert "ValueError: boom" in out  # the last line is the useful one
        assert "Traceback" not in out and "File thing" not in out

    def test_shows_dimensions_and_part_count(self, console, buf):
        report = ValidationReport(
            ok=True,
            dimensions=BuildDimensions(width=2, depth=3, height=1.0),
            brick_count=5,
        )
        out = render(_report_lines(report), console, buf)
        assert "2×3×1" in out
        assert "5 parts" in out

    def test_shows_detail_only_for_failed_checks(self, console, buf):
        report = ValidationReport(
            ok=False,
            checks=[
                CheckResult(name="passed_check", passed=True, detail="hidden detail"),
                CheckResult(name="failed_check", passed=False, detail="the reason"),
            ],
        )
        out = render(_report_lines(report), console, buf)
        assert "the reason" in out  # a failed check's detail is shown
        assert "hidden detail" not in out  # a passed check's detail is not


class TestFmtHeight:
    def test_trims_whole_brick_heights_but_keeps_fractions(self):
        assert _fmt(2.0) == "2"
        assert _fmt(1.5) == "1.5"
