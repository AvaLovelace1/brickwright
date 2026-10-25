"""A catalog of the Narrator's lifecycle, tool, and summary output."""

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from rich.console import Console

from ..config import Config, Effort
from ..record import Timing, Usage
from ..tools.registry import ToolOutcome, subagent_outcome, validation_outcome
from ..tools.subagents import SubagentResult
from ..tools.testing import CheckResult
from ..tools.validation import BuildDimensions, ValidationReport
from .narration import Narrator
from .report import RunReport

_SAMPLE_SOURCE = """\
import bricklayer as bl


def create_build():
    build = bl.LegoBuild()
    base = build.add(bl.brick(4, 2, color=bl.Color.RED), name="base")
    build.stack(bl.brick(4, 2, color=bl.Color.RED), on=base)
    return build
"""

_TRACEBACK = """\
Traceback (most recent call last):
  File "<explore>", line 1, in <module>
ValueError: no part matches id '9999'
"""


def print_gallery(console: Console | None = None) -> None:
    """Print one example of every Narrator output to ``console``."""
    console = console or Console()
    narrator = Narrator(console)
    record = _sample_record()
    config = _sample_config()

    _section(console, "lifecycle")
    narrator.run_started(record, config)
    narrator.turn_started(1)
    narrator.model_message(
        "I'll lay a 4×2 footprint and stack two courses of red brick."
    )
    narrator.warn("the cost limit cannot be enforced for this provider")

    _section(console, "tool calls & results")
    for call in _tool_scenes():
        narrator.tool_called(call.name, call.arguments)
        for outcome in call.outcomes:
            narrator.tool_finished(call.name, outcome)
        print()

    _section(console, "run summary")
    for result in _summary_scenes():
        narrator.run_finished(record, result)
        print()


@dataclass(frozen=True)
class _Call:
    """One tool's call line plus the result variants worth showing."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    outcomes: list[ToolOutcome] = field(default_factory=list)


def _tool_scenes() -> list[_Call]:
    return [
        _Call(
            name="read_build",
            outcomes=[ToolOutcome(_SAMPLE_SOURCE)],
        ),
        _Call(
            name="write_build",
            arguments={"content": _SAMPLE_SOURCE},
            outcomes=[
                ToolOutcome("ok: build.py written"),
                ToolOutcome("write failed: missing argument 'content'", ok=False),
            ],
        ),
        _Call(
            name="insert_build",
            arguments={
                "insert_line": 6,
                "insert_text": "    build.stack(bl.tile(4, 2, color=bl.Color.WHITE), on=base)",
            },
            outcomes=[
                ToolOutcome(
                    "ok: build.py edited. Edited region:\n"
                    "7:     build.stack(bl.tile(4, 2, color=bl.Color.WHITE), on=base)"
                ),
                ToolOutcome(
                    "insert failed: invalid insert_line 99: must be in 0..12 "
                    "(0 inserts at the top of the file; N inserts after line N)",
                    ok=False,
                ),
            ],
        ),
        _Call(
            name="edit_build",
            arguments={
                "old_str": "bl.brick(4, 2, color=bl.Color.RED), name=",
                "new_str": "bl.brick(4, 2, color=bl.Color.BLUE), name=",
            },
            outcomes=[
                ToolOutcome("ok: build.py edited"),
                ToolOutcome("edit failed: old_str not found", ok=False),
            ],
        ),
        _Call(
            name="multi_edit_build",
            arguments={
                "edits": [
                    {"old_str": "Color.RED", "new_str": "Color.BLUE"},
                    {"old_str": "bl.brick(4, 2,", "new_str": "bl.brick(4, 4,"},
                ]
            },
            outcomes=[
                ToolOutcome("ok: applied 2 edits to build.py"),
                ToolOutcome(
                    "multi-edit failed (build.py unchanged): "
                    "edit 2 of 2: old_str not found",
                    ok=False,
                ),
            ],
        ),
        _Call(
            name="validate",
            outcomes=[
                validation_outcome(
                    ValidationReport(
                        ok=True,
                        dimensions=BuildDimensions(width=4, depth=2, height=2.0),
                        brick_count=8,
                        checks=[
                            CheckResult(name="connected", passed=True, detail=""),
                            CheckResult(name="no_collisions", passed=True, detail=""),
                        ],
                    )
                ),
                validation_outcome(
                    ValidationReport(
                        ok=False,
                        dimensions=BuildDimensions(width=4, depth=2, height=2.0),
                        brick_count=8,
                        checks=[
                            CheckResult(name="connected", passed=True, detail=""),
                            CheckResult(
                                name="no_collisions",
                                passed=False,
                                detail="2 bricks overlap at (2, 0)",
                            ),
                        ],
                    )
                ),
                validation_outcome(
                    ValidationReport.error(
                        "Traceback (most recent call last):\n"
                        "NameError: name 'Color' is not defined"
                    )
                ),
            ],
        ),
        _Call(
            name="explore",
            arguments={"code": "print(bricklayer.search_parts('brick', limit=5))"},
            outcomes=[
                ToolOutcome("Brick 2x2"),
                ToolOutcome("Brick 2x2 (3003)\nBrick 2x4 (3001)\nBrick 1x2 (3004)"),
                ToolOutcome(f"explore error:\n{_TRACEBACK}", ok=False),
            ],
        ),
        _Call(
            name="render",
            outcomes=[
                ToolOutcome(
                    "ok: rendered the build to a multi-view contact sheet; "
                    "the image follows.",
                    image=Path("out/render.png"),
                ),
                ToolOutcome(f"render failed:\n{_TRACEBACK}", ok=False),
            ],
        ),
        _Call(
            name="finalize",
            outcomes=[
                ToolOutcome("ok: build compiled to out/build.ldr", done=True),
                ToolOutcome(f"compile failed:\n{_TRACEBACK}", ok=False, done=True),
            ],
        ),
        _Call(
            name="dispatch_subagents",
            arguments={
                "tasks": [
                    {"prompt": "Design the archway using arch parts.", "tier": "smart"},
                    {"prompt": "Design the two flanking towers.", "tier": "balanced"},
                ]
            },
            outcomes=[
                subagent_outcome(
                    [
                        SubagentResult(ok=True, text="Use two 1x6 arch bricks (3455)."),
                        SubagentResult(ok=True, text="Stack 2x2 round bricks (3941)."),
                    ]
                ),
                subagent_outcome(
                    [
                        SubagentResult(ok=True, text="Use two 1x6 arch bricks (3455)."),
                        SubagentResult(
                            ok=False,
                            reason="subagent produced no final answer",
                        ),
                    ]
                ),
            ],
        ),
    ]


def _summary_scenes() -> list[RunReport]:
    usage = Usage(
        prompt_tokens=18_432,
        completion_tokens=2_561,
        total_tokens=20_993,
        cost_usd=0.2317,
    )
    timing = Timing(
        total=42.8, llm=31.2, tools={"validate": 8.1, "render": 2.9}, other=0.6
    )
    return [
        RunReport(
            done=True,
            source_sha256="example-source",
            report=ValidationReport(ok=True, source_sha256="example-source"),
            validations=3,
            turns=11,
            usage=usage,
            timing=timing,
        ),
        RunReport(
            done=True,
            report=ValidationReport(ok=False),
            validations=5,
            turns=14,
            usage=usage,
            timing=timing,
        ),
        RunReport(
            done=False,
            report=ValidationReport(ok=True),
            validations=2,
            turns=30,
            usage=usage,
            timing=timing,
        ),
    ]


def _section(console: Console, title: str) -> None:
    console.print()
    console.rule(f"[bold]{title}", style="blue")
    console.print()


def _sample_record() -> Any:
    """A stand-in record exposing just what the narration panels read."""
    meta = SimpleNamespace(prompt="Build a 4×2 red brick wall, two courses high.")
    return SimpleNamespace(
        id="rec_3f9a2b-red-brick-wall",
        path=Path("records/rec_3f9a2b-red-brick-wall"),
        read_meta=lambda: meta,
    )


def _sample_config() -> Config:
    return Config(
        model="anthropic/claude-opus-4-8",
        effort=Effort.HIGH,
        max_validations=10,
        max_turns=30,
        max_cost=5.0,
    )
