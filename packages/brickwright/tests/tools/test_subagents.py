import pytest

from brickwright.config import Config
from brickwright.record import Record, Usage
from brickwright.tools import subagents
from brickwright.tools.subagents import (
    SubagentResult,
    SubagentTask,
    _resolve_subagent_model,
    _run_subagent,
    dispatch_subagents,
)


class _ConstantLLM:
    """A thread-safe fake: returns the same response no matter how often it is called."""

    def __init__(self, response):
        self._response = response

    def __call__(self, **kwargs):
        return self._response


class TestDispatchSubagents:
    def test_dispatch_runs_all_tasks_and_preserves_order(
        self, tmp_path, patch_complete, response
    ):
        config = Config(records_dir=tmp_path / "records", max_parallel_subagents=2)
        record = Record.create(config)
        patch_complete(_ConstantLLM(response(content="ok")))

        tasks = [SubagentTask(prompt=f"task {i}") for i in range(3)]
        results = dispatch_subagents(record, tasks, config)

        assert len(results) == 3
        assert all(r.ok and r.text == "ok" for r in results)
        assert len({r.record_id for r in results}) == 3  # three isolated records

    def test_dispatch_isolates_a_failing_task(self, config, record, monkeypatch):
        def fake_run(record, task, cfg):
            if task.prompt == "boom":
                raise RuntimeError("kaboom")
            return SubagentResult(ok=True, text="fine", usage=Usage(), record_id="r")

        monkeypatch.setattr(subagents, "_run_subagent", fake_run)

        results = dispatch_subagents(
            record,
            [
                SubagentTask(prompt="a"),
                SubagentTask(prompt="boom"),
                SubagentTask(prompt="b"),
            ],
            config,
        )

        assert [r.ok for r in results] == [True, False, True]
        assert "kaboom" in results[1].reason


class TestRunSubagent:
    def test_run_subagent_returns_its_final_text(
        self, config, record, patch_complete, response
    ):
        patch_complete(_ConstantLLM(response(content="2x2 brick")))

        result = _run_subagent(record, SubagentTask(prompt="name a part"), config)

        assert result.ok is True
        assert result.text == "2x2 brick"
        assert result.record_id  # a child record was created
        # The child record exists on disk under the record subagents_dir.
        assert (record.subagents_dir / result.record_id).is_dir()

    def test_run_subagent_reports_failure_when_no_text_is_produced(
        self, tmp_path, patch_complete, response, tool_call
    ):
        # A worker that never replies with text and hits its
        # turn budget yields ok=False rather than an empty success.
        config = Config(records_dir=tmp_path / "records", subagent_max_turns=2)
        record = Record.create(config)
        patch_complete(
            _ConstantLLM(response(tool_calls=[tool_call("1", "read_build")]))
        )

        result = _run_subagent(record, SubagentTask(prompt="loop forever"), config)

        assert result.ok is False
        assert "no final answer" in result.reason


class TestReportedValidity:
    """``ok`` says work came back; ``valid`` says the work passed its own checks."""

    def test_validity_is_reported_when_the_subagent_validated(
        self, tmp_path, patch_complete, response, tool_call, floating_build
    ):
        config = Config(records_dir=tmp_path / "records", subagent_max_turns=3)
        record = Record.create(config)
        patch_complete(
            _ConstantLLM(
                response(
                    tool_calls=[
                        tool_call("1", "write_build", content=floating_build),
                        tool_call("2", "validate"),
                    ]
                )
            )
        )

        result = _run_subagent(record, SubagentTask(prompt="build it"), config)

        assert result.valid is False  # the work is broken
        assert "no_floating" in result.failed_checks
        assert result.finalized is False

    def test_a_sound_result_reports_valid(
        self, tmp_path, patch_complete, response, tool_call, valid_build
    ):
        config = Config(records_dir=tmp_path / "records", subagent_max_turns=3)
        record = Record.create(config)
        patch_complete(
            _ConstantLLM(
                response(
                    tool_calls=[
                        tool_call("1", "write_build", content=valid_build),
                        tool_call("2", "validate"),
                    ]
                )
            )
        )

        result = _run_subagent(record, SubagentTask(prompt="build it"), config)

        assert result.valid is True
        assert result.failed_checks == []

    def test_validity_is_unknown_when_the_subagent_never_validated(
        self, config, record, patch_complete, response
    ):
        patch_complete(_ConstantLLM(response(content="done")))

        result = _run_subagent(record, SubagentTask(prompt="say done"), config)

        assert result.valid is None  # never validated -- not the same as "valid"


class TestResolveSubagentModel:
    @pytest.fixture
    def tiered_config(self, tmp_path):
        return Config(
            records_dir=tmp_path / "records",
            model="anthropic/main-model",
            subagent_tiers={
                "anthropic": {
                    "smart": "anthropic/smart",
                    "balanced": "anthropic/balanced",
                    "fast": "anthropic/fast",
                }
            },
        )

    def test_omitted_tier_resolves_to_the_main_model(self, tiered_config):
        assert _resolve_subagent_model(tiered_config, None) == "anthropic/main-model"

    @pytest.mark.parametrize(
        "tier,expected",
        [
            ("smart", "anthropic/smart"),
            ("balanced", "anthropic/balanced"),
            ("fast", "anthropic/fast"),
        ],
    )
    def test_named_tier_resolves_via_the_provider_map(
        self, tiered_config, tier, expected
    ):
        assert _resolve_subagent_model(tiered_config, tier) == expected

    def test_unknown_tier_falls_back_to_the_main_model(self, tiered_config):
        assert _resolve_subagent_model(tiered_config, "bogus") == "anthropic/main-model"

    def test_provider_absent_from_the_map_falls_back_to_the_main_model(self, tmp_path):
        config = Config(
            records_dir=tmp_path / "records",
            model="openai/gpt-x",
            subagent_tiers={"anthropic": {"fast": "anthropic/fast"}},
        )
        # OpenAI has no entry, so even a named tier resolves to the main model.
        assert _resolve_subagent_model(config, "fast") == "openai/gpt-x"

    def test_escalation_to_a_stronger_tier_is_permitted(self, tmp_path):
        config = Config(
            records_dir=tmp_path / "records",
            model="anthropic/fast",
            subagent_tiers={
                "anthropic": {"smart": "anthropic/smart", "fast": "anthropic/fast"}
            },
        )
        assert _resolve_subagent_model(config, "smart") == "anthropic/smart"
