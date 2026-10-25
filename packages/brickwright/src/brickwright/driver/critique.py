"""The visual-critique step: an independent model judges the build against the target.

A separate agent first picks a camera angle whose render matches the reference's
viewpoint (see :mod:`.viewpoint`); a single call then sees the reference beside that
matched render and reports whether they match and what differs.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from ..config import Config
from ..record import Record
from .completion import bad_request_error, litellm_complete
from .messages import image_content_block, request_kwargs
from .viewpoint import match_viewpoint

VIEWPOINT_COMPARE_PROMPT = """\
You are an independent reviewer judging how faithfully a LEGO build reproduces a
target object. You are given:

1. The target reference image.
2. A single rendered image of the LEGO build, captured from a camera viewpoint chosen
   to match the reference's viewpoint.
3. The original text prompt that requested the build.

First describe both objects in detail, then enumerate the concrete differences between
them. Judge only the main object that the prompt refers to -- ignore lighting, shadows,
background, camera angle, photographic style, and rendering artifacts. Focus on shape,
proportions, structure, parts and coloring, and any missing or extra features.

Reply with a single JSON object with exactly these keys:
- "differences_description": a string with your detailed descriptions of both objects
  followed by the differences between them.
- "done": a boolean -- true if the build faithfully matches the reference (only minor
  or cosmetic differences remain), false if it should be revised further.

Reply with only the JSON object, no prose around it."""

# What the critic is shown as the original prompt when the build had none.
NO_TEXT_PROMPT = "(no text prompt)"


class CritiqueResult(BaseModel):
    """An independent reviewer's verdict comparing the build to the target image."""

    model_config = ConfigDict(frozen=True)

    differences_description: str
    done: bool


def critique(
    record: Record,
    config: Config,
    *,
    complete: Callable[..., Any] | None = None,
    on_response: Callable[[Any], None] | None = None,
) -> CritiqueResult | None:
    """Compare the build to the prompt image and return the verdict.

    The build is shown from a camera angle matched to the reference's viewpoint.
    The result is ``None`` when no comparison could be made: no matched render, or a
    reply that won't parse into a verdict. Raises ``ValueError`` without a prompt
    image.

    ``on_response`` observes every raw completion response immediately (the
    viewpoint agent's and the critic's), so the caller can fold their usage and cost
    into the run's tracker; it may raise to stop before another paid request.
    """
    reference = record.prompt_image_path
    if reference is None:
        raise ValueError("critique requires a prompt image")
    complete = complete or litellm_complete()
    prompt = record.read_meta().prompt or NO_TEXT_PROMPT

    result = match_viewpoint(record, config, complete=complete, on_response=on_response)
    if result is None:
        return None  # no matched render to compare against

    content: list[dict[str, Any]] = [
        {"type": "text", "text": f"Original prompt:\n{prompt}"},
        {"type": "text", "text": "Target reference image:"},
        image_content_block(reference),
        {
            "type": "text",
            "text": (
                "The LEGO build, rendered from a viewpoint chosen to match the "
                f"reference (azimuth {result.azimuth:g}, elevation {result.elevation:g}):"
            ),
        },
        image_content_block(record.viewpoint_path),
    ]
    messages = [
        {"role": "system", "content": VIEWPOINT_COMPARE_PROMPT},
        {"role": "user", "content": content},
    ]
    response = _complete(complete, config, messages)
    if on_response is not None:
        on_response(response)
    try:
        return CritiqueResult.model_validate_json(_text_of(response))
    except ValidationError:
        return None


_RESPONSE_FORMATS = (CritiqueResult, {"type": "json_object"})


def _complete(
    complete: Callable[..., Any], config: Config, messages: list[dict[str, Any]]
) -> Any:
    """Run one critic completion, weakening response_format until the provider takes it."""
    kwargs = request_kwargs(config, "critique")

    def ask(**asked: Any) -> Any:
        return complete(messages=messages, **asked, **kwargs)

    for response_format in _RESPONSE_FORMATS:
        try:
            return ask(response_format=response_format)
        except bad_request_error() as exc:
            if "response_format" not in str(exc):
                raise
    return ask()


def _text_of(response: Any) -> str:
    """The text content of a completion response (``""`` if it has none)."""
    return response.choices[0].message.content or ""
