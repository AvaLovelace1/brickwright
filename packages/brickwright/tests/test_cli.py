"""Tests for the brickwright CLI."""

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from brickwright.cli import app
from brickwright.config import Config, Effort
from brickwright.driver import RunReport
from brickwright.driver.critique import VIEWPOINT_COMPARE_PROMPT
from brickwright.driver.viewpoint import VIEWPOINT_TASK
from brickwright.prompts import system_prompt
from brickwright.record import Meta, Record, ValidationFailures
from brickwright.tools.validation import ValidationReport

pytestmark = pytest.mark.integration

runner = CliRunner()


@pytest.fixture
def rd(tmp_path: Path):
    """A --records-dir argument pointing at a temp location."""
    return str(tmp_path / "records")


def run(*argv):
    """Invoke the CLI, returning Click's ``Result`` (exit_code, stdout, ...).

    Force color off so substring assertions see plain text (no ``rich`` colorization).
    """
    return runner.invoke(app, list(argv), env={"FORCE_COLOR": None, "NO_COLOR": "1"})


def ext(*argv):
    """Invoke an ``external`` subcommand (the agent-facing record operations)."""
    return run("external", *argv)


def _init_fields(out: str) -> dict[str, str]:
    """Parse init's ``key=value`` output lines into a dict."""
    return dict(line.split("=", 1) for line in out.splitlines())


def _init(rd: str, *extra) -> str:
    result = ext("init", "a red tower", "--records-dir", rd, *extra)
    assert result.exit_code == 0
    return _init_fields(result.stdout)["record_id"]


def _record(rd: str, record_id: str) -> Record:
    """Load a record."""
    return Record.load(Config(records_dir=Path(rd)), record_id)


def _meta(rd: str, record_id: str) -> Meta:
    """Load a record's metadata straight from disk."""
    return _record(rd, record_id).read_meta()


class TestGenerate:
    """`generate` initializes a record from a prompt (or --from) and drives the
    agent on it. The driver is mocked here -- this checks the CLI creates the
    record, builds the right Config, and maps the result to an exit code."""

    def test_initializes_a_record_then_runs_the_agent(self, rd, monkeypatch):
        seen = {}

        def fake(record, config):
            seen["record_id"] = record.id
            return RunReport(
                done=True,
                turns=2,
                validations=1,
                source_sha256=record.source_sha256,
                report=ValidationReport(ok=True, source_sha256=record.source_sha256),
            )

        monkeypatch.setattr("brickwright.cli.run_agent", fake)
        result = run("generate", "a tower", "--records-dir", rd)
        assert result.exit_code == 0
        # A real record was created before the agent ran.
        record_id = seen["record_id"]
        assert _record(rd, record_id).build_path.is_file()
        # Driver-built records are not marked external.
        assert _meta(rd, record_id).generation.external is False
        assert _meta(rd, record_id).prompt == "a tower"

    def test_uses_given_model_effort_turns_and_validations(self, rd, monkeypatch):
        seen = {}

        def fake(record, config):
            seen.update(
                model=config.model,
                effort=config.effort.value,
                turns=config.max_turns,
                validations=config.max_validations,
                build_timeout=config.build_timeout,
                render_timeout=config.render_timeout,
                cost=config.max_cost,
            )
            return RunReport(
                done=True,
                turns=1,
                validations=1,
                source_sha256=record.source_sha256,
                report=ValidationReport(ok=True, source_sha256=record.source_sha256),
            )

        monkeypatch.setattr("brickwright.cli.run_agent", fake)
        result = run(
            "generate",
            "a tower",
            "--records-dir",
            rd,
            "--model",
            "cli/model",
            "--effort",
            "high",
            "--max-turns",
            "7",
            "--max-validations",
            "5",
            "--build-timeout",
            "12.5",
            "--render-timeout",
            "45.0",
            "--max-cost",
            "0.5",
        )
        assert result.exit_code == 0
        assert seen == {
            "model": "cli/model",
            "effort": "high",
            "turns": 7,
            "validations": 5,
            "build_timeout": 12.5,
            "render_timeout": 45.0,
            "cost": 0.5,
        }

    def test_uses_given_subagent_options(self, rd, monkeypatch):
        seen = {}

        def fake(record, config):
            seen.update(
                enabled=config.subagents_enabled,
                parallel=config.max_parallel_subagents,
                turns=config.subagent_max_turns,
                cost=config.subagent_max_cost,
            )
            return RunReport(
                done=True,
                turns=1,
                validations=1,
                source_sha256=record.source_sha256,
                report=ValidationReport(ok=True, source_sha256=record.source_sha256),
            )

        monkeypatch.setattr("brickwright.cli.run_agent", fake)
        result = run(
            "generate",
            "a tower",
            "--records-dir",
            rd,
            "--use-subagents",
            "--max-parallel-subagents",
            "2",
            "--subagent-max-turns",
            "30",
            "--subagent-max-cost",
            "0.25",
        )
        assert result.exit_code == 0
        assert seen == {"enabled": True, "parallel": 2, "turns": 30, "cost": 0.25}

    def test_image_option_is_copied_into_the_record(
        self, rd, tmp_path, monkeypatch, png_bytes
    ):
        img = tmp_path / "ref.png"
        img.write_bytes(png_bytes)
        seen = {}

        def fake(record, config):
            seen["id"] = record.id
            return RunReport(
                done=True,
                turns=0,
                validations=0,
                source_sha256=record.source_sha256,
                report=ValidationReport(ok=True, source_sha256=record.source_sha256),
            )

        monkeypatch.setattr("brickwright.cli.run_agent", fake)
        result = run("generate", "a tower", "--records-dir", rd, "--image", str(img))
        assert result.exit_code == 0
        assert _meta(rd, seen["id"]).prompt_image == "prompt.png"
        prompt_image_path = _record(rd, seen["id"]).prompt_image_path
        assert prompt_image_path is not None
        assert prompt_image_path.read_bytes() == png_bytes

    def test_clones_with_from(self, rd, monkeypatch):
        source = _init(rd)
        seen = {}

        def fake(record, config):
            seen["id"] = record.id
            return RunReport(
                done=True,
                turns=0,
                validations=0,
                source_sha256=record.source_sha256,
                report=ValidationReport(ok=True, source_sha256=record.source_sha256),
            )

        monkeypatch.setattr("brickwright.cli.run_agent", fake)
        result = run("generate", "--records-dir", rd, "--from", source)
        assert result.exit_code == 0
        assert seen["id"] != source
        assert _record(rd, seen["id"]).build_path.is_file()

    def test_nonzero_exit_when_unfinished_or_invalid(self, rd, monkeypatch):
        monkeypatch.setattr(
            "brickwright.cli.run_agent",
            lambda record, config: RunReport(
                done=True, turns=1, validations=1, report=ValidationReport(ok=False)
            ),
        )
        result = run("generate", "a tower", "--records-dir", rd)
        assert result.exit_code != 0

    def test_generate_help_shows_the_effort_default(self):
        # Config defaults are wired into the options, so --help displays them.
        # (Strip Rich's line-wrapping so the multi-column help is searchable.)
        out = run("generate", "--help").stdout.replace("\n", " ")
        assert "high" in out  # Effort.HIGH, the default


class TestShow:
    def test_creates_a_record_and_prints_its_id(self, rd):
        record_id = _init(rd)
        # The id is usable by other commands.
        result = run("show", record_id, "--records-dir", rd)
        assert result.exit_code == 0
        assert record_id in result.stdout


class TestLs:
    def test_ls_lists_records(self, rd):
        a = _init(rd)
        b = _init(rd)
        result = run("ls", "--records-dir", rd)
        assert result.exit_code == 0
        assert a in result.stdout and b in result.stdout

    def test_ls_reports_a_record_with_corrupt_metadata(self, rd):
        a = _init(rd)
        b = _init(rd)
        _record(rd, a).meta_path.write_text("{not json")
        result = run("ls", "--records-dir", rd)
        assert result.exit_code == 0
        assert re.search(rf"{a}\s+unreadable", result.stdout)
        assert b in result.stdout

    def test_ls_is_empty_when_none(self, rd):
        result = run("ls", "--records-dir", rd)
        assert result.exit_code == 0
        assert result.stdout.strip() == ""

    def test_markup_like_prompts_are_printed_verbatim(self, rd):
        prompt = "tower [/] with [red on white] flags"
        result = ext("init", prompt, "--records-dir", rd)
        assert result.exit_code == 0
        record_id = _init_fields(result.stdout)["record_id"]

        ls_result = run("ls", "--records-dir", rd)
        assert ls_result.exit_code == 0
        assert prompt in ls_result.stdout

        show_result = run("show", record_id, "--records-dir", rd)
        assert show_result.exit_code == 0
        assert "[/]" in show_result.stdout


class TestGallery:
    def test_prints_the_gallery(self):
        result = run("gallery")
        assert result.exit_code == 0
        assert "BrickWright" in result.stdout  # the lifecycle banner
        assert "✓" in result.stdout and "✗" in result.stdout


class TestInit:
    def test_prints_record_id_and_build_path(self, rd):
        # init prints labeled "record_id=" and "build_path=" lines, so an
        # external agent can edit that build.py directly (no read/write/edit).
        result = ext("init", "a tower", "--records-dir", rd)
        assert result.exit_code == 0
        lines = result.stdout.splitlines()
        assert lines[0].startswith("record_id=")
        assert lines[1].startswith("build_path=")
        fields = _init_fields(result.stdout)
        path = Path(fields["build_path"])
        assert path == _record(rd, fields["record_id"]).build_path
        assert path.is_file()
        assert "def create_build(" in path.read_text()

    def test_records_dir_defaults_from_the_env_var(self, tmp_path, monkeypatch):
        # With no --records-dir, the BRICKWRIGHT_RECORDS_DIR env var picks the home.
        env_dir = tmp_path / "from-env"
        monkeypatch.setenv("BRICKWRIGHT_RECORDS_DIR", str(env_dir))
        result = ext("init", "a tower")
        assert result.exit_code == 0
        build_path = Path(_init_fields(result.stdout)["build_path"])
        assert env_dir in build_path.parents

    def test_missing_image_leaves_no_partial_record(self, rd):
        result = ext("init", "a tower", "--records-dir", rd, "--image", "nope.png")
        assert result.exit_code != 0
        ls_result = run("ls", "--records-dir", rd)
        assert ls_result.exit_code == 0
        assert ls_result.stdout.strip() == ""

    def test_rejects_missing_prompt_image_and_from(self, rd):
        # init/generate need at least one of: a prompt, --image, or --from.
        result = ext("init", "--records-dir", rd)
        assert result.exit_code != 0
        assert "provide a prompt" in result.output

    def test_from_clones_an_existing_record(self, rd):
        source = _init(rd)
        # Edit the source build.py directly, then clone it.
        source_model = _record(rd, source).build_path
        source_model.write_text(source_model.read_text().replace("2, 2", "4, 2"))
        result = ext("init", "--records-dir", rd, "--from", source)
        clone_id = _init_fields(result.stdout)["record_id"]
        assert result.exit_code == 0 and clone_id != source
        assert "brick(4, 2" in _record(rd, clone_id).read_build()

    @pytest.mark.usefixtures("in_process")
    def test_init_marks_the_record_as_external(self, rd):
        record_id = _init(rd)
        assert _meta(rd, record_id).generation.external is True


class TestInstructions:
    def test_prints_the_external_system_prompt(self):
        result = ext("instructions")
        assert result.exit_code == 0
        assert system_prompt(external=True) in result.stdout

    def test_agent_doc_lists_the_real_effort_values(self):
        doc = (Path(__file__).parents[1] / "EXTERNAL_AGENT_INSTRUCTIONS.md").read_text()
        match = re.search(r"--effort ([a-z|]+)", doc)
        assert match is not None
        assert set(match.group(1).split("|")) == {e.value for e in Effort}


@pytest.mark.usefixtures("in_process")
class TestValidate:
    def test_valid_build_exits_zero(self, rd, valid_build):
        record_id = _init(rd)
        _record(rd, record_id).build_path.write_text(valid_build)
        result = ext("validate", record_id, "--records-dir", rd)
        assert result.exit_code == 0
        assert '"ok": true' in result.stdout

    def test_invalid_build_exits_nonzero(self, rd, in_process):
        record_id = _init(rd)
        _record(rd, record_id).build_path.write_text("")  # empty build.py is invalid
        result = ext("validate", record_id, "--records-dir", rd)
        assert result.exit_code != 0
        assert '"ok": false' in result.stdout

    def test_validate_counts_each_cycle_as_a_validation(self, rd):
        record_id = _init(rd)
        assert _meta(rd, record_id).validations == 0
        ext("validate", record_id, "--records-dir", rd)
        ext("validate", record_id, "--records-dir", rd)
        assert _meta(rd, record_id).validations == 2

    def test_failed_validate_still_counts(self, rd, raising_build):
        record_id = _init(rd)
        model = _record(rd, record_id).build_path
        model.write_text(raising_build)
        ext("validate", record_id, "--records-dir", rd)
        assert _meta(rd, record_id).validations == 1

    def test_all_tools_are_counted_in_tool_calls(self, rd):
        record_id = _init(rd)
        # init does not record itself as a tool call.
        assert _meta(rd, record_id).tool_calls == {}
        ext("validate", record_id, "--records-dir", rd)
        ext("validate", record_id, "--records-dir", rd)
        ext("render", record_id, "--records-dir", rd)
        ext("finalize", record_id, "--records-dir", rd)
        assert _meta(rd, record_id).tool_calls == {
            "validate": 2,
            "render": 1,
            "finalize": 1,
        }

    def test_refused_validate_is_not_counted_as_a_tool_call(self, rd):
        record_id = _init(rd)

        def validate():
            return ext(
                "validate", record_id, "--max-validations", "1", "--records-dir", rd
            )

        assert validate().exit_code == 0
        assert validate().exit_code != 0  # budget spent; refused before any work
        assert _meta(rd, record_id).tool_calls == {"validate": 1}

    def test_zero_disables_the_external_validation_limit(self, rd):
        record_id = _init(rd)
        _record(rd, record_id).update_meta(validations=100)
        result = ext(
            "validate", record_id, "--max-validations", "0", "--records-dir", rd
        )
        assert result.exit_code == 0
        assert _meta(rd, record_id).validations == 101

    def test_validate_refuses_past_the_validation_budget(self, rd):
        record_id = _init(rd)

        def validate():
            return ext(
                "validate", record_id, "--max-validations", "2", "--records-dir", rd
            )

        # Spend the budget, then one more call is refused without re-validating.
        assert validate().exit_code == 0
        assert validate().exit_code == 0
        refused = validate()
        assert refused.exit_code != 0
        assert "budget" in refused.stderr
        assert _meta(rd, record_id).validations == 2  # the refused call didn't count

    def test_validate_tracks_a_build_error_by_type(self, rd, raising_build):
        record_id = _init(rd)
        _record(rd, record_id).build_path.write_text(raising_build)
        ext("validate", record_id, "--records-dir", rd)
        failures = _meta(rd, record_id).validation_failures
        assert failures is not None
        assert failures.build_errors == {"RuntimeError": 1}
        assert failures.failing_checks == {}

    def test_validate_accumulates_failing_checks_across_calls(self, rd, floating_build):
        record_id = _init(rd)
        _record(rd, record_id).build_path.write_text(floating_build)
        ext("validate", record_id, "--records-dir", rd)
        ext("validate", record_id, "--records-dir", rd)
        failures = _meta(rd, record_id).validation_failures
        assert failures is not None
        assert failures.failing_checks == {"no_floating": 2}
        assert failures.build_errors == {}

    def test_a_passing_validate_records_no_failures(self, rd, valid_build):
        record_id = _init(rd)
        _record(rd, record_id).build_path.write_text(valid_build)
        ext("validate", record_id, "--records-dir", rd)
        failures = _meta(rd, record_id).validation_failures
        assert failures == ValidationFailures()


@pytest.mark.usefixtures("in_process")
class TestFinalize:
    def test_renders_the_model_and_exits_zero(self, rd, valid_build):
        record_id = _init(rd)
        _record(rd, record_id).build_path.write_text(valid_build)
        result = ext("finalize", record_id, "--records-dir", rd)
        assert result.exit_code == 0
        assert _record(rd, record_id).ldr_path.is_file()

    def test_build_error_exits_nonzero(self, rd, raising_build):
        record_id = _init(rd)
        model = _record(rd, record_id).build_path
        model.write_text(raising_build)
        result = ext("finalize", record_id, "--records-dir", rd)
        assert result.exit_code != 0

    def test_timeout_bounds_the_finalize_child(self, rd, monkeypatch):
        from brickwright import cli
        from brickwright.tools import FinalizationReport

        seen: list[Config] = []

        def fake_finalize(record, config):
            seen.append(config)
            return FinalizationReport(ok=True)

        monkeypatch.setattr(cli, "finalize_record", fake_finalize)
        record_id = _init(rd)
        result = ext("finalize", record_id, "--records-dir", rd, "--timeout", "123")
        assert result.exit_code == 0
        # finalize builds, validates, and renders in one child bounded by this.
        assert seen[0].render_timeout == 123.0

    def test_finalize_records_the_timing_breakdown(self, rd):
        record_id = _init(rd)
        assert _meta(rd, record_id).timing is None
        assert ext("validate", record_id, "--records-dir", rd).exit_code == 0
        assert ext("finalize", record_id, "--records-dir", rd).exit_code == 0

        timing = _meta(rd, record_id).timing
        assert timing is not None
        assert timing.other == 0.0
        # Each external command is timed under its own name.
        assert set(timing.tools) == {"validate", "finalize"}
        tool_total = sum(timing.tools.values())
        assert timing.total >= tool_total >= 0.0
        # External runs attribute the unmeasured remainder to llm.
        assert timing.llm == pytest.approx(round(timing.total - tool_total, 3))

    def test_validate_then_finalize_record_per_command_time(
        self, rd, fake_render_pipeline, monkeypatch
    ):
        from brickwright import cli

        # Deterministic per-command durations: validate Δ=1.0s, finalize Δ=0.5s.
        # perf_counter is called start/end once per timed command.
        ticks = iter([0.0, 1.0, 10.0, 10.5])
        monkeypatch.setattr(cli.time, "perf_counter", lambda: next(ticks))

        record_id = _init(rd)
        assert ext("validate", record_id, "--records-dir", rd).exit_code == 0
        assert ext("finalize", record_id, "--records-dir", rd).exit_code == 0
        timing = _meta(rd, record_id).timing
        assert timing is not None
        assert timing.tools["validate"] == pytest.approx(1.0)
        assert timing.tools["finalize"] == pytest.approx(0.5)


@pytest.mark.usefixtures("in_process", "fake_render_pipeline")
class TestRender:
    def test_render_writes_a_png_and_prints_its_path(self, rd):
        record_id = _init(rd)
        record = _record(rd, record_id)
        result = ext("render", record_id, "--records-dir", rd)
        assert result.exit_code == 0
        png = record.render_path
        assert png.is_file()
        assert str(png) in result.stdout

    def test_render_failure_exits_nonzero(self, rd, monkeypatch):
        record_id = _init(rd)
        _record(rd, record_id).build_path.write_text("")  # empty build.py is invalid
        result = ext("render", record_id, "--records-dir", rd)
        assert result.exit_code != 0
        assert '"ok": false' in result.stdout


@pytest.mark.usefixtures("in_process", "fake_render_pipeline")
class TestRenderAngle:
    """`render-angle` renders the build from one camera angle -- the CLI seam the
    external critique's angle-finding subagent uses."""

    def test_writes_a_png_at_the_angle_and_prints_its_path(self, rd):
        record_id = _init(rd)
        record = _record(rd, record_id)
        result = ext(
            "render-angle",
            record_id,
            "--azimuth",
            "30",
            "--elevation",
            "15",
            "--records-dir",
            rd,
        )
        assert result.exit_code == 0
        # Default output is the canonical viewpoint path the critic reads.
        png = record.viewpoint_path
        assert png.is_file()
        assert str(png.absolute()) in result.stdout

    def test_honors_an_explicit_out_path(self, rd, tmp_path):
        record_id = _init(rd)
        out = tmp_path / "angle.png"
        result = ext("render-angle", record_id, "--out", str(out), "--records-dir", rd)
        assert result.exit_code == 0
        assert out.is_file()

    def test_failure_exits_nonzero(self, rd):
        record_id = _init(rd)
        _record(rd, record_id).build_path.write_text("")  # empty build.py is invalid
        result = ext("render-angle", record_id, "--records-dir", rd)
        assert result.exit_code != 0
        assert '"ok": false' in result.stdout

    def test_is_counted_in_tool_calls(self, rd):
        record_id = _init(rd)
        ext("render-angle", record_id, "--records-dir", rd)
        assert _meta(rd, record_id).tool_calls == {"render-angle": 1}

    def test_records_per_command_timing(self, rd):
        # Like the other external commands, render-angle is timed under its own name.
        record_id = _init(rd)
        assert ext("render-angle", record_id, "--records-dir", rd).exit_code == 0
        timing = _meta(rd, record_id).timing
        assert timing is not None
        assert "render-angle" in timing.tools

    def test_passes_azimuth_and_elevation_and_out_through(
        self, rd, tmp_path, monkeypatch
    ):
        # The CLI options must actually reach the renderer -- otherwise the angle the
        # viewpoint subagent asks for would be silently ignored.
        from brickwright import cli
        from brickwright.tools import RenderReport

        seen = {}

        def fake(record, azimuth, elevation, config, *, out_path=None):
            seen.update(azimuth=azimuth, elevation=elevation, out_path=out_path)
            return RenderReport(ok=True, image_path=record.viewpoint_path)

        monkeypatch.setattr(cli, "render_angle_record", fake)
        record_id = _init(rd)
        out = tmp_path / "angle.png"
        result = ext(
            "render-angle",
            record_id,
            "--azimuth",
            "42",
            "--elevation",
            "-7",
            "--out",
            str(out),
            "--records-dir",
            rd,
        )
        assert result.exit_code == 0
        assert seen == {"azimuth": 42.0, "elevation": -7.0, "out_path": out}


class TestCritiqueInstructions:
    """`critique-instructions` prints the record-specific critique playbook plus the two
    subagent system prompts (reused from the driver path)."""

    def _image_record(self, rd, tmp_path, png_bytes):
        img = tmp_path / "ref.png"
        img.write_bytes(png_bytes)
        result = ext("init", "a red apple", "--records-dir", rd, "--image", str(img))
        assert result.exit_code == 0
        return _init_fields(result.stdout)["record_id"]

    def test_prints_the_playbook_and_both_subagent_prompts(
        self, rd, tmp_path, png_bytes
    ):
        record_id = self._image_record(rd, tmp_path, png_bytes)
        result = ext("critique-instructions", record_id, "--records-dir", rd)
        assert result.exit_code == 0
        out = result.stdout
        # Both subagent system prompts are present, reused from the driver path.
        assert VIEWPOINT_TASK in out
        assert VIEWPOINT_COMPARE_PROMPT in out
        # Record-specific wiring for the agent to dispatch its subagents.
        assert record_id in out
        reference = _record(rd, record_id).prompt_image_path
        assert reference is not None
        assert str(reference.absolute()) in out
        assert "render-angle" in out
        assert "fresh subagent" in out

    def test_respects_the_critique_rounds_option(self, rd, tmp_path, png_bytes):
        record_id = self._image_record(rd, tmp_path, png_bytes)
        result = ext(
            "critique-instructions",
            record_id,
            "--critique-rounds",
            "4",
            "--records-dir",
            rd,
        )
        assert result.exit_code == 0
        assert "up to 4 time(s)" in result.stdout

    def test_defaults_to_two_rounds(self, rd, tmp_path, png_bytes):
        record_id = self._image_record(rd, tmp_path, png_bytes)
        result = ext("critique-instructions", record_id, "--records-dir", rd)
        assert result.exit_code == 0
        assert "up to 2 time(s)" in result.stdout

    def test_is_read_only_and_not_counted_as_a_tool_call(self, rd, tmp_path, png_bytes):
        # Printing the playbook must not mutate the record (no snapshot, no tally),
        # just like `instructions` and `init`.
        record_id = self._image_record(rd, tmp_path, png_bytes)
        before = _meta(rd, record_id).tool_calls
        assert (
            ext("critique-instructions", record_id, "--records-dir", rd).exit_code == 0
        )
        assert _meta(rd, record_id).tool_calls == before

    def test_requires_a_prompt_image(self, rd):
        record_id = _init(rd)  # text-only record
        result = ext("critique-instructions", record_id, "--records-dir", rd)
        assert result.exit_code != 0
        message = result.stdout + result.stderr + str(result.exception or "")
        assert "prompt image" in message
