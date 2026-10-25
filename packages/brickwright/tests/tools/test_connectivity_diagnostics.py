import json

import pytest
from bricklayer import Color, LegoBuild, Position, brick, flatten, to_ldraw

from brickwright.tools.connectivity_diagnostics import (
    connectivity_diagnostic,
    convert_connectivity_diagnostics,
)


def test_components_share_colors_without_changing_any_placement():
    model = LegoBuild()
    model.add(brick(1, 1, color=Color.RED))
    model.add(brick(1, 1, color=Color.BLUE), position=Position(0, 0, 1))
    model.add(brick(1, 1), position=Position(4, 0, 0))
    original = to_ldraw(model)
    diagnostic = connectivity_diagnostic(model)
    parts = [
        line.split() for line in diagnostic.ldraw.splitlines() if line.startswith("1 ")
    ]
    assert parts[0][1] == parts[1][1] != parts[2][1]
    assert [line[2:] for line in parts] == [
        line.split()[2:] for line in to_ldraw(flatten(model)).splitlines()
    ]
    assert diagnostic.components == ((0, 1), (2,))
    assert all(
        "ALPHA" in line for line in diagnostic.ldraw.splitlines() if "!COLOUR" in line
    )
    assert to_ldraw(model) == original


def test_nested_reused_models_are_grouped_by_instance():
    child = LegoBuild()
    child.add(brick(1, 1))
    child.add(brick(1, 1), position=Position(0, 0, 1))
    parent = LegoBuild()
    parent.add(child)
    parent.add(child, position=Position(5, 0, 0))
    assert connectivity_diagnostic(parent).components == ((0, 1), (2, 3))


def test_palette_does_not_repeat_after_the_standard_transparent_colors():
    model = LegoBuild()
    for i in range(40):
        model.add(brick(1, 1), position=Position(2 * i, 0, 0))
    diagnostic = connectivity_diagnostic(model)
    assert len(set(diagnostic.colors)) == 40
    assert diagnostic == connectivity_diagnostic(model)


def test_empty_model_and_invalid_component_partition():
    assert connectivity_diagnostic(LegoBuild()).components == ()
    model = LegoBuild()
    model.add(brick(1, 1))
    with pytest.raises(ValueError, match="partition"):
        connectivity_diagnostic(model, components=((0,), (0,)))


def test_glb_uses_transparent_component_colors_even_on_printed_geometry(tmp_path):
    library = tmp_path / "ldraw"
    (library / "parts").mkdir(parents=True)
    (library / "p").mkdir()
    (library / "LDConfig.ldr").write_text(
        "0 !COLOUR Red CODE 4 VALUE #C91A09 EDGE #333333\n"
    )
    (library / "parts/3005.dat").write_text(
        "0 Test printed part\n0 BFC CERTIFY CCW\n3 16 0 0 0 20 0 0 0 0 20\n3 4 0 0 0 0 0 20 0 -20 0\n"
    )
    model = LegoBuild()
    model.add(brick(1, 1))
    model.add(brick(1, 1), position=Position(3, 0, 0))
    diagnostic = connectivity_diagnostic(model)
    source = tmp_path / "components.ldr"
    source.write_text(diagnostic.ldraw)
    target = tmp_path / "components.glb"
    convert_connectivity_diagnostics(source, target, library=library)
    raw = target.read_bytes()
    gltf = json.loads(raw[20 : 20 + int.from_bytes(raw[12:16], "little")])
    assert len(gltf["materials"]) == 2
    assert sum("mesh" in node for node in gltf["nodes"]) == 2
    colors = []
    for material in gltf["materials"]:
        assert material["alphaMode"] == "BLEND"
        rgba = material["pbrMetallicRoughness"]["baseColorFactor"]
        assert 0 < rgba[3] < 1
        colors.append(rgba)
    assert colors[0] != colors[1]
