"""Tests for the fill construction helpers (bricklayer.fill)."""

import itertools
from collections.abc import Iterable

import pytest

from bricklayer import (
    PLATE,
    Box,
    Direction,
    Element,
    Position,
    fill_box,
    fill_inverted_slope,
    fill_slope,
    to_ldraw,
)
from bricklayer.construction.angled import _INVERTED_SLOPES, _SLOPES
from bricklayer.construction.basic import _BRICKS
from bricklayer.ldraw.partdata import STUD_HEIGHT


def _box_cells(w, d, h):
    """Every ``(x, y, z)`` grid cell (x/y in studs, z in plates) inside the box
    spanning the origin to ``(w, d, h)``."""
    return {
        (x, y, z)
        for x in range(round(w))
        for y in range(round(d))
        for z in range(round(3 * h))
    }


def _assert_box(box, lo, hi):
    """Assert a ``(min, max)`` box matches the given corners, within float tolerance."""
    actual_lo, actual_hi = box
    assert tuple(actual_lo) == pytest.approx(lo)
    assert tuple(actual_hi) == pytest.approx(hi)


def _height_at(cells: Iterable[tuple[int, int, int]], *, along: str) -> dict[int, int]:
    """Map run-position -> max occupied plate-height, indexed on the given axis."""
    profile: dict[int, int] = {}
    for x, y, z in cells:
        key = y if along == "y" else x
        profile[key] = max(profile.get(key, -1), z)
    return profile


def _min_height_at(
    cells: Iterable[tuple[int, int, int]], *, along: str
) -> dict[int, int]:
    """Map run-position -> min occupied plate-height, indexed on the given axis."""
    profile: dict[int, int] = {}
    for x, y, z in cells:
        key = y if along == "y" else x
        profile[key] = min(profile.get(key, z), z)
    return profile


class TestCornerInputs:
    @pytest.mark.parametrize("fill", [fill_box, fill_slope, fill_inverted_slope])
    def test_fill_accepts_tuple_corners(self, fill):
        assert to_ldraw(fill((0, 0, 0), (2, 2, 1))) == to_ldraw(
            fill(Position.ZERO, Position(2, 2, 1))
        )


class TestFillBox:
    TEST_DIMS = tuple(
        itertools.product((1, 2, 3, 17), (1, 2, 3, 17), (2 * PLATE, 1, 2 + 2 * PLATE))
    )

    @pytest.mark.parametrize("w,d,h", TEST_DIMS)
    def test_fill_covers_box_exactly_and_is_valid_and_connected(
        self, w, d, h, filled_region
    ):
        m = fill_box(Position.ZERO, Position(w, d, h))
        assert m.is_valid()
        assert m.is_connected()
        _assert_box(m.alignment_box, (0, 0, 0), (w, d, h))
        assert _box_cells(w, d, h) <= filled_region(m)

    def test_fill_box_spans_corners(self):
        m = fill_box(Position(2, 3, 1), Position(6, 8, 3))
        assert not m.colliding_placements
        assert m.is_connected()
        _assert_box(m.alignment_box, (2, 3, 1), (6, 8, 3))
        _assert_box(m.bounding_box, (2, 3, 1), (6, 8, 3 + STUD_HEIGHT))

    def test_fill_box_corner_order_is_irrelevant(self):
        a, b = Position(2, 3, 1), Position(6, 8, 3)
        reference = to_ldraw(fill_box(a, b))
        assert to_ldraw(fill_box(b, a)) == reference
        assert to_ldraw(fill_box(Position(2, 8, 3), Position(6, 3, 1))) == reference

    @pytest.mark.parametrize(
        "corner",
        [Position(0.5, 0, 0), Position(0, 0.5, 0), Position(0, 0, 0.5)],
        ids=["x", "y", "z"],
    )
    def test_fill_box_rejects_off_grid_corners(self, corner):
        with pytest.raises(ValueError):
            fill_box(corner, corner + Position(4, 2, 1))

    def test_fill_box_rejects_degenerate_box(self):
        with pytest.raises(ValueError):
            fill_box(Position.ZERO, Position(0, 2, 1))

    def test_fill_single_brick_shortcut(self):
        m = fill_box(Position.ZERO, Position(10, 2, 1))
        assert m.brick_count == 1
        assert _BRICKS.get(Box(10, 2, 1)) is not None

    def test_fill_single_brick_shortcut_spans_corners(self):
        m = fill_box(Position(3, 1, 2), Position(13, 3, 3))
        assert m.brick_count == 1
        _assert_box(m.alignment_box, (3, 1, 2), (13, 3, 3))

    def test_fill_single_brick_shortcut_rotated(self):
        m = fill_box(Position.ZERO, Position(2, 10, 1))
        assert m.brick_count == 1
        assert m.width == 2 and m.depth == 10

    def test_fill_single_plate_shortcut(self):
        m = fill_box(Position.ZERO, Position(10, 4, PLATE))
        assert m.brick_count == 1

    def test_fill_single_course_multi_brick_is_documented_disconnected(
        self, filled_region
    ):
        # height 1-plate wider than any single brick: must be disconnected,
        # but it is still a valid grounded build covering the box.
        w, d = 20, 20
        m = fill_box(Position.ZERO, Position(w, d, PLATE))
        _assert_box(m.alignment_box, (0, 0, 0), (w, d, PLATE))
        assert _box_cells(w, d, PLATE) <= filled_region(m)
        assert m.is_valid()
        assert not m.is_connected()

    @pytest.mark.parametrize(
        "w,d,h,basename",
        [
            pytest.param(17, 1, 3, "depth_1_wall", id="depth-1-wall"),
            pytest.param(17, 2, 3, "depth_2_wall", id="depth-2-wall"),
            pytest.param(17, 5, 3 + 2 * PLATE, "deeper_box", id="big-box"),
        ],
    )
    def test_fill_box_ldraw_regression(self, w, d, h, basename, file_regression):
        m = fill_box(Position.ZERO, Position(w, d, h))
        assert m.is_valid()
        assert m.is_connected()
        file_regression.check(to_ldraw(m), extension=".ldr", basename=basename)


class TestFillSlope:
    TEST_DIMS = tuple(
        itertools.product(
            (1, 2, 3, 7),
            (1, 2, 3, 17),
            (1, 2, 3, 10, 2 * PLATE, 2 + 2 * PLATE),
        )
    )

    @pytest.mark.parametrize("w,d,h", TEST_DIMS)
    def test_fill_slope_fits_in_box_exactly_and_is_valid(self, w, d, h):
        m = fill_slope(Position.ZERO, Position(w, d, h))
        assert m.is_valid()
        _assert_box(m.alignment_box, (0, 0, 0), (w, d, h))
        _assert_box(m.bounding_box, (0, 0, 0), (w, d, h + STUD_HEIGHT))

    def test_fill_slope_spans_corners(self):
        m = fill_slope(Position(1, 2, 1), Position(5, 10, 5))
        assert not m.colliding_placements
        _assert_box(m.alignment_box, (1, 2, 1), (5, 10, 5))
        _assert_box(m.bounding_box, (1, 2, 1), (5, 10, 5 + STUD_HEIGHT))

    def test_fill_slope_corner_order_is_irrelevant(self):
        a, b = Position(1, 2, 1), Position(5, 10, 5)
        assert to_ldraw(fill_slope(a, b)) == to_ldraw(fill_slope(b, a))

    def test_fill_slope_single_part_shortcut(self):
        m = fill_slope(Position.ZERO, Position(4, 2, 1), Direction.RIGHT)
        assert m.brick_count == 1
        content = m.placements[0].content
        assert isinstance(content, Element)
        # Uses a 2x4 slope to fit the rotated footprint
        assert content.spec == _SLOPES.get(Box(2, 4, 1))

    @pytest.mark.parametrize(
        "toward",
        [Direction.FRONT, Direction.BACK, Direction.RIGHT, Direction.LEFT],
    )
    def test_fill_slope_accepts_horizontal_toward(self, toward):
        # horizontal directions succeed; UP/DOWN raise (checked separately below)
        m = fill_slope(Position.ZERO, Position(6, 6, 3), toward)
        assert m.placements  # non-empty wedge

    @pytest.mark.parametrize("toward", [Direction.UP, Direction.DOWN])
    def test_fill_slope_rejects_vertical(self, toward):
        with pytest.raises(ValueError):
            fill_slope(Position.ZERO, Position(6, 6, 3), toward)

    def test_fill_slope_is_a_descending_wedge(self, filled_region):
        # toward BACK: high at front (y=0), descending to the back.
        m = fill_slope(Position.ZERO, Position(4, 8, 4), Direction.BACK)
        profile = _height_at(filled_region(m), along="y")
        heights = [profile[y] for y in sorted(profile)]
        assert heights == sorted(heights, reverse=True)  # monotonically descending

    @pytest.mark.parametrize(
        "w,d,h,basename",
        [
            pytest.param(5, 6, 10, "perfect_slope", id="perfect-slope"),
            pytest.param(5, 7, 10, "one_stud_deeper", id="one-stud-deeper"),
            pytest.param(5, 6, 11, "one_brick_taller", id="one-brick-taller"),
            pytest.param(5, 10, 3, "shallow_slope", id="shallow-slope"),
            pytest.param(
                5, 7, 10 + 2 * PLATE, "slope_with_plates", id="slope-with-plates"
            ),
        ],
    )
    def test_fill_slope_ldraw_regression(self, w, d, h, basename, file_regression):
        m = fill_slope(Position.ZERO, Position(w, d, h))
        assert m.is_valid()
        assert m.is_connected()
        file_regression.check(to_ldraw(m), extension=".ldr", basename=basename)


class TestFillInvertedSlope:
    TEST_DIMS = TestFillSlope.TEST_DIMS

    @pytest.mark.parametrize("w,d,h", TEST_DIMS)
    def test_fill_inverted_slope_fits_in_box_exactly_and_is_valid(self, w, d, h):
        m = fill_inverted_slope(Position.ZERO, Position(w, d, h))
        assert m.is_valid()
        _assert_box(m.alignment_box, (0, 0, 0), (w, d, h))
        _assert_box(m.bounding_box, (0, 0, 0), (w, d, h + STUD_HEIGHT))

    def test_fill_inverted_slope_spans_corners(self):
        m = fill_inverted_slope(Position(1, 2, 1), Position(5, 10, 5))
        assert not m.colliding_placements
        _assert_box(m.alignment_box, (1, 2, 1), (5, 10, 5))
        _assert_box(m.bounding_box, (1, 2, 1), (5, 10, 5 + STUD_HEIGHT))

    def test_fill_inverted_slope_single_part_shortcut(self):
        m = fill_inverted_slope(Position.ZERO, Position(3, 1, 1), Direction.RIGHT)
        assert m.brick_count == 1
        content = m.placements[0].content
        assert isinstance(content, Element)
        # Uses a 1x3 inverted slope to fit the rotated footprint
        assert content.spec == _INVERTED_SLOPES.get(Box(1, 3, 1))

    @pytest.mark.parametrize(
        "toward",
        [Direction.FRONT, Direction.BACK, Direction.RIGHT, Direction.LEFT],
    )
    def test_fill_inverted_slope_accepts_horizontal_toward(self, toward):
        m = fill_inverted_slope(Position.ZERO, Position(6, 6, 3), toward)
        assert m.placements  # non-empty wedge

    @pytest.mark.parametrize("toward", [Direction.UP, Direction.DOWN])
    def test_fill_inverted_slope_rejects_vertical(self, toward):
        with pytest.raises(ValueError):
            fill_inverted_slope(Position.ZERO, Position(6, 6, 3), toward)

    def test_fill_inverted_slope_has_flat_top_and_sloped_underside(self, filled_region):
        # An inverted slope hangs from a full top slab, so the top face is flat
        # across the whole footprint while the underside is the sloped face.
        m = fill_inverted_slope(Position.ZERO, Position(4, 8, 4), Direction.BACK)
        cells = filled_region(m)
        tops = _height_at(cells, along="y")
        undersides = _min_height_at(cells, along="y")
        top = list(tops.values())
        assert max(top) - min(top) <= 1
        under = [undersides[y] for y in sorted(undersides)]
        assert under == sorted(under) or under == sorted(under, reverse=True)
        assert len(set(under)) > 1  # the underside actually slopes

    @pytest.mark.parametrize(
        "w,d,h,basename",
        [
            pytest.param(5, 4, 9, "inverted_perfect_slope", id="perfect-slope"),
            pytest.param(5, 5, 9, "inverted_one_stud_deeper", id="one-stud-deeper"),
            pytest.param(5, 4, 10, "inverted_one_brick_taller", id="one-brick-taller"),
            pytest.param(5, 10, 3, "inverted_shallow_slope", id="shallow-slope"),
            pytest.param(
                5,
                7,
                10 + 2 * PLATE,
                "inverted_slope_with_plates",
                id="slope-with-plates",
            ),
        ],
    )
    def test_fill_inverted_slope_ldraw_regression(
        self, w, d, h, basename, file_regression
    ):
        m = fill_inverted_slope(Position.ZERO, Position(w, d, h))
        assert m.is_valid()
        assert m.is_connected()
        file_regression.check(to_ldraw(m), extension=".ldr", basename=basename)
