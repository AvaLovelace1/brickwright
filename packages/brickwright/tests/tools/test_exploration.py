"""Tests for the explore inspection-snippet tool."""

import pytest

from brickwright.tools.build_execution import MAX_OUTPUT
from brickwright.tools.exploration import explore


class TestExploreBuild:
    def test_prints_a_build_measurement(self, make_record, in_process, valid_build):
        rec = make_record(valid_build)
        result = explore(rec, "print(build.brick_count, build.width, build.depth)")
        assert result.ok is True
        assert result.output.strip() == "1 4.0 2.0"

    def test_build_is_visible_inside_snippet_functions(
        self, make_record, in_process, valid_build
    ):
        rec = make_record(valid_build)
        result = explore(
            rec, "def count():\n    return build.brick_count\nprint(count())"
        )
        assert result.ok is True
        assert result.output.strip() == "1"

    def test_does_not_modify_build_py(self, make_record, in_process, valid_build):
        rec = make_record(valid_build)
        before = rec.read_build()
        explore(rec, "print(build.brick_count)")
        assert rec.read_build() == before


class TestExploreCatalog:
    def test_bricklayer_is_in_scope(self, make_record, in_process, valid_build):
        rec = make_record(valid_build)
        result = explore(rec, "print(bricklayer.PartSpec('3001').name)")
        assert result.ok is True
        assert "Brick  2 x  4" in result.output

    def test_a_broken_build_does_not_block_a_catalog_lookup(
        self, make_record, in_process, raising_build
    ):
        # The build is created only when the snippet reads `build`.
        rec = make_record(raising_build)
        result = explore(rec, "print(bricklayer.PartSpec('3001').name)")
        assert result.ok is True
        assert "Brick  2 x  4" in result.output

    def test_an_attribute_named_build_does_not_create_the_build(
        self, make_record, in_process, raising_build
    ):
        rec = make_record(raising_build)
        result = explore(
            rec, "import types\nprint(types.SimpleNamespace(build=1).build)"
        )
        assert result.ok is True
        assert result.output.strip() == "1"


class TestExploreErrors:
    def test_build_error_is_surfaced_when_the_snippet_reads_build(
        self, make_record, in_process, raising_build
    ):
        rec = make_record(raising_build)
        result = explore(rec, "print(build.brick_count)\nprint('never reached')")
        assert result.ok is False
        assert "build error" in result.output
        assert "RuntimeError" in result.output and "boom" in result.output
        assert "never reached" not in result.output

    def test_syntax_error_is_reported_as_a_snippet_error(
        self, make_record, in_process, valid_build
    ):
        rec = make_record(valid_build)
        result = explore(rec, "print(")
        assert result.ok is False
        assert "explore error" in result.output
        assert "SyntaxError" in result.output

    def test_snippet_error_keeps_partial_output(
        self, make_record, in_process, valid_build
    ):
        rec = make_record(valid_build)
        result = explore(rec, "print('before')\nraise ValueError('snap')")
        assert result.ok is False
        assert "before" in result.output  # printed before the error
        assert "explore error" in result.output
        assert "ValueError" in result.output and "snap" in result.output

    def test_partial_output_without_a_newline_is_split_from_the_error(
        self, make_record, in_process, valid_build
    ):
        # write() leaves no trailing newline, so the captured text gets one added
        # before the error banner -- otherwise they would run together on one line.
        rec = make_record(valid_build)
        result = explore(
            rec, "import sys\nsys.stdout.write('partial')\nraise ValueError('x')"
        )
        assert result.ok is False
        assert "partial\nexplore error" in result.output


class TestExploreOutput:
    def test_empty_output_is_noted(self, make_record, in_process, valid_build):
        rec = make_record(valid_build)
        result = explore(rec, "x = build.brick_count")  # nothing printed
        assert result.ok is True
        assert result.output == "(explore produced no output)"

    def test_large_output_is_capped(self, make_record, in_process, valid_build):
        rec = make_record(valid_build)
        result = explore(rec, "print('a' * 50000)")
        assert result.ok is True
        assert "[truncated]" in result.output
        assert len(result.output) <= MAX_OUTPUT + 20

    def test_large_output_before_an_error_is_capped(
        self, make_record, in_process, valid_build
    ):
        rec = make_record(valid_build)
        result = explore(rec, "print('a' * 50000); 1 / 0")
        assert result.ok is False
        assert "[truncated]" in result.output
        assert "ZeroDivisionError" in result.output
        assert len(result.output) < MAX_OUTPUT + 2000


class TestExploreSubprocess:
    @pytest.mark.parametrize(
        "exc", [TimeoutError("timed out"), RuntimeError("exited with code 1")]
    )
    def test_wraps_a_subprocess_failure(self, record, subprocess_raises, exc):
        subprocess_raises(exc)
        result = explore(record, "print('x')")
        assert result.ok is False
        assert "Explore failed" in result.output
        assert str(exc) in result.output

    @pytest.mark.integration
    def test_large_failing_output_is_not_mistaken_for_a_timeout(self, record):
        result = explore(record, "print('a' * 200_000); 1 / 0")
        assert result.ok is False
        assert "ZeroDivisionError" in result.output

    @pytest.mark.integration
    def test_imports_bricklayer_in_a_real_subprocess(self, record):
        # The spawned child must import bricklayer for the pre-bound name to work.
        result = explore(record, "print(bricklayer.PartSpec('3001').name)")
        assert result.ok is True
        assert "Brick  2 x  4" in result.output
