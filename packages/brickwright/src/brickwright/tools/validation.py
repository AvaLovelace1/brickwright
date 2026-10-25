"""Run a record's build.py in a child process and validate the build."""

from __future__ import annotations

import io
import traceback
from collections.abc import Iterable
from contextlib import redirect_stdout
from hashlib import sha256
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from ..config import Config
from ..record import Record, Status
from . import build_execution
from .testing import CheckResult, TestContext

if TYPE_CHECKING:
    from bricklayer import LegoBuild


class BuildDimensions(BaseModel):
    """A build's bounding-box size: width/depth in studs, height in bricks."""

    model_config = ConfigDict(frozen=True)

    width: float  # extent along X (studs)
    depth: float  # extent along Y (studs)
    height: float  # extent along Z (bricks; a plate is 1/3)

    @classmethod
    def of(cls, build: LegoBuild) -> BuildDimensions:
        return cls(
            width=float(build.width),
            depth=float(build.depth),
            height=float(build.height),
        )


class ValidationReport(BaseModel):
    """The full result of validating a record's build.py."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    source_sha256: str | None = None
    build_error: str | None = None
    error_type: str | None = None  # exception type that caused a build error
    checks: list[CheckResult] = Field(default_factory=list)
    dimensions: BuildDimensions | None = None  # bounding-box size of the build
    brick_count: int | None = None  # total number of parts in the build
    stdout: str = ""  # everything printed to stdout while creating the build

    @property
    def failed_checks(self) -> list[str]:
        """The names of the checks that failed, in run order."""
        return [c.name for c in self.checks if not c.passed]

    @classmethod
    def from_checks(
        cls,
        checks: Iterable[CheckResult],
        stdout: str = "",
        *,
        build: LegoBuild | None = None,
    ) -> ValidationReport:
        """A report for a build that was created; ``ok`` is true iff every check passed."""
        checks = list(checks)
        return cls(
            ok=all(c.passed for c in checks),
            checks=checks,
            stdout=stdout,
            dimensions=BuildDimensions.of(build) if build is not None else None,
            brick_count=build.brick_count if build is not None else None,
        )

    @classmethod
    def error(
        cls, message: str, *, stdout: str = "", error_type: str | None = None
    ) -> ValidationReport:
        """A report for a build that raised or timed out before its checks ran."""
        return cls(ok=False, build_error=message, error_type=error_type, stdout=stdout)


def validate(record: Record, config: Config | None = None) -> ValidationReport:
    """Build and validate a record; persist the report and return it.

    Writes ``out/report.json``, sets the record's status to ``valid`` /
    ``invalid`` / ``error``, and snapshots the validated source and its report
    under ``snapshots/`` so the build's history across iterations is kept.
    """
    config = config or Config()
    source = record.read_build()
    report = build_execution.run_guarded(
        _validate,
        (str(record.build_path), source),
        config.build_timeout,
        lambda e: ValidationReport.error(
            f"Validation failed: {e}", error_type=type(e).__name__
        ),
    )
    return save_validation(record, source, report)


def save_validation(
    record: Record, source: str, report: ValidationReport
) -> ValidationReport:
    """Persist a report and snapshot bound to the exact source that was checked."""
    digest = sha256(source.encode()).hexdigest()
    if record.source_sha256 != digest:
        report = ValidationReport.error(
            "build.py changed during validation/export; validate the current source again",
            error_type="SourceChanged",
        )
    report = report.model_copy(update={"source_sha256": digest})

    serialized = report.model_dump_json(indent=2) + "\n"
    record.out_dir.mkdir(parents=True, exist_ok=True)
    record.report_path.write_text(serialized)
    record.add_snapshot(source, serialized)
    if report.ok:
        status = Status.VALID
    elif report.build_error:
        status = Status.ERROR
    else:
        status = Status.INVALID
    record.update_meta(status=status, validated_source_sha256=digest)
    return report


def _validate(build_path: str, source: str | None = None) -> ValidationReport:
    """Create the build, run its tests, and return the verification report."""
    return build_and_validate(build_path, source)[1]


def build_and_validate(
    build_path: str, source: str | None = None
) -> tuple[LegoBuild | None, ValidationReport]:
    """Create the build once, run custom tests, and enforce collision and support checks.

    No-argument create_build calls in tests reuse the build being exported.
    Connectivity remains a custom check so multipart builds can choose its policy.
    """
    buf = io.StringIO()

    try:
        with redirect_stdout(buf):
            module = build_execution.load_build_module(build_path, source)
            create = module.create_build
            build = create()
            module.create_build = lambda *args, **kwargs: (
                create(*args, **kwargs) if args or kwargs else build
            )
            custom = list(module.run_tests())
            physical = TestContext(build)
            physical.check_no_floating()
            physical.check_no_collisions()
            checks = physical.report()
            required = {check.name for check in checks}
            checks.extend(check for check in custom if check.name not in required)
        return build, ValidationReport.from_checks(
            checks, stdout=_stdout(buf), build=build
        )
    except Exception as exc:
        return None, ValidationReport.error(
            traceback.format_exc(), stdout=_stdout(buf), error_type=type(exc).__name__
        )


def _stdout(buf: io.StringIO) -> str:
    return build_execution.cap_output(buf.getvalue())
