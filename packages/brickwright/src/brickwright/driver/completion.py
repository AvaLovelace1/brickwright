"""The litellm completion seam, shared by the builder loop and the critic.

Kept in its own module so the loop and the critique step can each bind (and tests
can each patch) ``litellm_complete`` independently, without an import cycle.
"""

from collections.abc import Callable, Iterable
from typing import Any


def litellm_complete() -> Callable[..., Any]:
    # Imported lazily so tests can monkeypatch sys.modules["litellm"] before this
    # runs; a module-level import binds the real module too early for that to work.
    import litellm

    # Sanitize tool calls; see https://docs.litellm.ai/docs/completion/message_sanitization
    litellm.modify_params = True

    def complete(**kwargs: Any) -> Any:
        routed = _route(kwargs)
        response = litellm.completion(**routed)
        if (routed.get("model") or "").startswith("openai/responses/"):
            return _merge_choices(response)
        return response

    return complete


def bad_request_error() -> type[Exception]:
    import litellm

    return litellm.BadRequestError


def _route(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Configure Claude prefix caching and OpenAI's Responses API bridge.

    OpenAI rejects function tools alongside reasoning for gpt-6 on
    ``/v1/chat/completions``, and litellm doesn't list ``reasoning_effort`` among
    gpt-6's params, so it has to be allowed explicitly. The Responses API caches
    prompts automatically, and litellm's injected cache breakpoints defeat that.
    """
    model = kwargs.get("model") or ""
    if model.removeprefix("anthropic/").startswith("claude-"):
        # Keep the static prefix reusable across builds, and cache the growing
        # conversation through the latest tool result or rendered image.
        return {
            **kwargs,
            "cache_control_injection_points": [
                {"location": "message", "role": "system"},
                {"location": "message", "index": -1},
            ],
        }
    name = model.removeprefix("openai/")
    if not name.startswith("gpt-6"):
        return kwargs
    routed = {**kwargs, "model": f"openai/responses/{name}"}
    routed.pop("cache_control_injection_points", None)
    if "reasoning_effort" in kwargs:
        routed["allowed_openai_params"] = ["reasoning_effort"]
    return routed


def _merge_choices(response: Any) -> Any:
    """Fold the Responses API bridge's choices back into the one callers read.

    The bridge makes each output message (such as a preamble before tool calls) its
    own choice and puts every tool call in a trailing one, so ``choices[0]`` alone
    looks like a final text reply.
    """
    if len(response.choices) < 2:
        return response
    merged = response.choices[0]
    messages = [c.message for c in response.choices]
    # litellm's Message drops unset fields rather than holding None.
    merged.message.content = _join(getattr(m, "content", None) for m in messages)
    merged.message.reasoning_content = _join(
        getattr(m, "reasoning_content", None) for m in messages
    )
    merged.message.tool_calls = [
        tc for m in messages for tc in (getattr(m, "tool_calls", None) or [])
    ] or None
    merged.finish_reason = response.choices[-1].finish_reason
    response.choices = [merged]
    return response


def _join(texts: Iterable[str | None]) -> str | None:
    return "\n\n".join(t for t in texts if t) or None
