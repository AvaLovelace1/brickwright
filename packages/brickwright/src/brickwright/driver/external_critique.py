"""The playbook ``brickwright external critique-instructions`` prints.

It has the external agent dispatch two fresh subagents -- one to match the viewpoint
(rendering through ``brickwright external render-angle``), one to critique -- each
handed the driver's own system prompt.
"""

from __future__ import annotations

from ..record import Record
from .critique import NO_TEXT_PROMPT, VIEWPOINT_COMPARE_PROMPT
from .viewpoint import ANGLE_CONVENTIONS, ORIENTATION_HINT, VIEWPOINT_TASK

DEFAULT_CRITIQUE_ROUNDS = 2


def external_viewpoint_prompt(record_id: str, viewpoint_path: str) -> str:
    """The angle-finding subagent's system prompt: the driver's
    :data:`~driver.viewpoint.VIEWPOINT_TASK`, rendering through
    ``brickwright external render-angle``."""
    return f"""\
{VIEWPOINT_TASK}

Render the build from a camera angle by running this command from the repository root:

    uv run brickwright external render-angle {record_id} --azimuth <A> --elevation <E>

{ANGLE_CONVENTIONS}

The command renders the build, writes the image to
{viewpoint_path}
(overwriting any previous one), and prints that path. Open the PNG, compare its viewpoint
to the reference, and re-run the command with adjusted angles to get closer.
{ORIENTATION_HINT} Use as few renders as you need. When the render is seen from essentially the same viewpoint as
the reference, stop -- your final render must be that matched view, so it is left at the
path above for the critic to compare against. Then reply with a plain-text message
reporting the matched azimuth and elevation and confirming the render at that path."""


def external_critique_instructions(
    record: Record, *, rounds: int = DEFAULT_CRITIQUE_ROUNDS
) -> str:
    """Assemble the record-specific critique playbook for the external agent.

    Raises ``ValueError`` when the record has no prompt image, since there is nothing to
    critique the build against -- the external mirror of the driver skipping the loop.
    """
    reference = record.prompt_image_path
    if reference is None:
        raise ValueError("external critique requires a prompt image")

    record_id = record.id
    reference_path = str(reference.absolute())
    build_path = str(record.build_path.absolute())
    viewpoint_path = str(record.viewpoint_path.absolute())
    prompt = record.read_meta().prompt or NO_TEXT_PROMPT
    viewpoint_prompt = external_viewpoint_prompt(record_id, viewpoint_path)
    # Braces in the JSON schema example are doubled so the f-string emits them literally.
    return f"""\
# BrickWright visual critique (image prompt)

This is the external-agent counterpart of the driver's `viewpoint` visual-critique loop.
Run it for image-prompt builds once the build validates and renders acceptably, to check
the build against the reference image and revise it before finalizing.

The loop has two steps, and each is run by a **fresh subagent** -- a new agent started
with no prior context, so it judges independently, exactly as the driver runs each step as
an independent model call. Dispatch the subagents yourself, and give each one the system
prompt quoted below **verbatim**. Do not do these steps in your own context.

- Record: {record_id}
- Reference image: {reference_path}
- build.py: {build_path}
- Original prompt: {prompt}

Repeat the loop below up to {rounds} time(s), or until the critic reports `"done": true`.

## Step A -- match the camera viewpoint (fresh subagent)

Dispatch a fresh subagent whose system prompt is exactly:

----------------------------------------------------------------------
{viewpoint_prompt}
----------------------------------------------------------------------

Give that subagent this task: read the reference image at {reference_path} and the build
source at {build_path}, then find the matching camera angle as its system prompt
instructs. It leaves the matched render at {viewpoint_path} and reports the azimuth and
elevation it chose.

## Step B -- critique the build (fresh subagent)

Dispatch a second fresh subagent whose system prompt is exactly:

----------------------------------------------------------------------
{VIEWPOINT_COMPARE_PROMPT}
----------------------------------------------------------------------

Give that subagent this task:

- Original prompt: {prompt}
- Read the target reference image at {reference_path}.
- Read the LEGO build's matched render at {viewpoint_path}.

It must reply with only the JSON object its system prompt describes
(`{{"differences_description": "...", "done": true|false}}`).

## Step C -- revise

Parse the critic's JSON. If `"done"` is true, the build matches the reference well enough:
stop the loop and finalize. Otherwise edit `build.py` to address the
`differences_description`, re-run `uv run brickwright external validate {record_id}` until
it passes, then repeat from Step A. Stop after {rounds} round(s) even if the critic is not
yet satisfied."""
