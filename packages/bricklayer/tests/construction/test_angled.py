"""Tests for angled components."""

from bricklayer import (
    Box,
    Direction,
    Position,
)
from bricklayer.construction.angled import _INVERTED_SLOPES, _SLOPES


class TestSlope:
    def test_selected_slope_builds(self, assert_cuboid_geometry):
        for spec in _SLOPES.specs:
            assert isinstance(spec.shape, Box)
            w, d, h = spec.shape.dimensions
            assert_cuboid_geometry(spec, w, d, h)

    def test_slopes_have_back_top_row_of_studs(
        self, part_from_spec, anchored, assert_contains_connectors
    ):
        for spec in _SLOPES.specs:
            assert isinstance(spec.shape, Box)
            w, d, h = spec.shape.width, spec.shape.depth, spec.shape.height
            elem = anchored(part_from_spec(spec))
            expected = [
                (Position(x + 0.5, d - 0.5, float(h)), Direction.UP.value)
                for x in range(w)
            ]
            assert_contains_connectors(elem, "stud", expected)


class TestInvertedSlope:
    def test_selected_inverted_slope_builds(self, assert_cuboid_geometry):
        for spec in _INVERTED_SLOPES.specs:
            assert isinstance(spec.shape, Box)
            w, d, h = spec.shape.dimensions
            assert_cuboid_geometry(spec, w, d, h)

    def test_inverted_slopes_have_back_bottom_row_of_antistuds(
        self, part_from_spec, anchored, assert_contains_connectors
    ):
        for spec in _INVERTED_SLOPES.specs:
            assert isinstance(spec.shape, Box)
            w, d = spec.shape.width, spec.shape.depth
            elem = anchored(part_from_spec(spec))
            expected = [
                (Position(x + 0.5, d - 0.5, 0), Direction.UP.value) for x in range(w)
            ]
            assert_contains_connectors(elem, "antistud", expected)
