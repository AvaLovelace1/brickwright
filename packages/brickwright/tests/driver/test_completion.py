"""Tests for the litellm completion seam."""

import sys
from copy import deepcopy
from types import SimpleNamespace

import pytest

from brickwright.driver.completion import litellm_complete


@pytest.fixture
def fake_litellm(monkeypatch):
    """Stand in for litellm, recording the kwargs each completion call receives."""
    calls: list[dict] = []

    def completion(**kwargs):
        calls.append(kwargs)
        return fake.response

    fake = SimpleNamespace(
        modify_params=False,
        completion=completion,
        calls=calls,
        response=SimpleNamespace(choices=[]),
    )
    monkeypatch.setitem(sys.modules, "litellm", fake)
    return fake


def test_enables_tool_call_sanitization(fake_litellm):
    litellm_complete()

    assert fake_litellm.modify_params is True


@pytest.mark.parametrize("model", ["openai/gpt-5.5", "azure/gpt-6-astra", None])
def test_passes_other_models_through_unchanged(fake_litellm, model):
    kwargs = {"model": model, "messages": [], "reasoning_effort": "high"}

    assert litellm_complete()(**kwargs) is fake_litellm.response

    assert fake_litellm.calls == [kwargs]


@pytest.mark.parametrize("model", ["anthropic/claude-haiku-5-5", "claude-sonnet-5"])
def test_claude_caches_static_prefix_and_latest_message(fake_litellm, model):
    messages = [
        {"role": "system", "content": "instructions"},
        {"role": "user", "content": "build a tower"},
        {"role": "tool", "tool_call_id": "a", "content": "validation results"},
    ]
    points = [{"location": "message", "role": "system"}]
    fake_litellm.response = SimpleNamespace(choices=[object(), object()])

    result = litellm_complete()(
        model=model, messages=messages, cache_control_injection_points=points
    )

    assert result is fake_litellm.response
    assert fake_litellm.calls[0]["cache_control_injection_points"] == [
        {"location": "message", "role": "system"},
        {"location": "message", "index": -1},
    ]
    assert points == [{"location": "message", "role": "system"}]
    assert all("cache_control" not in message for message in messages)


def test_claude_critique_also_gets_conversation_caching(fake_litellm):
    litellm_complete()(
        model="anthropic/claude-haiku-5-5",
        messages=[{"role": "user", "content": "compare these images"}],
    )
    assert fake_litellm.calls[0]["cache_control_injection_points"] == [
        {"location": "message", "role": "system"},
        {"location": "message", "index": -1},
    ]


@pytest.mark.parametrize("rendered_image", [False, True])
def test_claude_breakpoints_reach_provider_payload(monkeypatch, rendered_image):
    import litellm
    from litellm.integrations.anthropic_cache_control_hook import (
        AnthropicCacheControlHook,
    )
    from litellm.llms.anthropic.chat.transformation import AnthropicConfig

    messages = [
        {"role": "system", "content": "instructions"},
        {"role": "user", "content": "build a tower"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "a",
                    "type": "function",
                    "function": {"name": "validate", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "a", "content": "validation results"},
    ]
    if rendered_image:
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,aGVsbG8="},
                    }
                ],
            }
        )
    original = deepcopy(messages)
    payloads = []

    def completion(**kwargs):
        model, marked, params = AnthropicCacheControlHook().get_chat_completion_prompt(
            model=kwargs["model"],
            messages=kwargs["messages"],
            non_default_params={
                "cache_control_injection_points": kwargs[
                    "cache_control_injection_points"
                ]
            },
            prompt_id=None,
            prompt_variables=None,
            dynamic_callback_params={},
        )
        payloads.append(
            AnthropicConfig().transform_request(
                model=model.removeprefix("anthropic/"),
                messages=marked,
                optional_params=params,
                litellm_params={},
                headers={},
            )
        )
        return SimpleNamespace(choices=[])

    monkeypatch.setattr(litellm, "completion", completion)
    complete = litellm_complete()
    complete(model="anthropic/claude-haiku-5-5", messages=messages)
    assert messages == original
    payload = payloads[0]
    assert payload["system"][-1]["cache_control"] == {"type": "ephemeral"}
    last = payload["messages"][-1]["content"][-1]
    assert last["type"] == ("image" if rendered_image else "tool_result")
    assert last["cache_control"] == {"type": "ephemeral"}
    messages.extend(
        [
            {"role": "assistant", "content": "I will revise the build."},
            {"role": "user", "content": "Please continue."},
        ]
    )
    complete(model="anthropic/claude-haiku-5-5", messages=messages)
    payload = payloads[1]
    assert payload["messages"][-1]["content"][-1]["cache_control"] == {
        "type": "ephemeral"
    }
    marked_blocks = [
        block
        for message in payload["messages"]
        for block in message["content"]
        if "cache_control" in block
    ]
    assert len(marked_blocks) == 1
    assert messages[: len(original)] == original


@pytest.mark.parametrize("model", ["openai/gpt-6-astra", "gpt-6-astra"])
def test_routes_openai_gpt_6_through_the_responses_api(fake_litellm, model):
    litellm_complete()(model=model, messages=[], reasoning_effort="high")

    assert fake_litellm.calls == [
        {
            "model": "openai/responses/gpt-6-astra",
            "messages": [],
            "reasoning_effort": "high",
            "allowed_openai_params": ["reasoning_effort"],
        }
    ]


def test_gpt_6_without_effort_allows_no_extra_params(fake_litellm):
    litellm_complete()(model="openai/gpt-6-sol", messages=[])

    assert fake_litellm.calls == [
        {"model": "openai/responses/gpt-6-sol", "messages": []}
    ]


def test_gpt_6_drops_cache_control_injection(fake_litellm):
    # The Responses API caches automatically, and injected breakpoints defeat it.
    litellm_complete()(
        model="openai/gpt-6-astra",
        messages=[],
        cache_control_injection_points=[{"location": "message", "role": "system"}],
    )

    assert "cache_control_injection_points" not in fake_litellm.calls[0]


def _choice(finish_reason, **message):
    # Like litellm's Message, unset fields are absent rather than None.
    return SimpleNamespace(
        message=SimpleNamespace(**message), finish_reason=finish_reason
    )


def test_gpt_6_folds_a_preamble_into_the_tool_call_choice(fake_litellm):
    # The Responses bridge gives each output message its own choice and puts the
    # tool calls in a trailing one; callers read only choices[0].
    calls = [SimpleNamespace(id="a"), SimpleNamespace(id="b")]
    fake_litellm.response = SimpleNamespace(
        choices=[
            _choice("stop", content="I'll build it.", reasoning_content="plan"),
            _choice("tool_calls", tool_calls=calls, reasoning_content="more"),
        ]
    )

    response = litellm_complete()(model="openai/gpt-6-astra", messages=[])

    [choice] = response.choices
    assert choice.finish_reason == "tool_calls"
    assert choice.message.content == "I'll build it."
    assert choice.message.tool_calls == calls
    assert choice.message.reasoning_content == "plan\n\nmore"


def test_gpt_6_leaves_a_single_choice_alone(fake_litellm):
    only = _choice("stop", content="done")
    fake_litellm.response = SimpleNamespace(choices=[only])

    response = litellm_complete()(model="openai/gpt-6-astra", messages=[])

    assert response.choices == [only]
