"""Tests for the agent tool registry, schemas, and dispatch."""

import json

import pytest

from brickwright.config import Config
from brickwright.record import Usage
from brickwright.tools import registry
from brickwright.tools.exploration import SnippetResult
from brickwright.tools.finalization import FinalizationReport
from brickwright.tools.registry import (
    _ALL_TOOLS,
    available_tools,
    execute_tool,
)
from brickwright.tools.rendering import RenderReport
from brickwright.tools.subagents import SubagentResult, SubagentTask
from brickwright.tools.validation import ValidationReport


@pytest.fixture
def stub_tool(monkeypatch):
    """Factory: replace a registry-level tool function with a stub returning
    ``result``; returns a list recording each call's positional args."""

    def _stub(name, result):
        calls = []

        def fake(*args, **kwargs):
            calls.append(args + tuple(kwargs.values()))
            return result

        monkeypatch.setattr(registry, name, fake)
        return calls

    return _stub


@pytest.fixture
def stub_dispatch(monkeypatch):
    """Factory: have dispatch_subagents build its results with ``fake(tasks)``;
    returns a list recording every task it receives."""

    def _stub(fake):
        received = []

        def _dispatch(record, tasks, cfg):
            received.extend(tasks)
            return fake(tasks)

        monkeypatch.setattr(registry, "dispatch_subagents", _dispatch)
        return received

    return _stub


def _schema(name):
    return next(tool for tool in _ALL_TOOLS if tool["function"]["name"] == name)


class TestSchemas:
    def test_each_tool_is_well_formed(self):
        for tool in _ALL_TOOLS:
            assert tool["type"] == "function"
            fn = tool["function"]
            assert fn["name"] and fn["description"]
            assert fn["parameters"]["type"] == "object"

    def test_read_build_takes_an_optional_view_range(self):
        read = _schema("read_build")
        params = read["function"]["parameters"]
        assert params["required"] == []
        assert params["properties"]["view_range"]["anyOf"][0]["type"] == "array"

    def test_edit_requires_old_str_and_new_str(self):
        params = _schema("edit_build")["function"]["parameters"]
        assert set(params["required"]) == {"old_str", "new_str"}
        assert params["properties"]["replace_all"]["type"] == "boolean"

    def test_multi_edit_requires_a_batch_of_edits(self):
        multi = _schema("multi_edit_build")
        params = multi["function"]["parameters"]
        assert params["required"] == ["edits"]
        items = params["properties"]["edits"]["items"]
        assert set(items["required"]) == {"old_str", "new_str"}

    def test_insert_requires_line_and_text(self):
        ins = _schema("insert_build")
        assert set(ins["function"]["parameters"]["required"]) == {
            "insert_line",
            "insert_text",
        }

    def test_render_takes_an_optional_camera_angle(self):
        params = _schema("render")["function"]["parameters"]
        assert params["required"] == []
        assert params["properties"]["azimuth"]["anyOf"][0]["type"] == "number"
        assert params["properties"]["elevation"]["anyOf"][0]["type"] == "number"

    def test_write_requires_content(self):
        write = _schema("write_build")
        assert write["function"]["parameters"]["required"] == ["content"]


class TestAvailableTools:
    def test_includes_render_when_a_library_is_present(self, monkeypatch):
        monkeypatch.setattr(registry, "render_available", lambda: True)
        names = {t["function"]["name"] for t in available_tools()}
        assert "render" in names

    def test_excludes_render_when_no_library_is_present(self, monkeypatch):
        monkeypatch.setattr(registry, "render_available", lambda: False)
        names = {t["function"]["name"] for t in available_tools()}
        assert "render" not in names

    def test_no_config_matches_the_base_toolset_without_dispatch(self):
        names = {t["function"]["name"] for t in available_tools()}
        assert "dispatch_subagents" not in names
        assert "finalize" in names

    def test_dispatch_appears_only_when_subagents_are_enabled(self):
        names_disabled = {
            t["function"]["name"]
            for t in available_tools(Config(subagents_enabled=False))
        }
        assert "dispatch_subagents" not in names_disabled

        names_enabled = {
            t["function"]["name"]
            for t in available_tools(Config(subagents_enabled=True))
        }
        assert "dispatch_subagents" in names_enabled

    def test_a_worker_loses_finalize_and_dispatch(self):
        names = {
            t["function"]["name"]
            for t in available_tools(Config(subagents_enabled=True, is_subagent=True))
        }
        assert "finalize" not in names
        assert "dispatch_subagents" not in names


class TestMalformedArguments:
    @pytest.mark.parametrize(
        "name,arguments,field",
        [
            ("insert_build", {"insert_line": True, "insert_text": "x"}, "insert_line"),
            ("read_build", {"view_range": [True, 2]}, "view_range"),
            ("render", {"azimuth": float("nan"), "elevation": 0}, "azimuth"),
        ],
    )
    def test_invalid_arguments_never_reach_a_handler(
        self, record, config, monkeypatch, name, arguments, field
    ):
        for operation in ("view", "insert_build", "render_angle"):
            monkeypatch.setattr(
                registry, operation, lambda *a, **kw: pytest.fail("ran")
            )
        out = execute_tool(record, config, name, arguments)
        assert out.ok is False
        assert field in out.content

    @pytest.mark.parametrize("arguments", [None, [], "content"])
    def test_non_object_arguments_are_reported(self, record, config, arguments):
        out = execute_tool(record, config, "read_build", arguments)
        assert out.ok is False
        assert "arguments must be a JSON object" in out.content


class TestUnknownTool:
    def test_unknown_tool_is_reported(self, record, config):
        out = execute_tool(record, config, "frobnicate", {})
        assert out.ok is False
        assert "unknown" in out.content.lower()


class TestReadBuild:
    def test_read_build_returns_numbered_source(self, record, config):
        out = execute_tool(record, config, "read_build", {})
        assert out.ok is True
        # right-aligned width depends on the file length, so lstrip first
        assert out.content.split("\n")[0].lstrip().startswith("1: ")
        assert "def create_build(" in out.content
        assert out.done is False

    def test_read_build_slices_with_view_range(self, record, config):
        record.write_build("l1\nl2\nl3\nl4\n")
        out = execute_tool(record, config, "read_build", {"view_range": [2, 3]})
        assert out.ok is True
        assert out.content == "2: l2\n3: l3"

    def test_read_build_reports_a_bad_range_without_raising(self, record, config):
        out = execute_tool(record, config, "read_build", {"view_range": [1, 999]})
        assert out.ok is False
        assert "view_range" in out.content


class TestWriteBuild:
    def test_write_build_overwrites_the_whole_file(self, record, config):
        source = "def create_build():\n    return None  # rewritten\n"
        out = execute_tool(record, config, "write_build", {"content": source})
        assert out.ok is True
        assert record.read_build() == source
        assert "error" not in out.content.lower()
        assert out.done is False

    def test_write_build_reports_missing_content_without_raising(self, record, config):
        before = record.read_build()
        out = execute_tool(record, config, "write_build", {})
        assert out.ok is False
        assert "missing" in out.content.lower()
        assert record.read_build() == before  # unchanged

    def test_write_build_non_string_content_returns_not_ok_without_raising(
        self, record, config
    ):
        before = record.read_build()
        out = execute_tool(record, config, "write_build", {"content": 123})
        assert out.ok is False
        assert "string" in out.content.lower()
        assert record.read_build() == before  # unchanged


class TestInsertBuild:
    def test_insert_build_inserts_and_echoes_the_region(self, record, config):
        record.write_build("l1\nl2\n")
        out = execute_tool(
            record,
            config,
            "insert_build",
            {"insert_line": 1, "insert_text": "NEW"},
        )
        assert out.ok is True
        assert record.read_build() == "l1\nNEW\nl2\n"
        assert "2: NEW" in out.content

    def test_insert_build_reports_errors_without_raising(self, record, config):
        before = record.read_build()
        out = execute_tool(
            record, config, "insert_build", {"insert_line": 999, "insert_text": "x"}
        )
        assert out.ok is False
        assert record.read_build() == before

    def test_insert_build_reports_missing_argument(self, record, config):
        out = execute_tool(record, config, "insert_build", {"insert_line": 1})
        assert "missing" in out.content.lower()
        assert out.ok is False

    def test_insert_build_non_string_insert_text_returns_not_ok_without_raising(
        self, record, config
    ):
        before = record.read_build()
        out = execute_tool(
            record, config, "insert_build", {"insert_line": 1, "insert_text": 5}
        )
        assert out.ok is False
        assert record.read_build() == before


class TestEditBuild:
    def test_edit_build_applies_and_echoes_the_region(self, record, config):
        out = execute_tool(
            record, config, "edit_build", {"old_str": "2, 2", "new_str": "4, 2"}
        )
        assert "brick(4, 2" in record.read_build()
        assert out.ok is True
        assert "4, 2" in out.content  # the snippet shows the edited region

    def test_edit_build_forwards_replace_all(self, record, config):
        record.write_build("a\na\n")
        out = execute_tool(
            record,
            config,
            "edit_build",
            {"old_str": "a", "new_str": "b", "replace_all": True},
        )
        assert out.ok is True
        assert record.read_build() == "b\nb\n"

    def test_edit_build_reports_errors_without_raising(self, record, config):
        before = record.read_build()
        out = execute_tool(
            record, config, "edit_build", {"old_str": "NOT THERE", "new_str": "x"}
        )
        assert out.ok is False
        assert "not found" in out.content.lower()
        assert record.read_build() == before  # unchanged

    def test_edit_build_reports_missing_argument(self, record, config):
        before = record.read_build()
        out = execute_tool(record, config, "edit_build", {"old_str": "x"})
        assert out.ok is False
        assert "missing" in out.content.lower()
        assert record.read_build() == before  # unchanged

    def test_edit_build_rejects_a_non_bool_replace_all(self, record, config):
        record.write_build("a\na\n")
        out = execute_tool(
            record,
            config,
            "edit_build",
            {"old_str": "a", "new_str": "b", "replace_all": "false"},
        )
        assert out.ok is False
        assert "replace_all" in out.content
        assert record.read_build() == "a\na\n"

    def test_edit_build_non_string_args_return_not_ok_without_raising(
        self, record, config
    ):
        before = record.read_build()
        out = execute_tool(record, config, "edit_build", {"old_str": 5, "new_str": "x"})
        assert out.ok is False
        assert record.read_build() == before


class TestMultiEditBuild:
    def test_multi_edit_build_applies_a_batch(self, record, config):
        record.write_build("a\nb\n")
        out = execute_tool(
            record,
            config,
            "multi_edit_build",
            {
                "edits": [
                    {"old_str": "a", "new_str": "x"},
                    {"old_str": "b", "new_str": "y"},
                ]
            },
        )
        assert out.ok is True
        assert "2 edits" in out.content
        assert record.read_build() == "x\ny\n"

    def test_multi_edit_build_is_atomic_and_names_the_failing_edit(
        self, record, config
    ):
        record.write_build("a\nb\n")
        out = execute_tool(
            record,
            config,
            "multi_edit_build",
            {
                "edits": [
                    {"old_str": "a", "new_str": "x"},
                    {"old_str": "zzz", "new_str": "y"},
                ]
            },
        )
        assert out.ok is False
        assert "edit 2 of 2" in out.content
        assert record.read_build() == "a\nb\n"  # nothing was written

    def test_multi_edit_build_reports_missing_argument(self, record, config):
        out = execute_tool(record, config, "multi_edit_build", {})
        assert "missing" in out.content.lower()
        assert out.ok is False

    def test_multi_edit_build_non_string_batch_item_returns_not_ok_without_raising(
        self, record, config
    ):
        before = record.read_build()
        out = execute_tool(
            record,
            config,
            "multi_edit_build",
            {"edits": [{"old_str": 5, "new_str": "x"}]},
        )
        assert out.ok is False
        assert "edits.0.old_str" in out.content
        assert record.read_build() == before


class TestValidate:
    def test_validate_dispatch_forwards_the_record_and_wraps_the_report(
        self, record, config, stub_tool
    ):
        report = ValidationReport(ok=True)
        calls = stub_tool("validate", report)
        out = execute_tool(record, config, "validate", {})
        assert out.ok is True
        assert calls == [(record, config)]  # forwarded through
        assert out.report is report
        assert out.done is False
        assert json.loads(out.content)["ok"] is True  # content is the report as JSON


class TestExplore:
    def test_explore_dispatch_returns_the_snippet_output(
        self, record, config, stub_tool
    ):
        calls = stub_tool("explore", SnippetResult(ok=True, output="Brick parts"))
        code = "print(bricklayer.search_parts('brick', limit=5))"
        out = execute_tool(record, config, "explore", {"code": code})
        assert calls == [(record, code, config)]
        assert out.ok is True
        assert out.content == "Brick parts"
        assert out.done is False

    def test_explore_dispatch_carries_the_snippet_ok_flag(
        self, record, config, stub_tool
    ):
        stub_tool("explore", SnippetResult(ok=False, output="explore error:\nboom"))
        out = execute_tool(record, config, "explore", {"code": "boom"})
        assert out.ok is False
        assert out.content == "explore error:\nboom"

    def test_explore_rejects_non_string_code(self, record, config, stub_tool):
        calls = stub_tool("explore", SnippetResult(ok=True, output="ran"))
        out = execute_tool(record, config, "explore", {"code": 123})
        assert out.ok is False
        assert "code" in out.content and "string_type" in out.content
        assert calls == []

    def test_explore_reports_missing_code_without_raising(self, record, config):
        out = execute_tool(record, config, "explore", {})
        assert out.ok is False
        assert "missing" in out.content.lower()


class TestRender:
    def test_render_dispatch_returns_the_rendered_image_on_success(
        self, record, config, stub_tool, tmp_path
    ):
        stub_tool("render", RenderReport(ok=True, image_path=tmp_path / "render.png"))
        out = execute_tool(record, config, "render", {})
        assert out.image == tmp_path / "render.png"
        assert out.done is False
        assert "error" not in out.content.lower()

    def test_render_dispatch_surfaces_a_failure_as_text_without_a_render(
        self, record, config, stub_tool
    ):
        stub_tool("render", RenderReport(ok=False, error="boom"))
        out = execute_tool(record, config, "render", {})
        assert out.image is None
        assert out.ok is False
        assert "render failed" in out.content.lower()
        assert "boom" in out.content

    def test_render_dispatch_renders_the_requested_camera_angle(
        self, record, config, stub_tool, tmp_path
    ):
        calls = stub_tool(
            "render_angle", RenderReport(ok=True, image_path=tmp_path / "angle.png")
        )
        out = execute_tool(
            record, config, "render", {"azimuth": 30, "elevation": -15.5}
        )
        assert calls == [(record, 30.0, -15.5, config, record.angle_render_path)]
        assert out.image == tmp_path / "angle.png"
        assert "30" in out.content and "-15.5" in out.content

    def test_a_posed_render_leaves_the_viewpoint_render_alone(self, record):
        assert record.angle_render_path != record.viewpoint_path

    @pytest.mark.parametrize(
        "arguments",
        [
            {"azimuth": 30},
            {"elevation": 10},
            {"azimuth": "left", "elevation": 0},
            {"azimuth": 0, "elevation": 180},
        ],
    )
    def test_render_dispatch_rejects_an_incomplete_or_malformed_angle(
        self, record, config, stub_tool, arguments
    ):
        calls = stub_tool("render_angle", RenderReport(ok=True))
        out = execute_tool(record, config, "render", arguments)
        assert out.ok is False
        assert "render failed" in out.content.lower()
        assert calls == []


class TestFinalize:
    def test_finalize_dispatch_forwards_the_record_and_signals_completion(
        self, record, config, stub_tool
    ):
        calls = stub_tool("finalize", FinalizationReport(ok=True))
        out = execute_tool(record, config, "finalize", {})
        assert out.ok is True
        assert calls == [(record, config)]  # forwarded through
        assert out.done is True
        assert out.content.startswith("ok")

    def test_finalize_dispatch_allows_recovery_after_a_render_failure(
        self, record, config, stub_tool
    ):
        stub_tool("finalize", FinalizationReport(ok=False, error="boom"))
        out = execute_tool(record, config, "finalize", {})
        assert out.ok is False
        assert out.done is False
        assert "failed" in out.content.lower()
        assert "boom" in out.content  # the underlying error is surfaced


class TestDispatchSubagents:
    def test_dispatch_subagents_aggregates_results_and_usage(
        self, record, config, stub_dispatch
    ):
        stub_dispatch(
            lambda tasks: [
                SubagentResult(
                    ok=True,
                    text=f"did {t.prompt}",
                    usage=Usage(
                        prompt_tokens=10,
                        completion_tokens=2,
                        total_tokens=12,
                        cost_usd=0.01,
                    ),
                    record_id=f"rec-{i}",
                )
                for i, t in enumerate(tasks)
            ]
        )

        out = execute_tool(
            record,
            config,
            "dispatch_subagents",
            {"tasks": [{"prompt": "left", "tier": "fast"}, {"prompt": "right"}]},
        )

        assert out.ok is True
        payload = json.loads(out.content)
        assert [r["result"] for r in payload["results"]] == ["did left", "did right"]
        assert out.usage is not None
        assert out.usage.total_tokens == 24  # 12 + 12
        assert out.usage.cost_usd == 0.02

    def test_dispatch_subagents_rejects_empty_tasks(self, record, config):
        outcome = execute_tool(record, config, "dispatch_subagents", {"tasks": []})
        assert outcome.ok is False

    def test_dispatch_subagents_rejects_blank_prompt_without_dispatching(
        self, record, config, stub_dispatch
    ):
        received = stub_dispatch(lambda tasks: [])
        out = execute_tool(
            record, config, "dispatch_subagents", {"tasks": [{"prompt": "  "}]}
        )
        assert out.ok is False
        assert not received  # dispatch was never called

    def test_dispatch_subagents_rejects_malformed_tasks_by_index(
        self, record, config, stub_dispatch
    ):
        received = stub_dispatch(lambda tasks: [])
        out = execute_tool(
            record,
            config,
            "dispatch_subagents",
            {"tasks": [{"prompt": "valid"}, 42, {"prompt": ""}, {"tier": "fast"}]},
        )
        assert out.ok is False
        assert all(f"tasks.{index}" in out.content for index in (1, 2, 3))
        assert not received  # dispatch was never called

    def test_dispatch_subagents_drops_a_non_string_tier_without_raising(
        self, record, config, stub_dispatch
    ):
        received = stub_dispatch(
            lambda tasks: [
                SubagentResult(ok=True, text="done", usage=Usage(), record_id="r")
                for _ in tasks
            ]
        )
        out = execute_tool(
            record,
            config,
            "dispatch_subagents",
            {"tasks": [{"prompt": "valid", "tier": 3}]},
        )
        assert out.ok is True
        assert received == [SubagentTask(prompt="valid")]
