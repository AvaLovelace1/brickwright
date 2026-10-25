"""Harness configuration: where records live and how the agent is driven."""

import os
from copy import deepcopy
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

# Where records live by default, and the env var that overrides it.
DEFAULT_RECORDS_DIR = "records"
RECORDS_DIR_ENV = "BRICKWRIGHT_RECORDS_DIR"


def default_records_dir() -> Path:
    return Path(os.environ.get(RECORDS_DIR_ENV, DEFAULT_RECORDS_DIR))


class Effort(str, Enum):
    """How much reasoning effort to request from the model."""

    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


# Subagent model tiers per provider; an absent provider uses the main model.
DEFAULT_SUBAGENT_TIERS: dict[str, dict[str, str]] = {
    "openai": {
        "smart": "openai/gpt-6-astra",
        "balanced": "openai/gpt-6-sol",
        "fast": "openai/gpt-6-luna",
    },
    "anthropic": {
        "smart": "anthropic/claude-opus-4-8",
        "balanced": "anthropic/claude-sonnet-5",
        "fast": "anthropic/claude-haiku-4-5",
    },
    "google": {
        "smart": "gemini/gemini-pro-latest",
        "balanced": "gemini/gemini-flash-latest",
        "fast": "gemini/gemini-flash-lite-latest",
    },
}


class CritiqueMode(str, Enum):
    """How the builder re-enters after a visual critique asks for changes."""

    CONTINUE = "continue"  # resume the builder's existing conversation
    FRESH = "fresh"  # re-seed a new conversation each round


class Config(BaseModel):
    """Main configuration class for BrickWright."""

    model_config = ConfigDict(frozen=True)

    records_dir: Path = Field(default_factory=default_records_dir)
    model: str | None = None
    effort: Effort | None = Effort.HIGH
    max_validations: int = Field(default=50, ge=0)  # 0 disables the validation cap
    max_turns: int = Field(default=200, ge=0)  # 0 disables the turn cap
    max_cost: float = 5.0  # cap on USD spent per run
    build_timeout: float = 30.0
    render_timeout: float = 60.0
    # Seconds allowed for one LLM request; ``None`` leaves it to the client.
    request_timeout: float | None = None
    subagents_enabled: bool = False
    is_subagent: bool = False  # internal: this run is a subagent
    subagent_tiers: dict[str, dict[str, str]] = Field(
        default_factory=lambda: deepcopy(DEFAULT_SUBAGENT_TIERS)
    )
    max_parallel_subagents: int = 4
    subagent_max_turns: int = 100
    subagent_max_cost: float = 1.0  # USD
    max_critique_rounds: int = 0  # outer visual-critique rounds (0 disables the loop)
    critique_mode: CritiqueMode = CritiqueMode.CONTINUE  # how the builder re-enters
    critique_model: str | None = None  # critic model id (None -> use ``model``)
    critique_effort: Effort | None = None  # critic effort (None -> use ``effort``)
    # Viewpoint-matching agent: picks a camera angle whose render matches the
    # reference image's viewpoint. 0 disables it, and with it the critique.
    max_viewpoint_iterations: int = 6  # max render/adjust turns the agent gets
    viewpoint_model: str | None = None  # viewpoint agent model (None -> use ``model``)
    viewpoint_effort: Effort | None = None  # viewpoint effort (None -> use ``effort``)

    @property
    def can_dispatch_subagents(self) -> bool:
        """Whether this run may hand subtasks to subagents."""
        return self.subagents_enabled and not self.is_subagent

    def agent_model_and_effort(self, prefix: str) -> tuple[str | None, Effort]:
        """The model and effort for a helper agent, falling back to the builder's.

        ``prefix`` names the agent's option pair, e.g. ``"critique"`` reads
        ``critique_model`` and ``critique_effort``.
        """
        model = getattr(self, f"{prefix}_model") or self.model
        effort = getattr(self, f"{prefix}_effort") or self.effort or Effort.NONE
        return model, effort
