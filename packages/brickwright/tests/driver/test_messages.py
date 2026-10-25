"""Tests for building litellm messages and request kwargs."""

import base64
import json

import pytest

from brickwright.config import Config, Effort
from brickwright.driver.messages import (
    assistant_message,
    fresh_round_messages,
    image_user_message,
    request_kwargs,
    tool_call_message,
    user_message,
)
from brickwright.record import Record
from brickwright.tools.registry import ToolOutcome


class TestRequestKwargs:
    def test_off_sends_no_reasoning_or_timeout(self):
        config = Config(model="m", effort=Effort.NONE)
        assert request_kwargs(config) == {"model": "m"}

    @pytest.mark.parametrize("effort", [Effort.LOW, Effort.HIGH, Effort.MAX])
    def test_levels_map_to_reasoning_effort(self, effort):
        kwargs = request_kwargs(Config(model="m", effort=effort))
        assert kwargs == {"model": "m", "reasoning_effort": effort.value}

    def test_timeout_is_forwarded_when_set(self):
        config = Config(model="m", effort=None, request_timeout=30.0)
        assert request_kwargs(config) == {"model": "m", "timeout": 30.0}

    def test_helper_agents_use_their_own_model_and_effort(self):
        config = Config(model="m", critique_model="c", critique_effort=Effort.LOW)
        assert request_kwargs(config, "critique") == {
            "model": "c",
            "reasoning_effort": "low",
        }


class TestUserMessage:
    def test_text_prompt(self, record):
        msg = user_message(record)
        assert msg["role"] == "user"
        assert msg["content"][0] == {"type": "text", "text": "build a wall"}

    @pytest.mark.parametrize(
        "name, mime", [("ref.png", "image/png"), ("ref.jpg", "image/jpeg")]
    )
    def test_image_prompt_is_attached_with_its_mime_type(
        self, config, tmp_path, name, mime
    ):
        data = b"\x89 fake image bytes"
        img = tmp_path / name
        img.write_bytes(data)
        rec = Record.create(config, image=img)
        url = next(
            p["image_url"]["url"]
            for p in user_message(rec)["content"]
            if p["type"] == "image_url"
        )
        # The MIME type is derived from the extension and
        # the real image bytes are embedded.
        assert url.startswith(f"data:{mime};base64,")
        assert base64.b64decode(url.split("base64,", 1)[1]) == data


class TestFreshRoundMessages:
    def test_closes_the_code_fence_on_its_own_line(self, record, config):
        record.write_build("x = 1")  # no trailing newline
        handoff = fresh_round_messages(record, "differences", config)[-1]
        assert "x = 1\n```" in handoff["content"]


class TestAssistantMessage:
    def test_plain_reply_has_no_reasoning_fields(self, message):
        out = assistant_message(message(content="looks good"))
        assert out == {"role": "assistant", "content": "looks good"}

    def test_preserves_thinking_blocks_and_reasoning_content(self, message, tool_call):
        # Anthropic rejects a thinking turn that also calls a tool unless the
        # thinking blocks are echoed back.
        blocks = [{"type": "thinking", "thinking": "plan it", "signature": "sig"}]
        out = assistant_message(
            message(
                content="",
                tool_calls=[tool_call("1", "validate")],
                reasoning_content="plan it",
                thinking_blocks=blocks,
            )
        )
        assert out["thinking_blocks"] == blocks
        assert out["reasoning_content"] == "plan it"
        assert out["tool_calls"][0]["function"]["name"] == "validate"

    def test_tool_calls_echo_the_full_call_structure(self, message, tool_call):
        out = assistant_message(
            message(
                tool_calls=[tool_call("call-1", "edit_build", old_str="a", new_str="b")]
            )
        )
        (tc,) = out["tool_calls"]
        assert tc["id"] == "call-1"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "edit_build"
        assert json.loads(tc["function"]["arguments"]) == {
            "old_str": "a",
            "new_str": "b",
        }


class TestToolCallMessage:
    def test_correlates_id_name_and_content(self, tool_call):
        # The tool result is keyed back to its call by id and tool name.
        msg = tool_call_message(
            tool_call("call-9", "validate"), ToolOutcome("a report")
        )
        assert msg["role"] == "tool"
        assert msg["tool_call_id"] == "call-9"
        assert msg["name"] == "validate"
        assert msg["content"] == "a report"


class TestImageUserMessage:
    def test_image_user_message_carries_a_base64_data_url(self, tmp_path, png_bytes):
        png = tmp_path / "render.png"
        png.write_bytes(png_bytes)
        msg = image_user_message(png)

        assert msg["role"] == "user"
        block = msg["content"][0]
        assert block["type"] == "image_url"
        assert block["image_url"]["url"].startswith("data:image/png;base64,")
