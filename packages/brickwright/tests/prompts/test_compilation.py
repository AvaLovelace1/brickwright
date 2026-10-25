"""Tests for the agent's system prompt."""

import ast
import re
from collections import Counter
from unittest import mock

import pytest
from bricklayer.docs.utils import code_blocks

from brickwright.config import Config
from brickwright.prompts import system_prompt
from brickwright.tools import available_tools

INTERNAL_ONLY_TOOLS = (
    "read_build",
    "write_build",
    "insert_build",
    "edit_build",
    "multi_edit_build",
)


CONFIGS = {
    "no-config": None,
    "default": Config(),
    "subagents": Config(subagents_enabled=True),
    "subagent": Config(is_subagent=True),
    "subagent-with-subagents": Config(subagents_enabled=True, is_subagent=True),
}


def every_prompt_snippet():
    """Each distinct Python snippet the system prompt can contain, over every
    combination of its arguments.

    ``render_available`` is patched both ways so the render guidance is covered
    whether or not an LDraw library is installed. Snippets shared by several
    combinations -- the API reference's, above all -- are collected once.
    """
    snippets = {}
    for config in CONFIGS.values():
        for external in (False, True):
            for render in (True, False):
                with mock.patch(
                    "brickwright.prompts.compilation.render_available",
                    return_value=render,
                ):
                    prompt = system_prompt(config, external=external)
                for block in code_blocks(prompt):
                    if block.language == "python":
                        snippets.setdefault(block.code, block)
    return snippets.values()


def snippet_params(blocks):
    """Parametrization for code blocks, identified by the heading each sits under."""
    params: list = []
    seen: Counter[str] = Counter()
    for block in blocks:
        slug = re.sub(r"\W+", "-", block.heading).strip("-").lower() or "untitled"
        seen[slug] += 1
        params.append(pytest.param(block, id=f"{slug}-{seen[slug]}"))
    return params


def test_describes_the_workflow_and_tools():
    sp = system_prompt()
    assert "create_build()" in sp
    assert "run_tests()" in sp
    for tool in ("read_build", "edit_build", "validate", "finalize"):
        assert tool in sp
    assert ".check(" in sp  # the custom-requirement convention


def test_embeds_the_bricklayer_reference():
    sp = system_prompt()
    assert "BrickLayer documentation" in sp  # the live docs are included
    assert "LegoBuild.connect" in sp


def test_external_prompt_keeps_the_shared_authoring_guide():
    sp = system_prompt(external=True)
    assert "create_build()" in sp
    assert "TestContext" in sp
    assert ".check(" in sp
    assert "BrickLayer documentation" in sp
    assert "LegoBuild.connect" in sp


def test_external_prompt_omits_internal_only_tools():
    sp = system_prompt(external=True)
    for tool in INTERNAL_ONLY_TOOLS:
        assert tool not in sp


def test_internal_prompt_includes_the_function_call_tools():
    sp = system_prompt(external=False)
    for tool in INTERNAL_ONLY_TOOLS:
        assert tool in sp


def test_main_prompt_omits_subagent_guidance_when_disabled():
    text = system_prompt(config=Config(subagents_enabled=False))
    assert "dispatch_subagents" not in text


def test_main_prompt_includes_subagent_guidance_when_enabled():
    text = system_prompt(config=Config(subagents_enabled=True))
    assert "dispatch_subagents" in text
    assert "tier" in text.lower()


def test_worker_prompt_tells_the_subagent_to_return_text_and_not_finalize():
    text = system_prompt(config=Config(subagents_enabled=True, is_subagent=True))
    assert "reply with a plain text message" in text.lower()
    assert "dispatch_subagents" not in text
    assert "finalize" not in text  # workers are not told about a finalize step


class TestPromptSnippets:
    @pytest.mark.parametrize("block", snippet_params(every_prompt_snippet()))
    def test_every_snippet_runs(self, block, tmp_path, monkeypatch):
        """A complete snippet runs (and its checks pass); a fragment must parse."""
        ast.parse(block.code)  # even a fragment must be syntactically valid
        if not block.is_complete:
            pytest.skip("fragment: does not open with an import, so it needs context")
        monkeypatch.chdir(tmp_path)
        source = tmp_path / "snippet.py"
        source.write_text(block.code)
        namespace: dict = {"__name__": "__snippet__"}
        exec(compile(block.code, str(source), "exec"), namespace)
        # A `build.py` example only defines the scaffold, so run it: an example
        # whose own checks fail is teaching the agent to build an invalid model.
        if run_tests := namespace.get("run_tests"):
            assert all(check.passed for check in run_tests())

    def test_every_fence_uses_a_known_language(self):
        """A typo'd info string would drop a snippet from the suite unnoticed."""
        languages = {b.language for b in code_blocks(system_prompt())}
        assert languages <= {"", "python", "text"}


def test_tool_descriptions_are_sourced_from_the_schemas():
    sp = system_prompt(external=False)
    for tool in available_tools():
        fn = tool["function"]
        params = ", ".join(fn["parameters"]["properties"])
        assert f"`{fn['name']}({params})`" in sp
        assert fn["description"] in sp
    assert "### `write_build(" in sp


def test_tool_parameters_show_type_and_description():
    sp = system_prompt(external=False)
    for tool in available_tools():
        props = tool["function"]["parameters"]["properties"]
        for pname, pschema in props.items():
            value_schema = pschema.get("anyOf", [pschema])[0]
            assert f"`{pname}` ({value_schema['type']}" in sp
            if "description" in pschema:
                assert pschema["description"] in sp
            if "description" in value_schema:
                assert value_schema["description"] in sp


def test_nullable_tool_parameters_keep_their_types_and_descriptions(monkeypatch):
    monkeypatch.setattr("brickwright.tools.registry.render_available", lambda: True)
    sp = system_prompt()
    assert "`view_range` (array of integer | null) (optional)" in sp
    assert "`azimuth` (number | null) (optional): horizontal camera angle" in sp
    assert "`elevation` (number | null) (optional): vertical camera angle" in sp


def test_object_valued_parameters_show_their_fields():
    sp = system_prompt(config=Config(subagents_enabled=True))
    # dispatch_subagents.tasks is an array of objects; its fields must appear.
    tool = next(
        t
        for t in available_tools(Config(subagents_enabled=True))
        if t["function"]["name"] == "dispatch_subagents"
    )
    item = tool["function"]["parameters"]["properties"]["tasks"]["items"]
    for field, schema in item["properties"].items():
        value_schema = schema.get("anyOf", [schema])[0]
        assert f"`{field}` ({value_schema['type']}" in sp
        assert schema["description"] in sp
