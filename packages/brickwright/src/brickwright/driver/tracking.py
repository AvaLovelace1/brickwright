"""Per-run bookkeeping: token usage, cost, and wall-clock time."""

import time
from collections import Counter, defaultdict
from collections.abc import Generator
from contextlib import contextmanager
from math import isfinite
from typing import Any

from ..record import (
    CompletionTokensDetails,
    PromptTokensDetails,
    Timing,
    Usage,
    UsageTracker,
    ValidationFailures,
)
from ..tools.validation import ValidationReport


class RunTracker:
    """Accumulates token usage and cost across completions, and times the run.

    Construct at the start of a run. Wrap each completion call in
    :meth:`time_llm` and each tool call in :meth:`time_tool` (which also tallies
    it by name). Call :meth:`record` once per completion response. At the end of
    the run, read :meth:`usage`, :meth:`timing`, and :meth:`tool_calls` to obtain
    the accumulated totals.
    """

    def __init__(self) -> None:
        self._started = time.perf_counter()
        self._ended: float | None = None
        self._llm_time = 0.0
        self._tool_time: defaultdict[str, float] = defaultdict(float)
        self._usage_tracker = UsageTracker()
        self._subagent_usage_tracker = UsageTracker()
        self._tool_calls: Counter[str] = Counter()
        self._validation_failures = ValidationFailures()
        self.turns = 0  # builder turns taken across every pass
        self.validations = 0  # validate calls made
        self.critique_rounds = 0  # critique rounds that reached a verdict

    def meta(self) -> dict[str, Any]:
        """The run bookkeeping to persist on the record."""
        return {
            "usage": self.usage(),
            "validations": self.validations,
            "turns": self.turns,
            "tool_calls": self.tool_calls(),
            "timing": self.timing(),
            "validation_failures": self.validation_failures(),
            "critique_rounds": self.critique_rounds,
        }

    def record(self, response: Any) -> None:
        """Fold one completion response's usage and cost into the totals."""
        self._usage_tracker.add(_usage_of(response))

    def add_subagent_usage(self, usage: Usage) -> None:
        """Fold a subagent's total usage into this run.

        Counts toward both the run total and a separate subagent subtotal.
        """
        self._usage_tracker.add(usage)
        self._subagent_usage_tracker.add(usage)

    def subagent_usage(self) -> Usage:
        """The portion of usage that came from subagents."""
        return self._subagent_usage_tracker.usage()

    def usage(self) -> Usage:
        """The accumulated token counts and cost (``cost_usd`` None if unknown)."""
        return self._usage_tracker.usage()

    def cost(self) -> float:
        """USD spent so far (0.0 while no completion has reported a cost)."""
        return self._usage_tracker.cost

    def cost_known(self) -> bool:
        """Whether every recorded completion has a usable cost."""
        return self._usage_tracker.cost_known

    def has_unknown_cost(self) -> bool:
        """Whether any recorded response or subagent has an unpriced charge."""
        return self._usage_tracker.has_unknown_cost

    @contextmanager
    def time_llm(self) -> Generator[None]:
        """Accumulate the wrapped block's wall-clock into the llm bucket."""
        start = time.perf_counter()
        try:
            yield
        finally:
            self._llm_time += time.perf_counter() - start

    def tool_calls(self) -> dict[str, int]:
        """How many times each tool was called, keyed by name."""
        return dict(self._tool_calls)

    def validation_budget_left(self, max_validations: int) -> bool:
        """Whether validations remain; zero means unlimited."""
        return max_validations == 0 or self.validations < max_validations

    def record_validation(self, report: ValidationReport) -> None:
        """Tally why a validation failed (see :func:`tally_failure`)."""
        self._validation_failures = tally_failure(self._validation_failures, report)

    def validation_failures(self) -> ValidationFailures:
        """Why validations failed so far, tallied by reason."""
        return self._validation_failures

    @contextmanager
    def time_tool(self, name: str) -> Generator[None]:
        """Time the wrapped tool call and tally it by name.

        The wall-clock is added to this tool's entry in :meth:`timing`'s per-tool
        breakdown, and the call is counted toward :meth:`tool_calls`.
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            self._tool_time[name] += time.perf_counter() - start
            self._tool_calls[name] += 1

    def _elapsed(self) -> float:
        """Seconds from construction to the first call (frozen after, so reads agree)."""
        if self._ended is None:
            self._ended = time.perf_counter()
        return self._ended - self._started

    def timing(self) -> Timing:
        """The per-phase breakdown; ``llm``, ``other``, and the per-tool times sum
        to ``total`` (``other`` absorbs the remainder, clamped at 0)."""
        total = round(self._elapsed(), 3)
        llm = round(self._llm_time, 3)
        tools = {name: round(dt, 3) for name, dt in self._tool_time.items()}
        other = max(0.0, round(total - llm - sum(tools.values()), 3))
        return Timing(total=total, llm=llm, tools=tools, other=other)


def _usage_of(response: Any) -> Usage:
    """One completion response's usage as a :class:`Usage`.

    Defensive: a response with no ``usage`` (a test stub, a provider that omits it)
    contributes zero tokens, and a detail or cost the provider doesn't report stays None.
    """
    usage = getattr(response, "usage", None)
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(usage, "completion_tokens", 0) or 0)
    total = int(getattr(usage, "total_tokens", 0) or 0) or prompt + completion
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    completion_details = getattr(usage, "completion_tokens_details", None)
    return Usage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        cost_usd=_response_cost(response),
        prompt_tokens_details=PromptTokensDetails(
            cached_tokens=_reported_int(prompt_details, "cached_tokens"),
        ),
        completion_tokens_details=CompletionTokensDetails(
            reasoning_tokens=_reported_int(completion_details, "reasoning_tokens"),
            accepted_prediction_tokens=_reported_int(
                completion_details, "accepted_prediction_tokens"
            ),
            rejected_prediction_tokens=_reported_int(
                completion_details, "rejected_prediction_tokens"
            ),
        ),
    )


def _reported_int(obj: Any, attr: str) -> int | None:
    """``obj.attr`` as an int, or None if absent or reported as None."""
    value = getattr(obj, attr, None)
    return None if value is None else int(value)


def _response_cost(response: Any) -> float | None:
    """The USD cost litellm attached to a completion response, if it knows one.

    litellm stores it on ``response._hidden_params['response_cost']``; an injected
    ``complete`` (e.g. a test stub) or an un-priced model simply has none.
    """
    hidden = getattr(response, "_hidden_params", None)
    if isinstance(hidden, dict):
        cost = hidden.get("response_cost")
        if cost is not None:
            try:
                value = float(cost)
            except (TypeError, ValueError, OverflowError):
                return None
            if isfinite(value) and value >= 0:
                return value
    return None


def tally_failure(
    failures: ValidationFailures, report: ValidationReport
) -> ValidationFailures:
    """``failures`` with ``report``'s failure reason folded in (a passing report
    leaves it unchanged).

    A build error is tallied by its exception type (``"Unknown"`` if absent);
    otherwise each failing check is tallied by name. Returns a new value.
    """
    if report.ok:
        return failures
    if report.build_error is not None:
        counts = Counter(failures.build_errors)
        counts[report.error_type or "Unknown"] += 1
        return failures.model_copy(update={"build_errors": dict(counts)})
    counts = Counter(failures.failing_checks)
    counts.update(report.failed_checks)
    return failures.model_copy(update={"failing_checks": dict(counts)})
