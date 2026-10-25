"""The result of a full agent run."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..record import StopReason, Timing, Usage, ValidationFailures
from ..tools import ValidationReport
from .critique import CritiqueResult


class RunReport(BaseModel):
    """The outcome of an agent run."""

    model_config = ConfigDict(frozen=True)

    done: bool  # whether the final pass successfully finalized
    source_sha256: str | None = None
    stop_reason: StopReason | None = None
    over_budget: bool = False
    report: ValidationReport | None = None  # the last verification report, if any
    validations: int  # how many times the model was validated during the run
    validation_failures: ValidationFailures = Field(  # why validations failed
        default_factory=ValidationFailures
    )
    turns: int  # how many model turns the run took
    tool_calls: dict[str, int] = Field(  # how many times each tool was called
        default_factory=dict
    )
    timing: Timing = Field(default_factory=Timing)  # per-phase breakdown
    usage: Usage = Field(default_factory=Usage)  # token counts and cost
    subagent_usage: Usage = Field(default_factory=Usage)  # usage from subagents
    final_text: str | None = None  # the run's final plain-text reply, if any
    critique_rounds: int = 0  # how many outer visual-critique rounds ran
    last_critique: CritiqueResult | None = None  # the most recent critique, if any

    @property
    def critique_done(self) -> bool | None:
        """The critic's final verdict, or ``None`` if it never ran."""
        return self.last_critique.done if self.last_critique is not None else None

    @property
    def succeeded(self) -> bool:
        """Whether the final source was verified/exported without unknown spend."""
        return (
            self.done
            and self.stop_reason is not StopReason.UNKNOWN_COST
            and self.source_sha256 is not None
            and self.report is not None
            and self.report.ok
            and self.report.source_sha256 == self.source_sha256
        )
