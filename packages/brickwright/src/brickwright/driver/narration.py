"""Console narration for the agent loop."""

import json
from contextlib import AbstractContextManager
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..config import Config, Effort
from ..record import Record
from ..tools import ValidationReport
from .critique import CritiqueResult
from .messages import DEFAULT_PROMPT
from .report import RunReport


class Narrator:
    """Renders the loop's progress as styled panels and lines via ``rich``."""

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    def run_started(self, record: Record, config: Config) -> None:
        self._console.print(_header_panel(record, config))

    def turn_started(self, n: int) -> None:
        self._console.rule(f"[dim]turn {n}", style="dim", align="left")

    def thinking(self) -> AbstractContextManager[Any]:
        return self._console.status("[cyan]Thinking…", spinner="dots")

    def model_message(self, text: str) -> None:
        self._console.print(Text(text.strip(), style="italic grey70"))

    def warn(self, message: str) -> None:
        self._console.print(Text(f"⚠ {message}", style="yellow"))

    def tool_called(self, name: str, arguments: dict[str, Any]) -> None:
        self._console.print(_call_line(name, arguments))

    def tool_finished(self, name: str, outcome: Any) -> None:
        if outcome.report is not None:
            self._console.print(_report_lines(outcome.report))
            if not outcome.ok and outcome.report.ok:
                self._console.print(_outcome_line(name, outcome))
        else:
            self._console.print(_outcome_line(name, outcome))

    def critique_started(self, round_num: int, total: int) -> None:
        self._console.rule(
            f"[dim]critique {round_num}/{total}", style="dim", align="left"
        )

    def critique_result(self, result: CritiqueResult) -> None:
        self._console.print(_critique_lines(result))

    def critique_skipped(self, reason: str) -> None:
        self._console.print(Text(f"  critique skipped — {reason}", style="dim"))

    def run_finished(self, record: Record, result: RunReport) -> None:
        self._console.print(_summary_panel(record, result))


# --- Rendering helpers ---------------------------------------------------------
#
# Pure: each turns loop state into a rich renderable. The narrator decides when
# to print; these decide how it looks.

# Per-tool display label and accent color, keyed by tool name.
_TOOL_LOOK: dict[str, tuple[str, str]] = {
    "read_build": ("read", "blue"),
    "write_build": ("write", "magenta"),
    "edit_build": ("edit", "magenta"),
    "insert_build": ("insert", "magenta"),
    "multi_edit_build": ("multi-edit", "magenta"),
    "validate": ("validate", "yellow"),
    "explore": ("explore", "cyan"),
    "render": ("render", "cyan"),
    "finalize": ("finalize", "green"),
    "dispatch_subagents": ("dispatch", "black"),
}

# How wide a one-line code/snippet gloss may get before it is clipped.
_SNIPPET_WIDTH = 56


def _header_panel(record: Record, config: Config) -> Panel:
    """The opening banner: the prompt plus the run's model/effort/limits."""
    prompt = (record.read_meta().prompt or DEFAULT_PROMPT).strip()
    model = config.model or "(provider default)"
    effort = (config.effort or Effort.NONE).value
    body = Text()
    body.append(prompt, style="bold")
    body.append("\n\n")
    body.append(
        " · ".join(
            [
                f"model {model}",
                f"effort {effort}",
                f"max {config.max_validations} validations"
                if config.max_validations
                else "unlimited validations",
                f"max {config.max_turns} turns"
                if config.max_turns
                else "unlimited turns",
                f"max cost ${config.max_cost:.2f}",
            ]
        ),
        style="dim",
    )
    return Panel(
        body,
        title="🧱 BrickWright",
        title_align="left",
        subtitle=record.id,
        subtitle_align="right",
        border_style="cyan",
        padding=(1, 2),
    )


def _call_line(name: str, arguments: dict[str, Any]) -> Text:
    """A one-line ``→ tool  summary`` header for a tool call."""
    label, color = _TOOL_LOOK.get(name, (name, "white"))
    line = Text("→ ", style="dim")
    line.append(label, style=f"bold {color}")
    summary = _call_summary(name, arguments)
    if summary:
        line.append(f"  {summary}", style="dim")
    return line


def _call_summary(name: str, arguments: dict[str, Any]) -> str:
    """A short, human-readable gloss of a tool call's arguments."""
    if name == "write_build":
        return f"{len(str(arguments.get('content', '')).splitlines())} lines"
    if name == "insert_build":
        return _shorten(str(arguments.get("insert_text", "")))
    if name == "edit_build":
        return _shorten(str(arguments.get("new_str", "")))
    if name == "multi_edit_build":
        edits = arguments.get("edits")
        return f"{len(edits) if isinstance(edits, list) else 0} edits"
    if name == "explore":
        return _shorten(str(arguments.get("code", "")))
    if name == "dispatch_subagents":
        tasks = arguments.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            return ""
        if len(tasks) == 1 and isinstance(tasks[0], dict):
            return _shorten(str(tasks[0].get("prompt", "")))
        return f"{len(tasks)} subagents"
    return ""


def _outcome_line(name: str, outcome: Any) -> Text:
    """A ``✓``/``✗`` result line for a non-validate tool call."""
    mark, style = ("✓", "green") if outcome.ok else ("✗", "red")
    line = Text(f"  {mark}", style=style)
    summary = _outcome_summary(name, outcome)
    if summary:
        line.append(f" {summary}", style="dim" if outcome.ok else "red")
    return line


# Tools whose failure is best glossed by its first line (the error), not its last.
_FIRST_LINE_ERROR_TOOLS = {
    "read_build",
    "insert_build",
    "edit_build",
    "multi_edit_build",
}


def _outcome_summary(name: str, outcome: Any) -> str:
    """A short display gloss for a non-validate tool result."""
    content = outcome.content
    if name == "read_build" and outcome.ok:
        return f"{len(content.splitlines())} lines"
    if name == "explore":
        if not outcome.ok:
            return _last_line(content)
        lines = content.splitlines()
        if len(lines) == 1 and len(lines[0]) <= _SNIPPET_WIDTH:
            return lines[0]
        return f"{len(lines)} lines of output"
    if name == "dispatch_subagents":
        return _subagent_summary(content)
    if not outcome.ok:
        if name in _FIRST_LINE_ERROR_TOOLS:
            return content.split("\n", 1)[0]
        return _last_line(content)
    stripped = content.removeprefix("ok: ")
    return stripped.split("\n", 1)[0]


def _subagent_summary(content: str) -> str:
    """A count of returned subagents, or the ratio and reason when some failed."""
    try:
        results = json.loads(content).get("results", [])
    except (ValueError, AttributeError):
        return _last_line(content)  # a plain error string, not the results JSON
    total = len(results)
    failed = [r for r in results if not r.get("ok")]
    if not failed:
        return f"{total} subagents returned"
    reason = _clip((failed[0].get("reason") or "").strip())
    tail = f" — {reason}" if reason else ""
    return f"{len(failed)}/{total} subagents failed{tail}"


def _report_lines(report: ValidationReport) -> Group:
    """A validation report rendered as a group of lines: status, size, checks."""
    if report.build_error:
        last = report.build_error.strip().splitlines()[-1]
        return Group(
            Text("  ✗ build failed", style="red"),
            Text(f"    {last}", style="dim red"),
        )

    lines: list[Text] = []
    stats = []
    if report.dimensions is not None:
        d = report.dimensions
        stats.append(f"{_fmt(d.width)}×{_fmt(d.depth)}×{_fmt(d.height)}")
    if report.brick_count is not None:
        stats.append(f"{report.brick_count} parts")
    if stats:
        lines.append(Text("  " + " · ".join(stats), style="dim"))

    for check in report.checks:
        mark, style = ("✓", "green") if check.passed else ("✗", "red")
        line = Text(f"  {mark} {check.name}", style=style)
        if not check.passed and check.detail:
            line.append(f" — {check.detail}", style="dim red")
        lines.append(line)
    return Group(*lines)


def _critique_lines(result: CritiqueResult) -> Group:
    """A critique rendered as its verdict line followed by the differences text."""
    if result.done:
        verdict = Text("  ✓ matches the target", style="green")
    else:
        verdict = Text("  ↻ revising — differences found", style="yellow")
    return Group(verdict, Text(result.differences_description.strip(), style="grey70"))


def _summary_panel(record: Record, result: RunReport) -> Panel:
    """The closing summary."""
    grid = Table.grid(padding=(0, 3))
    grid.add_column(style="bold", justify="right")
    grid.add_column()

    if result.succeeded:
        outcome = Text("✓ finished — build valid", style="bold green")
    elif result.done:
        outcome = Text("finished — build invalid", style="bold yellow")
    else:
        outcome = Text("⚠ stalled before finalizing", style="bold yellow")
    usage = result.usage
    grid.add_row("outcome", outcome)
    if result.stop_reason is not None:
        grid.add_row("stop reason", result.stop_reason.value)
    if result.over_budget:
        grid.add_row("budget", Text("exceeded", style="bold yellow"))
    grid.add_row("validations", str(result.validations))
    grid.add_row("turns", str(result.turns))
    if result.critique_rounds:
        verdict = "matches" if result.critique_done else "differences remain"
        grid.add_row("critique", f"{result.critique_rounds} rounds — {verdict}")
    grid.add_row(
        "tokens",
        f"{usage.total_tokens:,} "
        f"[dim]({usage.prompt_tokens:,} in / {usage.completion_tokens:,} out)[/dim]",
    )
    if usage.cost_usd is not None:
        grid.add_row("cost", f"${usage.cost_usd:.4f}")
    t = result.timing
    timing_detail = " · ".join(
        f"{label} {value:.1f}"
        for label, value in (
            ("llm", t.llm),
            ("tools", sum(t.tools.values())),
            ("other", t.other),
        )
    )
    grid.add_row("elapsed", f"{t.total:.1f}s [dim]({timing_detail})[/dim]")
    grid.add_row("output dir", Text(str(record.path)))

    return Panel(
        grid,
        title="summary",
        title_align="left",
        border_style="green" if result.done else "yellow",
        padding=(1, 2),
    )


def _shorten(text: str) -> str:
    """Clip the first line of ``text`` to the snippet width with an ellipsis."""
    return _clip(next((line.strip() for line in text.strip().splitlines()), ""))


def _clip(text: str) -> str:
    """Clip ``text`` to the snippet width with an ellipsis."""
    return text if len(text) <= _SNIPPET_WIDTH else text[: _SNIPPET_WIDTH - 1] + "…"


def _last_line(text: str) -> str:
    """The last non-blank line of ``text`` -- the useful tail of a traceback."""
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _fmt(value: float) -> str:
    return str(int(value)) if value == int(value) else f"{value:g}"
