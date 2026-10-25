"""Tests for BrickLayer <-> LDraw coordinate conversion."""

import numpy as np
import pytest

from bricklayer import PLATE, Position, Vec3
from bricklayer.geometry import Mat3, Pose, Rotation, rotation_about
from bricklayer.ldraw.conversion import (
    LDrawVec,
    format_ldu,
    pose_from_ldraw,
    pose_from_type1,
    pose_to_ldraw,
)


class TestLdrawVec:
    def test_from_position_scales_and_swaps_axes(self):
        # x*20 LDU; y (height, negated) at 8 LDU per plate; z is BrickLayer's depth.
        assert LDrawVec.from_position(Position(1, 2, 1 + PLATE)) == LDrawVec(
            20, -32, 40
        )

    def test_to_position_round_trips_whole_placements(self):
        p = Position(3, 4, 2)
        assert LDrawVec.from_position(p).to_position() == p

    def test_to_position_round_trips_float_placements(self):
        p = Position(3.14, -2.71, 1.618)
        assert LDrawVec.from_position(p).to_position() == pytest.approx(p)

    def test_arithmetic_stays_in_the_ldraw_frame(self):
        assert LDrawVec(1, 2, 3) + LDrawVec(10, 20, 30) == LDrawVec(11, 22, 33)
        a: Vec3 = LDrawVec(0, 0, 0)
        b: Vec3 = Position(0, 0, 0)
        with pytest.raises(TypeError, match="coordinate systems"):
            a + b


class TestPoseFromLDraw:
    """The inverse of `pose_to_ldraw`: an LDraw type-1 line's matrix and
    translation back into a BrickLayer pose."""

    @pytest.mark.parametrize(
        "pose",
        [
            Pose.IDENTITY,
            Pose(translation=Position(2, 3, 1)),
            Pose(Rotation.DEG_90.matrix, Position(2, 3, PLATE)),
            Pose(Rotation.DEG_180.matrix, Position(-4, 5, 2)),
            Pose(Rotation.DEG_270.matrix, Position(0, 0, 2 * PLATE)),
        ],
    )
    def test_inverts_pose_to_ldraw(self, pose, assert_same_pose):
        rotation, translation = pose_to_ldraw(pose)
        recovered = pose_from_ldraw(Mat3.from_array(rotation), LDrawVec(*translation))
        assert_same_pose(recovered, pose)

    def test_reads_ldraw_axes_into_bricklayer_axes(self):
        # LDraw (X, Y, Z) = BrickLayer (x, -z, y): 20 LDU per stud across, 8 per
        # plate down.
        pose = pose_from_ldraw(Mat3.IDENTITY, LDrawVec(40, -24, 20))
        assert pose.translation == pytest.approx((2, 1, 1))

    def test_type1_numbers_give_the_translation_then_the_matrix(self):
        numbers = [40, -24, 20, 0, 0, 1, 0, 1, 0, -1, 0, 0]
        assert pose_from_type1(numbers) == pose_from_ldraw(
            Mat3.from_flattened(numbers[3:]), LDrawVec(40, -24, 20)
        )

    def test_rejects_a_reflection(self):
        # LDraw allows a mirrored type-1 line; a Pose is a proper rotation only.
        mirrored = Mat3(((-1, 0, 0), (0, 1, 0), (0, 0, 1)))
        with pytest.raises(ValueError, match="rotation"):
            pose_from_ldraw(mirrored, LDrawVec(0, 0, 0))

    def test_rejects_a_scale(self):
        with pytest.raises(ValueError, match="rotation"):
            pose_from_ldraw(Mat3(((2, 0, 0), (0, 2, 0), (0, 0, 2))), LDrawVec(0, 0, 0))

    def test_rejects_a_near_rotation_with_a_reflection(self):
        almost_mirrored = Mat3(((-1, 0, 0), (0, 1, 0), (0, 0, 1.0001)))
        with pytest.raises(ValueError, match="rotation"):
            pose_from_ldraw(almost_mirrored, LDrawVec(0, 0, 0))

    def test_rounded_rotations_round_trip(self):
        # The writer rounds each matrix entry to six decimals, which leaves an
        # arbitrary rotation slightly off orthogonal.
        rng = np.random.default_rng(0)
        for _ in range(200):
            direction = rng.normal(size=3)
            axis = Vec3(*(direction / np.linalg.norm(direction)).tolist())
            pose = Pose(rotation_about(axis, float(rng.uniform(0, 360))))
            rotation, _ = pose_to_ldraw(pose)
            written = Mat3.from_array(np.round(rotation, 6))
            recovered = pose_from_ldraw(written, LDrawVec(0, 0, 0))
            assert recovered.rotation.array == pytest.approx(
                pose.rotation.array, abs=1e-5
            )

    def test_reads_a_four_decimal_rotation(self):
        # Third-party files commonly write 45 degrees as 0.7071.
        quarter = Mat3(((0.7071, 0, 0.7071), (0, 1, 0), (-0.7071, 0, 0.7071)))
        pose = pose_from_ldraw(quarter, LDrawVec(0, 0, 0))
        expected = rotation_about(Vec3(0, 0, 1), -45)
        assert pose.rotation.array == pytest.approx(expected.array, abs=1e-6)

    def test_reads_official_rounded_minifigure_hand_rotation(self):
        # Official parts/16360p5i.dat, hand 3820.dat.
        matrix = Mat3(((0.985, -0.12, 0.12), (0.17, 0.696, -0.696), (0, 0.707, 0.707)))
        pose = pose_from_ldraw(matrix, LDrawVec(0, 0, 0))
        assert pose.rotation.array @ pose.rotation.array.T == pytest.approx(
            np.eye(3), abs=1e-12
        )

    def test_sub_tolerance_rounding_does_not_accumulate_in_nested_models(self):
        matrix = Mat3(((0.866025, 0, 0.5), (0, 1, 0), (-0.5, 0, 0.866025)))
        pose = pose_from_ldraw(matrix, LDrawVec(0, 0, 0))
        composed = Pose.IDENTITY
        for _ in range(100):
            composed = composed.compose(pose)
        assert composed.rotation.array @ composed.rotation.array.T == pytest.approx(
            np.eye(3), abs=1e-12
        )


class TestNumberFormatting:
    def test_integers_stay_bare(self):
        assert format_ldu(0) == "0"
        assert format_ldu(40.0) == "40"
        assert format_ldu(-3) == "-3"
        assert format_ldu(-0.0) == "0"

    def test_fixed_pose_floats_get_up_to_six_decimals(self):
        assert format_ldu(0.5) == "0.5"
        assert format_ldu(1 / 3) == "0.333333"
        assert format_ldu(-0.5) == "-0.5"

    def test_small_magnitudes_never_use_scientific_notation(self):
        # ``str(5e-05)`` is ``"5e-05"``, which LDraw parsers reject.
        for value in (5e-5, 1e-6, 9e-5, -7e-5):
            formatted = format_ldu(value)
            assert "e" not in formatted.lower()
            assert float(formatted) == round(value, 6)
