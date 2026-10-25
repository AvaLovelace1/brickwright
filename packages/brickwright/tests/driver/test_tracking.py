"""Tests for token/cost accumulation and run timing."""

from types import SimpleNamespace

import pytest

from brickwright.driver import tracking
from brickwright.driver.tracking import RunTracker, _usage_of
from brickwright.record import (
    CompletionTokensDetails,
    PromptTokensDetails,
    Usage,
    ValidationFailures,
)
from brickwright.tools.testing import CheckResult
from brickwright.tools.validation import ValidationReport


class TestUsageTracking:
    def test_usage_tracking(self):
        tracker = RunTracker()
        tracker.record(
            SimpleNamespace(
                usage=SimpleNamespace(
                    prompt_tokens=100, completion_tokens=20, total_tokens=120
                )
            )
        )
        tracker.record(
            SimpleNamespace(
                usage=SimpleNamespace(
                    prompt_tokens=50, completion_tokens=10, total_tokens=60
                )
            )
        )
        usage = tracker.usage()
        assert isinstance(usage, Usage)
        assert usage.prompt_tokens == 150
        assert usage.completion_tokens == 30
        assert usage.total_tokens == 180
        assert usage.cost_usd is None
        assert tracker.subagent_usage() == Usage()

    def test_token_details_accumulate_across_responses(self):
        tracker = RunTracker()
        tracker.record(
            SimpleNamespace(
                usage=SimpleNamespace(
                    prompt_tokens=100,
                    completion_tokens=20,
                    total_tokens=120,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=40),
                    completion_tokens_details=SimpleNamespace(
                        reasoning_tokens=12,
                        accepted_prediction_tokens=2,
                        rejected_prediction_tokens=1,
                    ),
                )
            )
        )
        tracker.record(
            SimpleNamespace(
                usage=SimpleNamespace(
                    prompt_tokens=50,
                    completion_tokens=10,
                    total_tokens=60,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=10),
                    completion_tokens_details=SimpleNamespace(
                        reasoning_tokens=8,
                        accepted_prediction_tokens=3,
                        rejected_prediction_tokens=0,
                    ),
                )
            )
        )
        usage = tracker.usage()
        assert usage.prompt_tokens_details == PromptTokensDetails(cached_tokens=50)
        assert usage.completion_tokens_details == CompletionTokensDetails(
            reasoning_tokens=20,
            accepted_prediction_tokens=5,
            rejected_prediction_tokens=1,
        )

    def test_absent_details_are_none(self):
        tracker = RunTracker()
        tracker.record(
            SimpleNamespace(
                usage=SimpleNamespace(
                    prompt_tokens=10,
                    completion_tokens=2,
                    total_tokens=12,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=None),
                )
            )
        )
        usage = tracker.usage()
        assert usage.prompt_tokens_details == PromptTokensDetails()
        assert usage.completion_tokens_details == CompletionTokensDetails()
        assert usage.prompt_tokens_details.cached_tokens is None
        assert usage.completion_tokens_details.reasoning_tokens is None
        assert usage.completion_tokens_details.accepted_prediction_tokens is None
        assert usage.completion_tokens_details.rejected_prediction_tokens is None

    def test_an_explicitly_reported_zero_is_kept_distinct_from_absent(self):
        # A field the provider does report as 0 stays 0; only absent fields are None.
        tracker = RunTracker()
        tracker.record(
            SimpleNamespace(
                usage=SimpleNamespace(
                    prompt_tokens=10,
                    completion_tokens=2,
                    total_tokens=12,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=0),
                )
            )
        )
        usage = tracker.usage()
        assert usage.prompt_tokens_details.cached_tokens == 0
        assert usage.completion_tokens_details.reasoning_tokens is None

    def test_add_usage_folds_a_usage_into_the_totals(self):
        tracker = RunTracker()
        tracker.add_subagent_usage(
            Usage(
                prompt_tokens=100, completion_tokens=20, total_tokens=120, cost_usd=0.01
            )
        )
        tracker.add_subagent_usage(
            Usage(prompt_tokens=5, completion_tokens=1, total_tokens=6, cost_usd=0.002)
        )

        usage = tracker.usage()
        assert usage.prompt_tokens == 105
        assert usage.completion_tokens == 21
        assert usage.total_tokens == 126
        assert usage.cost_usd == pytest.approx(0.012)
        assert tracker.cost() == pytest.approx(0.012)
        sub = tracker.subagent_usage()
        assert sub.prompt_tokens == 105
        assert sub.completion_tokens == 21
        assert sub.total_tokens == 126
        assert sub.cost_usd == pytest.approx(0.012)


class TestCostAccess:
    """``cost``/``cost_known`` expose the running spend for the loop's budget check."""

    def test_subagent_unknown_total_retains_its_known_subtotal(self):
        tracker = RunTracker()
        tracker.record(SimpleNamespace(_hidden_params={"response_cost": 0.01}))
        tracker.add_subagent_usage(Usage(cost_usd=None, known_cost_usd=0.02))
        assert not tracker.cost_known()
        assert tracker.usage().cost_usd is None
        assert tracker.usage().known_cost_usd == pytest.approx(0.03)
        assert tracker.cost() == pytest.approx(0.03)

    @pytest.mark.parametrize("costs", [(0.01, None, 0.02), (None, 0.01)])
    def test_partial_costs_stay_unknown(self, costs):
        tracker = RunTracker()
        for cost in costs:
            tracker.record(SimpleNamespace(_hidden_params={"response_cost": cost}))
        assert not tracker.cost_known()
        assert tracker.usage().cost_usd is None
        assert tracker.cost() == pytest.approx(sum(c for c in costs if c is not None))

    @pytest.mark.parametrize("cost", [float("nan"), float("inf"), -0.01, "bad"])
    def test_invalid_costs_are_unknown(self, cost):
        tracker = RunTracker()
        tracker.record(SimpleNamespace(_hidden_params={"response_cost": cost}))
        assert not tracker.cost_known()
        assert tracker.usage().cost_usd is None
        assert tracker.cost() == 0

    def test_cost_sums_priced_responses_and_is_known(self):
        tracker = RunTracker()
        tracker.record(SimpleNamespace(_hidden_params={"response_cost": 0.01}))
        tracker.record(SimpleNamespace(_hidden_params={"response_cost": 0.02}))
        assert tracker.cost() == pytest.approx(0.03)
        assert tracker.cost_known() is True

    def test_cost_is_zero_and_unknown_without_a_price(self):
        tracker = RunTracker()
        tracker.record(SimpleNamespace())  # no usage, no cost reported
        assert tracker.cost() == 0.0
        assert tracker.cost_known() is False


class TestToolCallCounts:
    """``time_tool`` tallies how many times each tool was called, by name."""

    def test_timing_a_tool_counts_it_by_name(self):
        tracker = RunTracker()
        with tracker.time_tool("validate"):
            pass
        with tracker.time_tool("edit_build"):
            pass
        with tracker.time_tool("validate"):
            pass
        assert tracker.tool_calls() == {"validate": 2, "edit_build": 1}

    def test_tool_calls_is_empty_before_any_call(self):
        assert RunTracker().tool_calls() == {}


class TestValidationFailureTracking:
    """``record_validation`` tallies why each failed validation failed; passing
    validations contribute nothing."""

    def test_no_failures_before_any_validation(self):
        assert RunTracker().validation_failures() == ValidationFailures()

    def test_a_passing_validation_is_not_counted(self):
        tracker = RunTracker()
        tracker.record_validation(
            ValidationReport.from_checks([CheckResult(name="a", passed=True)])
        )
        assert tracker.validation_failures() == ValidationFailures()

    def test_build_errors_are_counted_by_type(self):
        tracker = RunTracker()
        tracker.record_validation(
            ValidationReport.error("boom", error_type="InvalidPartError")
        )
        tracker.record_validation(
            ValidationReport.error("again", error_type="InvalidPartError")
        )
        tracker.record_validation(
            ValidationReport.error("slow", error_type="TimeoutError")
        )
        tracker.record_validation(ValidationReport.error("???", error_type=None))
        assert tracker.validation_failures().build_errors == {
            "InvalidPartError": 2,
            "TimeoutError": 1,
            "Unknown": 1,
        }

    def test_failing_checks_are_counted_by_name(self):
        tracker = RunTracker()
        tracker.record_validation(
            ValidationReport.from_checks(
                [
                    CheckResult(name="no_collisions", passed=False, detail="x"),
                    CheckResult(name="no_floating", passed=False, detail="y"),
                ]
            )
        )
        tracker.record_validation(
            ValidationReport.from_checks(
                [CheckResult(name="no_collisions", passed=False, detail="z")]
            )
        )
        assert tracker.validation_failures().failing_checks == {
            "no_collisions": 2,
            "no_floating": 1,
        }


class TestPhaseTiming:
    """RunTracker attributes wall-clock to llm and per-tool buckets, remainder to other."""

    def test_timing_breaks_down_by_phase(self, monkeypatch):
        # perf_counter calls, in order: construct(1), llm enter/exit(2),
        # validate enter/exit(2), read_build enter/exit(2), timing()->_elapsed(1).
        ticks = iter([100.0, 100.0, 108.0, 108.0, 111.0, 111.0, 111.2, 130.0])
        monkeypatch.setattr(tracking.time, "perf_counter", lambda: next(ticks))

        tracker = RunTracker()
        with tracker.time_llm():
            pass
        with tracker.time_tool("validate"):
            pass
        with tracker.time_tool("read_build"):
            pass
        timing = tracker.timing()

        assert timing.total == pytest.approx(30.0)
        assert timing.llm == pytest.approx(8.0)
        assert timing.tools["validate"] == pytest.approx(3.0)
        assert timing.tools["read_build"] == pytest.approx(0.2)
        assert timing.other == pytest.approx(18.8)
        assert (
            timing.llm + sum(timing.tools.values()) + timing.other
        ) == pytest.approx(timing.total)

    def test_each_tool_gets_its_own_named_bucket(self, monkeypatch):
        # construct(1), finalize enter/exit(2), write_build enter/exit(2), timing()(1)
        ticks = iter([0.0, 0.0, 2.0, 2.0, 2.5, 5.0])
        monkeypatch.setattr(tracking.time, "perf_counter", lambda: next(ticks))

        tracker = RunTracker()
        with tracker.time_tool("finalize"):
            pass
        with tracker.time_tool("write_build"):
            pass
        timing = tracker.timing()

        assert timing.tools["finalize"] == pytest.approx(2.0)
        assert timing.tools["write_build"] == pytest.approx(0.5)
        assert timing.llm == 0.0

    def test_repeated_calls_to_a_tool_accumulate(self, monkeypatch):
        # construct(1), validate#1 enter/exit(2), validate#2 enter/exit(2), timing()(1)
        ticks = iter([0.0, 0.0, 2.0, 2.0, 3.0, 6.0])
        monkeypatch.setattr(tracking.time, "perf_counter", lambda: next(ticks))

        tracker = RunTracker()
        with tracker.time_tool("validate"):
            pass
        with tracker.time_tool("validate"):
            pass
        timing = tracker.timing()

        assert timing.tools == {"validate": pytest.approx(3.0)}


class TestUsageExtraction:
    def test_reported_total_is_authoritative(self):
        usage = SimpleNamespace(
            prompt_tokens=100, completion_tokens=20, total_tokens=999
        )
        assert _usage_of(SimpleNamespace(usage=usage)).total_tokens == 999

    def test_total_falls_back_to_prompt_plus_completion(self):
        # Some providers omit or zero total_tokens; derive it from the parts.
        usage = _usage_of(
            SimpleNamespace(
                usage=SimpleNamespace(
                    prompt_tokens=100, completion_tokens=20, total_tokens=0
                )
            )
        )
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 20
        assert usage.total_tokens == 120

    def test_a_response_without_usage_contributes_nothing(self):
        assert _usage_of(SimpleNamespace()) == Usage()
