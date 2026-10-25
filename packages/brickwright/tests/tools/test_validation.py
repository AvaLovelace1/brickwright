"""Tests for the validation tool."""

import pytest
from bricklayer import Color, LegoBuild, brick

from brickwright.record import Status
from brickwright.tools.build_execution import MAX_OUTPUT
from brickwright.tools.testing import CheckResult
from brickwright.tools.validation import (
    ValidationReport,
    validate,
)

# The stud layer's protrusion above a part's body, in bricks (a 4 LDU stud on
# top of the 24 LDU brick body).
STUD_H = 1 / 6

_BUILD_TEMPLATE = """\
from bricklayer import PLATE, Color, LegoBuild, Position, brick

from brickwright import TestContext

{}

def run_tests():
    ctx = TestContext(create_build())
    ctx.check_no_floating()
    ctx.check_no_collisions()
    return ctx.report()
"""

_INVALID_PART = _BUILD_TEMPLATE.format("""\
def create_build():
    m = LegoBuild()
    m.add(brick(1000, 1000, 1))  # no such brick
    return m
""")

_COLLIDING = _BUILD_TEMPLATE.format("""\
def create_build():
    m = LegoBuild()
    m.add(brick(2, 2, color=Color.RED), Position(0, 0, 0))
    m.add(brick(2, 2, color=Color.BLUE), Position(0, 0, 0))
    return m
""")

_COLLIDING_SUBPLATE = _BUILD_TEMPLATE.format("""\
def create_build():
    m = LegoBuild()
    m.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
    m.add(brick(1, 1, color=Color.BLUE), Position(0, 0, PLATE))  # one plate up
    return m
""")

_PASSING_CHECK = """\
from bricklayer import Color, LegoBuild, brick

from brickwright import TestContext


def create_build():
    m = LegoBuild()
    m.add(brick(2, 2, color=Color.RED))
    return m


def run_tests():
    model = create_build()
    ctx = TestContext(model)
    ctx.check_connected()
    ctx.check_no_collisions()
    n = model.brick_count
    ctx.check("has_parts", n >= 1)
    return ctx.report()
"""

_FAILING_CHECK = """\
from bricklayer import Color, LegoBuild, brick

from brickwright import TestContext


def create_build():
    m = LegoBuild()
    m.add(brick(2, 2, color=Color.RED))
    return m


def run_tests():
    model = create_build()
    ctx = TestContext(model)
    ctx.check_connected()
    ctx.check_no_collisions()
    n = model.brick_count
    ctx.check("over_100_bricks", n > 100, f"only {n} bricks")
    return ctx.report()
"""

_PRINTS = _BUILD_TEMPLATE.format("""\
def create_build():
    print("building the tower")
    m = LegoBuild()
    m.add(brick(2, 2, color=Color.RED))
    return m
""")

_PRINTS_A_LOT = _PRINTS.replace('print("building the tower")', 'print("x" * 200_000)')

_NO_CHECKS = """\
from bricklayer import Color, LegoBuild, brick


def create_build():
    m = LegoBuild()
    m.add(brick(2, 2, color=Color.RED))
    return m


def run_tests():
    return None
"""

_NOT_A_BUILD = _BUILD_TEMPLATE.replace(
    "ctx = TestContext(create_build())", "ctx = TestContext(LegoBuild())"
).format("""\
def create_build():
    return [LegoBuild()]
""")


def _check(report, name):
    return next(c for c in report.checks if c.name == name)


class TestValidationReport:
    def test_from_checks_computes_ok_as_all_passed(self):
        passing = [
            CheckResult(name="a", passed=True),
            CheckResult(name="b", passed=True),
        ]
        assert ValidationReport.from_checks(passing).ok is True
        mixed = passing + [CheckResult(name="c", passed=False)]
        assert ValidationReport.from_checks(mixed).ok is False

    def test_error_report_is_not_ok_and_carries_the_message(self):
        report = ValidationReport.error("boom")
        assert report.ok is False
        assert report.build_error == "boom"
        assert report.checks == []

    def test_from_checks_carries_the_checks_and_build_metrics(self):
        # When a model is supplied, the report records its checks verbatim plus
        # the model's bounding box and part count.
        m = LegoBuild()
        m.add(brick(2, 2, color=Color.RED))
        checks = [CheckResult(name="a", passed=True)]
        report = ValidationReport.from_checks(checks, build=m)
        assert report.checks == checks
        # Height includes the stud layer: 1 brick + the stud protrusion.
        assert report.dimensions is not None
        assert report.dimensions.width == 2
        assert report.dimensions.depth == 2
        assert report.dimensions.height == pytest.approx(1 + STUD_H)
        assert report.brick_count == 1

    def test_error_report_carries_the_error_type(self):
        report = ValidationReport.error("boom", error_type="RuntimeError")
        assert report.error_type == "RuntimeError"

    def test_error_type_is_none_for_a_passing_report(
        self, make_record, in_process, valid_build
    ):
        assert validate(make_record(valid_build)).error_type is None


class TestValidBuild:
    def test_digest_preserves_source_line_endings(self, record, in_process):
        record.build_path.write_bytes(
            record.build_path.read_bytes().replace(b"\n", b"\r\n")
        )
        report = validate(record)
        assert report.ok
        assert report.source_sha256 == record.source_sha256

    def test_report_is_bound_to_the_validated_source(self, record, in_process):
        import hashlib

        report = validate(record)
        digest = hashlib.sha256(record.build_path.read_bytes()).hexdigest()
        assert report.source_sha256 == digest
        assert record.read_meta().validated_source_sha256 == digest

    def test_edit_invalidates_validation(self, record, in_process, floating_build):
        validate(record)
        record.write_build(floating_build)
        assert record.read_meta().status is Status.CREATED
        assert record.read_meta().validated_source_sha256 is None

    def test_direct_file_edit_is_not_reported_as_current_validation(
        self, record, in_process, floating_build
    ):
        validate(record)
        record.build_path.write_text(floating_build)
        assert record.read_meta().status is Status.CREATED

    def test_reports_ok_and_writes_outputs(self, make_record, in_process, valid_build):
        rec = make_record(valid_build)
        report = validate(rec)
        assert report.ok is True
        assert all(c.passed for c in report.checks)
        assert report.build_error is None
        assert rec.report_path.is_file()
        assert rec.read_meta().status is Status.VALID

    def test_does_not_render_the_model(self, make_record, in_process, valid_build):
        rec = make_record(valid_build)
        validate(rec)
        assert not rec.ldr_path.is_file()


class TestInvalidBuild:
    @pytest.mark.parametrize(
        "tests",
        [
            "return []",
            'return [CheckResult(name="no_collisions", passed=True)]',
        ],
    )
    def test_mandatory_physics_does_not_trust_agent_checks(
        self,
        make_record,
        in_process,
        tests,
    ):
        source = _COLLIDING.split("def run_tests():")[0]
        source += "from brickwright.tools.testing import CheckResult\n"
        source += "def run_tests():\n    " + tests + "\n"
        report = validate(make_record(source))
        assert not report.ok
        assert not _check(report, "no_collisions").passed

    def test_floating_is_checked_even_with_empty_custom_tests(
        self,
        make_record,
        in_process,
        floating_build,
    ):
        source = floating_build.split("def run_tests():")[0]
        source += "def run_tests():\n    return []\n"
        report = validate(make_record(source))
        assert not report.ok
        assert not _check(report, "no_floating").passed

    def test_collisions_are_reported(self, make_record, in_process):
        report = validate(make_record(_COLLIDING))
        assert report.ok is False
        collision = _check(report, "no_collisions")
        assert collision.passed is False
        # The detail names the culprit parts, not raw volumes.
        assert "overlaps" in collision.detail
        assert "Cuboid(" not in collision.detail

    def test_collisions_report_positions_in_brick_units(self, make_record, in_process):
        # The two bricks collide because one is a single plate (1/3 brick) up.
        report = validate(make_record(_COLLIDING_SUBPLATE))
        detail = _check(report, "no_collisions").detail
        assert "Position(0.5, 0.5, 0.333)" in detail

    def test_floating_parts_are_reported(self, make_record, floating_build, in_process):
        rec = make_record(floating_build)
        report = validate(rec)
        assert report.ok is False
        floating = _check(report, "no_floating")
        assert floating.passed is False
        assert floating.detail
        assert rec.read_meta().status is Status.INVALID


class TestChecks:
    def test_multipart_models_can_choose_their_connectivity_policy(
        self,
        make_record,
        in_process,
    ):
        source = _COLLIDING.replace(
            "Color.BLUE), Position(0, 0, 0)", "Color.BLUE), Position(10, 0, 0)"
        ).split("def run_tests():")[0]
        source += """def run_tests():
    ctx = TestContext(create_build())
    ctx.check_connected(expected_components=2)
    return ctx.report()
"""
        report = validate(make_record(source))
        assert report.ok
        assert {c.name for c in report.checks} == {
            "no_floating",
            "no_collisions",
            "connected",
        }

    def test_rechecks_the_model_after_custom_tests_mutate_it(
        self,
        make_record,
        in_process,
    ):
        source = _PASSING_CHECK.split("def run_tests():")[0]
        source += """def run_tests():
    m = create_build()
    ctx = TestContext(m)
    ctx.check_no_collisions()
    m.add(brick(2, 2, color=Color.BLUE))
    return ctx.report()
"""
        report = validate(make_record(source))
        assert not report.ok
        assert not _check(report, "no_collisions").passed
        assert len([c for c in report.checks if c.name == "no_collisions"]) == 1

    def test_passing_check_is_recorded(self, make_record, in_process):
        report = validate(make_record(_PASSING_CHECK))
        assert _check(report, "has_parts").passed is True
        assert report.ok is True

    def test_failing_check_fails_the_run_with_a_detail(self, make_record, in_process):
        report = validate(make_record(_FAILING_CHECK))
        assert report.ok is False
        check = _check(report, "over_100_bricks")
        assert check.passed is False
        assert "only" in check.detail
        # The model itself is physically valid -- only the custom check fails.
        assert _check(report, "connected").passed is True
        assert _check(report, "no_collisions").passed is True


class TestBuildMetrics:
    def test_reports_build_dimensions(self, make_record, in_process, valid_build):
        report = validate(make_record(valid_build))
        assert report.dimensions is not None
        dims = (
            report.dimensions.width,
            report.dimensions.depth,
            report.dimensions.height,
        )
        # Height includes the stud layer
        assert dims == pytest.approx((4, 2, 1 + STUD_H))

    def test_reports_brick_count(self, make_record, in_process, valid_build):
        report = validate(make_record(valid_build))
        assert report.brick_count == 1

    def test_metrics_are_absent_when_the_build_fails(
        self, make_record, in_process, raising_build
    ):
        # A build that raises never produces a model, so it has no metrics.
        report = validate(make_record(raising_build))
        assert report.dimensions is None
        assert report.brick_count is None


class TestSnapshots:
    def test_validate_snapshots_the_build_and_its_report(
        self, make_record, in_process, valid_build
    ):
        rec = make_record(valid_build)
        report = validate(rec)

        snapshots = rec.snapshots
        assert len(snapshots) == 1
        snap = snapshots[0]
        # The snapshot captures the exact source that was validated...
        assert snap.read_build() == valid_build
        # ...alongside the report produced for it.
        saved = ValidationReport.model_validate_json(snap.read_report())
        assert saved == report

    def test_snapshots_accumulate_one_per_iteration(
        self, make_record, in_process, valid_build
    ):
        rec = make_record(valid_build)
        validate(rec)
        rec.write_build(_FAILING_CHECK)
        validate(rec)

        snapshots = rec.snapshots
        assert len(snapshots) == 2
        # Snapshots are numbered as a zero-padded 1-based sequence.
        assert [s.name for s in snapshots] == ["001", "002"]
        # Each snapshot preserves the model as it was at that iteration, so the
        # user can see how it changed: the first passed, the second does not.
        assert snapshots[0].read_build() == valid_build
        assert snapshots[1].read_build() == _FAILING_CHECK
        first = ValidationReport.model_validate_json(snapshots[0].read_report())
        second = ValidationReport.model_validate_json(snapshots[1].read_report())
        assert first.ok is True
        assert second.ok is False


class TestReportTransport:
    def test_model_stdout_is_captured_in_the_report(self, make_record, in_process):
        report = validate(make_record(_PRINTS))
        assert report.ok is True
        assert "building the tower" in report.stdout

    def test_model_stdout_is_capped(self, make_record, in_process):
        report = validate(make_record(_PRINTS_A_LOT))
        assert report.ok is True
        assert report.stdout.endswith("[truncated]")
        assert len(report.stdout) <= MAX_OUTPUT + 20

    @pytest.mark.integration
    def test_large_stdout_is_not_mistaken_for_a_timeout(self, make_record):
        report = validate(make_record(_PRINTS_A_LOT))
        assert report.ok is True

    @pytest.mark.integration
    def test_report_crosses_the_subprocess_boundary_intact(self, make_record):
        # The full ValidationReport object survives the real process boundary,
        # including fields beyond ok/checks such as the captured stdout.
        report = validate(make_record(_PRINTS))
        assert report.ok is True
        assert "building the tower" in report.stdout


class TestBuildErrors:
    def test_exception_in_build_is_captured(
        self, make_record, in_process, raising_build
    ):
        rec = make_record(raising_build)
        report = validate(rec)
        assert report.ok is False
        assert report.checks == []
        assert report.build_error is not None
        assert "RuntimeError" in report.build_error
        assert "boom" in report.build_error
        assert rec.read_meta().status is Status.ERROR

    @pytest.mark.parametrize(
        "source, error_type",
        [(_NO_CHECKS, "TypeError"), (_NOT_A_BUILD, "AttributeError")],
    )
    def test_a_malformed_result_is_reported_as_a_build_error(
        self, make_record, in_process, source, error_type
    ):
        report = validate(make_record(source))
        assert report.ok is False
        assert report.error_type == error_type
        assert report.build_error is not None
        assert "Traceback" in report.build_error

    @pytest.mark.parametrize(
        "exc", [TimeoutError("timed out"), RuntimeError("exited with code 42")]
    )
    def test_wraps_a_subprocess_failure(self, record, subprocess_raises, exc):
        # validate turns either subprocess failure -- a timeout or a child that
        # dies without a result -- into an error report and an ERROR status.
        subprocess_raises(exc)
        report = validate(record)
        assert report.ok is False
        assert report.build_error is not None
        assert "Validation failed" in report.build_error
        assert str(exc) in report.build_error
        assert record.read_meta().status is Status.ERROR
        assert record.report_path.is_file()  # the failure report is still persisted

    def test_build_exception_type_is_captured(
        self, make_record, in_process, raising_build
    ):
        # raising_build raises RuntimeError inside create_build().
        report = validate(make_record(raising_build))
        assert report.error_type == "RuntimeError"

    def test_invalid_part_error_is_captured(self, make_record, in_process):
        report = validate(make_record(_INVALID_PART))
        assert report.error_type == "InvalidPartError"
