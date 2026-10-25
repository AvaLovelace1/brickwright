"""Agent tool registry, schema exposure, and dispatch to tool operations.

The schemas are the litellm/OpenAI function-calling format. :func:`execute_tool`
runs a single tool call against a record and returns a :class:`ToolOutcome`. Tool
*failures* (a bad edit, an unknown tool) are returned as content for the model to
read and recover from -- they do not raise.
"""

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import ValidationError

from ..config import Config
from ..record import Record, Usage, UsageTracker
from .editing import (
    EditError,
    ViewError,
    edit_build,
    insert_build,
    multi_edit_build,
    view,
)
from .exploration import explore
from .finalization import finalize
from .rendering import (
    render,
    render_angle,
    render_available,
)
from .schemas import (
    DispatchArgs,
    EditBuildArgs,
    ExploreArgs,
    FinalizeArgs,
    InsertBuildArgs,
    MultiEditBuildArgs,
    ReadBuildArgs,
    RenderArgs,
    ToolArgs,
    ValidateArgs,
    WriteBuildArgs,
    function_tool,
)
from .subagents import SubagentResult, dispatch_subagents
from .validation import ValidationReport, validate


def available_tools(config: Config | None = None) -> list[dict[str, Any]]:
    """The tools offered to the agent, gated by environment and ``config``."""
    excluded = set()
    if not render_available():
        excluded.add("render")
    if config is not None and config.is_subagent:
        excluded.add("finalize")
    if config is None or not config.can_dispatch_subagents:
        excluded.add("dispatch_subagents")
    return [tool for tool in _ALL_TOOLS if tool["function"]["name"] not in excluded]


@dataclass
class ToolOutcome:
    """The result of one tool call, fed back to the model as the tool message."""

    content: str
    ok: bool = True
    done: bool = False
    report: ValidationReport | None = None
    image: Path | None = None  # an image to show the model next, e.g. a fresh render
    usage: Usage | None = None  # token usage to fold into the run (e.g. from subagents)


def execute_tool(
    record: Record, config: Config, name: str, arguments: dict[str, Any]
) -> ToolOutcome:
    """Run a single tool call against ``record`` and return its outcome."""
    if not isinstance(arguments, dict):
        return ToolOutcome(f"{name} failed: arguments must be a JSON object", ok=False)
    tool = _TOOLS.get(name)
    if tool is None:
        return ToolOutcome(f"unknown tool {name!r}", ok=False)
    try:
        parsed = tool.arguments.model_validate(arguments)
    except ValidationError as exc:
        return ToolOutcome(f"{name} failed: invalid arguments\n{exc}", ok=False)
    return tool.handler(record, config, parsed)


def validation_outcome(report: ValidationReport) -> ToolOutcome:
    """The reply for a ``validate`` call that produced ``report``."""
    return ToolOutcome(report.model_dump_json(), ok=report.ok, report=report)


def subagent_outcome(results: list[SubagentResult]) -> ToolOutcome:
    """The reply for a ``dispatch_subagents`` call that produced ``results``."""
    return ToolOutcome(
        format_subagent_results(results),
        ok=all(r.ok for r in results),
        usage=_sum_usages(r.usage for r in results),
    )


def format_subagent_results(results: list[SubagentResult]) -> str:
    """Serialize subagent results into the JSON the model reads."""
    return json.dumps(
        {
            "results": [
                {
                    "task": i,
                    "ok": r.ok,
                    "valid": r.valid,
                    "failed_checks": r.failed_checks,
                    "finalized": r.finalized,
                    "result": r.text,
                    "reason": r.reason,
                    "record_id": r.record_id,
                }
                for i, r in enumerate(results)
            ]
        }
    )


_Args = TypeVar("_Args", bound=ToolArgs)


@dataclass(frozen=True)
class _Tool(Generic[_Args]):
    arguments: type[_Args]
    handler: Callable[[Record, Config, _Args], ToolOutcome]


def _read_build(record: Record, config: Config, args: ReadBuildArgs) -> ToolOutcome:
    try:
        return ToolOutcome(view(record.read_build(), args.view_range))
    except ViewError as exc:
        return ToolOutcome(f"read failed: {exc}", ok=False)


def _write_build(record: Record, config: Config, args: WriteBuildArgs) -> ToolOutcome:
    record.write_build(args.content)
    return ToolOutcome("ok: build.py written")


def _insert_build(record: Record, config: Config, args: InsertBuildArgs) -> ToolOutcome:
    try:
        snippet = insert_build(record, args.insert_line, args.insert_text)
    except EditError as exc:
        return ToolOutcome(f"insert failed: {exc}", ok=False)
    return _edited(snippet)


def _edit_build(record: Record, config: Config, args: EditBuildArgs) -> ToolOutcome:
    try:
        snippet = edit_build(record, args.old_str, args.new_str, args.replace_all)
    except EditError as exc:
        return ToolOutcome(f"edit failed: {exc}", ok=False)
    return _edited(snippet)


def _multi_edit_build(
    record: Record, config: Config, args: MultiEditBuildArgs
) -> ToolOutcome:
    try:
        applied = multi_edit_build(record, list(args.edits))
    except EditError as exc:
        return ToolOutcome(f"multi-edit failed (build.py unchanged): {exc}", ok=False)
    return ToolOutcome(f"ok: applied {applied} edits to build.py")


def _validate(record: Record, config: Config, args: ValidateArgs) -> ToolOutcome:
    return validation_outcome(validate(record, config))


def _explore(record: Record, config: Config, args: ExploreArgs) -> ToolOutcome:
    result = explore(record, args.code, config)
    return ToolOutcome(result.output, ok=result.ok)


def _render(record: Record, config: Config, args: RenderArgs) -> ToolOutcome:
    """Render the contact sheet, or a single view when a camera angle is given."""
    if args.azimuth is None:
        report = render(record, config)
        rendered = "a multi-view contact sheet"
    else:
        azimuth, elevation = args.azimuth, args.elevation
        assert elevation is not None  # RenderArgs validates the pair.
        report = render_angle(
            record, azimuth, elevation, config, out_path=record.angle_render_path
        )
        rendered = f"a single view at azimuth {azimuth:g}, elevation {elevation:g}"
    if report.ok:
        return ToolOutcome(
            f"ok: rendered the build to {rendered}; the image follows.",
            image=report.image_path,
        )
    return ToolOutcome(f"render failed:\n{report.error}", ok=False)


def _finalize(record: Record, config: Config, args: FinalizeArgs) -> ToolOutcome:
    report = finalize(record, config)
    message = (
        "ok: build compiled to out/build.ldr"
        if report.ok
        else f"compile failed:\n{report.error}"
    )
    return ToolOutcome(message, ok=report.ok, done=report.ok, report=report.validation)


def _dispatch(record: Record, config: Config, args: DispatchArgs) -> ToolOutcome:
    return subagent_outcome(dispatch_subagents(record, args.tasks, config))


_TOOLS: dict[str, _Tool[Any]] = {
    "read_build": _Tool(ReadBuildArgs, _read_build),
    "write_build": _Tool(WriteBuildArgs, _write_build),
    "insert_build": _Tool(InsertBuildArgs, _insert_build),
    "edit_build": _Tool(EditBuildArgs, _edit_build),
    "multi_edit_build": _Tool(MultiEditBuildArgs, _multi_edit_build),
    "validate": _Tool(ValidateArgs, _validate),
    "explore": _Tool(ExploreArgs, _explore),
    "render": _Tool(RenderArgs, _render),
    "finalize": _Tool(FinalizeArgs, _finalize),
    "dispatch_subagents": _Tool(DispatchArgs, _dispatch),
}
_ALL_TOOLS = [function_tool(name, tool.arguments) for name, tool in _TOOLS.items()]


def _edited(snippet: str) -> ToolOutcome:
    """The reply for an edit that applied, showing the region it touched."""
    return ToolOutcome(f"ok: build.py edited. Edited region:\n{snippet}")


def _sum_usages(usages: Iterable[Usage]) -> Usage:
    tracker = UsageTracker()
    for u in usages:
        tracker.add(u)
    return tracker.usage()
