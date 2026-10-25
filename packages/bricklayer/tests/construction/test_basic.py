"""Tests for the basic components."""

from bricklayer import (
    PLATE,
    Box,
    Color,
    Element,
    Footprint,
    brick,
    plate,
    tile,
)
from bricklayer.construction.basic import _BRICKS, _PLATES, _TILES


class TestBrick:
    def test_selected_brick_builds(self, assert_cuboid_geometry):
        for spec in _BRICKS.specs:
            assert isinstance(spec.shape, Box)
            w, d, h = spec.shape.dimensions
            assert_cuboid_geometry(spec, w, d, h)

    def test_factory_and_direct_construction_are_identical(self):
        assert brick(4, 2, color=Color.RED) == Element("3001", Color.RED)


class TestPlate:
    def test_selected_plate_builds(self, assert_cuboid_geometry):
        for spec in _PLATES.specs:
            assert isinstance(spec.shape, Footprint)
            w, d = spec.shape.dimensions
            assert_cuboid_geometry(spec, w, d, PLATE)


class TestTile:
    def test_selected_tile_builds(self, assert_cuboid_geometry):
        for spec in _TILES.specs:
            assert isinstance(spec.shape, Footprint)
            w, d = spec.shape.dimensions
            assert_cuboid_geometry(spec, w, d, PLATE, has_studs=False)


def test_size_arguments_are_followed_by_color():
    assert brick(4, 2, 1, Color.RED) == Element("3001", Color.RED)
    assert plate(2, 1, Color.BLUE) == Element("3023b", Color.BLUE)
    assert tile(2, 1, Color.GREEN) == Element("3069b", Color.GREEN)
