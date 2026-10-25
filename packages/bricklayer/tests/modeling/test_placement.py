"""Tests for Placement: an Element or sub-model posed in a model."""

import pickle

import pytest

from bricklayer import (
    Color,
    Connector,
    Direction,
    LegoBuild,
    Mat3,
    Placement,
    Pose,
    Position,
    Rotation,
    Vec3,
    brick,
    slope,
)
from bricklayer.geometry.linalg import rotation_about
from bricklayer.ldraw.partdata import get_connector_type
from bricklayer.modeling.placement import grid_placement

STUD = get_connector_type("stud")
ANTISTUD = get_connector_type("antistud")


class TestPlacementIdentity:
    def test_hashable_and_compared_by_identity(self):
        # Placements are identity objects: distinct instances never compare
        # equal, even with identical content and pose, but stay hashable.
        a = Placement.at(brick(4, 2, color=Color.RED), Position(0, 0, 0))
        b = Placement.at(brick(4, 2, color=Color.RED), Position(0, 0, 0))
        assert a != b
        assert len({a, b}) == 2


class TestPlacementCaching:
    def test_geometry_is_cached(self, anchored, element_with):
        placement = Placement(
            element_with((), bounding_box=(Position(0, 0, 0), Position(2, 1, 1)))
        )
        assert placement.bounding_box is placement.bounding_box

    def test_a_placement_registers_as_a_dependent_of_a_model_content(self):
        model = LegoBuild()
        placement = Placement(model)
        assert placement in model.__dict__["_dependents"]

    def test_a_placement_of_an_element_registers_nothing(self, element_with):
        placement = Placement(element_with(()))
        assert "_dependents" not in placement.content.__dict__

    def test_a_model_content_invalidation_reaches_the_placement(self):
        model = LegoBuild()
        placement = Placement(model)
        assert placement.bounding_box == (Position.ZERO, Position.ZERO)
        model._invalidate()
        assert "bounding_box" not in placement.__dict__

    def test_a_pickled_placement_reregisters_as_a_dependent_of_its_content(self):
        model = LegoBuild()
        placement = Placement(model)
        restored = pickle.loads(pickle.dumps(placement))
        restored_model = restored.content
        assert restored.bounding_box == (Position.ZERO, Position.ZERO)
        restored_model._invalidate()
        assert "bounding_box" not in restored.__dict__


class TestPlacementPose:
    def test_defaults_to_origin_unrotated(self):
        p = Placement(brick(4, 2, color=Color.RED))
        assert p.pose == Pose.IDENTITY

    def test_at_accepts_any_position_without_grid_checks(self):
        # Grid alignment is add()/stack()'s job; a raw placement takes any position.
        p = Placement.at(brick(1, 1, color=Color.RED), Position(0.5, 0, 0.5))
        assert p.pose.translation == Position(1, 0.5, 0.5)  # position - box corner

    def test_at_re_anchors_the_rotated_footprint(self):
        bd = brick(4, 2, color=Color.RED)  # alignment box (-2, -1)..(2, 1)
        moved = Placement.at(bd, Position(1, 0, 0))
        turned = Placement.at(bd, Position(0, 0, 0), Rotation.DEG_90)
        # ``at`` spins the content about its centered origin, then shifts the
        # rotated alignment box's min corner onto the position -- the pose
        # records that shift.
        assert moved.pose == Pose(Mat3.IDENTITY, Position(3, 1, 0))
        assert turned.pose == Pose(Rotation.DEG_90.matrix, Position(1, 2, 0))

    def test_at_anchors_off_grid_content_by_its_grid_rounded_bounding_box(self):
        # A sub-model whose only part sits off the stud grid has no grid-marked
        # connectors, so its alignment box is the largest grid-aligned box
        # inside its bounding box -- here (0, -1, 0)..(1, 1, 4/3) inside
        # (-0.75, -1, 0)..(1.25, 1, 4/3) -- and ``at`` anchors its min corner.
        part = Placement(
            brick(2, 2, color=Color.RED), Pose(translation=Position(0.25, 0, 0))
        )
        content = LegoBuild([part])
        assert not any(c.is_grid_marked for c in content.connectors)
        placed = Placement.at(content, Position(3, 4, 1))
        assert placed.alignment_box[0] == Position(3, 4, 1)
        assert placed.alignment_width == 1
        assert placed.alignment_depth == 2
        assert placed.bounding_box[0] == Position(2.25, 4, 1)

    def test_90_rotates_footprint_in_place(self, filled_region):
        bd = brick(2, 1, color=Color.RED)  # 1 deep, 2 wide
        p = Placement.at(bd, rotation=Rotation.DEG_90)
        bottom = {c for c in filled_region(p) if c[2] == 0}
        assert bottom == {(0, 0, 0), (0, 1, 0)}  # now 2 deep, 1 wide

    def test_rotation_then_translation(self, filled_region):
        bd = brick(2, 1, color=Color.RED)
        p = Placement.at(bd, Position(5, 5, 0), Rotation.DEG_90)
        bottom = {c for c in filled_region(p) if c[2] == 0}
        assert bottom == {(5, 5, 0), (5, 6, 0)}

    def test_tuple_raw_position(self):
        part = brick(2, 1)
        a = Placement.at(part, (0.5, 1, 0.5), Rotation.DEG_90)
        b = Placement.at(part, Position(0.5, 1, 0.5), Rotation.DEG_90)
        assert a.pose == b.pose
        assert a.to_world((1, 2, 3)) == a.to_world(Position(1, 2, 3))


class TestRepr:
    def test_placement_shows_its_content_and_pose(self):
        p = Placement(brick(4, 2, color=Color.RED))
        assert repr(p) == f"Placement(Element(Brick  2 x  4, Red); {p.pose!r})"

    def test_placement_falls_back_to_submodel_repr(self):
        sub = LegoBuild([Placement(brick(2, 2, 3, color=Color.RED))])
        p = Placement(sub)
        assert repr(p) == f"Placement(LegoBuild(1 brick, 2x2x3.167); {p.pose!r})"


class TestPlacementGeometry:
    def test_connectors_rotate_and_translate(self, connector_specs):
        p = Placement.at(
            brick(1, 1, color=Color.RED), Position(1, 1, 0), Rotation.DEG_90
        )
        # The quarter turn carries the whole frame: the sides turn with it.
        assert connector_specs(
            {
                Connector(STUD, Position(1.5, 1.5, 1), Direction.UP, Direction.BACK),
                Connector(
                    ANTISTUD, Position(1.5, 1.5, 0), Direction.UP, Direction.BACK
                ),
            }
        ) <= connector_specs(p)

    def test_facing_alias_turns_the_slope_low_edge(self, connector_specs):
        # Rotation.RIGHT points the slope's low front edge to the right, so the
        # studded back wall becomes the left-hand column.
        s = slope(2, 2, color=Color.BLUE)
        p = Placement.at(s, rotation=Rotation.RIGHT)
        studs = set(p.find_connectors(STUD))
        assert connector_specs(studs) == connector_specs(
            {
                Connector(STUD, Position(1.5, 0.5, 1), Direction.UP, Direction.FRONT),
                Connector(STUD, Position(1.5, 1.5, 1), Direction.UP, Direction.FRONT),
            }
        )

    def test_slope_studs_follow_the_rotation(self, connector_specs):
        # A 2x2 slope has studs on its back row (y=1); a quarter turn moves them.
        s = slope(2, 2, color=Color.BLUE)
        p = Placement.at(s, rotation=Rotation.DEG_90)
        studs = set(p.find_connectors(STUD))
        assert connector_specs(studs) == connector_specs(
            {
                Connector(STUD, Position(0.5, 0.5, 1), Direction.UP, Direction.BACK),
                Connector(STUD, Position(0.5, 1.5, 1), Direction.UP, Direction.BACK),
            }
        )

    def test_tipped_brick_height_uses_stud_scaling(self):
        # The brick's 1-stud depth becomes 5/6 of a brick of height.
        tilt = Pose(rotation_about(Vec3(1, 0, 0), 90))
        p = Placement(brick(1, 1, color=Color.RED), tilt)
        lo, hi = p.bounding_box
        assert hi.z - lo.z == pytest.approx(5 / 6)

    def test_tipped_connectors_follow_the_pose(self):
        tilt = Pose(rotation_about(Vec3(1, 0, 0), 90))
        p = Placement(brick(1, 1, color=Color.RED), tilt)
        (stud,) = p.find_connectors("stud")
        assert stud.axis == Vec3(0, -1, 0)  # UP tips toward the front


class TestGridPlacement:
    @pytest.fixture
    def wide(self, element_with):
        """A 2x1x1 element double, anchored on its own alignment box."""
        return element_with((), (Position(0, 0, 0), Position(2, 1, 1)))

    def test_accepted_rounding_noise_is_snapped_to_the_grid(self, wide):
        placement = grid_placement(wide, offset=Position(3.004, 3.996, 1 / 3 + 0.001))
        expected = grid_placement(wide, offset=Position(3, 4, 1 / 3))
        assert placement.pose == expected.pose

    def test_an_absolute_placement_lands_at_the_offset(self, wide):
        placement = grid_placement(wide, offset=Position(3, 4, 0))
        lo, _ = placement.bounding_box
        assert (lo.x, lo.y, lo.z) == (3, 4, 0)

    def test_an_off_grid_offset_is_rejected(self, wide):
        with pytest.raises(ValueError):
            grid_placement(wide, offset=Position(0.5, 0, 0))

    def test_a_relative_placement_is_measured_from_the_reference(self, wide):
        base = grid_placement(wide, offset=Position(1, 1, 0))
        near = grid_placement(wide, reference=base, offset=Position(2, 0, 0))
        lo, _ = near.bounding_box
        assert (lo.x, lo.y) == (3, 1)

    def test_stacking_lifts_by_the_reference_alignment_height(self, wide):
        base = grid_placement(wide)
        on_top = grid_placement(wide, reference=base, stacked=True)
        assert on_top.bounding_box[0].z == base.alignment_height
