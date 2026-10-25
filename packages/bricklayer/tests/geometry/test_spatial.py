"""Tests for the grid primitives: positions, directions, poses, and volumes."""

from fractions import Fraction

import pytest

from bricklayer import (
    PLATE,
    Anchor,
    Axis,
    Cuboid,
    Direction,
    Mat3,
    Pose,
    Position,
    Rotation,
    Vec3,
    to_bricks,
    to_plates,
)
from bricklayer.geometry.linalg import rotation_about
from bricklayer.geometry.spatial import (
    require_grid_position,
    to_exact_height,
    to_whole_studs,
)

# extent -> (min, center, max) offset
_ANCHOR_OFFSETS = {1: (0, 0, 0), 2: (0, 0, 1), 3: (0, 1, 2), 4: (0, 1, 3), 5: (0, 2, 4)}


class TestConversions:
    def test_brick_plate_conversion(self):
        assert PLATE == 1 / 3
        assert to_plates(1) == 3  # one brick is three plate-heights
        assert to_plates(PLATE) == 1
        assert to_plates(1 + PLATE) == 4
        assert to_bricks(3) == 1
        assert to_bricks(1) == PLATE

    def test_to_plates_accepts_a_fraction(self):
        assert to_plates(Fraction(5, 3)) == 5
        assert to_plates(Fraction(2)) == 6

    def test_to_plates_rejects_non_plate_fractions(self):
        with pytest.raises(ValueError, match="multiple of 1/3"):
            to_plates(0.5)

    def test_to_whole_studs(self):
        assert to_whole_studs(3) == 3
        assert to_whole_studs(4 / 2) == 2
        with pytest.raises(ValueError, match="whole number"):
            to_whole_studs(0.5)

    def test_to_plates_round_down(self):
        assert to_plates(0.5, round_down=True) == 1
        assert to_plates(4 / 3, round_down=True) == 4
        assert to_plates(-0.5, round_down=True) == -2

    def test_to_whole_studs_round_down(self):
        assert to_whole_studs(1.6, round_down=True) == 1
        assert to_whole_studs(1.5, round_down=True) == 1
        assert to_whole_studs(5, round_down=True) == 5
        assert to_whole_studs(-1.5, round_down=True) == -2


class TestToExactHeight:
    def test_to_exact_height_is_exact(self):
        assert to_exact_height(5 / 3) == Fraction(5, 3)
        assert to_exact_height(1 / 3) == Fraction(1, 3)
        assert to_exact_height(Fraction(5, 3)) == Fraction(5, 3)

    def test_to_exact_height_keeps_whole_heights_whole(self):
        assert to_exact_height(3) == 3
        assert str(to_exact_height(3)) == "3"

    def test_to_exact_height_rejects_non_plate_fractions(self):
        for bad in (0.5, 1.1):
            with pytest.raises(ValueError, match="multiple of 1/3"):
                to_exact_height(bad)

    def test_to_exact_height_snaps_within_tolerance_only(self):
        assert to_exact_height(PLATE + 0.002) == Fraction(1, 3)
        with pytest.raises(ValueError, match="multiple of 1/3"):
            to_exact_height(PLATE + 0.02)


class TestPosition:
    def test_position_is_studs_and_a_brick_elevation(self):
        p = Position(2, 3, 1 + PLATE)
        assert (p.x, p.y) == (2, 3)  # studs
        assert p.z == 1 + PLATE  # 1 1/3 bricks
        assert Position(0, 0, 2).z == 2  # whole bricks are fine too

    def test_align_to_grid_floors_to_the_containing_cell(self):
        # An off-grid position floors to the grid cell that contains it:
        # x/y to whole studs, z to whole plates.
        p = Position(1.5, 2.5, 0.5)
        assert p.align_to_grid() == Position(1, 2, PLATE)

    def test_align_to_grid_floors_toward_negative_infinity(self):
        p = Position(-1.5, -2.5, -0.5)
        assert p.align_to_grid() == Position(-2, -3, to_bricks(-2))

    def test_different_coordinate_systems_do_not_compare_equal(self):
        # Two vector classes with the same components are still distinct.
        assert Vec3(1, 2, 3) != Position(1, 2, 3)

    def test_mixing_coordinate_systems_is_an_error(self):
        a: Vec3 = Vec3(1, 2, 3)
        b: Vec3 = Position(1, 2, 3)
        with pytest.raises(TypeError, match="coordinate systems"):
            a + b
        with pytest.raises(TypeError, match="coordinate systems"):
            a - b

    def test_operators_return_the_concrete_class(self):
        total = Vec3(1, 2, 3) + Vec3(1, 1, 1)
        assert total == Vec3(2, 3, 4)
        assert type(total) is Vec3
        delta = Position(1, 2, 1) - Position(0, 0, PLATE)
        assert type(delta) is Position
        assert tuple(delta) == pytest.approx((1, 2, 2 / 3))


class TestRequireGridPosition:
    def test_accepts_whole_studs_and_whole_plates(self):
        pos = Position(0, 0, 1 + PLATE)
        assert require_grid_position(pos) == pos

    @pytest.mark.parametrize(
        "bad",
        [
            Position(0.5, 0.5, 0.5),
            Position(0.5, 0, 0),
            Position(0, 0.5, 0),
            Position(0, 0, 0.25),
        ],
    )
    def test_rejects_fractional_studs_or_plates(self, bad):
        with pytest.raises(ValueError, match="integer"):
            require_grid_position(bad)


class TestAnchorOffset:
    """`Anchor.offset`: the (ox, oy) in studs from a footprint's min corner to
    the anchor point, floored toward min. The per-extent table is
    1->0/0/0, 2->0/0/1, 3->0/1/2, 4->0/1/3, 5->0/2/4 (min/center/max)."""

    @pytest.mark.parametrize("extent", [1, 2, 3, 4, 5])
    @pytest.mark.parametrize("half", [0, 1, 2])  # min / center / max
    def test_x_offsets(self, extent, half):
        # A 1-deep footprint `extent` wide; vary the x half-step.
        ox, oy = Anchor((half, 0)).offset(extent, 1)
        assert (ox, oy) == (_ANCHOR_OFFSETS[extent][half], 0)

    @pytest.mark.parametrize("extent", [1, 2, 3, 4, 5])
    @pytest.mark.parametrize("half", [0, 1, 2])
    def test_y_offsets(self, extent, half):
        # A 1-wide footprint `extent` deep; vary the y half-step.
        ox, oy = Anchor((0, half)).offset(1, extent)
        assert (ox, oy) == (0, _ANCHOR_OFFSETS[extent][half])

    def test_center_of_even_extent_floors_toward_front_right(self):
        # A 4x2 footprint's center floors to (1, 0): biased toward front/right.
        assert Anchor.CENTER.offset(4, 2) == (1, 0)

    def test_min_corner_is_always_the_origin(self):
        assert Anchor.FRONT_RIGHT.offset(7, 3) == (0, 0)

    def test_max_corner_is_the_far_stud(self):
        assert Anchor.BACK_LEFT.offset(7, 3) == (6, 2)


class TestDirection:
    def test_direction_values_are_vectors(self):
        assert Direction.UP.value == Vec3(0, 0, 1)
        assert Direction.DOWN.value == Vec3(0, 0, -1)
        assert Direction.LEFT.value == Vec3(1, 0, 0)
        assert Direction.FRONT.value == Vec3(0, -1, 0)
        # All six axis directions are present.
        assert len(Direction) == 6


class TestRotation:
    def test_quarter_turns(self):
        assert Rotation.DEG_0.quarter_turns == 0
        assert Rotation.DEG_90.quarter_turns == 1
        assert Rotation.DEG_180.quarter_turns == 2
        assert Rotation.DEG_270.quarter_turns == 3

    def test_facing_aliases_name_where_the_front_side_ends_up(self):
        # E.g. BACK is a half turn: the side that usually faces front (-y)
        # ends up facing back. A CCW quarter turn sends the front to the left.
        assert Rotation.FRONT is Rotation.DEG_0
        assert Rotation.LEFT is Rotation.DEG_90
        assert Rotation.BACK is Rotation.DEG_180
        assert Rotation.RIGHT is Rotation.DEG_270

    def test_facing_aliases_are_aliases_not_new_members(self):
        assert len(list(Rotation)) == 4

    def test_composition_wraps(self):
        assert Rotation.DEG_90 + Rotation.DEG_90 is Rotation.DEG_180
        assert Rotation.DEG_270 + Rotation.DEG_180 is Rotation.DEG_90

    def test_inverse_and_relative(self):
        assert -Rotation.DEG_90 is Rotation.DEG_270
        assert -Rotation.DEG_0 is Rotation.DEG_0
        assert Rotation.DEG_90 - Rotation.DEG_180 is Rotation.DEG_270

    def test_repeat(self):
        assert Rotation.DEG_90 * 3 is Rotation.DEG_270
        assert 2 * Rotation.DEG_90 is Rotation.DEG_180
        assert Rotation.DEG_90 * 0 is Rotation.DEG_0

    @pytest.mark.parametrize(
        ("rotation", "expected"),
        [
            (Rotation.DEG_0, Vec3(2, 3, 5)),
            (Rotation.DEG_90, Vec3(-3, 2, 5)),
            (Rotation.DEG_180, Vec3(-2, -3, 5)),
            (Rotation.DEG_270, Vec3(3, -2, 5)),
        ],
    )
    def test_rotate_is_a_ccw_quarter_turn_about_z(self, rotation, expected):
        assert rotation.rotate(Vec3(2, 3, 5)) == expected

    def test_rotate_preserves_the_vector_class(self):
        rotated = Rotation.DEG_90.rotate(Position(1, 0, 2))
        assert rotated == Position(0, 1, 2)
        assert type(rotated) is Position

    def test_rotation_matrices(self):
        vec = Vec3(1, 2, 3)
        for rotation in Rotation:
            assert rotation.matrix @ vec == rotation.rotate(vec)

    def test_from_matrix_inverts_matrix(self):
        for rotation in Rotation:
            assert Rotation.from_matrix(rotation.matrix) is rotation

    def test_from_matrix_rejects_non_quarter_turns(self):
        tilted = Mat3(((1, 0, 0), (0, 0, -1), (0, 1, 0)))
        with pytest.raises(ValueError, match="quarter-turn"):
            Rotation.from_matrix(tilted)


class TestPose:
    def test_accepts_arbitrary_valid_rotation(self):
        # 45 degrees about z is a proper rotation with irrational entries.
        Pose(rotation_about(Vec3(0, 0, 1), 45))

    def test_accepts_rotation_with_floating_point_error(self):
        cos = 0.7071067811865476
        sin = 0.7071067811865475
        Pose(Mat3(((cos, -sin, 0), (sin, cos, 0), (0, 0, 1))))

    def test_rejects_non_orthogonal_matrix(self):
        with pytest.raises(ValueError, match="rotation matrix"):
            Pose(Mat3(((1, 0, 0), (0, 1, 0), (0, 1, 1))))

    def test_rejects_scaling_matrix(self):
        with pytest.raises(ValueError, match="rotation matrix"):
            Pose(Mat3(((2, 0, 0), (0, 2, 0), (0, 0, 2))))

    def test_rejects_reflection(self):
        # Orthogonal but determinant -1.
        with pytest.raises(ValueError, match="rotation matrix"):
            Pose(Mat3(((-1, 0, 0), (0, 1, 0), (0, 0, 1))))

    def test_identity_is_grid_preserving_noop(self):
        p = Position(3, 4, 1 + PLATE)
        assert Pose.IDENTITY.apply(p) == p
        assert Pose.IDENTITY.is_grid_preserving

    def test_quarter_turn_matches_rotation_rotate(self):
        pose = Pose.from_rotation(Rotation.DEG_90)
        assert pose.apply(Position(2, 1, 0)) == Position(-1, 2, 0)
        assert pose.is_grid_preserving

    def test_quarter_turn_entries_are_exact(self):
        pose = Pose.from_rotation(Rotation.DEG_270)
        assert all(v in (-1, 0, 1) for row in pose.rotation for v in row)

    def test_translation_composes_after_rotation(self):
        pose = Pose(translation=Position(10, 0, 1)).compose(
            Pose.from_rotation(Rotation.DEG_180)
        )
        # compose = self ∘ other: rotate first, then translate.
        assert pose.apply(Position(1, 1, 0)) == Position(9, -1, 1)

    def test_apply_converts_height_units_for_axis_mixing_rotations(self):
        # 90 degrees about x (row-major, stud units): (x, y, z) -> (x, -z, y).
        about_x = Pose(Mat3(((1, 0, 0), (0, 0, -1), (0, 1, 0))))
        # 1 brick of height (6/5 studs) becomes 6/5 studs of depth;
        # 1 stud of depth becomes 1 stud of height = 5/6 brick.
        assert tuple(about_x.apply(Position(0, 0, 1))) == pytest.approx((0, -6 / 5, 0))
        assert tuple(about_x.apply(Position(0, 1, 0))) == pytest.approx((0, 0, 5 / 6))
        assert not about_x.is_grid_preserving

    def test_apply_works_on_sequences(self):
        pose = Pose.from_rotation(Rotation.DEG_90)
        positions = [Position(1, 0, 0), Position(0, 1, 0)]
        transformed = pose.apply(positions)
        assert transformed == (Position(0, 1, 0), Position(-1, 0, 0))

    def test_fractional_translation_is_not_grid_preserving(self):
        half = Pose(translation=Position(0.5, 0, 0))
        assert not half.is_grid_preserving

    def test_plate_translation_is_grid_preserving(self):
        assert Pose(translation=Position(1, 2, PLATE)).is_grid_preserving
        assert not Pose(translation=Position(0, 0, 1 / 6)).is_grid_preserving

    def test_quarter_turn_rotations_are_grid_preserving(self):
        for rotation in Rotation:
            assert Pose.from_rotation(rotation).is_grid_preserving


class TestCuboid:
    def test_rejects_negative_sizes(self):
        with pytest.raises(ValueError, match="non-negative"):
            Cuboid(Position(-1, 1, 1))
        with pytest.raises(ValueError, match="non-negative"):
            Cuboid(Position(1, -1, 1))
        with pytest.raises(ValueError, match="non-negative"):
            Cuboid(Position(1, 1, -1))

    def test_unposed_cuboid_is_centered_at_the_origin(self):
        box = Cuboid(Position(2, 1, 1))
        assert box.center == Position(0, 0, 0)
        assert box.aabb == (Position(-1, -0.5, -0.5), Position(1, 0.5, 0.5))

    def test_spanning_has_the_given_corners(self):
        box = Cuboid.spanning(Position(1, 2, 1), Position(4, 3, 2))
        assert box.size == Position(3, 1, 1)
        assert box.aabb == (Position(1, 2, 1), Position(4, 3, 2))

    def test_is_empty_when_any_dimension_is_zero(self):
        assert Cuboid(Position(0, 1, 1)).is_empty
        assert Cuboid(Position(1, 0, 1)).is_empty
        assert Cuboid(Position(1, 1, 0)).is_empty
        assert not Cuboid(Position(1, 1, 1)).is_empty

    def test_center_is_the_midpoint(self):
        box = Cuboid.spanning(Position(1, 1, 0), Position(3, 2, 1))
        assert box.center == Position(2, 1.5, 0.5)

    def test_quarter_turn_swaps_the_footprint(self):
        # The unposed box is centered on the origin, spanning +-(1, 0.5, 0.5);
        # a quarter turn swaps its x/y extents, then the translation shifts it.
        pose = Pose(Rotation.DEG_90.matrix, Position(5, 0, 0))
        box = Cuboid(Position(2, 1, 1), pose)
        assert box.aabb == (Position(4.5, -1, -0.5), Position(5.5, 1, 0.5))

    def test_axis_mixing_pose_scales_height_units(self):
        # 90 degrees about x: depth becomes height, so a 1-stud edge is
        # 5/6 of a brick tall in the tipped-over box.
        about_x = Pose(Mat3(((1, 0, 0), (0, 0, -1), (0, 1, 0))))
        box = Cuboid(Position(1, 1, PLATE), about_x)
        lo, hi = box.aabb
        assert tuple(lo) == pytest.approx((-0.5, -1 / 5, -5 / 12))
        assert tuple(hi) == pytest.approx((0.5, 1 / 5, 5 / 12))

    def test_transformed_composes_the_pose(self):
        box = Cuboid.spanning(Position(0, 0, 0), Position(1, 1, 1))
        moved = box.transformed(Pose(translation=Position(2, 0, PLATE)))
        lo, hi = moved.aabb
        assert tuple(lo) == pytest.approx((2, 0, PLATE))
        assert tuple(hi) == pytest.approx((3, 1, 1 + PLATE))

    def test_corners_enumerate_all_eight(self):
        box = Cuboid.spanning(Position(0, 0, 0), Position(1, 2, 1))
        assert len(set(box.corners)) == 8
        assert Position(0, 0, 0) in box.corners
        assert Position(1, 2, 1) in box.corners

    def test_corners_are_correct_for_axis_mixing_pose(self):
        about_x = Pose(Mat3(((1, 0, 0), (0, 0, -1), (0, 1, 0))))
        box = Cuboid(Position(1, 1, PLATE), about_x)
        corners = set(box.corners)
        assert len(corners) == 8
        assert any(tuple(c) == pytest.approx((0.5, -1 / 5, 5 / 12)) for c in corners)
        assert any(tuple(c) == pytest.approx((-0.5, 1 / 5, -5 / 12)) for c in corners)


class TestRepr:
    def test_position_is_positional(self):
        assert repr(Position(1, 2, 0)) == "Position(1, 2, 0)"

    def test_enums_render_as_bare_member(self):
        assert repr(Rotation.DEG_90) == "Rotation.DEG_90"
        assert repr(Direction.UP) == "Direction.UP"
        assert repr(Anchor.CENTER) == "Anchor.CENTER"
        assert repr(Axis.X) == "Axis.X"
