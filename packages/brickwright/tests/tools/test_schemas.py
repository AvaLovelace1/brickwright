"""Argument models shared by tool schemas and dispatch validation."""

import json

import pytest
from pydantic import BaseModel, ValidationError

from brickwright.tools.schemas import (
    CameraAngle,
    DispatchArgs,
    EditBuildArgs,
    MultiEditBuildArgs,
    RenderArgs,
    function_tool,
)


def test_nested_edit_schema_is_self_contained():
    schema = function_tool("multi_edit_build", MultiEditBuildArgs)
    parameters = schema["function"]["parameters"]
    edits = parameters["properties"]["edits"]
    assert edits["minItems"] == 1
    assert edits["items"]["required"] == ["old_str", "new_str"]
    assert edits["items"]["properties"]["replace_all"]["default"] is False
    assert "$ref" not in json.dumps(schema)
    assert "$defs" not in json.dumps(schema)


def test_schema_keeps_a_parameter_named_title():
    class Args(BaseModel):
        title: str

    schema = function_tool("title", Args, description="Set a title")
    assert schema["function"]["parameters"]["properties"] == {
        "title": {"type": "string"}
    }


@pytest.mark.parametrize("value", ["false", 0, None])
def test_edit_flag_is_not_coerced(value):
    with pytest.raises(ValidationError):
        EditBuildArgs(old_str="a", new_str="b", replace_all=value)


def test_edit_defaults_and_extra_fields():
    args = EditBuildArgs.model_validate({"old_str": "a", "new_str": "b", "extra": 1})
    assert args.model_dump() == {"old_str": "a", "new_str": "b", "replace_all": False}


def test_optional_render_angles_and_required_viewpoint_angles():
    assert RenderArgs().azimuth is None
    assert RenderArgs(azimuth=None, elevation=None).elevation is None
    assert CameraAngle(azimuth=30, elevation=-10).azimuth == 30.0
    with pytest.raises(ValidationError):
        CameraAngle.model_validate({})
    with pytest.raises(ValidationError):
        RenderArgs(azimuth=30)


@pytest.mark.parametrize("value", [True, "30", float("nan"), float("inf")])
@pytest.mark.parametrize("model", [RenderArgs, CameraAngle])
def test_camera_angles_reject_non_numeric_or_non_finite_values(model, value):
    with pytest.raises(ValidationError):
        model(azimuth=value, elevation=0)


def test_dispatch_preserves_prompt_and_tier_fallback():
    args = DispatchArgs.model_validate({"tasks": [{"prompt": " build ", "tier": 3}]})
    assert args.tasks[0].prompt == " build "
    assert args.tasks[0].tier is None
    with pytest.raises(ValidationError):
        DispatchArgs.model_validate({"tasks": [{"prompt": "  "}]})


def test_nested_validation_names_the_bad_edit():
    with pytest.raises(ValidationError) as caught:
        MultiEditBuildArgs.model_validate(
            {
                "edits": [
                    {"old_str": "a", "new_str": "b"},
                    {"old_str": 3, "new_str": "c"},
                ]
            }
        )
    assert caught.value.errors()[0]["loc"] == ("edits", 1, "old_str")
