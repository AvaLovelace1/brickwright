"""The agent loop: drive the model through edit/validate cycles, then critique."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..config import Config, CritiqueMode
from ..record import Record, StopReason
from ..tools import (
    ValidationReport,
    available_tools,
    execute_tool,
    render_available,
    render_views,
)
from .completion import litellm_complete
from .critique import CritiqueResult, critique
from .messages import (
    assistant_message,
    critique_followup_message,
    fresh_round_messages,
    image_user_message,
    request_kwargs,
    system_message,
    tool_call_arguments,
    tool_call_message,
    truncation_retry_message,
    user_message,
)
from .narration import Narrator
from .report import RunReport
from .tracking import RunTracker
from .transcript import Transcript


class AgentRuntime:
    """The prompt and tool surface used by a builder pass."""

    def system_message(self, config: Config) -> dict[str, Any]:
        return system_message(config)

    def available_tools(self, config: Config) -> list[dict[str, Any]]:
        return available_tools(config)

    def execute_tool(
        self, record: Record, config: Config, name: str, arguments: dict[str, Any]
    ):
        return execute_tool(record, config, name, arguments)


@dataclass
class _Run:
    """Mutable state threaded through one agent run (builder passes + critique)."""

    record: Record
    config: Config
    complete: Callable[..., Any]
    transcript: Transcript
    tracker: RunTracker
    narrator: Narrator
    runtime: AgentRuntime = field(default_factory=AgentRuntime)
    last_report: ValidationReport | None = None
    done: bool = False  # did the final builder pass finalize (last pass wins)
    warned_cost: bool = False
    final_text: str | None = None  # the run's last plain-text reply, if any
    truncations: int = 0  # turns lost to the output cap, across the whole run


def run_agent(
    record: Record,
    config: Config | None = None,
    *,
    narrator: Narrator | None = None,
    runtime: AgentRuntime | None = None,
) -> RunReport:
    """Drive the model through edit/validate cycles until it finishes or stalls.

    When ``config.max_critique_rounds`` is set and the record has a prompt image, an
    outer loop then has an independent model compare the render to that image and
    feeds back any differences for another pass. Progress is narrated to
    ``narrator``; pass ``Narrator(Console(quiet=True))`` to run silently.
    """
    config = config or Config()
    if runtime is not None and config.max_critique_rounds:
        raise ValueError("custom runtimes require critique rounds to be disabled")
    narrator = narrator or Narrator()

    narrator.run_started(record, config)
    if not render_available():
        narrator.warn(
            "render tool is disabled: no LDraw parts library found; "
            "to enable, download the library from https://www.ldraw.org "
            "and set $LDRAW_LIBRARY_PATH"
        )

    tracker = RunTracker()
    run = None
    stop_reason = StopReason.ERROR
    try:
        with Transcript(record.messages_path) as transcript:
            run = _Run(
                record=record,
                config=config,
                complete=litellm_complete(),
                transcript=transcript,
                tracker=tracker,
                narrator=narrator,
                runtime=runtime or AgentRuntime(),
            )
            transcript.append(run.runtime.system_message(config))
            transcript.append(user_message(record))

            _run_builder_pass(run)
            last_critique = _run_critique_loop(run)
            stop_reason = _stop_reason(run)
    finally:
        # Persist accumulated metadata, even if the run errored or was interrupted.
        record.update_meta(
            **tracker.meta(),
            stop_reason=stop_reason,
            over_budget=tracker.cost() > config.max_cost,
            finalized=bool(run and run.done and record.read_meta().finalized),
        )

    assert run is not None  # the report path is reached only on an uninterrupted run
    run_report = RunReport(
        **tracker.meta(),
        done=run.done,
        report=run.last_report,
        subagent_usage=tracker.subagent_usage(),
        final_text=run.final_text,
        last_critique=last_critique,
        source_sha256=record.source_sha256,
        stop_reason=stop_reason,
        over_budget=tracker.cost() > config.max_cost,
    )
    narrator.run_finished(record, run_report)
    return run_report


# How many turns a run may lose to the output cap before we stop nudging and let it
# end -- enough to recover from a one-off, few enough not to burn a budget looping.
_MAX_TRUNCATIONS = 3


def _run_builder_pass(run: _Run) -> None:
    """Drive the builder until it finalizes, stalls, or a budget is spent.

    One call is one pass over the current conversation; it mutates ``run``'s counters
    and appends to the shared transcript. Re-entered (with new feedback appended) once
    per critique round.
    """
    config = run.config
    tools = run.runtime.available_tools(config)
    # Each pass re-decides ``done``, so run.done ends up the final pass's verdict.
    run.done = False
    while _within_budget(run):
        run.tracker.turns += 1
        run.narrator.turn_started(run.tracker.turns)

        # --- Send & receive message ---
        with run.narrator.thinking(), run.tracker.time_llm():
            response = run.complete(
                messages=run.transcript.messages,
                tools=tools,
                tool_choice="auto",
                **request_kwargs(config),
                cache_control_injection_points=[
                    {"location": "message", "role": "system"}
                ],
            )
        run.tracker.record(response)
        _warn_unknown_cost(run)
        choice = response.choices[0]
        message = choice.message
        run.transcript.append(assistant_message(message))

        if message.content:
            run.narrator.model_message(message.content)

        # --- Run tool calls ---
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            if getattr(choice, "finish_reason", None) == "length":
                run.truncations += 1
                run.narrator.warn(
                    f"turn {run.tracker.turns} was cut off at the output-token limit "
                    "before it produced a tool call"
                    + ("" if run.truncations > _MAX_TRUNCATIONS else "; retrying")
                )
                if run.truncations <= _MAX_TRUNCATIONS:
                    run.transcript.append(truncation_retry_message())
                    continue
            run.final_text = message.content  # a plain text reply -- nothing more to do
            return

        _run_tool_calls(run, tool_calls)
        if run.done:
            return


def _run_tool_calls(run: _Run, tool_calls: list[Any]) -> None:
    """Answer the whole tool batch before appending its last rendered image."""
    image: dict[str, Any] | None = None
    for tc in tool_calls:
        if run.done:
            run.transcript.append(tool_call_message(tc, "skipped: already finalized"))
            continue

        name = tc.function.name
        if name == "dispatch_subagents" and run.tracker.has_unknown_cost():
            run.transcript.append(
                tool_call_message(tc, "skipped: cost is unknown; no further paid calls")
            )
            continue
        if name == "validate" and not run.tracker.validation_budget_left(
            run.config.max_validations
        ):
            run.transcript.append(
                tool_call_message(tc, "skipped: validation budget reached")
            )
            continue
        arguments = tool_call_arguments(tc)
        run.narrator.tool_called(name, arguments)
        source = run.record.source_sha256
        with run.tracker.time_tool(name):
            outcome = run.runtime.execute_tool(run.record, run.config, name, arguments)
        run.narrator.tool_finished(name, outcome)
        if run.record.source_sha256 != source:
            run.last_report = None
        if outcome.report is not None:
            run.last_report = outcome.report
        if name == "validate":
            run.tracker.validations += 1
            if outcome.report is not None:
                run.tracker.record_validation(outcome.report)
        run.transcript.append(tool_call_message(tc, outcome))
        if outcome.image is not None:
            image = image_user_message(outcome.image)
        if outcome.usage is not None:
            run.tracker.add_subagent_usage(outcome.usage)
            _warn_unknown_cost(run)
        if outcome.done:
            run.done = True

    # Hand the freshly rendered contact sheet back as a single image turn.
    if image is not None:
        run.transcript.append(image)


def _run_critique_loop(run: _Run) -> CritiqueResult | None:
    """Render -> critique -> revise, until the critic is satisfied or rounds run out.

    Counts completed rounds on ``run.tracker.critique_rounds`` and returns the last
    critique; a no-op returning ``None`` when the loop is disabled or the record has
    no image to compare against.
    """
    config = run.config
    if config.max_critique_rounds <= 0:
        return None
    if run.record.prompt_image_path is None:
        run.narrator.critique_skipped("no prompt image to compare against")
        return None

    last_result: CritiqueResult | None = None
    needs_final_render = False
    for round_num in range(1, config.max_critique_rounds + 1):
        if run.tracker.has_unknown_cost() or run.tracker.cost() >= config.max_cost:
            break
        run.narrator.critique_started(round_num, config.max_critique_rounds)

        needs_final_render = False
        if not _render_and_snapshot(run):
            run.narrator.critique_skipped("render failed; cannot compare to the target")
            break

        try:
            result = critique(
                run.record,
                config,
                on_response=lambda response: _record_critique_response(run, response),
            )
        except _UnknownCost:
            break
        if result is None:
            run.narrator.warn(
                "could not obtain a critique verdict; stopping the critique loop"
            )
            break

        run.tracker.critique_rounds += 1
        last_result = result
        run.record.critique_path.write_text(result.model_dump_json(indent=2) + "\n")
        run.record.update_meta(critique_rounds=run.tracker.critique_rounds)
        run.narrator.critique_result(result)
        if result.done or not _within_budget(run):
            break

        _reenter_builder(run, result)
        needs_final_render = True

    # Make sure the final build.py is reflected in the render/LDraw outputs.
    if needs_final_render:
        _render_and_snapshot(run)
    return last_result


def _render_and_snapshot(run: _Run) -> bool:
    """Render the current build and snapshot the judged build + its contact sheet.

    Returns whether the render succeeded. Each call adds its own snapshot, so every
    critique round's render is kept even when the builder revised between rounds
    without re-validating.
    """
    if not render_views(run.record, run.config).ok:
        return False
    run.record.add_render_snapshot()
    return True


def _reenter_builder(run: _Run, result: CritiqueResult) -> None:
    """Feed the critique back to the builder and run another pass.

    ``continue`` keeps the builder's conversation and appends the differences;
    ``fresh`` re-seeds a new conversation carrying over the current build.py.
    """
    differences = result.differences_description
    if run.config.critique_mode is CritiqueMode.FRESH:
        run.transcript.reset(fresh_round_messages(run.record, differences, run.config))
    else:
        run.transcript.append(critique_followup_message(differences))
    _run_builder_pass(run)


def _within_budget(run: _Run) -> bool:
    """Whether the run still has turns, validations, and spend left for a builder turn."""
    config = run.config
    return (
        (config.max_turns == 0 or run.tracker.turns < config.max_turns)
        and run.tracker.validation_budget_left(config.max_validations)
        and run.tracker.cost() < config.max_cost
        and not run.tracker.has_unknown_cost()
    )


def _stop_reason(run: _Run) -> StopReason:
    if run.tracker.has_unknown_cost():
        return StopReason.UNKNOWN_COST
    if run.done:
        return StopReason.FINALIZED
    if run.tracker.cost() >= run.config.max_cost:
        return StopReason.MAX_COST
    if not run.tracker.validation_budget_left(run.config.max_validations):
        return StopReason.MAX_VALIDATIONS
    if run.config.max_turns and run.tracker.turns >= run.config.max_turns:
        return StopReason.MAX_TURNS
    return StopReason.MODEL_STOPPED


def _warn_unknown_cost(run: _Run) -> None:
    if run.tracker.has_unknown_cost() and not run.warned_cost:
        run.narrator.warn(
            "A response has missing or invalid cost data; stopping further paid calls. "
            f"Known spend is ${run.tracker.cost():g}; total cost is unknown."
        )
        run.warned_cost = True


class _UnknownCost(Exception):
    """Stop a multi-request critique after recording an unpriced response."""


def _record_critique_response(run: _Run, response: Any) -> None:
    run.tracker.record(response)
    _warn_unknown_cost(run)
    if run.tracker.has_unknown_cost():
        raise _UnknownCost
