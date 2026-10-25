"""The viewpoint-matching agent: choose a camera angle whose render matches the photo.

Given the reference image and the build's ``build.py``, an independent agent picks a
camera angle (azimuth + elevation), renders the build from it, looks at the result, and
adjusts until the render is seen from the same viewpoint as the reference object -- then
finalizes. Enabled by ``config.max_viewpoint_iterations``.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..config import Config
from ..record import Record
from ..tools import render_angle
from ..tools.schemas import CameraAngle, ToolArgs, function_tool
from ..tools.software_rendering import MAX_ELEVATION
from .completion import litellm_complete
from .messages import (
    assistant_message,
    image_content_block,
    request_kwargs,
    tool_call_arguments,
    tool_call_message,
)
from .transcript import Transcript

# What "matching the viewpoint" means, independent of how a render is produced; shared
# with the external-agent playbook.
VIEWPOINT_TASK = """\
You are matching the camera viewpoint of a 3D LEGO render to a reference image.

You are given:
1. The reference image of the target object.
2. The Python source (`build.py`) that creates the LEGO build.

Your goal: find the camera angle from which the rendered build is seen from the same
viewpoint as the object in the reference image -- the same facing, rotation, and tilt --
so the two can be compared fairly. You are matching the *camera angle only*, not the
build: ignore differences in shape, parts, or color, and judge only orientation."""

# How the two camera angles are oriented; shared with the external-agent playbook.
ANGLE_CONVENTIONS = f"""\
- azimuth: horizontal angle in degrees, -180 to 180. 0 faces the build's front;
  positive swings the camera to the build's right.
- elevation: vertical angle in degrees, -{MAX_ELEVATION:g} to {MAX_ELEVATION:g}. 0 is level;
  positive looks down from above; negative looks up from below."""

ORIENTATION_HINT = (
    "Reason from `build.py` about how the build is oriented (which face is the front, "
    "which way is up)."
)

VIEWPOINT_SYSTEM_PROMPT = f"""\
{VIEWPOINT_TASK}

Call `render_view(azimuth, elevation)` to render the build from a camera angle:
{ANGLE_CONVENTIONS}

The render is shown to you right after. Compare its viewpoint to the reference and call
`render_view` again with adjusted angles to get closer. {ORIENTATION_HINT} When the render
is seen from essentially the same viewpoint as the reference, call `finalize`. Use as few
renders as you need."""

_TOOLS = [
    function_tool(
        "render_view",
        CameraAngle,
    ),
    function_tool(
        "finalize",
        ToolArgs,
        description=(
            "Call when the latest render is seen from the same viewpoint as the "
            "reference image."
        ),
    ),
]


class ViewpointResult(BaseModel):
    """The viewpoint agent's chosen camera angle and how it got there."""

    model_config = ConfigDict(frozen=True)

    azimuth: float  # degrees; the matched horizontal camera angle
    elevation: float  # degrees; the matched vertical camera angle
    iterations: int  # how many renders the agent took
    done: bool  # whether it finalized (vs ran out of iterations)


def match_viewpoint(
    record: Record,
    config: Config,
    *,
    complete: Callable[..., Any] | None = None,
    on_response: Callable[[Any], None] | None = None,
) -> ViewpointResult | None:
    """Drive an agent to pick a camera angle matching the reference image's viewpoint.

    Returns the chosen angle, or ``None`` if the agent never produced a render; its
    render is copied to ``record.viewpoint_path``. Raises ``ValueError`` if the record
    has no prompt image to match against.

    ``on_response`` observes each raw completion response as it arrives, so the caller
    can fold its usage and cost into the run's tracker; it may raise to stop requests.
    """
    if record.prompt_image_path is None:
        raise ValueError("viewpoint matching requires a prompt image")

    complete = complete or litellm_complete()
    kwargs = request_kwargs(config, "viewpoint")

    # Each run gets its own session dir holding every candidate render, the matched
    # render, and the agent's transcript (jsonl + pretty, images elided).
    session = record.new_viewpoint_session()

    last_render: tuple[float, float, Path] | None = None  # azimuth, elevation, image
    attempts = 0  # every render_view call
    iterations = 0  # successful renders
    done = False

    with Transcript(session / "transcript.jsonl") as convo:
        convo.append({"role": "system", "content": VIEWPOINT_SYSTEM_PROMPT})
        convo.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Reference image of the target object:"},
                    image_content_block(record.prompt_image_path),
                    {
                        "type": "text",
                        "text": (
                            "The current build is produced by this build.py:\n\n"
                            f"```python\n{record.read_build()}\n```\n\n"
                            "Pick a camera angle and call render_view to see the build."
                        ),
                    },
                ],
            }
        )

        for _ in range(max(0, config.max_viewpoint_iterations)):
            response = complete(
                messages=convo.messages, tools=_TOOLS, tool_choice="auto", **kwargs
            )
            message = response.choices[0].message
            convo.append(assistant_message(message))
            if on_response is not None:
                on_response(response)

            tool_calls = getattr(message, "tool_calls", None)
            if not tool_calls:
                break  # a plain text reply -- the agent has nothing more to do

            # Renders are held back until every call in the batch has been answered:
            # the tool messages answering one turn have to reach the provider as an
            # unbroken run, and a rendered-image user message in among them reads as
            # missing answers (which strict providers reject outright).
            pending_renders: list[dict[str, Any]] = []

            for tc in tool_calls:
                name = tc.function.name
                if done:
                    convo.append(tool_call_message(tc, "skipped: already finalized"))
                    continue
                if name == "finalize":
                    done = True
                    convo.append(tool_call_message(tc, "ok: finalized"))
                    continue
                if name != "render_view":
                    convo.append(tool_call_message(tc, f"unknown tool {name!r}"))
                    continue

                try:
                    angle = CameraAngle.model_validate(tool_call_arguments(tc))
                except ValueError as exc:
                    convo.append(tool_call_message(tc, f"invalid arguments: {exc}"))
                    continue
                azimuth, elevation = angle.azimuth, angle.elevation
                attempts += 1
                candidate = (
                    session
                    / f"candidate_{attempts:02d}_az{azimuth:g}_el{elevation:g}.png"
                )
                report = render_angle(
                    record, azimuth, elevation, config, out_path=candidate
                )
                if not report.ok:
                    convo.append(
                        tool_call_message(tc, f"render failed:\n{report.error}")
                    )
                    continue
                last_render = (azimuth, elevation, candidate)
                iterations += 1
                convo.append(
                    tool_call_message(
                        tc,
                        f"ok: rendered from azimuth {azimuth:g}, "
                        f"elevation {elevation:g}; the image follows.",
                    )
                )
                pending_renders.append(_render_message(azimuth, elevation, candidate))

            for render_message in pending_renders:
                convo.append(render_message)

            if done:
                break

    if last_render is None:
        return None
    azimuth, elevation, matched = last_render

    # Keep this round's matched render, and mirror it to the canonical path the critic
    # reads (record.viewpoint_path).
    shutil.copyfile(matched, session / "matched.png")
    record.out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(matched, record.viewpoint_path)

    return ViewpointResult(
        azimuth=azimuth, elevation=elevation, iterations=iterations, done=done
    )


def _render_message(azimuth: float, elevation: float, image: Path) -> dict[str, Any]:
    """The user turn showing the agent one candidate render."""
    return {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": f"Render at azimuth {azimuth:g}, elevation {elevation:g}:",
            },
            image_content_block(image),
        ],
    }
