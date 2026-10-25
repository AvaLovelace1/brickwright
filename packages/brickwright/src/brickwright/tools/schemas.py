"""Pydantic arguments shared by tool schemas and runtime validation."""

from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .software_rendering import MAX_ELEVATION


class ToolArgs(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")


class ReadBuildArgs(ToolArgs):
    """Return the current contents of build.py with 1-indexed line numbers. The `N: `
    prefixes are display-only -- never include them in edit_build's old_str or
    insert_build's insert_text."""

    view_range: list[int] | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="[start, end] line range, 1-indexed inclusive; end -1 means end of file; omit for the whole file",
    )


class WriteBuildArgs(ToolArgs):
    """Overwrite the entire build.py."""

    content: str = Field(description="the complete new build.py source")


class InsertBuildArgs(ToolArgs):
    """Insert text at a line boundary of build.py, leaving the rest of the file unchanged.
    Line numbers follow read_build's numbering."""

    insert_line: int = Field(description="insert after this line; 0 = top of file")
    insert_text: str = Field(description="the lines to insert")


class EditBuildArgs(ToolArgs):
    """Replace a snippet of build.py. old_str must match exactly one location, unless
    replace_all=True (matching tolerates leading/trailing whitespace differences per
    line). Never include read_build's `N: ` line-number prefixes in old_str. On success,
    returns the edited region."""

    old_str: str = Field(description="text to replace, exactly as in the file")
    new_str: str = Field(description="replacement text")
    replace_all: bool = Field(default=False, description="replace every occurrence")


class MultiEditBuildArgs(ToolArgs):
    """Apply several str-replace edits to build.py in one call. Edits apply in order, each
    seeing the previous one's result, and the batch is atomic: if any edit fails, none
    are applied."""

    edits: list[EditBuildArgs] = Field(
        min_length=1, description="the edits to apply, in order"
    )


class ValidateArgs(ToolArgs):
    """Create the build and run validity + custom checks. Returns a JSON report."""


class ExploreArgs(ToolArgs):
    """Run a short Python snippet for inspection only. The `bricklayer` package is in
    scope, and if the snippet reads `build`, build.py is run and its LegoBuild is
    bound to it; use print(...) to return what you want to see (catalog lookups,
    measurements, part counts, positions). The snippet does not change build.py."""

    code: str = Field(
        description="Python to run with `bricklayer` (and `build`, if read) in scope; print(...) whatever you want returned."
    )


Azimuth = Annotated[
    float,
    Field(
        allow_inf_nan=False,
        description="horizontal camera angle in degrees, -180 to 180 (0 = front, positive = camera to the build's right)",
    ),
]
Elevation = Annotated[
    float,
    Field(
        ge=-MAX_ELEVATION,
        le=MAX_ELEVATION,
        allow_inf_nan=False,
        description=f"vertical camera angle in degrees, -{MAX_ELEVATION:g} to {MAX_ELEVATION:g} (0 = level, positive = looking down from above)",
    ),
]


class CameraAngle(ToolArgs):
    """Render the build from a camera angle and show it to you."""

    azimuth: Azimuth
    elevation: Elevation


class RenderArgs(ToolArgs):
    """Render the current build to an image and look at it. With no arguments, returns a
    multi-view contact sheet (front, side, top, and isometric views) of the build as
    created; give `azimuth` and `elevation` together to render a single view from that
    camera angle instead. The image is shown to you right after."""

    azimuth: Azimuth | None = None
    elevation: Elevation | None = None

    @model_validator(mode="after")
    def paired_angles(self) -> Self:
        if (self.azimuth is None) != (self.elevation is None):
            raise ValueError(
                "give both azimuth and elevation, or neither for the contact sheet"
            )
        return self


class FinalizeArgs(ToolArgs):
    """Validate the current source and export that build to LDraw, rendering when available.
    Finishes only on success; correct any reported failure and retry. Call this when
    the build satisfies the request."""


class SubagentTask(ToolArgs):
    """One unit of work to hand to a subagent."""

    prompt: str = Field(description="Self-contained instructions for one subagent.")
    tier: str | None = Field(
        default=None,
        description="Model tier: 'fast' is cheapest/quickest, 'smart' is most capable, 'balanced' is in between. Omit to use the main model.",
    )

    @field_validator("prompt")
    @classmethod
    def nonblank_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value

    @field_validator("tier", mode="before")
    @classmethod
    def optional_tier(cls, value: Any) -> str | None:
        return value if isinstance(value, str) else None


class DispatchArgs(ToolArgs):
    """Run independent subtasks in parallel. Each subagent works in its own isolated build
    with the same tools you have (except this one), and returns its answer to you as
    text. Subagents do not touch `build.py`; you must integrate the returned text
    yourself. Each result reports `ok` (it handed work back) separately from `valid`
    (its own last validation passed) plus `failed_checks`: a subagent can run out of
    budget and return work that is still broken, so read `valid` before you integrate,
    and repair what came back broken."""

    tasks: list[SubagentTask] = Field(
        min_length=1, description="The subtasks to run in parallel."
    )


def function_tool(
    name: str, arguments: type[BaseModel], *, description: str | None = None
) -> dict[str, Any]:
    """Wrap a Pydantic argument schema in the function-calling envelope."""
    parameters = _inline_schema(arguments.model_json_schema())
    model_description = parameters.pop("description", "")
    if description is None:
        description = model_description
    parameters.setdefault("required", [])
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": " ".join(description.split()),
            "parameters": parameters,
        },
    }


def _inline_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline our nonrecursive argument models for providers expecting inline schemas."""
    definitions = schema.get("$defs", {})

    def inline(value: Any) -> Any:
        if isinstance(value, list):
            return [inline(item) for item in value]
        if not isinstance(value, dict):
            return value
        resolved = (
            inline(definitions[value["$ref"].rsplit("/", 1)[-1]])
            if "$ref" in value
            else {}
        )
        return resolved | {
            key: {name: inline(field) for name, field in item.items()}
            if key == "properties"
            else inline(item)
            for key, item in value.items()
            if key not in {"$ref", "$defs", "title"}
        }

    return inline(schema)
