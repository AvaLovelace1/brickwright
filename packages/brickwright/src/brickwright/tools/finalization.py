"""Run a record's build.py in a child process, compile it to LDraw, and render it."""

from __future__ import annotations

import traceback

from pydantic import BaseModel, ConfigDict

from ..config import Config
from ..record import Record, StopReason
from . import build_execution, rendering
from .validation import ValidationReport, build_and_validate, save_validation


class FinalizationReport(BaseModel):
    """The result of finalizing a build."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    error: str | None = None  # the traceback/message when the build failed
    validation: ValidationReport | None = None


def finalize(record: Record, config: Config | None = None) -> FinalizationReport:
    """Validate and export one source snapshot and the one build it creates."""
    config = config or Config()
    source = record.read_build()
    record.clear_exports()
    report = build_execution.run_guarded(
        _finalize,
        (record, source),
        config.render_timeout,
        lambda e: FinalizationReport(ok=False, error=f"Finalization failed: {e}"),
    )
    if report.validation is not None:
        validation = save_validation(record, source, report.validation)
        report = report.model_copy(update={"validation": validation})
        if validation.error_type == "SourceChanged":
            report = report.model_copy(
                update={"ok": False, "error": validation.build_error}
            )
    if report.ok:
        record.update_meta(
            finalized=True,
            exported_source_sha256=record.source_sha256,
            stop_reason=StopReason.FINALIZED,
        )
    else:
        record.clear_exports()
    return report


def _finalize(record: Record, source: str) -> FinalizationReport:
    """Create the build, write the LDraw file, and (when able) render a PNG."""
    build, validation = build_and_validate(str(record.build_path), source)
    if not validation.ok:
        return FinalizationReport(
            ok=False,
            validation=validation,
            error=validation.build_error
            or f"Validation failed: {', '.join(validation.failed_checks)}",
        )
    assert build is not None
    try:
        if rendering.render_available():
            rendering.mesh2png(rendering.build_mesh(record, build), record.render_path)
        else:
            rendering.build_ldraw(record, build)
    except Exception:
        return FinalizationReport(
            ok=False, error=traceback.format_exc(), validation=validation
        )
    return FinalizationReport(ok=True, validation=validation)
