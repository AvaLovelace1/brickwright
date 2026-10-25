"""Tests for the PartShape hierarchy."""

from fractions import Fraction

import pytest

from bricklayer.parts.shape import Box, Disc, Ell, Footprint, Length, Pane, Rod

# Every shape kind, as (shape, label, dimensions, transpose). A shape transposes
# to itself unless its width and depth are separately meaningful; an L-shaped
# part is excluded because turning it about z is not a mirror of its plate alone.
SHAPES = [
    (Box(4, 2, 3), "4x2x3", (4, 2, 3), Box(2, 4, 3)),
    (Footprint(4, 2), "4x2", (4, 2), Footprint(2, 4)),
    (Rod(4, 2), "⌀4x2", (4, 2), Rod(4, 2)),
    (Disc(4), "⌀4", (4,), Disc(4)),
    (Pane(4, 6), "4x6", (4, 6), Pane(4, 6)),
    (Length(4), "4L", (4,), Length(4)),
    (Ell(2, 1, 4, 1), "2x1-4x1", (2, 1, 4, 1), Ell(2, 1, 4, 1)),
]
SHAPE_IDS = [type(shape).__name__ for shape, *_ in SHAPES]


# The height-bearing shapes, each as (factory, whole-height call, 5/3-height call).
TALL_SHAPES = (
    (Box, lambda h: Box(1, 2, h)),
    (Rod, lambda h: Rod(2, h)),
    (Pane, lambda h: Pane(2, h)),
)


class TestPartShape:
    def test_shapes_are_value_objects(self):
        assert Box(4, 2, 1) == Box(4, 2, 1)
        assert Box(4, 2, 1) != Box(2, 4, 1)
        assert Footprint(4, 2) != Box(4, 2, 1)
        assert len({Box(4, 2, 1), Box(4, 2, 1), Footprint(4, 2)}) == 2

    @pytest.mark.parametrize("shape,label,_dims,_t", SHAPES, ids=SHAPE_IDS)
    def test_label_renders_the_dimensions(self, shape, label, _dims, _t):
        assert shape.label == label
        assert repr(shape) == f"{type(shape).__name__}({label})"

    @pytest.mark.parametrize("shape,_label,dims,_t", SHAPES, ids=SHAPE_IDS)
    def test_dimensions_are_the_fields_in_declaration_order(
        self, shape, _label, dims, _t
    ):
        assert shape.dimensions == dims

    @pytest.mark.parametrize("shape,_label,_dims,transposed", SHAPES, ids=SHAPE_IDS)
    def test_transpose_mirrors_width_and_depth_where_they_differ(
        self, shape, _label, _dims, transposed
    ):
        assert shape.transpose() == transposed

    def test_equal_lengths_are_the_same_shape_however_they_are_written(self):
        assert Length(1.5) == Length(Fraction(3, 2))
        assert Length(1.5).label == "3/2L"


class TestFractionalHeights:
    @pytest.mark.parametrize(
        "shape,make", TALL_SHAPES, ids=lambda s: getattr(s, "__name__", "")
    )
    def test_every_spelling_of_a_height_is_one_value(self, shape, make):
        assert 1 + 2 / 3 != 5 / 3  # the float trap this guards against
        variants = [
            make(h) for h in (5 / 3, 1 + 2 / 3, Fraction(5, 3), Fraction(10, 6))
        ]
        assert len(set(variants)) == 1
        assert len({hash(v) for v in variants}) == 1

    @pytest.mark.parametrize(
        "shape,make", TALL_SHAPES, ids=lambda s: getattr(s, "__name__", "")
    )
    def test_integer_and_float_whole_heights_have_equal_values_hashes_and_labels(
        self, shape, make
    ):
        assert make(3) == make(3.0)
        assert hash(make(3)) == hash(make(3.0))
        assert make(3).height == 3
        assert make(3).label.endswith("x3")

    @pytest.mark.parametrize(
        "shape,make", TALL_SHAPES, ids=lambda s: getattr(s, "__name__", "")
    )
    def test_fractional_height_reads_as_a_fraction_in_the_label(self, shape, make):
        assert make(5 / 3).label.endswith("x5/3")
        assert make(1 / 3).label.endswith("x1/3")

    @pytest.mark.parametrize(
        "shape,make", TALL_SHAPES, ids=lambda s: getattr(s, "__name__", "")
    )
    def test_a_non_plate_height_is_rejected(self, shape, make):
        with pytest.raises(ValueError, match="multiple of 1/3"):
            make(0.5)

    def test_dimensions_carry_the_fractional_height(self):
        assert Box(1, 2, 5 / 3).dimensions == (1, 2, Fraction(5, 3))
        assert Rod(2, 5 / 3).dimensions == (2, Fraction(5, 3))
