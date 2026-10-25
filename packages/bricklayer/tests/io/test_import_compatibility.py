"""External LDraw files retain their geometry without widening the build palette."""

import warnings

import pytest

from bricklayer import (
    Color,
    Finish,
    LDrawImportWarning,
    api_reference,
    from_ldraw,
    read_ldraw,
    to_ldraw,
    translate_to_ground,
)


def reference(part="3005.dat", color=4, transform="10 -24 10 1 0 0 0 1 0 0 0 1"):
    return f"1 {color} {transform} {part}"


def colors(model):
    return [p.content.color for p in model.flattened_placements]


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "ldraw"
    (root / "parts").mkdir(parents=True)
    (root / "LDConfig.ldr").write_text(
        "0 !COLOUR Brown CODE 6 VALUE #583927 EDGE #333333\n"
        "0 !COLOUR Rubber_Black CODE 256 VALUE #1B2A34 EDGE #808080 RUBBER\n"
        "0 !COLOUR Trans_Legacy CODE 999 VALUE #123456 EDGE #333333 ALPHA 128\n"
    )
    return root


def test_library_colors_preserve_parts_and_round_trip(library, tmp_path):
    source = tmp_path / "model.ldr"
    source.write_text("\n".join(reference(color=c) for c in (6, 256, 999, 4)))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        model = read_ldraw(source, ldraw_library=library)
        imported = from_ldraw(to_ldraw(model))
    assert [c.ldraw_id for c in colors(model)] == [6, 256, 999, 4]
    assert [c.rgb for c in colors(model)[:3]] == ["583927", "1B2A34", "123456"]
    assert colors(model)[-1] is Color.RED
    assert colors(imported) == colors(model)


def test_import_colors_do_not_expand_the_documented_palette(library):
    before = api_reference()
    palette = tuple(Color)
    from_ldraw(reference(color=256), ldraw_library=library)
    api_reference.cache_clear()
    assert api_reference() == before
    assert tuple(Color) == palette
    assert "Rubber_Black" not in before
    assert "Trans_Legacy" not in before


def test_direct_color_retains_rgb_and_hex_code():
    model = from_ldraw(reference(color="0x2ABCDEF"))
    assert colors(model)[0].rgb == "ABCDEF"
    assert "1 0x2ABCDEF " in to_ldraw(model)
    assert colors(from_ldraw(to_ldraw(model))) == colors(model)


def test_unknown_color_keeps_geometry_and_warns_about_appearance():
    with pytest.warns(LDrawImportWarning, match="unknown LDraw color 98765"):
        model = from_ldraw(reference(color=98765))
    assert model.brick_count == 1
    assert colors(model)[0].ldraw_id == 98765
    assert "1 98765 " in to_ldraw(model)


def test_inherited_colors_are_distinct_per_submodel_instance():
    text = "\n".join(
        [
            "0 FILE main.ldr",
            "0 main",
            reference("child.ldr", 4),
            reference("child.ldr", 1),
            "0 FILE child.ldr",
            "0 child",
            reference(color=16),
            reference(color=14),
        ]
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        model = from_ldraw(text)
    assert colors(model) == [Color.RED, Color.YELLOW, Color.BLUE, Color.YELLOW]
    assert colors(from_ldraw(to_ldraw(model))) == colors(model)


def test_scoped_color_definitions_follow_order_and_do_not_leak_from_children():
    red = "0 !COLOUR Local_Red CODE 4 VALUE #AA0000 EDGE #333333"
    blue = "0 !COLOUR Local_Blue CODE 4 VALUE #0000AA EDGE #333333"
    text = "\n".join(
        [
            "0 FILE main.ldr",
            "0 main",
            reference(),
            red,
            reference("child.ldr"),
            blue,
            reference("child.ldr"),
            reference(),
            "0 FILE child.ldr",
            "0 child",
            reference(),
            "0 !COLOUR Local_Green CODE 4 VALUE #00AA00 EDGE #333333",
            reference(),
        ]
    )
    model = from_ldraw(text)
    assert [c.rgb for c in colors(model)] == [
        Color.RED.rgb,
        "AA0000",
        "00AA00",
        "0000AA",
        "00AA00",
        "0000AA",
    ]
    assert colors(from_ldraw(to_ldraw(model))) == colors(model)


def test_glitter_material_value_does_not_replace_base_color():
    text = (
        "0 !COLOUR Glitter CODE 999 VALUE #ABCDEF EDGE #333333 ALPHA 128 "
        "MATERIAL GLITTER VALUE #123456 FRACTION 0.17 VFRACTION 0.2 SIZE 1\n"
        + reference(color=999)
    )
    assert colors(from_ldraw(text))[0].rgb == "ABCDEF"


@pytest.mark.parametrize("name", ["CODE", "VALUE", "GLITTER", "CHROME"])
def test_color_names_are_not_interpreted_as_parameter_tags(name):
    text = f"0 !COLOUR {name} CODE 999 VALUE #ABCDEF EDGE #333333\n" + reference(
        color=999
    )
    color = colors(from_ldraw(text))[0]
    assert color.rgb == "ABCDEF"
    assert color.finish is Finish.SOLID


def test_malformed_color_definition_warns_without_losing_geometry():
    with pytest.warns(LDrawImportWarning, match="malformed !COLOUR"):
        model = from_ldraw(
            "0 !COLOUR Bad CODE 4 VALUE #oops EDGE #333333\n" + reference()
        )
    assert colors(model) == [Color.RED]


@pytest.mark.parametrize("header", ["0 = Brick alias", "0 =Brick alias"])
def test_alias_chain_composes_rigid_transforms(library, assert_same_pose, header):
    (library / "parts/old.dat").write_text(
        "0 ~Moved to older\n" + reference("older.dat", 16, "20 0 0 0 0 -1 0 1 0 1 0 0")
    )
    (library / "parts/older.dat").write_text(
        header + "\n" + reference("3005.dat", 16, "10 0 0 1 0 0 0 1 0 0 0 1")
    )
    model = from_ldraw(reference("OLD.DAT"), ldraw_library=library)
    expected = from_ldraw(reference(transform="30 -24 20 0 0 -1 0 1 0 1 0 0"))
    assert model.brick_count == 1
    assert model.placements[0].content.ldraw_id == "3005"
    assert_same_pose(model.placements[0].pose, expected.placements[0].pose)


@pytest.mark.parametrize(
    "body",
    [
        "0 ~Moved to old\n" + reference("old.dat", 16),
        "0 ~Moved to brick\n" + reference(color=16) + "\n" + reference(color=16),
        "0 Custom shape\n" + reference(color=16),
        "0 ~Moved to brick\n" + reference(color=4),
        "0 ~Moved to brick\n"
        + reference(color=16, transform="0 0 0 2 0 0 0 2 0 0 0 2"),
        "0 =Brick alias\n" + reference(color=16, transform="0 0 0 -1 0 0 0 1 0 0 0 1"),
        "0 ~Moved to brick\n" + reference("../secret.dat", 16),
    ],
)
def test_unsupported_aliases_remain_explicitly_unassessable(library, body):
    (library / "parts/old.dat").write_text(body)
    with pytest.warns(LDrawImportWarning, match="uncatalogued part"):
        model = from_ldraw(reference("old.dat"), ldraw_library=library)
    assert model.brick_count == 0


def test_library_can_be_selected_by_environment(library, monkeypatch):
    monkeypatch.setenv("LDRAW_LIBRARY_PATH", str(library))
    assert colors(from_ldraw(reference(color=6)))[0].rgb == "583927"


def test_collider_only_part_imports_and_detects_collisions():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        model = from_ldraw(
            reference("52629.dat", transform="0 -48 0 1 0 0 0 1 0 0 0 1")
        )
    assert model.brick_count == 1
    assert not model.placements[0].content.connectors
    assert "52629.dat" in to_ldraw(model)
    grounded = translate_to_ground(model)
    assert grounded.is_valid()
    assert model.is_valid()
    grounded.add_raw(grounded.placements[0].content, grounded.placements[0].pose)
    assert len(grounded.colliding_placements) == 1


@pytest.mark.parametrize("part_id", ["3816b", "3817b"])
def test_obsolete_legs_import_with_recovered_connectors(part_id):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        model = from_ldraw(reference(f"{part_id}.dat"))
    element = model.placements[0].content
    assert element.ldraw_id == part_id
    assert element.connectors
    assert any(c.type.name == "antistud" for c in element.connectors)
