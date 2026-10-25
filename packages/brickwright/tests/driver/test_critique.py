"""Tests for visual critique and response-format fallback."""

import json

import pytest

from brickwright.driver.critique import CritiqueResult, _complete, critique


def _format_name(call: dict) -> str:
    """Name the ``response_format`` a recorded call asked for."""
    response_format = call.get("response_format")
    if response_format is CritiqueResult:
        return "schema"
    if response_format is None:
        return "none"
    return response_format["type"]


class _Refusing:
    """A fake completion seam that 400s for each format named in ``refused``, else
    succeeds. Records every call's kwargs on ``.calls``."""

    def __init__(self, response, *refused, message="refused this response_format"):
        self.response = response
        self.refused = refused
        self.message = message
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        from litellm import BadRequestError

        self.calls.append(kwargs)
        if _format_name(kwargs) in self.refused:
            raise BadRequestError(
                message=self.message, model=kwargs["model"], llm_provider="fake"
            )
        return self.response(content=_verdict("rind is off", False))


_refusing = _Refusing


@pytest.fixture(autouse=True)
def _in_process_pipeline(in_process, fake_render_pipeline):
    """Run validate/finalize/render in-process with the heavy render steps stubbed."""


def _verdict(differences, done):
    """Serialize a critic reply the way the model is asked to return it."""
    return json.dumps({"differences_description": differences, "done": done})


class TestCritiqueViewpoint:
    def _viewpoint(self, config):
        return config.model_copy(update={"max_viewpoint_iterations": 3})

    def test_matches_a_viewpoint_then_compares_the_single_render(
        self, image_record, config, patch_critic, fake_llm, response, tool_call
    ):
        # The viewpoint agent renders + finalizes, then the critic compares the single
        # matched render against the reference in one call.
        fake = patch_critic(
            fake_llm(
                response(
                    tool_calls=[tool_call("1", "render_view", azimuth=20, elevation=10)]
                ),
                response(tool_calls=[tool_call("2", "finalize")]),
                response(content=_verdict("rind is off", False)),
            )
        )

        responses: list = []
        result = critique(
            image_record, self._viewpoint(config), on_response=responses.append
        )

        assert isinstance(result, CritiqueResult)
        assert result.differences_description == "rind is off"
        assert result.done is False
        # The matched render was written for the critic to look at.
        assert image_record.viewpoint_path.exists()
        # The comparison is the last call: it sees exactly two images -- the reference
        # and the single matched render, not the four views.
        compare = fake.calls[-1]["messages"][-1]["content"]
        images = [p for p in compare if p["type"] == "image_url"]
        assert len(images) == 2
        assert "tools" not in fake.calls[-1]  # the comparison call is not tool-using
        # Every call (viewpoint agent turns + the comparison) is observed for tracking.
        assert len(responses) == 3

    def test_comparison_call_requests_structured_output(
        self, image_record, config, patch_critic, fake_llm, response, tool_call
    ):
        fake = patch_critic(
            fake_llm(
                response(
                    tool_calls=[tool_call("1", "render_view", azimuth=0, elevation=0)]
                ),
                response(tool_calls=[tool_call("2", "finalize")]),
                response(content=_verdict("roof is off", False)),
            )
        )

        result = critique(image_record, self._viewpoint(config))

        assert result is not None
        assert result.differences_description == "roof is off"
        assert fake.calls[-1]["response_format"] is CritiqueResult

    def test_returns_none_when_the_viewpoint_agent_never_renders(
        self, image_record, config, patch_critic, fake_llm, response
    ):
        # The agent finalizes immediately without rendering -> no image to compare.
        patch_critic(fake_llm(response(content="I am done without looking")))

        result = critique(image_record, self._viewpoint(config))

        assert result is None


class TestResponseFormatFallback:
    """``_complete``'s response_format fallback ladder."""

    @pytest.mark.parametrize(
        "refused, settled_on",
        [
            pytest.param(("schema",), "json_object", id="schema-refused"),
            pytest.param(("schema", "json_object"), "none", id="both-refused"),
        ],
    )
    def test_steps_down_to_a_response_format_the_provider_accepts(
        self, config, response, refused, settled_on
    ):
        """A provider refusing a response format gets a weaker one, not a dead run."""
        fake = _refusing(response, *refused)

        result = _complete(fake, config, messages=[])

        assert result.choices[0].message.content == _verdict("rind is off", False)
        # Settled on the strongest format the provider accepts, having tried the
        # stronger ones first in order.
        assert [_format_name(c) for c in fake.calls] == [*refused, settled_on]

    def test_a_400_unrelated_to_the_format_is_not_retried(self, config, response):
        """Only a refusal naming response_format means try a weaker one."""
        fake = _refusing(response, "schema", message="context too long")

        with pytest.raises(Exception, match="context too long"):
            _complete(fake, config, messages=[])

        assert [_format_name(c) for c in fake.calls] == ["schema"]

    def test_a_refusal_that_outlasts_every_format_still_surfaces(
        self, config, response
    ):
        """A 400 that isn't about the format is raised, not swallowed."""
        fake = _refusing(response, "schema", "json_object", "none")

        with pytest.raises(Exception, match="refused"):
            _complete(fake, config, messages=[])
