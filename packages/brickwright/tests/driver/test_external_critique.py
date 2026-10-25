"""Tests for the external-agent critique playbook builder."""

import pytest

from brickwright.driver.critique import VIEWPOINT_COMPARE_PROMPT
from brickwright.driver.external_critique import (
    external_critique_instructions,
    external_viewpoint_prompt,
)
from brickwright.driver.viewpoint import VIEWPOINT_TASK
from brickwright.record import Record


class TestExternalViewpointPrompt:
    def test_shares_the_driver_task_body(self):
        # The mechanic-neutral body is the same one the driver's viewpoint agent uses.
        prompt = external_viewpoint_prompt("rec123", "/tmp/out/viewpoint.png")
        assert VIEWPOINT_TASK in prompt

    def test_uses_the_cli_render_seam_not_the_tool(self):
        prompt = external_viewpoint_prompt("rec123", "/tmp/out/viewpoint.png")
        # It renders through the external CLI command, not the API's render_view tool.
        assert "brickwright external render-angle rec123" in prompt
        assert "render_view" not in prompt
        # It points at the canonical viewpoint path the critic later reads.
        assert "/tmp/out/viewpoint.png" in prompt


class TestExternalCritiqueInstructions:
    def test_embeds_both_subagent_prompts_verbatim(self, image_record):
        out = external_critique_instructions(image_record)
        # The critic prompt is reused verbatim from the driver path.
        assert VIEWPOINT_COMPARE_PROMPT in out
        # The angle-finder prompt is the CLI variant sharing the driver's task body.
        assert VIEWPOINT_TASK in out
        assert (
            external_viewpoint_prompt(
                image_record.id, str(image_record.viewpoint_path.absolute())
            )
            in out
        )

    def test_includes_the_record_and_concrete_paths(self, image_record):
        out = external_critique_instructions(image_record)
        reference = image_record.prompt_image_path
        assert reference is not None
        assert image_record.id in out
        assert str(reference.absolute()) in out
        assert str(image_record.build_path.absolute()) in out
        assert str(image_record.viewpoint_path.absolute()) in out

    def test_tells_the_agent_to_use_fresh_subagents(self, image_record):
        out = external_critique_instructions(image_record)
        assert "fresh subagent" in out
        # Two independent subagents: angle-matching, then critique.
        assert out.count("Dispatch a") >= 2

    def test_describes_the_verdict_json_and_revise_loop(self, image_record):
        out = external_critique_instructions(image_record)
        assert '"differences_description"' in out
        assert '"done"' in out
        assert "external validate" in out  # the revise step re-validates

    def test_rounds_is_reflected_in_the_playbook(self, image_record):
        out = external_critique_instructions(image_record, rounds=5)
        assert "up to 5 time(s)" in out

    def test_requires_a_prompt_image(self, config):
        rec = Record.create(config, prompt="text only, no image")
        with pytest.raises(ValueError, match="prompt image"):
            external_critique_instructions(rec)
