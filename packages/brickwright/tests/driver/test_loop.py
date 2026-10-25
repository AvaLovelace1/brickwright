"""Tests for the agent loop: edit/write -> validate -> finalize, and its limits."""

import base64
import copy
import json
from types import SimpleNamespace

import pytest

from brickwright.config import CritiqueMode, Effort
from brickwright.driver import Narrator, RunReport, loop, run_agent
from brickwright.driver.critique import CritiqueResult
from brickwright.record import Record, StopReason, Timing, Usage
from brickwright.tools import RenderReport, ToolOutcome, available_tools


class _FakeLLM:
    """Returns scripted responses in order and records the kwargs of each call."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        return self.responses[len(self.calls) - 1]


@pytest.fixture(autouse=True)
def _validation_in_process(in_process, fake_render_pipeline):
    """The loop's integration tests validate/finalize in-process rather than in a
    spawned child. See the ``in_process`` fixture in the top-level conftest."""


def _vp_round(response, tool_call, differences, done, *, costs=(0.0, 0.0, 0.0), n=1):
    """The critic's three turns for one viewpoint critique round.

    The viewpoint-matching agent renders once and finalizes, then the comparison call
    returns the verdict -- the call shape ``_critique_viewpoint`` drives every round.
    ``n`` keeps the scripted tool-call ids distinct across rounds.
    """
    render_cost, finalize_cost, verdict_cost = costs
    return [
        response(
            tool_calls=[tool_call(f"r{n}", "render_view", azimuth=0, elevation=0)],
            cost=render_cost,
        ),
        response(tool_calls=[tool_call(f"f{n}", "finalize")], cost=finalize_cost),
        response(content=_verdict(differences, done), cost=verdict_cost),
    ]


def _verdict(differences, done):
    """Serialize a critic reply the way the model is asked to return it."""
    return json.dumps({"differences_description": differences, "done": done})


@pytest.mark.integration
class TestLoop:
    def test_custom_runtime_controls_prompt_tools_and_execution(
        self, record, config, patch_complete, response, tool_call
    ):
        class Runtime(loop.AgentRuntime):
            def system_message(self, config):
                return {"role": "system", "content": "custom prompt"}

            def available_tools(self, config):
                return [{"type": "function", "function": {"name": "submit"}}]

            def execute_tool(self, record, config, name, arguments):
                assert name == "submit"
                return ToolOutcome("submitted", done=True)

        fake = patch_complete(_FakeLLM(response(tool_calls=[tool_call("1", "submit")])))
        report = run_agent(record, config, runtime=Runtime())
        assert report.done
        assert fake.calls[0]["messages"][0]["content"] == "custom prompt"
        assert fake.calls[0]["tools"][0]["function"]["name"] == "submit"

    def test_render_survives_a_following_edit_in_the_same_batch(
        self,
        record,
        config,
        monkeypatch,
        patch_complete,
        response,
        tool_call,
        png_bytes,
        assert_tool_calls_answered,
    ):
        def render(rec, cfg):
            rec.render_path.write_bytes(png_bytes)
            return RenderReport(ok=True, image_path=rec.render_path)

        monkeypatch.setattr("brickwright.tools.registry.render", render)
        fake = patch_complete(
            _FakeLLM(
                response(
                    tool_calls=[
                        tool_call("1", "render"),
                        tool_call(
                            "2", "write_build", content=record.read_build() + "\n"
                        ),
                    ]
                ),
                response(content="done"),
            )
        )
        run_agent(record, config)

        messages = fake.calls[1]["messages"]
        assert_tool_calls_answered(messages)
        image = messages[-1]["content"][0]["image_url"]["url"]
        assert base64.b64decode(image.partition(",")[2]) == png_bytes
        assert not record.render_path.exists()

    def test_angled_render_can_be_finalized_in_the_same_batch(
        self,
        record,
        config,
        patch_complete,
        response,
        tool_call,
        assert_tool_calls_answered,
    ):
        patch_complete(
            _FakeLLM(
                response(
                    tool_calls=[
                        tool_call("1", "render", azimuth=45, elevation=30),
                        tool_call("2", "finalize"),
                    ]
                )
            )
        )

        result = run_agent(record, config)

        assert result.succeeded
        assert record.read_meta().finalized
        assert_tool_calls_answered(
            [json.loads(line) for line in record.messages_path.read_text().splitlines()]
        )

    def test_zero_count_limits_allow_work_past_the_default_caps(
        self, record, config, script
    ):
        script(*(["validate"] * 201), "finalize")
        result = run_agent(
            record, config.model_copy(update={"max_turns": 0, "max_validations": 0})
        )
        assert result.succeeded
        assert result.turns == 202
        assert result.validations == 201

    def test_last_allowed_validation_is_recorded_as_a_validation_limit(
        self, record, config, script
    ):
        from brickwright.record import StopReason

        script("validate")
        result = run_agent(record, config.model_copy(update={"max_validations": 1}))
        assert result.stop_reason is StopReason.MAX_VALIDATIONS
        assert not result.done
        assert result.report is not None and result.report.ok
        assert not record.read_meta().finalized

    def test_unvalidated_last_edit_is_not_a_current_pass(
        self, record, config, script, floating_build
    ):
        script("validate", ("write_build", {"content": floating_build}))
        result = run_agent(record, config.model_copy(update={"max_turns": 2}))
        assert result.report is None
        assert not result.succeeded
        assert record.read_meta().stop_reason.value == "max_turns"
        assert not record.read_meta().finalized

    def test_failed_finalize_can_be_repaired(
        self, record, config, script, valid_build, floating_build
    ):
        script(
            "validate",
            ("write_build", {"content": floating_build}),
            "finalize",
            ("write_build", {"content": valid_build}),
            "finalize",
        )
        result = run_agent(record, config)
        assert result.succeeded
        assert result.turns == 5
        assert record.read_meta().finalized

    @pytest.mark.parametrize("unlimited_counts", [False, True])
    def test_cost_stop_is_persisted_separately_from_validity(
        self, record, config, patch_complete, response, tool_call, unlimited_counts
    ):
        if unlimited_counts:
            config = config.model_copy(update={"max_turns": 0, "max_validations": 0})
        patch_complete(
            _FakeLLM(response(tool_calls=[tool_call("1", "validate")], cost=0.03))
        )
        result = run_agent(record, config.model_copy(update={"max_cost": 0.025}))
        assert result.stop_reason is not None
        assert result.stop_reason.value == "max_cost"
        assert result.over_budget
        meta = record.read_meta()
        assert meta.over_budget and meta.stop_reason == result.stop_reason
        assert meta.status.value == "valid"
        assert not meta.finalized

    def test_exception_records_an_error_stop(self, record, config, patch_complete):
        def failed_request(**kwargs):
            raise RuntimeError("provider down")

        patch_complete(failed_request)
        with pytest.raises(RuntimeError, match="provider down"):
            run_agent(record, config)
        assert record.read_meta().stop_reason.value == "error"

    def test_use_all_tools(self, record, config, script, valid_build):
        config = config.model_copy(update={"effort": Effort.HIGH})
        record.write_build(valid_build)
        fake = script(
            ("edit_build", {"old_str": "Color.RED", "new_str": "Color.BLUE"}),
            "validate",
            ("explore", {"code": "print(model.brick_count)"}),
            "finalize",
        )
        result = run_agent(record, config)

        assert isinstance(result, RunReport)
        assert result.done is True
        assert result.turns == 4
        assert result.validations == 1
        assert result.report is not None
        assert result.report.ok is True
        assert "Color.BLUE" in record.read_build()
        assert record.read_meta().turns == 4
        assert record.read_meta().validations == 1
        # Effort level + tools were forwarded to the model.
        assert fake.calls[0]["reasoning_effort"] == "high"
        assert fake.calls[0]["tools"] == available_tools()

    def test_write_validate_finalize(self, record, config, script, valid_build):
        script(
            ("write_build", {"content": valid_build}),
            "validate",
            "finalize",
        )
        result = run_agent(record, config)

        assert result.done is True
        assert result.report is not None
        assert result.report.ok is True
        assert record.read_build() == valid_build  # the whole file was replaced

    @pytest.mark.parametrize(
        "overrides, expected",
        [
            pytest.param({"max_turns": 3, "max_validations": 99}, 3, id="turn-cap"),
            pytest.param(
                {"max_turns": 99, "max_validations": 2}, 2, id="validation-cap"
            ),
        ],
    )
    def test_stops_at_its_budget(self, record, config, script, overrides, expected):
        # Every turn here validates, so turns == validations; the lower cap stops the run.
        config = config.model_copy(update=overrides)
        fake = script(*["validate"] * 5)
        result = run_agent(record, config)
        assert result.done is False
        assert result.turns == expected
        assert result.validations == expected
        assert len(fake.calls) == expected

    def test_stops_when_the_cost_budget_is_spent(
        self, record, config, patch_complete, response, tool_call
    ):
        # Each turn validates and costs $0.01; a $0.025 cap stops the run once
        # spending reaches it -- after turn 3 ($0.03), overshooting by one turn
        # (a turn's cost is only known once its completion returns).
        config = config.model_copy(update={"max_cost": 0.025})
        responses = [
            response(tool_calls=[tool_call(str(i), "validate")], cost=0.01)
            for i in range(1, 6)
        ]
        fake = patch_complete(_FakeLLM(*responses))
        result = run_agent(record, config)
        assert result.done is False
        assert result.turns == 3
        assert len(fake.calls) == 3
        assert result.usage.cost_usd == pytest.approx(0.03)

    def test_off_effort_sends_no_reasoning_kwarg(self, record, config, script):
        config = config.model_copy(update={"effort": Effort.NONE})
        fake = script("finalize")
        run_agent(record, config)
        assert "reasoning_effort" not in fake.calls[0]

    def test_forwards_the_configured_model_with_tool_use_enabled(
        self, record, config, script
    ):
        config = config.model_copy(update={"model": "test/model"})
        fake = script("finalize")
        run_agent(record, config)
        assert fake.calls[0]["model"] == "test/model"
        assert fake.calls[0]["tool_choice"] == "auto"

    def test_thinking_blocks_carry_into_the_next_turn(
        self, record, config, patch_complete, response, tool_call
    ):
        config = config.model_copy(update={"effort": Effort.HIGH})
        blocks = [{"type": "thinking", "thinking": "plan", "signature": "sig"}]
        fake = patch_complete(
            _FakeLLM(
                response(
                    tool_calls=[tool_call("1", "validate")],
                    thinking_blocks=blocks,
                    reasoning_content="plan",
                ),
                response(tool_calls=[tool_call("2", "finalize")]),
            )
        )
        run_agent(record, config)

        first_turn = fake.calls[0]["messages"]
        assert not any(m["role"] == "assistant" for m in first_turn)

        second_turn = fake.calls[1]["messages"]
        assistant = next(m for m in second_turn if m["role"] == "assistant")
        assert assistant["thinking_blocks"] == blocks

    def test_render_appends_the_contact_sheet_as_a_followup_message(
        self,
        record,
        config,
        png_bytes,
        monkeypatch,
        patch_complete,
        response,
        tool_call,
    ):
        # render writes the contact sheet; the loop must show that single image to the
        # model as a user message AFTER the tool result, then stop on the plain reply.

        def fake_render(rec, cfg):
            rec.render_path.parent.mkdir(parents=True, exist_ok=True)
            rec.render_path.write_bytes(b"\x89PNG\r\n fake")
            return RenderReport(ok=True, image_path=rec.render_path)

        monkeypatch.setattr("brickwright.tools.registry.render", fake_render)
        patch_complete(
            _FakeLLM(
                response(tool_calls=[tool_call("1", "render")]),
                response(content="looks good"),
            )
        )

        run_agent(record, config)

        msgs = [
            json.loads(line) for line in record.messages_path.read_text().splitlines()
        ]
        tool_idx = next(i for i, m in enumerate(msgs) if m["role"] == "tool")
        image_idx = next(
            i
            for i, m in enumerate(msgs)
            if m["role"] == "user"
            and isinstance(m["content"], list)
            and any(b.get("type") == "image_url" for b in m["content"])
        )
        assert (
            image_idx > tool_idx
        )  # the contact sheet comes after the tool result it followed
        images = [b for b in msgs[image_idx]["content"] if b.get("type") == "image_url"]
        assert len(images) == 1  # a single contact sheet, not one image per view

    def test_plain_text_response_ends_the_loop(
        self, record, config, patch_complete, response
    ):
        patch_complete(_FakeLLM(response(content="I think the build is fine.")))
        result = run_agent(record, config)
        assert result.done is False
        assert result.turns == 1

    def test_a_truncated_reply_is_retried_not_taken_as_the_final_answer(
        self, record, config, patch_complete, response, tool_call, valid_build
    ):
        # A turn cut off at max_tokens has content but no tool call, which looks
        # exactly like "the model is done" and used to end the run on turn 1.
        cut_off = response(
            content="def create_build():\n    b = Lego", finish_reason="length"
        )
        recovered = response(
            tool_calls=[tool_call("1", "write_build", content=valid_build)]
        )
        llm = patch_complete(_FakeLLM(cut_off, recovered, response(content="done")))

        result = run_agent(record, config)

        assert result.turns == 3  # the truncated turn did not end the run
        assert record.read_build() == valid_build
        nudge = llm.calls[1]["messages"][-1]  # the model was told what happened
        assert "cut off" in nudge["content"] and "no tool call" in nudge["content"]

    def test_repeated_truncation_gives_up_instead_of_looping(
        self, record, config, patch_complete, response
    ):
        cut_off = response(content="...", finish_reason="length")
        patch_complete(_FakeLLM(*[cut_off] * 6))

        result = run_agent(record, config)

        assert result.turns < 6  # bounded retries, then it stops

    def test_a_plain_reply_that_was_not_truncated_still_ends_the_loop(
        self, record, config, patch_complete, response
    ):
        patch_complete(_FakeLLM(response(content="all good", finish_reason="stop")))
        result = run_agent(record, config)
        assert result.turns == 1
        assert result.final_text == "all good"

    def test_malformed_tool_arguments_fall_back_to_empty(
        self, record, config, patch_complete, response
    ):
        bad_call = SimpleNamespace(
            id="1",
            type="function",
            function=SimpleNamespace(name="finalize", arguments="{not valid json"),
        )
        patch_complete(_FakeLLM(response(tool_calls=[bad_call])))
        result = run_agent(record, config)
        assert result.done is True  # finalize ran with {} despite the bad JSON
        assert result.turns == 1

    @pytest.mark.parametrize("raw", ["[1, 2]", "5", '"x"', "null"])
    def test_non_object_tool_arguments_fall_back_to_empty(
        self, record, config, patch_complete, response, raw
    ):
        call = SimpleNamespace(
            id="1",
            type="function",
            function=SimpleNamespace(name="finalize", arguments=raw),
        )
        patch_complete(_FakeLLM(response(tool_calls=[call])))
        assert run_agent(record, config).done is True

    def test_validations_batched_in_one_turn_respect_the_budget(
        self,
        record,
        config,
        patch_complete,
        response,
        tool_call,
        assert_tool_calls_answered,
    ):
        config = config.model_copy(update={"max_validations": 1})
        calls = [tool_call(str(i), "validate") for i in range(3)]
        patch_complete(_FakeLLM(response(tool_calls=calls)))
        result = run_agent(record, config)
        assert result.validations == 1
        assert record.read_meta().validations == 1
        lines = record.messages_path.read_text().splitlines()
        assert_tool_calls_answered([json.loads(line) for line in lines if line.strip()])

    def test_calls_batched_after_finalize_are_still_answered(
        self,
        record,
        config,
        patch_complete,
        response,
        tool_call,
        assert_tool_calls_answered,
    ):
        """Finalizing ends the pass, but every call in that turn still needs an answer"""
        patch_complete(
            _FakeLLM(
                response(
                    tool_calls=[
                        tool_call("1", "finalize"),
                        tool_call("2", "read_build"),
                    ]
                )
            )
        )
        result = run_agent(record, config)

        assert result.done is True
        lines = record.messages_path.read_text().splitlines()
        assert_tool_calls_answered([json.loads(line) for line in lines if line.strip()])

    @pytest.mark.parametrize(
        "request_timeout, expected",
        [
            pytest.param(None, None, id="unset-leaves-it-to-the-client"),
            pytest.param(1800.0, 1800.0, id="set-is-forwarded"),
        ],
    )
    def test_request_timeout_reaches_the_completion(
        self, record, config, script, request_timeout, expected
    ):
        """A slow model needs a turn longer than the client's own 600s default allows."""
        config = config.model_copy(update={"request_timeout": request_timeout})
        fake = script("finalize")
        run_agent(record, config)

        assert fake.calls[0].get("timeout") == expected
        assert ("timeout" in fake.calls[0]) is (expected is not None)

    def test_returns_a_run_report(self, record, config, script):
        script("finalize")
        result = run_agent(record, config)
        assert isinstance(result, RunReport)
        assert result.done is True
        assert result.turns == 1
        assert result.validations == 0  # no explicit validate calls
        assert result.report is not None and result.report.ok
        assert result.timing.total >= 0

    def test_timing_is_threaded_and_attributes_tools_by_name(
        self, record, config, script, valid_build
    ):
        script(("write_build", {"content": valid_build}), "validate", "finalize")
        result = run_agent(record, config)

        timing = result.timing
        assert isinstance(timing, Timing)
        assert timing.total >= 0
        # Each tool that ran in-process is timed under its own name.
        assert {"write_build", "validate", "finalize"} == set(timing.tools)
        # Buckets reconstruct the total.
        assert (
            timing.llm + sum(timing.tools.values()) + timing.other
        ) == pytest.approx(timing.total)
        # The same breakdown is persisted to the record's metadata.
        assert record.read_meta().timing == timing

    def test_usage_is_accumulated_and_persisted_to_meta(
        self, record, config, patch_complete, response, tool_call
    ):
        # Tokens and cost sum across turns, land in the RunReport, and are
        # persisted verbatim to the record's meta.
        patch_complete(
            _FakeLLM(
                response(
                    tool_calls=[tool_call("1", "validate")], usage=(100, 20), cost=0.01
                ),
                response(
                    tool_calls=[tool_call("2", "finalize")], usage=(50, 10), cost=0.005
                ),
            )
        )
        result = run_agent(record, config)

        usage = result.usage
        assert (usage.prompt_tokens, usage.completion_tokens) == (150, 30)
        assert usage.total_tokens == 180
        assert usage.cost_usd == pytest.approx(0.015)
        assert record.read_meta().usage == usage

    def test_tool_calls_are_counted_and_persisted_to_meta(
        self, record, config, script, valid_build
    ):
        script(
            ("write_build", {"content": valid_build}),
            "validate",
            "validate",
            "finalize",
        )
        result = run_agent(record, config)

        expected = {"write_build": 1, "validate": 2, "finalize": 1}
        assert result.tool_calls == expected
        assert record.read_meta().tool_calls == expected

    def test_validation_failures_are_tracked_and_persisted_to_meta(
        self, record, config, script, floating_build
    ):
        # The model floats: validating it fails the no_floating check, and the
        # reason is tallied into the RunReport and persisted to meta.
        script(
            ("write_build", {"content": floating_build}),
            "validate",
            "validate",
            "finalize",
        )
        result = run_agent(record, config.model_copy(update={"max_turns": 4}))

        assert result.validation_failures.failing_checks == {"no_floating": 2}
        assert result.validation_failures.build_errors == {}
        assert record.read_meta().validation_failures == result.validation_failures

    def test_a_clean_run_records_no_validation_failures(
        self, record, config, script, valid_build
    ):
        script(("write_build", {"content": valid_build}), "validate", "finalize")
        result = run_agent(record, config)
        assert result.validation_failures.failing_checks == {}
        assert result.validation_failures.build_errors == {}

    def test_final_text_is_captured_on_a_plain_text_reply(
        self, record, config, patch_complete, response
    ):
        patch_complete(_FakeLLM(response(content="here is my answer")))
        result = run_agent(record, config)
        assert result.final_text == "here is my answer"

    def test_final_text_is_none_when_the_run_ends_on_a_tool_call(
        self, record, config, script
    ):
        script("finalize")
        result = run_agent(record, config)
        assert result.final_text is None

    def test_usage_reported_by_a_tool_is_folded_into_the_run(
        self, record, config, monkeypatch, patch_complete, response, tool_call
    ):
        def fake_execute(rec, cfg, name, args):
            return ToolOutcome(
                "ok",
                usage=Usage(prompt_tokens=70, completion_tokens=5, total_tokens=75),
            )

        monkeypatch.setattr(loop, "execute_tool", fake_execute)
        patch_complete(
            _FakeLLM(
                response(tool_calls=[tool_call("1", "read_build")]),
                response(content="done"),
            )
        )
        result = run_agent(record, config)
        assert result.usage.prompt_tokens == 70
        assert result.usage.total_tokens == 75
        assert result.subagent_usage.total_tokens == 75  # also tracked as a subtotal


@pytest.mark.integration
class TestRenderDisabled:
    def test_render_disabled_warning_is_emitted(
        self, record, config, monkeypatch, patch_complete, response
    ):
        from brickwright.driver import loop

        monkeypatch.setattr(loop, "render_available", lambda: False)

        warnings: list[str] = []
        monkeypatch.setattr(
            Narrator, "warn", lambda self, message: warnings.append(message)
        )
        patch_complete(_FakeLLM(response(content="done")))
        run_agent(record, config)
        assert any("render tool is disabled" in w for w in warnings)


@pytest.mark.integration
class TestCostWarning:
    """Unpriced requests must stop further spending and retain unknown totals."""

    @pytest.mark.parametrize("unpriced_turn", [0, 1, 2])
    def test_unpriced_critique_stops_before_another_paid_request(
        self,
        image_record,
        config,
        script,
        patch_critic,
        fake_llm,
        response,
        tool_call,
        unpriced_turn,
    ):
        config = config.model_copy(update={"max_critique_rounds": 2})
        script("finalize")
        costs = [0.01, 0.01, 0.01]
        costs[unpriced_turn] = None
        critic = patch_critic(
            fake_llm(
                *_vp_round(response, tool_call, "revise it", False, costs=costs),
            )
        )

        result = run_agent(image_record, config)

        assert len(critic.calls) == unpriced_turn + 1
        assert result.stop_reason is StopReason.UNKNOWN_COST
        assert result.usage.cost_usd is None
        assert not result.succeeded

    def test_unpriced_finalize_preserves_the_artifact_but_reports_unknown_cost(
        self,
        record,
        config,
        patch_complete,
        response,
        tool_call,
    ):
        patch_complete(
            _FakeLLM(
                response(
                    tool_calls=[tool_call("1", "finalize")],
                    cost=None,
                )
            )
        )
        result = run_agent(record, config)
        assert record.read_meta().finalized
        assert record.ldr_path.exists()
        assert result.stop_reason is StopReason.UNKNOWN_COST
        assert not result.succeeded

    @pytest.mark.parametrize(
        "bad_cost", [None, float("nan"), float("inf"), -0.1, "bad"]
    )
    def test_stops_after_unpriced_response_even_when_counts_are_unlimited(
        self,
        record,
        config,
        patch_complete,
        response,
        tool_call,
        bad_cost,
    ):
        config = config.model_copy(update={"max_turns": 0, "max_validations": 0})
        fake = patch_complete(
            _FakeLLM(
                response(tool_calls=[tool_call("1", "validate")], cost=0.01),
                response(tool_calls=[tool_call("2", "read_build")], cost=bad_cost),
                response(tool_calls=[tool_call("3", "finalize")], cost=0.01),
            )
        )

        result = run_agent(record, config)

        assert len(fake.calls) == 2
        assert result.stop_reason is StopReason.UNKNOWN_COST
        assert result.usage.cost_usd is None
        assert record.read_meta().usage.cost_usd is None
        assert record.read_meta().stop_reason == result.stop_reason
        assert not result.succeeded

    def test_unpriced_builder_does_not_dispatch_paid_children(
        self,
        record,
        config,
        patch_complete,
        response,
        tool_call,
        monkeypatch,
    ):
        config = config.model_copy(update={"subagents_enabled": True})
        monkeypatch.setattr(
            "brickwright.tools.registry.dispatch_subagents",
            lambda *a: pytest.fail("launched paid subagents"),
        )
        patch_complete(
            _FakeLLM(
                response(
                    tool_calls=[
                        tool_call(
                            "1",
                            "dispatch_subagents",
                            tasks=[{"prompt": "build a wheel"}],
                        )
                    ],
                    cost=None,
                )
            )
        )
        result = run_agent(record, config)
        assert result.stop_reason is StopReason.UNKNOWN_COST

    @staticmethod
    def _spy():
        warnings: list[str] = []

        class Spy(Narrator):
            def warn(self, message: str) -> None:
                warnings.append(message)

        return Spy(), warnings

    def test_warns_when_a_cost_cap_is_set_but_cost_is_unknown(
        self, record, config, patch_complete, response, tool_call
    ):
        spy, warnings = self._spy()
        config = config.model_copy(update={"max_cost": 0.05})
        patch_complete(
            _FakeLLM(
                response(tool_calls=[tool_call("1", "validate")], cost=None),
                response(tool_calls=[tool_call("2", "finalize")], cost=None),
            )
        )
        run_agent(record, config, narrator=spy)
        assert any("cost" in w.lower() for w in warnings)


@pytest.mark.integration
class TestRunAgentLog:
    def test_writes_the_conversation_to_the_record(self, record, config, script):
        script("finalize")
        run_agent(record, config, narrator=Narrator())

        lines = record.messages_path.read_text().splitlines()
        roles = [json.loads(line)["role"] for line in lines]
        assert roles == ["system", "user", "assistant", "tool"]

    def test_log_survives_an_interrupt(
        self, record, config, patch_complete, response, tool_call
    ):
        # The model is called, a tool runs, then the next call is interrupted.
        first = response(tool_calls=[tool_call("1", "read_build")])
        calls = {"n": 0}

        def complete(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return first
            raise KeyboardInterrupt

        patch_complete(complete)
        with pytest.raises(KeyboardInterrupt):
            run_agent(record, config, narrator=Narrator())

        # Everything logged before the interrupt is on disk.
        lines = record.messages_path.read_text().splitlines()
        roles = [json.loads(line)["role"] for line in lines]
        assert roles == ["system", "user", "assistant", "tool"]

    def test_meta_survives_an_error(
        self, record, config, patch_complete, response, tool_call
    ):
        # The second turn errors. The metadata accumulated so far must still reach the record.
        calls = {"n": 0}

        def complete(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return response(
                    tool_calls=[tool_call("1", "read_build")],
                    usage=(100, 20),
                    cost=0.01,
                )
            raise RuntimeError("boom")

        patch_complete(complete)
        with pytest.raises(RuntimeError):
            run_agent(record, config, narrator=Narrator())

        meta = record.read_meta()
        assert meta.usage.prompt_tokens == 100
        assert meta.usage.completion_tokens == 20
        assert meta.usage.cost_usd == pytest.approx(0.01)
        assert meta.tool_calls == {"read_build": 1}


@pytest.mark.integration
class TestNarratorContract:
    def test_run_finished_receives_the_run_report(
        self, record, config, patch_complete, response, tool_call
    ):
        # The narrator is handed the same RunReport that run_agent returns.
        captured: list[RunReport] = []

        class Spy(Narrator):
            def run_finished(self, record: Record, result: RunReport) -> None:
                captured.append(result)

        patch_complete(_FakeLLM(response(tool_calls=[tool_call("1", "finalize")])))
        result = run_agent(record, config, narrator=Spy())
        assert captured == [result]
        assert isinstance(captured[0], RunReport)


@pytest.mark.integration
class TestCritiqueLoop:
    @pytest.fixture(autouse=True)
    def _render_pipeline(self, fake_render_pipeline):
        """Stub rendering for the critique orchestration tests."""

    def test_iterates_until_the_critic_is_satisfied(
        self, image_record, config, script, patch_critic, fake_llm, response, tool_call
    ):
        config = config.model_copy(update={"max_critique_rounds": 3})
        builder = script("finalize", "finalize")  # one pass per round
        critic = patch_critic(
            fake_llm(
                *_vp_round(response, tool_call, "seeds too sparse", False, n=1),
                *_vp_round(response, tool_call, "matches now", True, n=2),
            )
        )

        result = run_agent(image_record, config)

        assert result.critique_rounds == 2
        assert result.critique_done is True
        assert result.last_critique is not None and result.last_critique.done is True
        assert len(builder.calls) == 2  # the builder re-entered once
        assert len(critic.calls) == 6  # (render + finalize + compare) per round
        # The verdict is persisted and the differences are fed back into the log.
        assert json.loads(image_record.critique_path.read_text())["done"] is True
        assert image_record.read_meta().critique_rounds == 2
        assert "seeds too sparse" in image_record.messages_path.read_text()

    def test_round_render_is_saved_as_a_snapshot(
        self, image_record, config, script, patch_critic, fake_llm, response, tool_call
    ):
        config = config.model_copy(update={"max_critique_rounds": 1})
        script("validate", "finalize")  # one validate -> one snapshot, then finalize
        patch_critic(fake_llm(*_vp_round(response, tool_call, "close enough", True)))

        run_agent(image_record, config)

        snapshot = image_record.snapshots[-1]
        # The judged contact sheet is kept alongside the snapshot's model.
        assert snapshot.render_path.exists()
        assert (
            snapshot.render_path.read_bytes() == image_record.render_path.read_bytes()
        )

    def test_each_round_snapshots_its_own_render(
        self, image_record, config, script, patch_critic, fake_llm, response, tool_call
    ):
        # Two rounds where the builder revises without re-validating between them:
        # each round must still leave its own render snapshot (none overwritten).
        config = config.model_copy(update={"max_critique_rounds": 2})
        script("validate", "finalize", "finalize")  # one validate, then a re-entry
        patch_critic(
            fake_llm(
                *_vp_round(response, tool_call, "too sparse", False, n=1),  # revise
                *_vp_round(response, tool_call, "matches now", True, n=2),  # done
            )
        )

        run_agent(image_record, config)

        render_snaps = [s for s in image_record.snapshots if s.render_path.exists()]
        assert len(render_snaps) == 2  # one render snapshot per critique round

    def test_is_off_by_default(
        self, image_record, config, script, patch_critic, fake_llm, response
    ):
        script("finalize")
        critic = patch_critic(fake_llm(response(content=_verdict("x", False))))

        result = run_agent(image_record, config)

        assert result.critique_rounds == 0
        assert result.critique_done is None
        assert result.last_critique is None
        assert critic.calls == []

    def test_is_skipped_without_a_prompt_image(
        self,
        make_record,
        config,
        script,
        patch_critic,
        fake_llm,
        response,
        image_record,
    ):
        rec = make_record(image_record.read_build())  # created without an image
        config = config.model_copy(update={"max_critique_rounds": 2})
        script("finalize")
        critic = patch_critic(fake_llm(response(content=_verdict("x", False))))

        result = run_agent(rec, config)

        assert result.critique_rounds == 0
        assert critic.calls == []

    def test_continue_mode_resumes_the_same_conversation(
        self, image_record, config, script, patch_critic, fake_llm, response, tool_call
    ):
        config = config.model_copy(
            update={"max_critique_rounds": 1, "critique_mode": CritiqueMode.CONTINUE}
        )
        builder = script("finalize", "finalize")
        patch_critic(fake_llm(*_vp_round(response, tool_call, "fix the rind", False)))

        run_agent(image_record, config)

        second = builder.calls[1]["messages"]  # the re-entered builder pass
        assert second[0]["role"] == "system"
        assert any(m["role"] == "assistant" for m in second)  # prior history retained
        assert any(
            m["role"] == "user" and "independent reviewer" in str(m["content"])
            for m in second
        )

    def test_fresh_mode_reseeds_the_conversation(
        self, image_record, config, script, patch_critic, fake_llm, response, tool_call
    ):
        config = config.model_copy(
            update={"max_critique_rounds": 1, "critique_mode": CritiqueMode.FRESH}
        )
        builder = script("finalize", "finalize")
        patch_critic(fake_llm(*_vp_round(response, tool_call, "fix the rind", False)))

        run_agent(image_record, config)

        second = builder.calls[1]["messages"]
        # Fresh: only system + the initial user turn + a handoff carrying the diffs.
        assert [m["role"] for m in second] == ["system", "user", "user"]
        assert "fix the rind" in str(second[-1]["content"])
        assert "build.py" in str(second[-1]["content"])
        assert '"event": "conversation_reset"' in image_record.messages_path.read_text()

    def test_critic_cost_is_added_to_the_run_total(
        self,
        image_record,
        config,
        patch_complete,
        patch_critic,
        fake_llm,
        response,
        tool_call,
    ):
        config = config.model_copy(update={"max_critique_rounds": 1})
        patch_complete(
            fake_llm(response(tool_calls=[tool_call("1", "finalize")], cost=0.01))
        )
        patch_critic(
            fake_llm(
                *_vp_round(response, tool_call, "ok", True, costs=(0.005, 0.005, 0.01))
            )
        )

        result = run_agent(image_record, config)

        assert result.critique_rounds == 1
        # Builder finalize ($0.01) + viewpoint agent + comparison ($0.02).
        assert result.usage.cost_usd == pytest.approx(0.03)

    def test_viewpoint_style_folds_in_the_agent_and_comparison_cost(
        self,
        image_record,
        config,
        patch_complete,
        patch_critic,
        fake_llm,
        response,
        tool_call,
    ):
        config = config.model_copy(
            update={"max_critique_rounds": 1, "max_viewpoint_iterations": 3}
        )
        patch_complete(
            fake_llm(response(tool_calls=[tool_call("1", "finalize")], cost=0.01))
        )
        patch_critic(
            fake_llm(
                response(
                    tool_calls=[
                        tool_call("v1", "render_view", azimuth=10, elevation=5)
                    ],
                    cost=0.02,
                ),
                response(tool_calls=[tool_call("v2", "finalize")], cost=0.03),
                response(content=_verdict("ok", True), cost=0.04),
            )
        )

        result = run_agent(image_record, config)

        assert result.critique_rounds == 1
        # Builder finalize + viewpoint agent's two turns + the comparison call.
        assert result.usage.cost_usd == pytest.approx(0.10)

    def test_viewpoint_style_saves_a_session_per_round(
        self, image_record, config, script, patch_critic, fake_llm, response, tool_call
    ):
        config = config.model_copy(
            update={"max_critique_rounds": 2, "max_viewpoint_iterations": 3}
        )
        script("finalize", "finalize")  # initial pass + one re-entry
        patch_critic(
            fake_llm(
                # round 1: viewpoint agent renders + finalizes, then the critic revises
                response(
                    tool_calls=[tool_call("v1", "render_view", azimuth=0, elevation=0)]
                ),
                response(tool_calls=[tool_call("v2", "finalize")]),
                response(content=_verdict("off", False)),
                # round 2: viewpoint agent again, then the critic is satisfied
                response(
                    tool_calls=[tool_call("w1", "render_view", azimuth=10, elevation=5)]
                ),
                response(tool_calls=[tool_call("w2", "finalize")]),
                response(content=_verdict("matches", True)),
            )
        )

        run_agent(image_record, config)

        sessions = sorted(image_record.viewpoints_dir.iterdir())
        assert len(sessions) == 2  # one viewpoint session per critique round
        for session in sessions:
            assert (session / "matched.png").is_file()  # each round's matched render
            assert (session / "transcript.jsonl").is_file()  # each round's transcript

    def test_runs_all_rounds_then_stops_when_never_satisfied(
        self, image_record, config, script, patch_critic, fake_llm, response, tool_call
    ):
        # The critic never says done: the loop runs exactly max_critique_rounds and
        # reports the differences that remain (no infinite loop).
        config = config.model_copy(update={"max_critique_rounds": 3})
        # One initial pass + a re-entry after each of the 3 unsatisfied rounds.
        script("finalize", "finalize", "finalize", "finalize")
        critic = patch_critic(
            fake_llm(
                *_vp_round(response, tool_call, "still off (1)", False, n=1),
                *_vp_round(response, tool_call, "still off (2)", False, n=2),
                *_vp_round(response, tool_call, "still off (3)", False, n=3),
            )
        )

        result = run_agent(image_record, config)

        assert result.critique_rounds == 3  # ran every round, then stopped
        assert result.critique_done is False  # never satisfied
        assert result.last_critique is not None and result.last_critique.done is False
        assert len(critic.calls) == 9  # (render + finalize + compare) per round

    def test_stops_once_the_builder_has_no_budget_to_revise(
        self, image_record, config, script, patch_critic, fake_llm, response, tool_call
    ):
        # With the builder's turns spent, another round would judge an unchanged model.
        config = config.model_copy(update={"max_critique_rounds": 3, "max_turns": 1})
        script("finalize")
        critic = patch_critic(
            fake_llm(*_vp_round(response, tool_call, "still off", False, n=1))
        )

        result = run_agent(image_record, config)

        assert result.critique_rounds == 1
        assert len(critic.calls) == 3

    def test_render_failure_skips_the_critique(
        self,
        image_record,
        config,
        script,
        patch_critic,
        fake_llm,
        response,
        monkeypatch,
    ):
        # If the current model cannot be rendered, the round is skipped and the critic
        # never runs (there is nothing to compare against the reference).
        config = config.model_copy(update={"max_critique_rounds": 2})
        script("finalize")
        monkeypatch.setattr(
            "brickwright.driver.loop.render_views",
            lambda rec, cfg: RenderReport(ok=False, error="boom"),
        )
        critic = patch_critic(fake_llm(response(content=_verdict("x", True))))

        result = run_agent(image_record, config)

        assert result.critique_rounds == 0
        assert critic.calls == []  # render failed, so no comparison happened

    def test_unparseable_verdict_stops_the_loop(
        self, image_record, config, script, patch_critic, fake_llm, response, tool_call
    ):
        # A reply the critic can't parse into a verdict stops the loop without counting
        # a round, rather than crashing it.
        config = config.model_copy(update={"max_critique_rounds": 3})
        script("finalize")
        critic = patch_critic(
            fake_llm(
                response(
                    tool_calls=[tool_call("r1", "render_view", azimuth=0, elevation=0)]
                ),
                response(tool_calls=[tool_call("f1", "finalize")]),
                response(content="not json at all"),
            )
        )

        result = run_agent(image_record, config)

        assert result.critique_rounds == 0  # the unparseable verdict ended the loop
        assert result.critique_done is None
        assert result.last_critique is None
        # The viewpoint agent's two turns ran, then the unparseable comparison stopped it.
        assert len(critic.calls) == 3

    def test_stops_when_the_critique_cost_budget_is_spent(
        self,
        image_record,
        config,
        patch_complete,
        patch_critic,
        fake_llm,
        response,
        tool_call,
    ):
        # The critique loop stops once spending reaches the cap, even with rounds left.
        # Builder finalize ($0.01) + round-1 critique ($0.02) = $0.03 >= the $0.025 cap.
        config = config.model_copy(update={"max_critique_rounds": 3, "max_cost": 0.025})
        patch_complete(
            fake_llm(response(tool_calls=[tool_call("1", "finalize")], cost=0.01))
        )
        critic = patch_critic(
            fake_llm(
                *_vp_round(
                    response,
                    tool_call,
                    "still off",
                    False,
                    costs=(0.005, 0.005, 0.01),
                    n=1,
                ),
                *_vp_round(response, tool_call, "should not run", False, n=2),
            )
        )

        result = run_agent(image_record, config)

        assert result.critique_rounds == 1  # round 1 ran; the budget stopped round 2
        assert len(critic.calls) == 3  # only round 1's viewpoint turns + compare ran

    def test_completed_rounds_survive_an_error_in_a_later_round(
        self, image_record, config, script, monkeypatch
    ):
        # Round 1 completes and is persisted; the critic then dies in round 2.
        # The persisted count must not be clobbered back to 0 on the way out.
        from brickwright.driver import loop as loop_mod

        verdicts = iter([CritiqueResult(differences_description="fix it", done=False)])

        def fake_critique(rec, cfg, *, on_response):
            try:
                return next(verdicts)
            except StopIteration:
                raise RuntimeError("critic died") from None

        monkeypatch.setattr(loop_mod, "critique", fake_critique)
        config = config.model_copy(update={"max_critique_rounds": 3})
        script("finalize", "finalize")

        with pytest.raises(RuntimeError, match="critic died"):
            run_agent(image_record, config)

        assert image_record.read_meta().critique_rounds == 1

    def test_final_render_runs_when_the_budget_is_spent_mid_revision(
        self,
        image_record,
        config,
        patch_complete,
        patch_critic,
        fake_llm,
        response,
        tool_call,
    ):
        config = config.model_copy(update={"max_critique_rounds": 3, "max_cost": 0.05})
        patch_complete(
            fake_llm(
                response(tool_calls=[tool_call("1", "finalize")], cost=0.01),
                response(tool_calls=[tool_call("2", "finalize")], cost=0.03),
            )
        )
        patch_critic(
            fake_llm(
                *_vp_round(
                    response, tool_call, "still off", False, costs=(0.005, 0.005, 0.01)
                )
            )
        )

        result = run_agent(image_record, config)

        assert result.critique_rounds == 1  # the cap ended the loop before round 2
        render_snaps = [s for s in image_record.snapshots if s.render_path.exists()]
        assert len(render_snaps) == 2  # round 1's judged render + the revision's

    def test_critique_reentry_runs_a_full_builder_pass(
        self, image_record, config, script, monkeypatch
    ):
        # Regression: after a critique, the re-entered builder pass must run a FULL
        # pass (multiple turns) rather than being cut off after one turn by a sticky
        # ``done`` flag left over from the initial build.
        from brickwright.driver import loop as loop_mod

        verdicts = iter(
            [
                CritiqueResult(differences_description="fix it", done=False),
                CritiqueResult(differences_description="great", done=True),
            ]
        )
        monkeypatch.setattr(loop_mod, "critique", lambda rec, cfg, **kw: next(verdicts))
        config = config.model_copy(update={"max_critique_rounds": 3})
        # Initial build finalizes; the re-entry must run TWO turns: validate, finalize.
        builder = script("finalize", "validate", "finalize")

        run_agent(image_record, config)

        # 1 (initial finalize) + 2 (re-entry: validate then finalize) = 3. The bug
        # capped the re-entry at one turn -> 2 calls, and it never re-finalized.
        assert len(builder.calls) == 3

    def test_run_done_reflects_the_final_builder_pass(
        self,
        image_record,
        config,
        patch_complete,
        fake_llm,
        response,
        tool_call,
        monkeypatch,
    ):
        # run.done tracks the FINAL pass: if the re-entered pass does not finalize, the
        # run is not "done" -- even though the initial pass did finalize (which the old
        # sticky flag would have wrongly reported as done).
        from brickwright.driver import loop as loop_mod

        monkeypatch.setattr(
            loop_mod,
            "critique",
            lambda rec, cfg, **kw: CritiqueResult(
                differences_description="fix", done=False
            ),
        )
        config = config.model_copy(update={"max_critique_rounds": 1})
        patch_complete(
            fake_llm(
                response(tool_calls=[tool_call("1", "finalize")]),  # initial: finalize
                response(content="looks right already"),  # re-entry: plain text
            )
        )

        result = run_agent(image_record, config)

        assert result.done is False  # the final (re-entered) pass did not finalize
