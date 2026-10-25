"""Tests for the viewpoint-matching agent.

The unit tests drive the agent with a scripted fake model and a stubbed renderer.
``TestMatchViewpointWithGPT`` is an integration test that runs the agent for real with
GPT against the finished watermelon example build.py (skipped unless OPENAI_API_KEY and
LDRAW_LIBRARY_PATH are set).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from brickwright.config import Effort
from brickwright.driver.viewpoint import ViewpointResult, match_viewpoint
from brickwright.record import Record
from brickwright.tools.rendering import RenderReport


@pytest.fixture
def fake_render(monkeypatch, png_bytes):
    """Stub ``render_angle``: write a fake image to the viewpoint path and succeed.

    Returns the list of ``(azimuth, elevation)`` it was called with.
    """
    calls: list[tuple[float, float]] = []

    def _render(record, azimuth, elevation, config=None, *, out_path=None):
        dest = out_path or record.viewpoint_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(png_bytes)
        calls.append((azimuth, elevation))
        return RenderReport(ok=True, image_path=dest)

    monkeypatch.setattr("brickwright.driver.viewpoint.render_angle", _render)
    return calls


def _transcript(record: Record) -> list[dict]:
    """The messages the agent's single session wrote, in order."""
    session = min(record.viewpoints_dir.iterdir())
    lines = (session / "transcript.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _carries_image(message: dict) -> bool:
    content = message.get("content")
    return isinstance(content, list) and any(
        block.get("type") == "image_url" for block in content
    )


class TestMatchViewpoint:
    def test_renders_the_chosen_angle_then_finalizes(
        self, image_record, config, fake_render, fake_llm, response, tool_call
    ):
        config = config.model_copy(update={"max_viewpoint_iterations": 5})
        fake = fake_llm(
            response(
                tool_calls=[tool_call("1", "render_view", azimuth=20, elevation=10)]
            ),
            response(tool_calls=[tool_call("2", "finalize")]),
        )
        responses: list = []
        result = match_viewpoint(
            image_record, config, complete=fake, on_response=responses.append
        )

        assert fake_render == [(20.0, 10.0)]  # rendered the angle the model chose
        assert isinstance(result, ViewpointResult)
        assert (result.azimuth, result.elevation) == (20.0, 10.0)
        assert result.done is True
        assert result.iterations == 1
        assert len(responses) == 2  # one per turn, for the tracker

    def test_saves_every_candidate_the_matched_render_and_a_transcript(
        self, image_record, config, fake_render, fake_llm, response, tool_call
    ):
        config = config.model_copy(update={"max_viewpoint_iterations": 5})
        fake = fake_llm(
            response(
                tool_calls=[tool_call("1", "render_view", azimuth=10, elevation=5)]
            ),
            response(
                tool_calls=[tool_call("2", "render_view", azimuth=30, elevation=15)]
            ),
            response(tool_calls=[tool_call("3", "finalize")]),
        )
        match_viewpoint(image_record, config, complete=fake)

        sessions = sorted(image_record.viewpoints_dir.iterdir())
        assert len(sessions) == 1  # one session for this run
        session = sessions[0]
        # (2) every candidate render is kept, not overwritten.
        candidates = sorted(session.glob("candidate_*.png"))
        assert len(candidates) == 2
        # (1) the matched render is kept, and mirrored to the canonical path.
        assert (session / "matched.png").is_file()
        assert image_record.viewpoint_path.is_file()
        # (3) the agent's conversation is persisted (jsonl + readable copy).
        assert (session / "transcript.jsonl").is_file()
        assert (session / "transcript.pretty.json").is_file()

    def test_iterates_until_it_finalizes(
        self, image_record, config, fake_render, fake_llm, response, tool_call
    ):
        config = config.model_copy(update={"max_viewpoint_iterations": 5})
        fake = fake_llm(
            response(
                tool_calls=[tool_call("1", "render_view", azimuth=0, elevation=0)]
            ),
            response(
                tool_calls=[tool_call("2", "render_view", azimuth=30, elevation=15)]
            ),
            response(tool_calls=[tool_call("3", "finalize")]),
        )
        result = match_viewpoint(image_record, config, complete=fake)

        assert fake_render == [(0.0, 0.0), (30.0, 15.0)]
        assert result is not None
        assert (result.azimuth, result.elevation) == (30.0, 15.0)  # the last render
        assert result.iterations == 2
        assert result.done is True

    def test_stops_at_the_iteration_cap_without_finalizing(
        self, image_record, config, fake_render, fake_llm, response, tool_call
    ):
        config = config.model_copy(update={"max_viewpoint_iterations": 2})
        # Never finalizes -- keeps asking to render past the cap.
        fake = fake_llm(
            response(
                tool_calls=[tool_call("1", "render_view", azimuth=0, elevation=0)]
            ),
            response(
                tool_calls=[tool_call("2", "render_view", azimuth=10, elevation=5)]
            ),
            response(
                tool_calls=[tool_call("3", "render_view", azimuth=20, elevation=5)]
            ),
        )
        responses: list = []
        result = match_viewpoint(
            image_record, config, complete=fake, on_response=responses.append
        )

        assert len(fake_render) == 2  # capped at max_viewpoint_iterations turns
        assert len(responses) == 2
        assert result is not None
        assert result.done is False
        assert (result.azimuth, result.elevation) == (10.0, 5.0)  # the last render

    def test_plain_text_reply_ends_the_loop(
        self, image_record, config, fake_render, fake_llm, response, tool_call
    ):
        config = config.model_copy(update={"max_viewpoint_iterations": 5})
        fake = fake_llm(
            response(
                tool_calls=[tool_call("1", "render_view", azimuth=0, elevation=0)]
            ),
            response(content="that viewpoint already matches"),
        )
        result = match_viewpoint(image_record, config, complete=fake)

        assert len(fake_render) == 1  # the plain reply (no finalize) stops the loop
        assert result is not None
        assert result.done is False

    def test_non_numeric_angles_get_a_tool_error_instead_of_crashing(
        self, image_record, config, fake_render, fake_llm, response, tool_call
    ):
        config = config.model_copy(update={"max_viewpoint_iterations": 5})
        fake = fake_llm(
            response(
                tool_calls=[tool_call("1", "render_view", azimuth=None, elevation=30)]
            ),
            response(
                tool_calls=[tool_call("2", "render_view", azimuth=20, elevation=10)]
            ),
            response(tool_calls=[tool_call("3", "finalize")]),
        )

        result = match_viewpoint(image_record, config, complete=fake)

        assert fake_render == [(20.0, 10.0)]  # only the valid call rendered
        assert result is not None
        assert (result.azimuth, result.elevation) == (20.0, 10.0)
        assert result.done is True
        # The bad call was answered in-conversation so the agent could retry.
        retry = fake.calls[1]["messages"]
        assert any(
            m.get("role") == "tool" and "invalid" in str(m.get("content"))
            for m in retry
        )

    def test_batched_tool_calls_are_all_answered_back_to_back(
        self,
        image_record,
        config,
        fake_render,
        fake_llm,
        response,
        tool_call,
        assert_tool_calls_answered,
    ):
        """One turn asking for several renders must answer every call contiguously."""

        config = config.model_copy(update={"max_viewpoint_iterations": 5})
        fake = fake_llm(
            response(
                tool_calls=[
                    tool_call("1", "render_view", azimuth=0, elevation=10),
                    tool_call("2", "render_view", azimuth=180, elevation=10),
                ]
            ),
            response(tool_calls=[tool_call("3", "finalize")]),
        )
        match_viewpoint(image_record, config, complete=fake)

        messages = _transcript(image_record)
        assert_tool_calls_answered(messages)
        assert fake_render == [(0.0, 10.0), (180.0, 10.0)]  # both still rendered
        # Both renders still reach the model, just after the answers rather than between.
        assert sum(_carries_image(m) for m in messages) == 3  # reference + 2 renders

    def test_finalize_batched_with_another_call_still_answers_it(
        self,
        image_record,
        config,
        fake_render,
        fake_llm,
        response,
        tool_call,
        assert_tool_calls_answered,
    ):
        """Finalizing ends the turn, but calls batched after it still need answers."""
        config = config.model_copy(update={"max_viewpoint_iterations": 5})
        fake = fake_llm(
            response(
                tool_calls=[tool_call("1", "render_view", azimuth=20, elevation=10)]
            ),
            response(
                tool_calls=[
                    tool_call("2", "finalize"),
                    tool_call("3", "render_view", azimuth=90, elevation=45),
                ]
            ),
        )
        result = match_viewpoint(image_record, config, complete=fake)

        assert_tool_calls_answered(_transcript(image_record))
        assert fake_render == [(20.0, 10.0)]  # nothing rendered after finalizing
        assert result is not None
        assert (result.azimuth, result.elevation) == (20.0, 10.0)
        assert result.done is True

    def test_requires_a_prompt_image(self, config, valid_build, fake_llm):
        rec = Record.create(config, prompt="no image here")
        rec.write_build(valid_build)
        with pytest.raises(ValueError, match="prompt image"):
            match_viewpoint(rec, config, complete=fake_llm())

    def test_render_failure_yields_no_result(
        self, image_record, config, monkeypatch, fake_llm, response, tool_call
    ):
        # When every render fails, the agent has no matched image and returns None,
        # but the calls are still returned so their cost can be tracked.
        config = config.model_copy(update={"max_viewpoint_iterations": 3})
        monkeypatch.setattr(
            "brickwright.driver.viewpoint.render_angle",
            lambda rec, az, el, cfg=None, *, out_path=None: RenderReport(
                ok=False, error="boom"
            ),
        )
        fake = fake_llm(
            response(
                tool_calls=[tool_call("1", "render_view", azimuth=0, elevation=0)]
            ),
            response(tool_calls=[tool_call("2", "finalize")]),
        )

        responses: list = []

        result = match_viewpoint(
            image_record, config, complete=fake, on_response=responses.append
        )

        assert result is None  # no successful render to match against
        assert len(responses) == 2

    def test_forwards_the_viewpoint_model_and_effort(
        self, image_record, config, fake_render, fake_llm, response, tool_call
    ):
        config = config.model_copy(
            update={
                "model": "builder/model",
                "effort": Effort.LOW,
                "viewpoint_model": "viewpoint/model",
                "viewpoint_effort": Effort.HIGH,
                "max_viewpoint_iterations": 3,
            }
        )
        fake = fake_llm(response(tool_calls=[tool_call("1", "finalize")]))
        match_viewpoint(image_record, config, complete=fake)

        assert fake.calls[0]["model"] == "viewpoint/model"  # overrides builder model
        assert fake.calls[0]["reasoning_effort"] == "high"  # overrides builder effort


# --- Integration: run the real agent with GPT on the watermelon example ----------

_ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
_WATERMELON_IMAGE = _ASSETS_DIR / "watermelon_easy.png"
_WATERMELON_BUILD = _ASSETS_DIR / "watermelon_build.py"
_VIEWPOINT_TEST_MODEL = os.environ.get("VIEWPOINT_TEST_MODEL", "gpt-5.5")
_CAN_RUN_GPT = (
    bool(os.environ.get("OPENAI_API_KEY"))
    and bool(os.environ.get("LDRAW_LIBRARY_PATH"))
    and _WATERMELON_IMAGE.is_file()
    and _WATERMELON_BUILD.is_file()
)


@pytest.mark.real_agent
@pytest.mark.skipif(
    not _CAN_RUN_GPT,
    reason="needs OPENAI_API_KEY, LDRAW_LIBRARY_PATH, and the watermelon example files",
)
class TestMatchViewpointWithGPT:
    def test_matches_the_watermelon_viewpoint(self, config):
        config = config.model_copy(
            update={
                "model": _VIEWPOINT_TEST_MODEL,
                "effort": Effort.HIGH,
                "max_viewpoint_iterations": 6,
            }
        )
        rec = Record.create(config, image=_WATERMELON_IMAGE)
        rec.write_build(_WATERMELON_BUILD.read_text())

        responses: list = []

        result = match_viewpoint(rec, config, on_response=responses.append)

        assert result is not None, "the agent produced no render"
        assert rec.viewpoint_path.is_file()
        assert -180.0 <= result.azimuth <= 180.0
        assert -89.0 <= result.elevation <= 89.0
        assert len(responses) >= 1
