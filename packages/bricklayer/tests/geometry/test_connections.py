"""Tests for connector types and mating rules."""

import math
import pickle
import random
from copy import deepcopy

import pytest

from bricklayer import (
    Direction,
    Mat3,
    Pose,
    Position,
    Rotation,
    Vec3,
)
from bricklayer.geometry.connections import (
    GRID_FAMILIES,
    Ball,
    Connector,
    ConnectorType,
    Cylindrical,
    Fixed,
    JointKind,
    Matings,
    Mounting,
    Prismatic,
    Revolute,
    connectors_mate,
    fit_mounting,
    joint_pose,
    mark_compatible,
    mate_pose,
    mated,
    mating_rule,
    mounting_pose,
    same_connector,
)
from bricklayer.geometry.linalg import is_orthogonal, rotation_about
from bricklayer.geometry.spatial import BUILD_TOLERANCE, to_bricks
from bricklayer.ldraw.partdata import get_connector_type

STUD = get_connector_type("stud")
ANTISTUD = get_connector_type("antistud")


def _assert_same_matrix(a: Mat3, b: Mat3) -> None:
    """Assert two matrices are equal up to float noise."""
    for row_a, row_b in zip(a.entries, b.entries):
        for x, y in zip(row_a, row_b):
            assert abs(x - y) < 1e-9


class TestConnectorTypeFamily:
    def test_catalog_types_preserve_identity_when_copied_or_pickled(self):
        for kind in (STUD, ANTISTUD, get_connector_type("axle")):
            assert deepcopy(kind) is kind
            assert pickle.loads(pickle.dumps(kind)) is kind

    def test_deepcopy_preserves_authored_type_mating_rules(self):
        a, b = ConnectorType("a"), ConnectorType("b")
        mark_compatible(a, b, joint=JointKind.REVOLUTE)
        rule = mating_rule(deepcopy(a), deepcopy(b))
        assert rule is not None
        assert rule.joint is JointKind.REVOLUTE

    def test_pickling_a_separate_type_does_not_alias_a_catalog_name(self):
        custom = ConnectorType("stud")
        restored = pickle.loads(pickle.dumps(custom))
        assert restored is not STUD
        assert restored.name == "stud"
        assert restored.family == "authored"

    def test_defaults_to_authored_without_grid(self):
        conn_type = ConnectorType("pane_tab")
        assert conn_type.family == "authored"
        assert conn_type.uses_grid is False

    def test_records_the_family_it_is_given(self):
        assert ConnectorType("stud", family="stud").family == "stud"

    def test_grid_families_are_stud_and_hole(self):
        assert GRID_FAMILIES == frozenset({"stud", "hole"})

    def test_compares_by_identity_not_value(self):
        assert ConnectorType("stud", family="stud") != ConnectorType(
            "stud", family="stud"
        )


class TestConnector:
    def test_rounded_connector_frame_stays_orthonormal_when_composed(self):
        c = Connector(STUD, Position.ZERO, Vec3(0.707107, 0, 0.707107), Vec3(0, 1, 0))
        frame = Pose(c.frame)
        assert frame.inverse.compose(frame).rotation.flatten() == pytest.approx(
            Mat3.IDENTITY.flatten()
        )

    def test_direction_axes_normalize_to_their_vectors(self):
        c = Connector(STUD, Position(0.5, 0.5, 1), Direction.UP)
        assert c.axis == Vec3(0, 0, 1)

    def test_axis_may_be_any_unit_vector(self):
        tilted = Vec3(0.6, 0.0, 0.8)
        c = Connector(STUD, Position(0, 0, 0), tilted)
        assert c.axis == tilted

    def test_non_unit_axis_is_rejected(self):
        with pytest.raises(ValueError, match="unit vector"):
            Connector(STUD, Position(0, 0, 0), Vec3(0, 0, 2))

    def test_side_defaults_orthogonal_to_the_axis(self):
        c = Connector(STUD, Position(0, 0, 0), Direction.UP)
        assert is_orthogonal(c.side, c.axis)

    def test_derives_an_orthogonal_side_for_a_nearly_downward_axis(self):
        axis = Vec3(1e-3, 0, -math.sqrt(1 - 1e-6))
        conn = Connector(ConnectorType("t"), Position.ZERO, axis)
        assert is_orthogonal(conn.axis, conn.side)

    def test_side_must_be_orthogonal_to_the_axis(self):
        with pytest.raises(ValueError, match="orthogonal"):
            Connector(STUD, Position(0, 0, 0), Direction.UP, Direction.UP)

    def test_length_defaults_to_zero(self):
        c = Connector(STUD, Position(0, 0, 0), Direction.UP)
        assert c.length == 0

    def test_negative_length_is_rejected(self):
        with pytest.raises(ValueError, match="length"):
            Connector(STUD, Position(0, 0, 0), Direction.UP, length=-1)

    def test_is_immutable(self):
        c = Connector(STUD, Position(0.5, 0.5, 1), Direction.UP)
        with pytest.raises(AttributeError, match="immutable"):
            c.axis = Vec3(1, 0, 0)
        with pytest.raises(AttributeError, match="immutable"):
            del c.position

    def test_compares_by_identity(self):
        # Same type, position, and axis, but distinct points on (potentially)
        # different parts: never equal, and distinct set members.
        a = Connector(STUD, Position(0.5, 0.5, 1), Direction.UP)
        b = Connector(STUD, Position(0.5, 0.5, 1), Direction.UP)
        assert a != b
        assert len({a, b}) == 2

    def test_transformed_maps_position_and_axis(self):
        c = Connector(STUD, Position(0.5, 0.5, 0), Direction.UP)
        pose = Pose(Rotation.DEG_180.matrix, Position(2, 2, 1))
        moved = c.transformed(pose)
        assert moved.position == Position(0.5 + 1, 0.5 + 1, 1)
        assert moved.axis == Vec3(0, 0, 1)

    def test_transformed_carries_the_roll(self):
        # An explicit roll (side) rotates with the part under transform.
        c = Connector(STUD, Position(0, 0, 0), Direction.UP, Direction.LEFT)
        moved = c.transformed(Pose(rotation_about(Vec3(0, 0, 1), 90)))
        assert moved.axis == Vec3(0, 0, 1)
        assert moved.side == Vec3(0, 1, 0)

    def test_transformed_carries_the_length(self):
        c = Connector(STUD, Position(0, 0, 0), Direction.UP, length=3)
        moved = c.transformed(Pose(translation=Position(1, 0, 0)))
        assert moved.length == 3

    def test_grid_marked_requires_vertical_axis_and_uses_grid_and_grid_aligned(self):
        on = Connector(STUD, Position(0.5, 1 + 0.5, 1), Direction.UP)
        # Whole-stud positions also mark: a centered odd footprint puts its
        # studs there. Only genuinely off-lattice positions are excluded.
        on_whole = Connector(STUD, Position(1, 0.5, 1), Direction.UP)
        off = Connector(STUD, Position(0.75, 0.5, 1), Direction.UP)
        snot = Connector(STUD, Position(0.5, 0.5, 1), Direction.LEFT)
        off_plate = Connector(STUD, Position(0.5, 0.5, 1 / 7), Direction.UP)
        no_use_grid = Connector(
            ConnectorType("not a stud", uses_grid=False),
            Position(0.5, 1 + 0.5, 1),
            Direction.UP,
        )
        assert on.is_grid_marked
        assert on_whole.is_grid_marked
        assert not off.is_grid_marked
        assert not snot.is_grid_marked
        assert not off_plate.is_grid_marked
        assert not no_use_grid.is_grid_marked

    def test_grid_marked_requires_cardinal_side(self):
        cardinal = Connector(STUD, Position(0.5, 0.5, 1), Direction.UP, Direction.LEFT)
        diagonal_side = Vec3(math.sqrt(0.5), math.sqrt(0.5), 0)
        off_axis = Connector(STUD, Position(0.5, 0.5, 1), Direction.UP, diagonal_side)
        assert cardinal.is_grid_marked
        assert not off_axis.is_grid_marked


class TestSameConnector:
    def test_matches_by_type_position_axis_and_roll(self):
        a = Connector(STUD, Position(0, 0, 0), Direction.UP, Direction.LEFT)
        b = Connector(STUD, Position(0, 0, 0), Direction.UP, Direction.LEFT)
        rolled = Connector(STUD, Position(0, 0, 0), Direction.UP, Direction.BACK)
        assert same_connector(a, b)
        assert not same_connector(a, rolled)

    def test_distinguishes_by_length(self):
        a = Connector(STUD, Position(0, 0, 0), Direction.UP, length=2)
        b = Connector(STUD, Position(0, 0, 0), Direction.UP)
        assert not same_connector(a, b)

    def test_tolerates_float_noise(self):
        # Two descriptions of the same physical point may carry sub-BUILD_TOLERANCE
        # noise when computed along different paths (e.g. a hand-built
        # connector vs. the part's own, or differently composed poses).
        noise = BUILD_TOLERANCE / 10
        a = Connector(STUD, Position(0, 0, 1), Direction.UP, length=1)
        b = Connector(
            STUD,
            Position(noise, -noise, 1 + noise),
            Vec3(noise, 0, 1),
            length=1 + noise,
        )
        assert same_connector(a, b)
        assert same_connector(b, a)

    def test_distinguishes_nearby_but_distinct_points(self):
        a = Connector(STUD, Position(0, 0, 0), Direction.UP)
        b = Connector(STUD, Position(100 * BUILD_TOLERANCE, 0, 0), Direction.UP)
        assert not same_connector(a, b)


@pytest.mark.usefixtures("patch_connector_rules_registry")
class TestMated:
    @staticmethod
    def _sliding_pair(joint):
        a, b = ConnectorType("a"), ConnectorType("b")
        mark_compatible(a, b, joint=joint)
        return a, b

    """One scan reporting both the joined groups and the connectors in use."""

    @staticmethod
    def _pair():
        """Two freshly registered, compatible connector types."""
        a, b = ConnectorType("a"), ConnectorType("b")
        mark_compatible(a, b, joint=JointKind.FIXED)
        return a, b

    def test_reports_the_mated_pairs(self):
        t, u = self._pair()
        tab = Connector(t, Position(0, 0, 1), Direction.UP, Direction.LEFT)
        slot = Connector(u, Position(0, 0, 1), Direction.UP, Direction.LEFT)

        assert mated([[tab], [slot]]).pairs == ((0, 1),)

    def test_reports_the_connectors_in_use(self):
        t, u = self._pair()
        tab = Connector(t, Position(0, 0, 1), Direction.UP, Direction.LEFT)
        slot = Connector(u, Position(0, 0, 1), Direction.UP, Direction.LEFT)

        assert mated([[tab], [slot]]).connectors == frozenset({tab, slot})

    def test_holds_the_very_objects_passed_in(self):
        t, u = self._pair()
        tab = Connector(t, Position(0, 0, 1), Direction.UP, Direction.LEFT)
        slot = Connector(u, Position(0, 0, 1), Direction.UP, Direction.LEFT)

        found = mated([[tab], [slot]]).connectors

        assert any(c is tab for c in found)
        assert any(c is slot for c in found)

    def test_an_unmated_connector_is_absent(self):
        t, u = self._pair()
        tab = Connector(t, Position(0, 0, 1), Direction.UP, Direction.LEFT)
        slot = Connector(u, Position(0, 0, 1), Direction.UP, Direction.LEFT)
        lone = Connector(u, Position(50, 50, 50), Direction.UP, Direction.LEFT)

        assert lone not in mated([[tab], [slot, lone]]).connectors

    def test_connectors_in_one_group_never_mate(self):
        t, u = self._pair()
        tab = Connector(t, Position(0, 0, 1), Direction.UP, Direction.LEFT)
        slot = Connector(u, Position(0, 0, 1), Direction.UP, Direction.LEFT)

        result = mated([[tab, slot]])

        assert isinstance(result, Matings)
        assert result.pairs == ()
        assert result.connectors == frozenset()

    def test_a_connector_mating_several_others_pairs_with_each(self):
        t, u = self._pair()
        tab = Connector(t, Position(0, 0, 1), Direction.UP, Direction.LEFT)
        first = Connector(u, Position(0, 0, 1), Direction.UP, Direction.LEFT)
        second = Connector(u, Position(0, 0, 1), Direction.UP, Direction.LEFT)

        result = mated([[tab], [first], [second]])

        assert result.pairs == ((0, 1), (0, 2))
        assert any(c is tab for c in result.connectors)
        assert any(c is first for c in result.connectors)
        assert any(c is second for c in result.connectors)

    def test_no_groups_find_nothing(self):
        result = mated([])

        assert result.pairs == ()
        assert result.connectors == frozenset()

    @pytest.mark.usefixtures("patch_connector_rules_registry")
    @pytest.mark.parametrize("boundary", [-1, 0, 1])
    @pytest.mark.parametrize("joint", [JointKind.PRISMATIC, JointKind.CYLINDRICAL])
    def test_sliding_mates_across_a_cell_boundary_within_tolerance(
        self, boundary, joint
    ):
        moving, fixed = ConnectorType("moving"), ConnectorType("fixed")
        mark_compatible(moving, fixed, joint=joint)
        a = Connector(moving, Position(boundary - 0.002, 0, 0), Direction.UP, length=1)
        b = Connector(fixed, Position(boundary + 0.002, 0, 0.5), Direction.UP, length=1)
        assert connectors_mate(a, b)
        assert mated([[a], [b]]) == Matings(((0, 1),), frozenset({a, b}))

    def test_mated_finds_spans_that_overlap_without_reaching_either_point(self):
        t, u = self._sliding_pair(JointKind.CYLINDRICAL)
        axle = Connector(t, Position(1, 0.95, 0.5), Direction.BACK, length=1.875)
        hole = Connector(u, Position(1, 3.05, 0.5), Direction.BACK, length=0.5)
        assert connectors_mate(axle, hole)
        assert mated([[axle], [hole]]).pairs == ((0, 1),)

    def test_mated_finds_zero_length_connectors_a_cell_apart(self):
        t, u = self._sliding_pair(JointKind.CYLINDRICAL)
        a = Connector(t, Position(0.9, 0, 0), Direction.LEFT)
        b = Connector(u, Position(1.1, 0, 0), Direction.LEFT)
        assert connectors_mate(a, b)
        assert mated([[a], [b]]).pairs == ((0, 1),)

    def test_mated_agrees_with_connectors_mate_over_random_slides(self):
        t, u = self._sliding_pair(JointKind.CYLINDRICAL)
        rng = random.Random(0)
        for _ in range(2000):
            x = rng.uniform(-3, 3)
            a = Connector(
                t, Position(x, 0.5, 0.3), Direction.LEFT, length=rng.uniform(0, 2)
            )
            b = Connector(
                u,
                Position(x + rng.uniform(-4, 4), 0.5, 0.3),
                Direction.LEFT,
                length=rng.uniform(0, 2),
            )
            assert bool(mated([[a], [b]]).pairs) == connectors_mate(a, b)


@pytest.mark.usefixtures("patch_connector_rules_registry")
class TestConnectorsMate:
    """The per-joint-kind mating rules: which frames a registered pair accepts."""

    @staticmethod
    def _pair(joint):
        a, b = ConnectorType("a"), ConnectorType("b")
        mark_compatible(a, b, joint=joint)
        return a, b

    def test_unregistered_types_never_mate(self):
        a = Connector(ConnectorType("a"), Position(0, 0, 0), Direction.UP)
        b = Connector(ConnectorType("b"), Position(0, 0, 0), Direction.DOWN)
        assert not connectors_mate(a, b)

    def test_fixed_mates_coincident_with_aligned_axis_and_side(self):
        t, u = self._pair(JointKind.FIXED)
        a = Connector(t, Position(1, 2, 1), Direction.UP, Direction.LEFT)
        b = Connector(u, Position(1, 2, 1), Direction.UP, Direction.LEFT)
        assert connectors_mate(a, b)
        assert connectors_mate(b, a)

    def test_fixed_requires_coincident_positions(self):
        t, u = self._pair(JointKind.FIXED)
        a = Connector(t, Position(1, 2, 1), Direction.UP, Direction.LEFT)
        b = Connector(u, Position(1, 2, 2), Direction.UP, Direction.LEFT)
        assert not connectors_mate(a, b)

    def test_fixed_requires_aligned_axes(self):
        t, u = self._pair(JointKind.FIXED)
        a = Connector(t, Position(0, 0, 0), Direction.UP, Direction.LEFT)
        b = Connector(u, Position(0, 0, 0), Direction.DOWN, Direction.LEFT)
        assert not connectors_mate(a, b)

    def test_fixed_requires_aligned_sides(self):
        t, u = self._pair(JointKind.FIXED)
        a = Connector(t, Position(0, 0, 0), Direction.UP, Direction.LEFT)
        rolled = Connector(u, Position(0, 0, 0), Direction.UP, Direction.BACK)
        assert not connectors_mate(a, rolled)

    def test_revolute_ignores_the_side(self):
        t, u = self._pair(JointKind.REVOLUTE)
        a = Connector(t, Position(0, 0, 0), Direction.UP, Direction.LEFT)
        rolled = Connector(u, Position(0, 0, 0), Direction.UP, Direction.BACK)
        assert connectors_mate(a, rolled)

    def test_revolute_mates_with_opposing_axes(self):
        t, u = self._pair(JointKind.REVOLUTE)
        a = Connector(t, Position(0, 0, 0), Direction.UP, Direction.LEFT)
        b = Connector(u, Position(0, 0, 0), Direction.DOWN, Direction.LEFT)
        assert connectors_mate(a, b)

    def test_revolute_requires_coincident_positions_and_aligned_axes(self):
        t, u = self._pair(JointKind.REVOLUTE)
        a = Connector(t, Position(0, 0, 0), Direction.UP)
        offset = Connector(u, Position(1, 0, 0), Direction.UP)
        askew = Connector(u, Position(0, 0, 0), Direction.RIGHT)
        assert not connectors_mate(a, offset)
        assert not connectors_mate(a, askew)

    def test_ball_needs_only_coincident_positions(self):
        t, u = self._pair(JointKind.BALL)
        a = Connector(t, Position(0, 0, 0), Direction.UP)
        askew = Connector(u, Position(0, 0, 0), Vec3(0.6, 0.0, 0.8))
        offset = Connector(u, Position(0, 0, 1), Direction.DOWN)
        assert connectors_mate(a, askew)
        assert not connectors_mate(a, offset)


@pytest.mark.usefixtures("patch_connector_rules_registry")
class TestSlidingMate:
    """Prismatic and cylindrical joints: mating across a slide along the axis."""

    @staticmethod
    def _pair(joint):
        a, b = ConnectorType("a"), ConnectorType("b")
        mark_compatible(a, b, joint=joint)
        return a, b

    def test_prismatic_mates_coincident_at_zero_length(self):
        t, u = self._pair(JointKind.PRISMATIC)
        a = Connector(t, Position(0, 0, 0), Direction.LEFT, Direction.UP)
        b = Connector(u, Position(0, 0, 0), Direction.LEFT, Direction.UP)
        assert connectors_mate(a, b)

    def test_prismatic_requires_aligned_sides(self):
        t, u = self._pair(JointKind.PRISMATIC)
        a = Connector(t, Position(0, 0, 0), Direction.LEFT, Direction.UP)
        rolled = Connector(u, Position(0, 0, 0), Direction.LEFT, Direction.BACK)
        assert not connectors_mate(a, rolled)

    def test_prismatic_mates_across_a_slide_within_the_length(self):
        t, u = self._pair(JointKind.PRISMATIC)
        bar = Connector(t, Position(0, 0, 0), Direction.LEFT, Direction.UP, length=4)
        clip = Connector(u, Position(3, 0, 0), Direction.LEFT, Direction.UP)
        assert connectors_mate(bar, clip)
        assert connectors_mate(clip, bar)

    def test_slide_beyond_the_length_does_not_mate(self):
        t, u = self._pair(JointKind.PRISMATIC)
        bar = Connector(t, Position(0, 0, 0), Direction.LEFT, Direction.UP, length=4)
        clip = Connector(u, Position(5, 0, 0), Direction.LEFT, Direction.UP)
        assert not connectors_mate(bar, clip)

    def test_slide_span_reaches_both_ways_from_the_point(self):
        t, u = self._pair(JointKind.PRISMATIC)
        bar = Connector(t, Position(0, 0, 0), Direction.LEFT, Direction.UP, length=4)
        ahead = Connector(u, Position(1, 0, 0), Direction.LEFT, Direction.UP)
        behind = Connector(u, Position(-1, 0, 0), Direction.LEFT, Direction.UP)
        assert connectors_mate(bar, ahead)
        assert connectors_mate(bar, behind)

    def test_slide_off_the_axis_does_not_mate(self):
        t, u = self._pair(JointKind.PRISMATIC)
        bar = Connector(t, Position(0, 0, 0), Direction.LEFT, Direction.UP, length=4)
        clip = Connector(u, Position(2, 1, 0), Direction.LEFT, Direction.UP)
        assert not connectors_mate(bar, clip)

    def test_segments_mate_when_they_overlap_not_when_disjoint(self):
        t, u = self._pair(JointKind.PRISMATIC)
        bar = Connector(t, Position(0, 0, 0), Direction.LEFT, Direction.UP, length=4)
        overlapping = Connector(
            u, Position(3, 0, 0), Direction.LEFT, Direction.UP, length=4
        )
        # Spans of 4 and 2 reach 6 studs between them, so 7 apart is disjoint.
        disjoint = Connector(
            u, Position(7, 0, 0), Direction.LEFT, Direction.UP, length=2
        )
        assert connectors_mate(bar, overlapping)
        assert not connectors_mate(bar, disjoint)

    def test_vertical_slide_measures_in_studs(self):
        # z is stored in bricks; the length cap is in studs along the axis.
        t, u = self._pair(JointKind.PRISMATIC)
        post = Connector(t, Position(0, 0, 0), Direction.UP, Direction.LEFT, length=2)
        near = Connector(u, Position(0, 0, to_bricks(5)), Direction.UP, Direction.LEFT)
        far = Connector(u, Position(0, 0, to_bricks(6)), Direction.UP, Direction.LEFT)
        assert connectors_mate(post, near)
        assert not connectors_mate(post, far)

    def test_cylindrical_ignores_the_side(self):
        t, u = self._pair(JointKind.CYLINDRICAL)
        rod = Connector(t, Position(0, 0, 0), Direction.LEFT, Direction.UP, length=4)
        rolled = Connector(u, Position(3, 0, 0), Direction.LEFT, Direction.BACK)
        assert connectors_mate(rod, rolled)

    def test_cylindrical_mates_with_opposing_axes(self):
        t, u = self._pair(JointKind.CYLINDRICAL)
        bar = Connector(t, Position(0, 0, 0), Direction.LEFT, Direction.UP, length=4)
        ring = Connector(u, Position(3, 0, 0), Direction.RIGHT, Direction.UP, length=1)
        assert connectors_mate(bar, ring)
        assert connectors_mate(ring, bar)

    def test_cylindrical_rejects_skew_axes(self):
        t, u = self._pair(JointKind.CYLINDRICAL)
        rod = Connector(t, Position(0, 0, 0), Direction.LEFT, Direction.UP, length=4)
        askew = Connector(u, Position(3, 0, 0), Direction.UP)
        assert not connectors_mate(rod, askew)


class TestMatePose:
    def test_seats_aligned_and_coincident(self):
        # An antistud onto an unrotated stud: frames align (both up), no roll.
        conn = Connector(ANTISTUD, Position(0.5, 0.5, 0), Direction.UP)
        target = Connector(STUD, Position(2.5, 3.5, 1), Direction.UP)
        pose = mate_pose(conn, target)
        assert pose.rotation == Mat3.IDENTITY
        assert pose.apply(conn.position) == target.position

    def test_carries_the_targets_roll(self):
        # Seating onto a stud spun 45 deg about its axis rolls the incoming
        # connector by the same 45 deg, so a placed part inherits that roll.
        conn = Connector(ANTISTUD, Position(0.5, 0.5, 0), Direction.UP)
        spin = Pose(rotation_about(Vec3(0, 0, 1), 45))
        target = Connector(STUD, Position(0.5, 0.5, 0), Direction.UP).transformed(spin)
        pose = mate_pose(conn, target)
        _assert_same_matrix(pose.rotation, rotation_about(Vec3(0, 0, 1), 45))


class TestMountingPose:
    @pytest.mark.parametrize("angle,flip", [(0, True), (90, True), (37, False)])
    def test_axial_clocking_and_flip(self, angle, flip):
        at = Connector(
            ConnectorType("t"), Position(1, 0, 2), Direction.UP, Direction.LEFT
        )
        pose = mounting_pose(
            Mounting(angle=angle, flip=flip), at, JointKind.CYLINDRICAL
        )
        expected = rotation_about(at.axis, angle)
        if flip:
            expected = expected @ rotation_about(at.side, 180)
        _assert_same_matrix(pose.rotation, expected)
        assert pose.apply(at.position) == at.position

    def test_mounting_rejects_a_slide_on_a_hinge(self):
        at = Connector(ConnectorType("t"), Position.ZERO, Direction.UP)
        with pytest.raises(ValueError, match="REVOLUTE"):
            mounting_pose(Mounting(offset=1), at, JointKind.REVOLUTE)


class TestJointPose:
    def test_slide_uses_uniform_studs(self):
        assert joint_pose(Prismatic(1)).translation == Position.from_stud_units(
            Vec3(0, 0, 1)
        )

    def test_ball_swing_and_twist_use_the_joint_frame(self):
        pose = joint_pose(Ball(swing_x=30, twist=45))
        expected = rotation_about(Vec3(1, 0, 0), 30) @ rotation_about(Vec3(0, 0, 1), 45)
        _assert_same_matrix(pose.rotation, expected)

    def test_diagonal_swing_is_a_rotation_vector(self):
        pose = joint_pose(Ball(swing_x=30, swing_y=40))
        _assert_same_matrix(pose.rotation, rotation_about(Vec3(0.6, 0.8, 0), 50))

    @pytest.mark.parametrize(
        "constructor", [Mounting, Revolute, Prismatic, Cylindrical, Ball]
    )
    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_coordinates_must_be_finite(self, constructor, value):
        with pytest.raises(ValueError, match="finite"):
            constructor(value)

    def test_swing_coordinate_chart_is_bounded(self):
        with pytest.raises(ValueError, match="180"):
            Ball(150, 150)


class TestFitMounting:
    @pytest.mark.parametrize(
        "kind,mount",
        [
            (JointKind.FIXED, Mounting()),
            (JointKind.REVOLUTE, Mounting(angle=37)),
            (JointKind.REVOLUTE, Mounting(angle=37, flip=True)),
            (JointKind.PRISMATIC, Mounting(offset=0.5)),
            (JointKind.CYLINDRICAL, Mounting(offset=0.5, angle=40, flip=True)),
            (JointKind.BALL, Mounting(swing_x=30, swing_y=20, angle=40)),
            (JointKind.BALL, Mounting(swing_x=180, angle=35)),
        ],
    )
    @pytest.mark.parametrize(
        "axis,side", [(Direction.UP, Direction.LEFT), (Direction.FRONT, Direction.UP)]
    )
    def test_recovers_mounted_pose(self, kind, mount, axis, side):
        at = Connector(ConnectorType("j"), Position(1, 0, 2), axis, side, length=2)
        rest = Pose(rotation_about(Vec3(1, 0, 0), 25))
        desired = mounting_pose(mount, at, kind).compose(rest)
        got = fit_mounting(
            kind,
            at,
            at,
            rest,
            target_rotation=desired.rotation,
            target_position=mounting_pose(mount, at, kind).apply(at.position),
        )
        remade = mounting_pose(got, at, kind).compose(rest)
        _assert_same_matrix(remade.rotation, desired.rotation)
        assert tuple(remade.translation) == pytest.approx(tuple(desired.translation))

    def test_slide_is_clamped_to_connector_engagement(self):
        at = Connector(ConnectorType("j"), Position.ZERO, Direction.UP, length=1)
        got = fit_mounting(
            JointKind.PRISMATIC,
            at,
            at,
            Pose.IDENTITY,
            target_rotation=Mat3.IDENTITY,
            target_position=Position(0, 0, 100),
        )
        assert got.offset == pytest.approx(1.8)


class TestRegistry:
    def test_unregistered_pair_has_no_rule(self):
        assert mating_rule(ConnectorType("a"), ConnectorType("b")) is None

    def test_one_type_may_mate_several(self):
        tall = ConnectorType("tall_stud")
        socket = ConnectorType("deep_socket")
        mark_compatible(tall, socket)
        mark_compatible(STUD, socket)
        assert mating_rule(tall, socket) and mating_rule(STUD, socket)
        assert mating_rule(tall, ANTISTUD) is None

    def test_reregistering_a_pair_is_an_error(self):
        a, b = ConnectorType("a"), ConnectorType("b")
        mark_compatible(a, b)
        with pytest.raises(ValueError, match="already registered"):
            mark_compatible(a, b)

    def test_params_kind(self):
        assert Fixed().kind is JointKind.FIXED
        assert Revolute(angle=45).kind is JointKind.REVOLUTE
