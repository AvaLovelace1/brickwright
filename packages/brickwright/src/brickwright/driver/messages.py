"""Build provider-agnostic request/response pieces for the litellm loop."""

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any

from ..config import Config, Effort
from ..prompts import system_prompt
from ..record import Record
from ..tools import ToolOutcome


def request_kwargs(config: Config, agent: str | None = None) -> dict[str, Any]:
    """litellm's ``model``, ``reasoning_effort``, and ``timeout`` params for an agent.

    ``agent`` names a helper agent's option pair (see
    :meth:`Config.agent_model_and_effort`); ``None`` is the builder.
    """
    if agent is None:
        model, effort = config.model, config.effort or Effort.NONE
    else:
        model, effort = config.agent_model_and_effort(agent)
    kwargs: dict[str, Any] = {"model": model}
    if effort is not Effort.NONE:
        kwargs["reasoning_effort"] = effort.value
    if config.request_timeout is not None:
        kwargs["timeout"] = config.request_timeout
    return kwargs


# The build request when a record has no text prompt.
DEFAULT_PROMPT = "Build a LEGO model."


def system_message(config: Config) -> dict[str, Any]:
    return {"role": "system", "content": system_prompt(external=False, config=config)}


def user_message(record: Record) -> dict[str, Any]:
    """The initial user turn: the prompt text, plus the image if there is one."""
    meta = record.read_meta()
    text = meta.prompt or DEFAULT_PROMPT
    content: list[dict[str, Any]] = [{"type": "text", "text": text}]
    image = record.prompt_image_path
    if image is not None:
        content.append(image_content_block(image))
    return {"role": "user", "content": content}


def critique_followup_message(differences: str) -> dict[str, Any]:
    """A user turn relaying a reviewer's differences back to the builder (continue mode)."""
    return {"role": "user", "content": _revision_request(differences)}


def fresh_round_messages(
    record: Record, differences: str, config: Config
) -> list[dict[str, Any]]:
    """Seed messages for a fresh builder conversation after a critique (fresh mode).

    Re-states the original task (system + the prompt/image user turn), then hands the
    builder the current build.py and the reviewer's differences so it picks up from
    the existing build instead of starting over.
    """
    handoff = {
        "role": "user",
        "content": (
            "Here is the current build.py:\n\n```python\n"
            f"{record.read_build()}\n```\n\n" + _revision_request(differences)
        ),
    }
    return [system_message(config), user_message(record), handoff]


def _revision_request(differences: str) -> str:
    """The instruction relaying a reviewer's differences and asking for a revision."""
    return (
        "An independent reviewer compared your build's rendered views to the target "
        f"image and found these differences:\n\n{differences}\n\n"
        "Revise build.py to address them, then validate and finalize again. Focus on "
        "the main object; ignore lighting and background."
    )


def assistant_message(message: Any) -> dict[str, Any]:
    """Normalize an assistant response into a provider-agnostic message dict.

    Extended-reasoning models return their thinking as ``thinking_blocks``.
    These must be echoed back on the next turn (see https://docs.litellm.ai/docs/reasoning_content).
    """
    out: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        out["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in tool_calls
        ]
    thinking_blocks = getattr(message, "thinking_blocks", None)
    if thinking_blocks:
        out["thinking_blocks"] = thinking_blocks
    reasoning_content = getattr(message, "reasoning_content", None)
    if reasoning_content:
        out["reasoning_content"] = reasoning_content
    return out


def tool_call_message(tc: Any, outcome: ToolOutcome | str) -> dict[str, Any]:
    """The tool-result turn for one tool call."""
    content = outcome if isinstance(outcome, str) else outcome.content
    return {
        "role": "tool",
        "tool_call_id": tc.id,
        "name": tc.function.name,
        "content": content,
    }


def tool_call_arguments(tc: Any) -> dict[str, Any]:
    """One tool call's arguments; an empty dict unless the model sent a JSON object."""
    try:
        arguments = json.loads(tc.function.arguments or "{}")
    except json.JSONDecodeError:
        return {}
    return arguments if isinstance(arguments, dict) else {}


def truncation_retry_message() -> dict[str, Any]:
    """Told to a model whose turn was cut off at the output cap, so it can recover.

    A truncated turn arrives as content with no tool call, which is indistinguishable
    from a deliberate final reply; without this nudge the run ends having produced
    nothing.
    """
    return {
        "role": "user",
        "content": (
            "Your last reply was cut off at the output-token limit, so none of it "
            "took effect -- no tool call was received. Do not "
            "resend it as-is. Write the build in stages instead: first write_build "
            "with a compact skeleton (the overall massing and structure, few parts), "
            "then add detail in separate edit_build or multi_edit_build calls, one "
            "region per turn. Keep every single reply well under the limit."
        ),
    }


def image_user_message(path: Path) -> dict[str, Any]:
    """A user turn carrying a single image, as a base64 data-URL image block.

    Used to hand a rendered image back to the model after a render tool call,
    since tool-result image blocks are not portably supported across providers.
    """
    return {"role": "user", "content": [image_content_block(path)]}


def image_content_block(path: Path) -> dict[str, Any]:
    """A single base64 data-URL image block for a message's ``content`` list."""
    data = base64.b64encode(path.read_bytes()).decode()
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}
