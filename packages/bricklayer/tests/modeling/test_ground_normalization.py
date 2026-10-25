import pytest

from bricklayer import (
    Color,
    Element,
    LegoBuild,
    Pose,
    Vec3,
    from_ldraw,
    rotation_about,
    translate,
    translate_to_ground,
)


@pytest.mark.parametrize("height", [-10, -1, 0, 3, 12])
def test_floating_is_invariant_under_global_translation(height):
    original = LegoBuild()
    original.add(Element("3001", Color.RED))
    original.add(Element("3001", Color.BLUE), (10, 0, 3))
    model = translate(original, (0, 0, height))
    placements = model.flattened_placements
    poses = tuple(p.pose for p in placements)
    assert model.floating_placements == (placements[1],)
    assert tuple(p.pose for p in model.flattened_placements) == poses


def test_suspended_connected_assembly_uses_its_lowest_extent():
    model = LegoBuild()
    base = model.add(Element("3001", Color.RED), (0, 0, 10))
    model.stack(Element("3001", Color.BLUE), base)
    assert model.floating_placements == ()
    assert model.is_valid()
    assert model.bounding_box[0].z == 10


def test_below_ground_base_does_not_ground_a_separate_higher_tile():
    model = from_ldraw(
        "1 0 0 0 0 1 0 0 0 1 0 0 0 1 3035.dat\n"
        "1 1 -10 -8 -70 1 0 0 0 1 0 0 0 1 3070b.dat\n"
    )
    tile = model.flattened_placements[1]
    assert model.floating_placements == (tile,)
    assert translate_to_ground(model).floating_placements


def test_nested_rotated_model_matches_explicit_ground_translation():
    inner = LegoBuild()
    inner.add(Element("3001", Color.RED))
    inner.add(Element("3001", Color.BLUE), (10, 0, 10))
    outer = LegoBuild()
    outer.add_raw(inner, Pose(rotation=rotation_about(Vec3(0, 1, 0), 30)))
    assert outer.bounding_box[0].z < min(
        p.bounding_box[0].z for p in outer.flattened_placements
    )
    expected = translate_to_ground(outer)
    assert [p.content.color for p in outer.floating_placements] == [
        p.content.color for p in expected.floating_placements
    ]
    assert len(outer.floating_placements) == 1


def test_ground_level_is_invalidated_when_lowest_part_changes():
    model = LegoBuild()
    base = model.add(Element("3001", Color.RED))
    high = model.add(Element("3001", Color.BLUE), (10, 0, 3))
    assert model.floating_placements == (high,)
    model.remove(base)
    assert model.floating_placements == ()
    model.add(Element("3001", Color.GREEN), (0, 0, -2))
    assert model.floating_placements == (high,)


def test_surface_support_survives_ground_normalization():
    model = LegoBuild()
    tile = model.add(Element("3068b", Color.WHITE), (0, 0, 4))
    model.stack(Element("3003", Color.BLUE), tile)
    assert model.floating_placements == ()
    assert not model.is_connected()
