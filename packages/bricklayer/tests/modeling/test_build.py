"""Tests for LegoBuild: validity, geometry, and coupling queries."""

import gc
import pickle
import time
import weakref
from functools import cached_property

import pytest

from bricklayer import (
    PLATE,
    Anchor,
    Color,
    Connector,
    ConnectorType,
    Direction,
    Element,
    LegoBuild,
    Mat3,
    MotionRange,
    Mounting,
    Placement,
    Pose,
    Position,
    Prismatic,
    Revolute,
    Rotation,
    Vec3,
    brick,
    fill_box,
    plate,
    tile,
    to_ldraw,
)
from bricklayer.geometry.connections import (
    JointKind,
    mark_compatible,
    mated,
)
from bricklayer.geometry.linalg import rotation_about
from bricklayer.ldraw.partdata import STUD_HEIGHT, get_connector_type

STUD = get_connector_type("stud")
ANTISTUD = get_connector_type("antistud")


def _connect_pair(
    holder: Element | LegoBuild,
    insert: Element | LegoBuild,
    connector: ConnectorType,
    to_connector: ConnectorType,
    *,
    holder_position: Position = Position.ZERO,
    holder_rotation: Rotation = Rotation.DEG_0,
    mounting: Mounting | None = None,
    target_rotation: Mat3 | Rotation | None = None,
    target_position: Position | tuple[float, float, float] | None = None,
):
    """Build a model with ``holder`` placed and ``insert`` connected to it;
    return the model and the insert's placement."""
    model = LegoBuild()
    model.add(holder, holder_position, holder_rotation, name="holder")
    ins = model.connect(
        insert,
        connector,
        to=model.named("holder").find_connector(to_connector),
        mounting=mounting,
        target_rotation=target_rotation,
        target_position=target_position,
        name="ins",
    )
    return model, ins


def _assert_box(box, lo, hi):
    """Assert a ``(min, max)`` box matches, tolerating float noise."""
    actual_lo, actual_hi = box
    assert tuple(actual_lo) == pytest.approx(tuple(lo))
    assert tuple(actual_hi) == pytest.approx(tuple(hi))


def coupled(a, b):
    """Whether two parts are joined through mated connectors (in either order)."""
    return bool(mated([a.connectors, b.connectors]).pairs)


def _brute_force_edges(placements):
    """Every coupled index pair, by testing all pairs -- the definition the
    spatial-hash coupling graph has to agree with."""
    return {
        frozenset((i, j))
        for i in range(len(placements))
        for j in range(i + 1, len(placements))
        if coupled(placements[i], placements[j])
    }


class TestPickling:
    def test_a_model_containing_a_sub_model_pickles(self):
        parent, child = LegoBuild(), LegoBuild()
        child.add(brick(2, 2, color=Color.RED))
        parent.add(child)
        pickle.loads(pickle.dumps(parent))  # does not raise

    def test_unpickled_dependency_links_still_propagate(self):
        parent, child = LegoBuild(), LegoBuild()
        child.add(brick(2, 2, color=Color.RED))
        parent.add(child)
        restored = pickle.loads(pickle.dumps(parent))
        before = restored.brick_count
        restored_child = restored.placements[0].content
        restored_child.add(brick(2, 2, color=Color.BLUE))
        assert restored.brick_count == before + 1

    def test_markers_survive_a_pickle_round_trip(self, model):
        model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        model.add_step()
        assert pickle.loads(pickle.dumps(model)).step_markers == (1,)


class TestSteps:
    """Build-step markers: positions in the placement list where a step closes."""

    @staticmethod
    def _placements(n: int) -> list[Placement]:
        return [
            Placement(
                brick(1, 1, color=Color.RED), Pose(translation=Position(2 * i, 0, 0))
            )
            for i in range(n)
        ]

    @pytest.mark.parametrize(
        ("markers", "n", "expected"),
        [
            ((), 2, ((0, 1),)),
            ((2,), 2, ((0, 1),)),
            ((1,), 2, ((0,), (1,))),
            ((1, 1), 1, ((0,), ())),
            ((0,), 1, ((), (0,))),
            ((), 0, ()),
            ((0,), 0, ((),)),
        ],
    )
    def test_steps_group_placements(self, markers, n, expected):
        # A marker closes the step ahead of it; placements after the last marker
        # form a final step only if there are any.
        placements = self._placements(n)
        model = LegoBuild(placements, steps=markers)
        assert model.step_markers == markers
        assert model.steps == tuple(
            tuple(placements[i] for i in group) for group in expected
        )

    @pytest.mark.parametrize("markers", [(-1,), (3,), (1, 0)])
    def test_init_rejects_markers_no_placement_list_can_hold(self, markers):
        with pytest.raises(ValueError, match="step marker"):
            LegoBuild(self._placements(2), steps=markers)


class TestAdding:
    def test_empty_model_is_valid(self):
        m = LegoBuild()
        assert m.placements == ()
        assert m.is_valid()

    def test_add_global(self, model):
        # add() is immediate: the returned placement is already resolved, so
        # its alignment box (not its raw pose) is what the position promises.
        p = model.add(brick(4, 2, color=Color.RED), Position(1, 2, 0))
        assert p.alignment_box[0] == Position(1, 2, 0)
        assert model.placements[0] is p
        assert p in model.placements

    def test_add_defaults_to_origin_unrotated(self, model):
        p = model.add(brick(4, 2, color=Color.RED))
        assert p.pose.rotation == Rotation.DEG_0.matrix
        assert p.alignment_box[0] == Position(0, 0, 0)

    def test_add_with_rotation(self, model):
        p = model.add(brick(2, 1, color=Color.RED), Position(0, 0, 0), Rotation.DEG_90)
        assert p.pose.rotation == Rotation.DEG_90.matrix

    def test_an_off_grid_position_is_rejected(self, model):
        with pytest.raises(ValueError):
            model.add(brick(2, 2, color=Color.RED), Position(0.5, 0, 0))


class TestInsertionIndex:
    def test_index_zero_places_first(self, model):
        model.add(brick(4, 2), name="a")
        model.add(brick(4, 2), Position(0, 0, 1), name="b")
        inserted = model.add(brick(4, 2), Position(0, 0, 2), index=0, name="c")

        assert model.placements[0] is inserted
        assert [model.name_of(p) for p in model.placements] == ["c", "a", "b"]

    def test_negative_index_counts_from_the_end(self, model):
        model.add(brick(4, 2), name="a")
        model.add(brick(4, 2), Position(0, 0, 1), name="b")
        model.add(brick(4, 2), Position(0, 0, 2), index=-1, name="c")

        assert [model.name_of(p) for p in model.placements] == ["a", "c", "b"]

    def test_index_at_the_end_appends(self, model):
        model.add(brick(4, 2), name="a")
        model.add(brick(4, 2), Position(0, 0, 1), index=1, name="b")

        assert [model.name_of(p) for p in model.placements] == ["a", "b"]

    def test_add_raw_and_stack_take_an_index(self, model):
        model.add(brick(4, 2), name="base")
        model.add_raw(brick(4, 2), Pose(translation=Position(0, 0, 5)), index=0)
        model.stack(brick(4, 2), "base", index=0)

        assert len(model.placements) == 3
        assert model.name_of(model.placements[2]) == "base"

    @pytest.mark.parametrize("index", (2, -3, 99, -99))
    def test_out_of_range_index_raises(self, model, index):
        model.add(brick(4, 2))

        with pytest.raises(IndexError, match="out of range"):
            model.add(brick(4, 2), Position(0, 0, 1), index=index)

    def test_a_refused_index_leaves_the_model_untouched(self, model):
        model.add(brick(4, 2), name="a")

        with pytest.raises(IndexError):
            model.add(brick(4, 2), Position(0, 0, 1), index=9, name="b")

        assert len(model.placements) == 1
        assert "b" not in model.names

    def test_markers_past_the_insertion_shift_up(self, model):
        model.add(brick(4, 2), name="a")
        model.add_step()
        model.add(brick(4, 2), Position(0, 0, 1), name="b")
        model.add(brick(4, 2), Position(0, 0, 2), index=0, name="c")

        assert model.step_markers == (2,)
        assert [model.name_of(p) for p in model.steps[0]] == ["c", "a"]
        assert [model.name_of(p) for p in model.steps[1]] == ["b"]

    def test_a_marker_at_the_insertion_point_stays(self, model):
        model.add_step()
        model.add(brick(4, 2), index=0, name="a")

        assert model.step_markers == (0,)
        assert model.steps[0] == ()


class TestAnchors:
    """Each anchor pins that footprint point to the resolved position, across
    add() -- absolute and relative -- and stack()."""

    @pytest.mark.parametrize(
        "anchor, expected_min",
        [
            (Anchor.FRONT_RIGHT, Position(10, 10, 0)),
            (Anchor.FRONT, Position(9, 10, 0)),  # center x of 3-wide: offset 1
            (Anchor.FRONT_LEFT, Position(8, 10, 0)),  # max x: offset 2
            (Anchor.CENTER, Position(9, 10, 0)),  # depth 1 -> no y offset
            (Anchor.BACK_LEFT, Position(8, 10, 0)),
        ],
    )
    def test_anchor_a_3x1_odd_part(self, model, anchor, expected_min):
        model.add(
            brick(3, 1, color=Color.RED), Position(10, 10, 0), anchor=anchor, name="b"
        )
        assert model.named("b").alignment_box[0] == expected_min
        # The footprint is the same 3 studs, just shifted by the anchor.
        lo, hi = model.named("b").bounding_box
        assert lo.x == expected_min.x and hi.x == expected_min.x + 3

    @pytest.mark.parametrize(
        "anchor, expected_min",
        [
            (Anchor.FRONT_RIGHT, Position(10, 10, 0)),
            (Anchor.FRONT_LEFT, Position(9, 10, 0)),  # 2-wide max x: offset 1
            (Anchor.CENTER, Position(10, 10, 0)),  # even center floors to 0
            (Anchor.LEFT, Position(9, 10, 0)),
        ],
    )
    def test_anchor_a_2x1_even_part(self, model, anchor, expected_min):
        model.add(
            brick(2, 1, color=Color.RED), Position(10, 10, 0), anchor=anchor, name="b"
        )
        assert model.named("b").alignment_box[0] == expected_min

    def test_center_anchor_places_the_footprint_around_the_position(self, model):
        # A 3x3 plate centered on (5, 5): min corner one stud front-right.
        model.add(
            plate(3, 3, color=Color.WHITE),
            Position(5, 5, 0),
            anchor=Anchor.CENTER,
            name="p",
        )
        assert model.named("p").alignment_box[0] == Position(4, 4, 0)
        lo, hi = model.named("p").bounding_box
        assert (lo.x, hi.x) == (4, 7) and (lo.y, hi.y) == (4, 7)

    def test_anchor_with_quarter_turn_uses_rotated_footprint(self, model):
        # A 3-wide x 1-deep brick turned DEG_90 becomes 1 wide x 3 deep.
        # Anchoring BACK_LEFT pins the far (+x, +y) corner to the position.
        model.add(
            brick(3, 1, color=Color.RED),
            Position(10, 10, 0),
            Rotation.DEG_90,
            anchor=Anchor.BACK_LEFT,
            name="b",
        )
        _, hi = model.named("b").bounding_box
        # Far corner (max x, max y) of the rotated footprint sits at (10, 10).
        assert hi.x == 11 and hi.y == 11
        assert model.named("b").alignment_box[0] == Position(10, 8, 0)  # min corner

    def test_anchor_with_three_quarter_turn(self, model):
        model.add(
            brick(3, 1, color=Color.RED),
            Position(10, 10, 0),
            Rotation.DEG_270,
            anchor=Anchor.FRONT_RIGHT,
            name="b",
        )
        # Min corner stays at the position with the default anchor.
        assert model.named("b").alignment_box[0] == Position(10, 10, 0)
        # 1 wide x 3 deep footprint.
        lo, hi = model.named("b").bounding_box
        assert (lo.x, hi.x) == (10, 11) and (lo.y, hi.y) == (10, 13)

    def test_add_relative_to_honors_anchor(self, model):
        model.add(brick(2, 2, color=Color.RED), Position(5, 5, 0), name="base")
        # Place a 3x1 centered (in x) at offset (0,0,1) from the base's min corner.
        model.add(
            brick(3, 1, color=Color.BLUE),
            Position(0, 0, 1),
            anchor=Anchor.FRONT,
            relative_to="base",
            name="top",
        )
        # Resolved min-corner before anchor would be (5,5,1); FRONT subtracts x=1.
        assert model.named("top").alignment_box[0] == Position(4, 5, 1)

    def test_stack_honors_anchor_and_still_seats_on_top(self, model):
        model.add(brick(4, 2, color=Color.RED), Position(0, 0, 0), name="base")
        # A centered 2x2 cap. Its center anchor floors x to 0, so min corner
        # offset is (0,0): with offset (1,0) it slides to x=1, resting on top.
        model.stack(
            brick(2, 2, color=Color.BLUE),
            "base",
            Position(1, 0, 0),
            anchor=Anchor.CENTER,
            name="cap",
        )
        # Still seated one brick up (studs meet antistuds).
        assert model.named("cap").alignment_box[0].z == 1
        assert model.is_valid()

    def test_relative_offset_measured_from_referenced_min_corner(self, model):
        # Even when the reference itself used an anchor, offsets are measured
        # from its true (stored) min corner.
        model.add(
            brick(3, 1, color=Color.RED),
            Position(10, 0, 0),
            anchor=Anchor.FRONT_LEFT,  # min corner ends at (8, 0, 0)
            name="base",
        )
        model.add(
            brick(1, 1, color=Color.BLUE),
            Position(0, 0, 1),
            relative_to="base",
            name="dot",
        )
        assert model.named("base").alignment_box[0] == Position(8, 0, 0)
        # dot sits at base min corner + offset, no anchor of its own.
        assert model.named("dot").alignment_box[0] == Position(8, 0, 1)

    def test_relative_offset_measured_from_rotated_references_min_corner(self, model):
        # A 3x1 turned DEG_90 occupies (10..11, 10..13): its footprint min
        # corner -- not its pose translation -- is the offset origin.
        model.add(
            brick(3, 1, color=Color.RED),
            Position(10, 10, 0),
            Rotation.DEG_90,
            name="base",
        )
        model.add(
            brick(1, 1, color=Color.BLUE),
            Position(0, 0, 1),
            relative_to="base",
            name="dot",
        )
        assert model.named("dot").alignment_box[0] == Position(10, 10, 1)

    def test_add_relative_to_honors_target_anchor(self, model):
        model.add(brick(4, 2, color=Color.RED), Position(5, 5, 0), name="base")
        model.add(
            brick(1, 1, color=Color.BLUE),
            Position(0, 0, 1),
            relative_to="base",
            target_anchor=Anchor.BACK_LEFT,
            name="dot",
        )
        # Offset is measured from the base's back-left stud (8, 6) instead of
        # its min corner.
        assert model.named("dot").alignment_box[0] == Position(8, 6, 1)

    def test_stack_with_center_anchors_centers_on_the_reference(self, model):
        model.add(brick(4, 2, color=Color.RED), Position(0, 0, 0), name="base")
        model.stack(
            brick(2, 2, color=Color.BLUE),
            "base",
            anchor=Anchor.CENTER,
            target_anchor=Anchor.CENTER,
            name="cap",
        )
        # Base center (1, 0) meets cap center (0, 0), still seated one brick up.
        assert model.named("cap").alignment_box[0] == Position(1, 0, 1)
        assert model.is_valid()

    def test_target_anchor_uses_references_rotated_footprint(self, model):
        # A 3x1 turned DEG_90 is 1 wide x 3 deep; BACK is the center of its
        # far-y edge, (10, 12).
        model.add(
            brick(3, 1, color=Color.RED),
            Position(10, 10, 0),
            Rotation.DEG_90,
            name="base",
        )
        model.add(
            brick(1, 1, color=Color.BLUE),
            Position(0, 0, 1),
            relative_to="base",
            target_anchor=Anchor.BACK,
            name="dot",
        )
        assert model.named("dot").alignment_box[0] == Position(10, 12, 1)


class TestSubModels:
    def test_a_model_can_be_placed_in_another_model(self, model, filled_region):
        # A sub-assembly built at the origin, then placed as a unit.
        pair = LegoBuild()
        pair.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        pair.add(brick(1, 1, color=Color.BLUE), Position(1, 0, 0))

        model.add(pair, Position(0, 0, 0))
        # The sub-model contributes a single placement whose body is the union
        # of the two 1x1 brick boxes, side by side (x in 0..1 and 1..2).
        (placed,) = model.placements
        assert {(x, y) for x, y, _ in filled_region(placed)} == {(0, 0), (1, 0)}

    def test_sub_model_geometry_is_the_union_of_its_parts(self):
        pair = LegoBuild()
        pair.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        pair.add(brick(1, 1, color=Color.BLUE), Position(2, 0, 0))
        assert pair.width == 3  # spans x = 0..2
        assert pair.depth == 1
        assert pair.height == pytest.approx(1 + STUD_HEIGHT)  # bodies plus stud layer

    def test_placed_sub_model_grounds_and_supports(self, model):
        pair = LegoBuild()
        pair.add(brick(2, 2, color=Color.RED), Position(0, 0, 0))
        model.add(pair, Position(0, 0, 0), name="base")
        # A brick stacked on top of the placed sub-model is supported.
        model.stack(brick(2, 2, color=Color.BLUE), "base")
        assert model.is_valid()

    def test_a_sub_model_becomes_a_nested_model(self, model):
        sub = LegoBuild()
        sub.add(brick(2, 2, color=Color.RED), name="cell")
        model.add(sub, Position(0, 0, 0), name="sub")
        assert isinstance(model.placements[0].content, LegoBuild)
        cell = model.named(["sub", "cell"]).content
        assert isinstance(cell, Element)
        other = brick(2, 2, color=Color.RED)
        assert (cell.spec.ldraw_id, cell.color) == (other.spec.ldraw_id, other.color)

    def test_a_shared_sub_model_appears_twice_by_the_same_object(self, model):
        # The same LegoBuild placed twice must appear as ONE shared sub-model
        # object, not two separate copies.
        sub = LegoBuild()
        sub.add(brick(2, 2, color=Color.RED), name="cell")
        model.add(sub, Position(0, 0, 0), name="a")
        model.add(sub, Position(5, 0, 0), name="b")
        assert model.named("a").content is model.named("b").content is sub

    @staticmethod
    def _origin_sub():
        # Built with its min corner at the origin.
        sub = LegoBuild()
        sub.add(brick(2, 1, color=Color.RED), Position(0, 0, 0), name="a")
        sub.add(brick(1, 1, color=Color.BLUE), Position(2, 0, 0), name="b")
        return sub

    @staticmethod
    def _offset_sub():
        # The same layout, but built away from the origin (min corner at 5,3).
        sub = LegoBuild()
        sub.add(brick(2, 1, color=Color.RED), Position(5, 3, 0), name="a")
        sub.add(brick(1, 1, color=Color.BLUE), Position(7, 3, 0), name="b")
        return sub

    def test_offset_sub_places_like_an_origin_sub(self, filled_region):
        # ``add`` anchors the alignment box's min corner wherever the box sits
        # in the sub-model's own frame, so the two builds fill the same cells.
        m1 = LegoBuild()
        m1.add(self._origin_sub(), Position(0, 0, 0))
        m2 = LegoBuild()
        m2.add(self._offset_sub(), Position(0, 0, 0))
        assert filled_region(m1) == filled_region(m2)

    def test_offset_sub_rotates_like_an_origin_sub(self, filled_region):
        m1 = LegoBuild()
        m1.add(self._origin_sub(), Position(0, 0, 0), Rotation.DEG_90)
        m2 = LegoBuild()
        m2.add(self._offset_sub(), Position(0, 0, 0), Rotation.DEG_90)
        assert filled_region(m1) == filled_region(m2)

    def test_rotated_offset_sub_matches_hand_verified_cells(self, model, filled_region):
        # The origin sub spans x 0..2, y 0 (a 2x1 brick at 0, a 1x1 at x=2).
        # DEG_90 (CCW): (x, y) -> (depth-1-y, x) over a 3-wide x 1-deep footprint
        # -> 1 wide x 3 deep. Brick "a" (x 0,1) -> y 0,1; "b" (x 2) -> y 2.
        # Each brick's alignment box is 3 plates tall.
        model.add(self._offset_sub(), Position(0, 0, 0), Rotation.DEG_90)
        cells = filled_region(model)
        expected = {(0, y, z) for y in range(3) for z in range(3)}
        assert cells == expected

    def test_sub_model_keeps_its_own_frame_and_identity(self, model):
        # No normalization: the sub-model is placed as-is, and ``add``
        # compensates through the placement pose instead.
        sub = self._offset_sub()
        model.add(sub, Position(0, 0, 0), name="x")
        model.add(sub, Position(10, 0, 0), name="y")
        assert model.named("x").content is sub
        assert model.named("y").content is sub
        assert model.named("x").pose.translation == Position(-5, -3, 0)

    def test_empty_sub_model_placement_is_a_no_op(self, model, filled_region):
        empty = LegoBuild()
        model.add(empty, Position(0, 0, 0))  # must not raise a bounding_box ValueError
        assert filled_region(model) == frozenset()

    def test_an_empty_sub_model_does_not_stretch_the_bounding_box(self, model):
        model.add(brick(2, 2, color=Color.RED), Position(0, 0, 2))
        before = model.bounding_box
        empty = LegoBuild()
        empty.add(LegoBuild())
        model.add(empty, Position(5, 5, 0))
        assert model.bounding_box == before

    def test_a_model_of_empty_sub_models_has_the_empty_models_box(self, model):
        model.add(LegoBuild(), Position(5, 5, 1))
        assert model.bounding_box == LegoBuild().bounding_box
        assert model.alignment_box == LegoBuild().alignment_box

    def test_filling_an_empty_sub_model_stretches_the_bounding_box(self, model):
        model.add(brick(2, 2, color=Color.RED))
        sub = LegoBuild()
        model.add(sub, Position(5, 0, 0))
        _ = model.bounding_box
        sub.add(brick(1, 1, color=Color.BLUE))
        assert model.bounding_box[1].x == 6


class TestCycles:
    def test_a_model_cannot_contain_itself(self, model):
        with pytest.raises(ValueError, match="cannot contain itself"):
            model.add(model)

    def test_two_models_cannot_contain_each_other(self, model):
        inner = LegoBuild()
        inner.add(brick(2, 2, color=Color.RED))
        model.add(inner)
        with pytest.raises(ValueError, match="already contains this model"):
            inner.add(model)


class TestRemoval:
    @pytest.fixture
    def shared_placement(self):
        """One placement of a sub-model, for the cases that record it twice."""
        sub = LegoBuild()
        sub.add(brick(4, 2), name="inner")
        return Placement(sub)

    def test_removes_by_index_and_returns_the_placement(self, model):
        model.add(brick(4, 2), name="a")
        target = model.add(brick(4, 2), Position(0, 0, 1), name="b")
        model.add(brick(4, 2), Position(0, 0, 2), name="c")

        removed = model.remove(1)

        assert removed is target
        assert [model.name_of(p) for p in model.placements] == ["a", "c"]

    def test_removes_by_name(self, model):
        model.add(brick(4, 2), name="a")
        target = model.add(brick(4, 2), Position(0, 0, 1), name="b")

        assert model.remove("b") is target
        assert len(model.placements) == 1

    def test_negative_index_counts_from_the_end(self, model):
        model.add(brick(4, 2), name="a")
        model.add(brick(4, 2), Position(0, 0, 1), name="b")

        model.remove(-1)

        assert [model.name_of(p) for p in model.placements] == ["a"]

    def test_frees_the_name_for_reuse(self, model):
        model.add(brick(4, 2), name="arm")
        model.remove("arm")

        assert "arm" not in model.names
        with pytest.raises(KeyError):
            model.named("arm")

        replacement = model.add(brick(4, 2), name="arm")
        assert model.named("arm") is replacement

    def test_markers_past_the_removal_shift_down(self, model):
        model.add(brick(4, 2), name="a")
        model.add(brick(4, 2), Position(0, 0, 1), name="b")
        model.add_step()
        model.add(brick(4, 2), Position(0, 0, 2), name="c")

        model.remove(0)

        assert model.step_markers == (1,)
        assert [model.name_of(p) for p in model.steps[0]] == ["b"]

    def test_insert_then_remove_restores_the_markers(self, model):
        model.add(brick(4, 2), name="a")
        model.add_step()
        model.add(brick(4, 2), Position(0, 0, 1), name="b")
        before = model.step_markers

        model.add(brick(4, 2), Position(0, 0, 2), index=1, name="c")
        model.remove(1)

        assert model.step_markers == before

    def test_drops_the_dependency_on_a_removed_sub_model(self, model):
        sub = LegoBuild()
        sub.add(brick(4, 2))
        placement = model.add(sub, name="sub")
        model.remove("sub")

        # The model depends on the Placement; the Placement depends on its
        # content. Removal severs only the first of those two edges.
        assert model not in placement.__dict__.get("_dependents", set())
        assert not any(s is placement for s in model.__dict__.get("_sources", []))

    def test_removing_every_copy_of_a_shared_placement_drops_the_edge(
        self, shared_placement
    ):
        placement = shared_placement
        shared = LegoBuild([placement, placement])

        shared.remove(0)
        shared.remove(0)

        assert not any(s is placement for s in shared.__dict__.get("_sources", []))
        assert shared not in placement.__dict__.get("_dependents", set())

    def test_a_removed_sub_model_no_longer_invalidates(self, model):
        sub = LegoBuild()
        sub.add(brick(4, 2))
        model.add(sub, name="sub")
        model.add(brick(4, 2), Position(10, 0, 0))
        model.remove("sub")

        assert model.brick_count == 1
        sub.add(brick(4, 2), Position(0, 0, 1))

        assert "brick_count" in model.__dict__

    def test_shared_content_keeps_its_other_link(self, model):
        sub = LegoBuild()
        sub.add(brick(4, 2))
        model.add(sub, name="first")
        model.add(sub, Position(10, 0, 0), name="second")
        model.remove("first")

        assert model.brick_count == 1
        sub.add(brick(4, 2), Position(0, 0, 1))

        assert model.brick_count == 2

    def test_removal_invalidates_derived_geometry(self, model):
        model.add(brick(4, 2), name="a")
        model.add(brick(4, 2), Position(10, 0, 0), name="b")
        assert model.brick_count == 2

        model.remove("b")

        assert model.brick_count == 1

    def test_removed_placement_can_still_be_used_as_a_reference(self, model):
        removed = model.add(brick(4, 2), name="a")
        model.remove("a")

        placed = model.add(brick(4, 2), relative_to=removed)
        assert placed.pose == removed.pose

    def test_removal_drops_composed_placements_rooted_at_it(self, model):
        sub = LegoBuild()
        sub.add(brick(4, 2))
        placement = model.add(sub, name="sub")
        assert model.brick_count == 1  # populates _compose_cache

        model.remove("sub")

        cache = model._compose_cache
        assert not any(key[0] is placement for key in cache)

    def test_copy_and_pickle_survive_a_removal(self, model):
        model.add(brick(4, 2), name="a")
        model.add(brick(4, 2), Position(0, 0, 1), name="b")
        model.remove("a")

        duplicate = model.copy()
        assert duplicate.brick_count == 1
        assert "a" not in duplicate.names

        revived = pickle.loads(pickle.dumps(model))
        assert revived.brick_count == 1
        assert "a" not in revived.names

    def test_pickling_drops_the_composition_caches_after_a_removal(self, model):
        sub = LegoBuild()
        sub.add(brick(4, 2))
        model.add(sub, name="sub")
        assert model.brick_count == 1  # populates _compose_cache

        model.remove("sub")
        revived = pickle.loads(pickle.dumps(model))

        assert revived._compose_cache == {}

    @pytest.mark.parametrize("index", (1, -2, 99))
    def test_out_of_range_index_raises(self, model, index):
        model.add(brick(4, 2))

        with pytest.raises(IndexError, match="out of range"):
            model.remove(index)

    def test_unknown_name_raises(self, model):
        with pytest.raises(KeyError, match="nope"):
            model.remove("nope")

    def test_a_name_path_is_rejected(self, model):
        sub = LegoBuild()
        sub.add(brick(4, 2), name="inner")
        model.add(sub, name="sub")

        with pytest.raises(TypeError, match="sub-model"):
            model.remove(["sub", "inner"])

    def test_a_placement_can_be_removed_by_identity(self, model):
        placement = model.add(brick(4, 2), name="a")

        assert model.remove(placement) is placement
        assert model.placements == ()
        assert "a" not in model.names

    def test_a_bool_is_rejected(self, model):
        model.add(brick(4, 2))
        model.add(brick(4, 2), Position(0, 0, 1))

        with pytest.raises(TypeError, match="not a bool"):
            model.remove(True)

    def test_removing_an_unnamed_placement(self, model):
        named = model.add(brick(4, 2), name="a")
        unnamed = model.add(brick(4, 2), Position(0, 0, 1))

        removed = model.remove(1)

        assert removed is unnamed
        assert model.placements == (named,)

    def test_a_name_survives_while_another_slot_still_holds_the_placement(
        self, shared_placement
    ):
        placement = shared_placement
        shared = LegoBuild([placement, placement], {"dup": placement})

        shared.remove(0)

        assert shared.named("dup") is placement
        assert shared.placements == (placement,)

        shared.remove(0)

        assert "dup" not in shared.names

    def test_a_reference_survives_removing_all_slots_holding_the_placement(
        self, shared_placement
    ):
        """Saved references remain usable independently of cache pruning."""
        placement = shared_placement
        shared = LegoBuild([placement, placement], {"dup": placement})
        nested = shared.named(["dup", "inner"])

        shared.remove(0)

        assert shared.add(brick(2, 2), Position(0, 0, 1), relative_to=nested)

        shared.remove(0)

        assert shared.add(brick(2, 2), Position(0, 0, 2), relative_to=nested)

    def test_remove_by_placement_updates_names_steps_and_rejects_foreign(self):
        model = LegoBuild()
        first = model.add(brick(1, 1), name="first")
        model.add_step()
        second = model.add(brick(1, 1), (2, 0, 0))
        assert model.remove(first) is first
        assert "first" not in model.names
        assert model.step_markers == (0,)
        assert model.placements == (second,)
        with pytest.raises(ValueError, match="not a placement"):
            model.remove(first)
        with pytest.raises(ValueError, match="not a placement"):
            model.remove(Placement.at(brick(1, 1)))


class TestAddRaw:
    def test_places_content_at_the_exact_pose(self, model):
        tilted = Pose(Mat3(((1, 0, 0), (0, 0, -1), (0, 1, 0))), Position(0.5, 0, 0.25))
        model.add_raw(brick(1, 1, color=Color.RED), tilted, name="tipped")
        assert model.named("tipped").pose == tilted

    def test_does_not_re_anchor_quarter_turn_poses(self, model):
        # add() re-anchors the rotated footprint into the +quadrant; add_raw
        # applies the pose verbatim.
        pose = Pose(Rotation.DEG_90.matrix, Position(3, 2, 0))
        model.add_raw(brick(4, 2, color=Color.RED), pose)
        assert model.placements[0].pose == pose

    def test_poses_a_sub_assembly_in_its_own_frame(self, model):
        # A sub-assembly is NOT normalized: the pose maps the frame it was
        # built in, so where its parts sit in that frame is where they land.
        sub = LegoBuild()
        sub.add(brick(2, 2, color=Color.RED), Position(5, 5, 0))
        model.add_raw(sub, Pose(translation=Position(1, 0, 0)))
        lo, hi = model.alignment_box
        assert (lo, hi) == (Position(6, 5, 0), Position(8, 7, 1))

    def test_add_raw_applies_the_pose_to_the_built_frame(self, filled_region):
        # A part added to a sub-model must not shift where add_raw puts the
        # rest of it: the pose maps the sub-model's own build frame verbatim.
        before = LegoBuild()
        before.add(brick(2, 1, color=Color.RED), Position(5, 3, 0), name="a")
        before.add(brick(1, 1, color=Color.BLUE), Position(7, 3, 0), name="b")
        extended = before.copy()
        extended.add(brick(1, 1, color=Color.BLUE), Position(0, 0, 0))
        m1 = LegoBuild()
        m1.add_raw(before, Pose.IDENTITY)
        m2 = LegoBuild()
        m2.add_raw(extended, Pose.IDENTITY)
        assert filled_region(m1) <= filled_region(m2)


class TestRelativePlacement:
    """add() with relative_to and stack(): grid placement measured from
    another placement's resolved position."""

    def test_offsets_from_the_named_brick(self, model):
        model.add(brick(4, 2, color=Color.RED), Position(5, 5, 0), name="base")
        model.add(
            brick(4, 2, color=Color.BLUE),
            Position(0, 0, 1),
            relative_to="base",
            name="top",
        )
        assert model.named("top").alignment_box[0] == Position(5, 5, 1)

    def test_relative_to_a_relative(self, model):
        model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0), name="a")
        model.add(
            brick(1, 1, color=Color.BLUE), Position(0, 0, 1), relative_to="a", name="b"
        )
        model.add(
            brick(1, 1, color=Color.GREEN), Position(0, 0, 1), relative_to="b", name="c"
        )
        assert model.named("c").alignment_box[0] == Position(0, 0, 2)

    def test_offset_applies_on_all_axes_and_rotation_is_kept(self, model):
        model.add(brick(4, 2, color=Color.RED), Position(5, 5, 0), name="base")
        p = model.add(
            brick(1, 1, color=Color.BLUE),
            Position(2, 3, 1),
            Rotation.DEG_90,
            relative_to="base",
            name="off",
        )
        assert model.named("off").alignment_box[0] == Position(7, 8, 1)
        assert p.pose.rotation == Rotation.DEG_90.matrix

    def test_stack_sits_on_the_reference_top(self, model):
        model.add(
            brick(4, 2, color=Color.RED), Position(0, 0, 0), name="base"
        )  # 1 brick
        model.stack(brick(4, 2, color=Color.BLUE), "base", name="top")
        assert model.named("top").alignment_box[0] == Position(0, 0, 1)  # one brick up
        assert model.is_valid()  # studs meet antistuds; grounded

    def test_stack_uses_the_reference_height(self, model):
        model.add(
            brick(2, 1, height=2, color=Color.RED), Position(0, 0, 0), name="tall"
        )  # 2 bricks
        model.add(
            plate(4, 2, color=Color.WHITE), Position(5, 0, 0), name="thin"
        )  # 1/3 brick
        model.stack(brick(2, 1, color=Color.BLUE), "tall", name="on_tall")
        # Stacking on a plate lands one plate up -- a sub-brick elevation.
        model.stack(brick(4, 2, color=Color.BLUE), "thin", name="on_thin")
        assert model.named("on_tall").alignment_box[0] == Position(0, 0, 2)
        assert model.named("on_thin").alignment_box[0] == Position(5, 0, PLATE)

    def test_stack_with_horizontal_offset(self, model):
        model.add(
            brick(4, 2, color=Color.RED), Position(0, 0, 0), name="base"
        )  # 4 wide (X)
        model.stack(
            brick(2, 2, color=Color.BLUE), "base", Position(2, 0, 0), name="top"
        )
        # slid across the top, still resting
        assert model.named("top").alignment_box[0] == Position(2, 0, 1)

    def test_stack_honors_rotation_and_vertical_gap(self, model):
        model.add(brick(4, 2, color=Color.RED), name="base")  # 1 brick tall
        top = model.stack(
            brick(2, 2, color=Color.BLUE),
            "base",
            Position(0, 0, 1),
            Rotation.DEG_90,
            name="top",
        )
        # +1-brick gap; the rotated footprint's min corner stays at the anchor
        assert model.named("top").alignment_box[0] == Position(0, 0, 2)
        assert top.pose.rotation == Rotation.DEG_90.matrix

    def test_tuple_grid_placement_matches_positions(self):
        def build(coord):
            model = LegoBuild()
            base = model.add(brick(4, 2), coord(2, 3, 0), Rotation.DEG_90)
            model.stack(plate(2, 1), base, offset=coord(1, 0, 0))
            model.add(brick(1, 1), coord(0, 2, 0), relative_to=base)
            sub = LegoBuild()
            sub.add(brick(1, 1))
            model.extend(sub, coord(8, 0, 0))
            return model

        tuples = build(lambda x, y, z: (x, y, z))
        positions = build(Position)
        assert to_ldraw(tuples) == to_ldraw(positions)
        with pytest.raises(ValueError, match="grid"):
            tuples.add(brick(1, 1), (0.5, 0, 0))
        with pytest.raises(ValueError, match="grid"):
            tuples.stack(brick(1, 1), tuples.placements[0], offset=(0, 0, 0.5))


class TestReferenceSnapshot:
    """add()/stack()/connect() read the reference's geometry once, at call
    time: growing a nested reference afterwards does not move a dependent
    already placed against it."""

    def test_stack_on_a_sub_model_uses_its_current_height(self, model):
        # A sub-assembly two bricks tall: stacking on it lands two bricks up.
        sub = LegoBuild()
        sub.add(brick(2, 2, color=Color.RED), Position(0, 0, 0), name="lo")
        sub.stack(brick(2, 2, color=Color.RED), "lo")  # sub is 2 bricks tall
        model.add(sub, Position(0, 0, 0), name="tower")
        model.stack(brick(2, 2, color=Color.BLUE), "tower", name="cap")
        assert model.named("cap").alignment_box[0] == Position(0, 0, 2)

    def test_growing_a_nested_reference_after_stacking_leaves_the_dependent_in_place(
        self, model
    ):
        # add/stack/connect read the reference's geometry once, at call time
        # -- growing a nested sub-model afterwards does not move a part
        # already placed against it.
        sub = LegoBuild()
        sub.add(brick(2, 2, color=Color.RED), Position(0, 0, 0), name="lo")
        model.add(sub, Position(0, 0, 0), name="tower")
        cap = model.stack(brick(2, 2, color=Color.BLUE), "tower", name="cap")
        before = cap.alignment_box[0]
        sub.stack(brick(2, 2, color=Color.RED), "lo")  # tower grows after cap sits
        assert cap.alignment_box[0] == before

    def test_stack_resolves_against_the_reference_as_it_currently_stands(self, model):
        # A stack chain resolves immediately, each against the reference's
        # current top -- so calling in order still stacks in order.
        model.add(brick(2, 2, color=Color.RED), Position(0, 0, 0), name="a")
        model.stack(brick(2, 2, color=Color.GREEN), "a", name="b")
        model.stack(brick(2, 2, color=Color.BLUE), "b", name="c")
        assert model.named("b").alignment_box[0] == Position(0, 0, 1)
        assert model.named("c").alignment_box[0] == Position(0, 0, 2)


@pytest.mark.usefixtures("patch_connector_rules_registry")
class TestConnect:
    """LegoBuild.connect(): resolution, validation, registration."""

    @pytest.fixture
    def holder_and_insert(self, model, element_with, compatible_connector_types):
        """A model holding a "holder" exposing a slot connector, plus a loose
        insert element exposing a tab, ready to connect()."""
        tab, slot = compatible_connector_types
        holder = element_with({Connector(slot, Position(1, 0, 0), Direction.UP)})
        insert = element_with({Connector(tab, Position(1, 0, 0), Direction.UP)})
        model.add(holder, name="holder")
        return model, insert, tab, slot

    def test_connect_joins_and_couples_the_parts(self, holder_and_insert):
        model, insert, tab, slot = holder_and_insert
        model.connect(insert, tab, to=model.named("holder").find_connector(slot))
        assert model.is_connected()

    def test_connect_accepts_a_sub_model_as_content(
        self, element_with, compatible_connector_types, connector_specs
    ):
        tab, slot = compatible_connector_types
        holder = element_with({Connector(slot, Position(1, 0, 0), Direction.UP)})
        sub = LegoBuild()
        sub.add(
            element_with({Connector(tab, Position(0, 0, 0), Direction.UP)}),
            Position(2, 0, 0),
        )
        model = LegoBuild()
        model.add(holder, name="holder")
        model.connect(
            sub, tab, to=model.named("holder").find_connector(slot), name="arm"
        )
        assert model.is_connected()
        assert model.brick_count == 2
        # The sub-assembly's tab seats onto the holder's slot at (1, 0, 0).
        assert (tab, (1.0, 0.0, 0.0), (0, 0, 1), (1, 0, 0), 0) in connector_specs(
            model.named("arm")
        )

    def test_connect_registers_the_placement_under_name(self, holder_and_insert):
        model, insert, tab, slot = holder_and_insert
        placement = model.connect(
            insert, tab, to=model.named("holder").find_connector(slot), name="ins"
        )
        assert model.named("ins") is placement

    def test_connect_takes_an_index(self, holder_and_insert):
        model, insert, tab, slot = holder_and_insert
        model.add(brick(1, 1), Position(0, 0, 5), name="loose")

        placement = model.connect(
            insert, tab, to=model.named("holder").find_connector(slot), index=0
        )

        assert model.placements[0] is placement

    def test_connect_accepts_a_target_from_a_nested_named_placement(
        self, element_with, compatible_connector_types
    ):
        tab, slot = compatible_connector_types
        holder = element_with({Connector(slot, Position(1, 0, 0), Direction.UP)})
        insert = element_with({Connector(tab, Position(1, 0, 0), Direction.UP)})
        inner = LegoBuild()
        inner.add(holder, name="holder")
        outer = LegoBuild()
        outer.add(inner, name="inner")

        outer.connect(
            insert, tab, to=outer.named(["inner", "holder"]).find_connector(slot)
        )

        assert outer.is_connected()
        assert outer.brick_count == 2

    def test_connect_rejects_incompatible_types(self):
        model = LegoBuild()
        model.add(brick(1, 1, 1), name="base")
        with pytest.raises(ValueError, match="cannot mate"):
            model.connect(
                brick(1, 1, 1), STUD, to=model.named("base").find_connector(STUD)
            )

    def test_selecting_an_ambiguous_target_connector_raises(self):
        model = LegoBuild()
        model.add(brick(2, 2), name="base")
        with pytest.raises(ValueError, match="ambiguous"):
            model.connect(
                plate(1, 1), ANTISTUD, to=model.named("base").find_connector(STUD)
            )

    def test_connect_by_type_rejects_an_ambiguous_content_connector(
        self, element_with, holder_and_insert
    ):
        model, _insert, tab, slot = holder_and_insert
        double = element_with(
            {
                Connector(tab, Position(1, 0, 0), Direction.DOWN),
                Connector(tab, Position(2, 0, 0), Direction.DOWN),
            }
        )
        with pytest.raises(ValueError, match="ambiguous"):
            model.connect(double, tab, to=model.named("holder").find_connector(slot))

    def test_connect_matches_a_concrete_source_connector_by_value(
        self, holder_and_insert
    ):
        model, insert, tab, slot = holder_and_insert
        original = insert.find_connector(tab)
        equivalent = Connector(
            original.type,
            original.position,
            original.axis,
            original.side,
            length=original.length,
        )
        assert equivalent is not original
        model.connect(insert, equivalent, to=model.named("holder").find_connector(slot))
        assert model.is_connected()

    def test_connect_rejects_a_connector_not_on_the_content(self, holder_and_insert):
        model, insert, tab, slot = holder_and_insert
        with pytest.raises(ValueError, match="not a connector"):
            model.connect(
                insert,
                Connector(tab, Position(9, 9, 9), Direction.DOWN),
                to=model.named("holder").find_connector(slot),
            )

    def test_connect_rejects_wrong_params_kind(self, holder_and_insert):
        model, insert, tab, slot = holder_and_insert
        with pytest.raises(ValueError, match="FIXED"):
            model.connect(
                insert,
                tab,
                to=model.named("holder").find_connector(slot),
                mounting=Mounting(90),
            )

    # `connect` resolves a connector spec against the content before placing.
    def test_a_type_the_content_lacks_raises(
        self, model, element_with, compatible_connector_types
    ):
        tab, slot = compatible_connector_types
        holder = element_with({Connector(slot, Position(0, 0, 0), Direction.UP)})
        bare = element_with(frozenset())  # no connectors at all
        model.add(holder, name="holder")
        with pytest.raises(ValueError, match=f"has no {tab.name} connector"):
            model.connect(bare, tab, to=model.named("holder").find_connector(slot))

    # Passing concrete Connector points chosen from ``content.connectors``:
    # build two parts, pick a connector off each via their ``connectors``, and
    # hand those exact points to connect() -- this must work even when a
    # sub-assembly's own frame is not normalized to the origin.
    def test_element_content_and_target(
        self, element_with, compatible_connector_types, connector_specs
    ):
        tab, slot = compatible_connector_types
        holder = element_with({Connector(slot, Position(1, 0, 0), Direction.UP)})
        insert = element_with({Connector(tab, Position(0, 0, 0), Direction.UP)})
        (tab_conn,) = insert.connectors
        (slot_conn,) = holder.connectors
        model = LegoBuild()
        model.add(holder, name="holder")
        model.connect(
            insert,
            tab_conn,
            to=slot_conn.transformed(model.named("holder").pose),
            name="ins",
        )
        assert model.is_connected()
        assert (tab, (1.0, 0.0, 0.0), (0, 0, 1), (1, 0, 0), 0) in connector_specs(
            model.named("ins")
        )

    def test_sub_model_content(
        self, element_with, compatible_connector_types, connector_specs
    ):
        tab, slot = compatible_connector_types
        holder = element_with({Connector(slot, Position(1, 0, 0), Direction.UP)})
        sub = LegoBuild()
        sub.add(
            element_with({Connector(tab, Position(0, 0, 0), Direction.UP)}),
            Position(3, 0, 0),
        )
        (tab_conn,) = sub.find_connectors(tab)
        assert tab_conn.position == Position(3, 0, 0)  # own frame, not normalized
        model = LegoBuild()
        model.add(holder, name="holder")
        model.connect(
            sub, tab_conn, to=model.named("holder").find_connector(slot), name="arm"
        )
        assert model.is_connected()
        assert (tab, (1.0, 0.0, 0.0), (0, 0, 1), (1, 0, 0), 0) in connector_specs(
            model.named("arm")
        )

    def test_sub_model_target(self, element_with, compatible_connector_types):
        tab, slot = compatible_connector_types
        insert = element_with({Connector(tab, Position(0, 0, 0), Direction.UP)})
        holder = LegoBuild()
        holder.add(
            element_with({Connector(slot, Position(0, 0, 0), Direction.UP)}),
            Position(3, 0, 0),
        )
        (slot_conn,) = holder.find_connectors(slot)
        assert slot_conn.position == Position(3, 0, 0)
        model = LegoBuild()
        model.add(holder, name="holder")
        model.connect(
            insert,
            tab,
            to=slot_conn.transformed(model.named("holder").pose),
            name="ins",
        )
        assert model.is_connected()

    def test_connect_mates_by_connector_type(self, model):
        # `base` and `content` differ in height, so their `stud`/`antistud`
        # connectors sit at different local offsets: resolving either against
        # the wrong part (a content/reference mix-up) would land `content` at
        # the wrong height and disconnected from the ground.
        model.add(brick(1, 1, height=3, color=Color.RED), name="base")
        top = model.connect(
            brick(1, 1, color=Color.BLUE),
            "antistud",
            to=model.named("base").find_connector("stud"),
        )
        assert top.bounding_box[0] == Position(0, 0, 3)
        assert model.is_valid()

    def test_connect_resolves_each_connector_against_its_own_part(self, model):
        model.add(brick(1, 1, color=Color.RED), name="base")
        with pytest.raises(ValueError, match="stud and stud cannot mate"):
            model.connect(
                brick(1, 1, color=Color.BLUE),
                "stud",
                to=model.named("base").find_connector("stud"),
            )

    def test_connect_accepts_a_geometric_target_without_an_owner(self):
        model = LegoBuild()
        target = (
            brick(1, 1)
            .find_connector("stud")
            .transformed(Pose(translation=Position(4, 7, 2)))
        )
        placed = model.connect(plate(1, 1), "antistud", to=target)
        assert placed.find_connector("antistud").position == target.position
        assert model.brick_count == 1
        assert not model.floating_placements


@pytest.mark.usefixtures("patch_connector_rules_registry")
class TestConnectGeometry:
    """connect() geometry: coinciding points, aligning axes, whole-part poses,
    and the joint params that articulate the mated connector."""

    def test_connecting_a_stud_matches_stacking(self, connector_specs):
        model = LegoBuild()
        model.add(brick(1, 1, color=Color.RED), name="base")
        model.connect(
            plate(1, 1),
            ANTISTUD,
            to=model.named("base").find_connector(STUD),
            name="cap",
        )
        stacked = LegoBuild()
        stacked.add(brick(1, 1, color=Color.RED), name="base")
        stacked.stack(plate(1, 1), "base", name="cap")
        assert model.is_valid()
        assert connector_specs(model.named("cap")) == connector_specs(
            stacked.named("cap")
        )

    def test_point_coincides_and_axes_align(
        self, element_with, compatible_connector_types, connector_specs
    ):
        tab, slot = compatible_connector_types
        holder = element_with({Connector(slot, Position(1, 0, 0), Direction.LEFT)})
        insert = element_with({Connector(tab, Position(1, 0, 0), Direction.LEFT)})
        _, ins = _connect_pair(holder, insert, tab, slot)
        assert (tab, (1.0, 0.0, 0.0), (1, 0, 0), (0, 0, -1), 0) in connector_specs(ins)

    def test_a_second_connector_follows_the_whole_part(
        self, element_with, compatible_connector_types, connector_specs
    ):
        # A probe connector lets us observe the part's orientation, not just
        # the mated point: seating a FRONT tab onto a LEFT slot reorients the
        # whole frame, carrying the probe along (its 1-stud offset becomes 5/6
        # of a brick along the vertical on the non-square grid).
        tab, slot = compatible_connector_types
        probe = ConnectorType("probe")
        holder = element_with({Connector(slot, Position(1, 0, 0), Direction.LEFT)})
        insert = element_with(
            {
                Connector(tab, Position(0, 0, 0), Direction.FRONT),
                Connector(probe, Position(1, 0, 0), Direction.LEFT),
            }
        )
        _, ins = _connect_pair(holder, insert, tab, slot)
        specs = connector_specs(ins)
        assert (tab, (1.0, 0.0, 0.0), (1, 0, 0), (0, 0, -1), 0) in specs
        assert (probe, (1.0, 0.0, round(-5 / 6, 6)), (0, 0, -1), (0, -1, 0), 0) in specs

    def test_snot_tilts_the_content_sideways(self, element_with, connector_specs):
        # A sideways stud: the plate's antistud aligns to the holder's LEFT-facing
        # stud, so the plate tilts to face LEFT. Its own stud ends up facing LEFT,
        # one plate further out (2/5 of a stud on the non-square grid). The stud
        # sits at mid-height so its interface stays inside the holder's body and
        # the bounding-box anchoring (no grid-marked connectors) adds no offset.
        holder = element_with({Connector(STUD, Position(1, 0.5, 0.5), Direction.LEFT)})
        model, ins = _connect_pair(holder, plate(1, 1), ANTISTUD, STUD)
        specs = connector_specs(ins)
        assert (ANTISTUD, (1.0, 0.5, 0.5), (1, 0, 0), (0, 0, -1), 0) in specs
        assert (STUD, (1.4, 0.5, 0.5), (1, 0, 0), (0, 0, -1), 0) in specs
        assert model.is_connected()

    def test_flip_for_a_downward_facing_stud(self, element_with, connector_specs):
        holder = element_with({Connector(STUD, Position(0.5, 0.5, 0), Direction.DOWN)})
        _, ins = _connect_pair(holder, plate(1, 1), ANTISTUD, STUD)
        specs = connector_specs(ins)
        assert (ANTISTUD, (0.5, 0.5, 0.0), (0, 0, -1), (-1, 0, 0), 0) in specs
        assert (STUD, (0.5, 0.5, round(-PLATE, 6)), (0, 0, -1), (-1, 0, 0), 0) in specs

    def test_target_connector_follows_the_reference_pose(
        self, element_with, compatible_connector_types, connector_specs
    ):
        tab, slot = compatible_connector_types
        holder = element_with({Connector(slot, Position(1, 0, 0), Direction.LEFT)})
        insert = element_with({Connector(tab, Position(0, 0, 0), Direction.FRONT)})
        model, ins = _connect_pair(
            holder,
            insert,
            tab,
            slot,
            holder_position=Position(2, 2, 0),
            holder_rotation=Rotation.DEG_90,
        )
        (hslot,) = model.named("holder").find_connectors(slot)
        # The insert exposes a tab at the holder's world slot, frame aligned.
        seated = Connector(tab, hslot.position, hslot.axis, hslot.side)
        assert connector_specs([seated]) <= connector_specs(ins)

    def test_revolute_rotates_about_the_connector_axis(
        self, element_with, connector_specs
    ):
        pin, hole = ConnectorType("pin"), ConnectorType("hole")
        probe = ConnectorType("probe")
        mark_compatible(pin, hole, joint=JointKind.REVOLUTE)
        holder = element_with({Connector(hole, Position(1, 0, 1), Direction.UP)})
        insert = element_with(
            {
                Connector(pin, Position(1, 0, 0), Direction.UP),
                Connector(probe, Position(2, 0, 0), Direction.LEFT),
            }
        )
        _, ins = _connect_pair(holder, insert, pin, hole, mounting=Mounting(angle=90))
        specs = connector_specs(ins)
        # The mated pin pivots in place; the probe swings a quarter turn.
        assert (pin, (1.0, 0.0, 1.0), (0, 0, 1), (0, 1, 0), 0) in specs
        assert (probe, (1.0, 1.0, 1.0), (0, 1, 0), (0, 0, -1), 0) in specs

    def test_prismatic_slides_along_the_axis_in_studs(
        self, element_with, connector_specs
    ):
        bar, clip = ConnectorType("bar"), ConnectorType("clip")
        mark_compatible(bar, clip, joint=JointKind.PRISMATIC)
        holder = element_with({Connector(clip, Position(0, 0, 1), Direction.UP)})
        insert = element_with({Connector(bar, Position(0, 0, 0), Direction.UP)})
        _, ins = _connect_pair(holder, insert, bar, clip, mounting=Mounting(offset=1))
        # One stud along UP is 5/6 of a brick on the non-square grid.
        assert (
            bar,
            (0.0, 0.0, round(11 / 6, 6)),
            (0, 0, 1),
            (1, 0, 0),
            0,
        ) in connector_specs(ins)

    def test_cylindrical_slides_and_rotates(self, element_with, connector_specs):
        rod, grip = ConnectorType("rod"), ConnectorType("grip")
        probe = ConnectorType("probe")
        mark_compatible(rod, grip, joint=JointKind.CYLINDRICAL)
        holder = element_with({Connector(grip, Position(0, 0, 1), Direction.UP)})
        insert = element_with(
            {
                Connector(rod, Position(0, 0, 0), Direction.UP),
                Connector(probe, Position(1, 0, 0), Direction.LEFT),
            }
        )
        _, ins = _connect_pair(
            holder, insert, rod, grip, mounting=Mounting(offset=1, angle=90)
        )
        specs = connector_specs(ins)
        assert (rod, (0.0, 0.0, round(11 / 6, 6)), (0, 0, 1), (0, 1, 0), 0) in specs
        assert (probe, (0.0, 1.0, round(11 / 6, 6)), (0, 1, 0), (0, 0, -1), 0) in specs

    def test_ball_yaw_swings_about_the_vertical(self, element_with, connector_specs):
        ball, socket = ConnectorType("ball"), ConnectorType("socket")
        probe = ConnectorType("probe")
        mark_compatible(ball, socket, joint=JointKind.BALL)
        holder = element_with({Connector(socket, Position(1, 0, 2), Direction.UP)})
        insert = element_with(
            {
                Connector(ball, Position(1, 0, 0), Direction.UP),
                Connector(probe, Position(2, 0, 0), Direction.LEFT),
            }
        )
        _, ins = _connect_pair(
            holder, insert, ball, socket, mounting=Mounting(angle=90)
        )
        assert (probe, (1.0, 1.0, 2.0), (0, 1, 0), (0, 0, -1), 0) in connector_specs(
            ins
        )

    def test_pose_orients_a_revolute_joint(self, element_with, connector_specs):
        pin, hole = ConnectorType("pin"), ConnectorType("hole")
        probe = ConnectorType("probe")
        mark_compatible(pin, hole, joint=JointKind.REVOLUTE)
        holder = element_with({Connector(hole, Position(1, 0, 1), Direction.UP)})
        insert = element_with(
            {
                Connector(pin, Position(1, 0, 0), Direction.UP),
                Connector(probe, Position(2, 0, 0), Direction.LEFT),
            }
        )
        # A revolute about +Z by a quarter turn == Rotation.DEG_90's matrix.
        _, by_pose = _connect_pair(
            holder,
            insert,
            pin,
            hole,
            target_rotation=Rotation.DEG_90.matrix,
            target_position=Position.ZERO,
        )
        _, by_angle = _connect_pair(holder, insert, pin, hole, mounting=Mounting(90))
        assert connector_specs(by_pose) == connector_specs(by_angle)

    def test_pose_and_mounting_sum(self, element_with, connector_specs):
        pin, hole = ConnectorType("pin"), ConnectorType("hole")
        probe = ConnectorType("probe")
        mark_compatible(pin, hole, joint=JointKind.REVOLUTE)
        holder = element_with({Connector(hole, Position(1, 0, 1), Direction.UP)})
        insert = element_with(
            {
                Connector(pin, Position(1, 0, 0), Direction.UP),
                Connector(probe, Position(2, 0, 0), Direction.LEFT),
            }
        )
        _, summed = _connect_pair(
            holder,
            insert,
            pin,
            hole,
            target_rotation=Rotation.DEG_90.matrix,
            target_position=Position.ZERO,
            mounting=Mounting(10),
        )
        _, direct = _connect_pair(holder, insert, pin, hole, mounting=Mounting(100))
        assert connector_specs(summed) == connector_specs(direct)

    @pytest.mark.parametrize("rotation", list(Rotation))
    def test_connect_uses_world_target(self, rotation):
        model = LegoBuild()
        base = model.add(brick(1, 1), (4, 7, 2), rotation)
        target = base.find_connector("stud")
        placed = model.connect(plate(1, 1), "antistud", to=target)
        assert placed.find_connector("antistud").position == target.position
        assert model.is_connected()

    @pytest.mark.usefixtures("patch_connector_rules_registry")
    def test_connect_targets_can_be_specified_independently(self, element_with):
        rod, grip = ConnectorType("test_rod"), ConnectorType("test_grip")
        mark_compatible(rod, grip, joint=JointKind.CYLINDRICAL)
        source = Connector(rod, Position.ZERO, Direction.UP, Direction.FRONT, length=5)
        target = Connector(
            grip, Position(8, 3, 2), Direction.UP, Direction.RIGHT, length=5
        )
        part = element_with({source})
        model = LegoBuild()
        rest = model.connect(part, source, to=target)
        moved = model.connect(part, source, to=target, target_position=(8, 3, 3))
        assert moved.pose.rotation == rest.pose.rotation
        assert moved.find_connector(rod).position == Position(8, 3, 3)
        rotated = model.connect(
            part, source, to=target, target_rotation=Rotation.DEG_90
        )
        assert rotated.find_connector(rod).position == target.position
        assert rotated.pose.rotation == Rotation.DEG_90.matrix
        both = model.connect(
            part,
            source,
            to=target,
            target_position=(8, 3, 3),
            target_rotation=Rotation.DEG_90.matrix,
        )
        assert both.pose == Pose(Rotation.DEG_90.matrix, Position(8, 3, 3))


class TestJointRecords:
    @pytest.mark.parametrize("missing", [0, 1])
    def test_constructor_rejects_a_joint_with_a_missing_endpoint(
        self, turntable, missing
    ):
        model, _, _ = turntable()
        placements = list(model.placements)
        placements.pop(missing)
        with pytest.raises(ValueError, match="endpoint"):
            LegoBuild(placements, joints=model.joints)

    @pytest.mark.parametrize("depth", [1, 2])
    def test_nested_joint_handles_survive_unrelated_edits(self, turntable, depth):
        inner, _, _ = turntable(motion=MotionRange(Revolute(-45), Revolute(45)))
        outer = inner
        for _ in range(depth):
            wrapper = LegoBuild()
            wrapper.add_raw(outer)
            outer = wrapper
        joint = outer.flattened_joints[0]
        for model in (inner, outer):
            other = model.add_raw(brick(1, 1), Pose(translation=Position(10, 0, 0)))
            assert outer.flattened_joints[0] is joint
            outer.posed({joint: Revolute(10)})
            model.remove(other)
            assert outer.flattened_joints[0] is joint

    def test_repeated_submodels_keep_distinct_stable_joint_handles(self, turntable):
        inner, _, _ = turntable(motion=MotionRange(Revolute(-45), Revolute(45)))
        outer = LegoBuild()
        outer.add_raw(inner)
        outer.add_raw(inner, Pose(translation=Position(10, 0, 0)))
        first, second = outer.flattened_joints
        assert first is not second
        outer.add_raw(brick(1, 1), Pose(translation=Position(20, 0, 0)))
        assert outer.flattened_joints == (first, second)
        posed = outer.posed({first: Revolute(20)})
        assert posed.placements[3].pose == outer.flattened_placements[3].pose

    def test_nested_handles_are_invalidated_when_the_joint_changes(self, turntable):
        inner, _, top = turntable(motion=MotionRange(Revolute(-45), Revolute(45)))
        outer = LegoBuild()
        outer.add_raw(inner)
        joint = outer.flattened_joints[0]
        inner.set_motion(top, MotionRange(Revolute(-30), Revolute(30)))
        with pytest.raises(ValueError, match="belong"):
            outer.posed({joint: Revolute(0)})
        current = outer.flattened_joints[0]
        outer.posed({current: Revolute(10)})
        inner.remove(top)
        assert outer.flattened_joints == ()

    def test_nested_joint_caches_do_not_break_copying_or_pickling(self, turntable):
        inner, _, _ = turntable(motion=MotionRange(Revolute(-45), Revolute(45)))
        outer = LegoBuild()
        outer.add_raw(inner)
        assert len(outer.flattened_joints) == 1
        for copied in (outer.deepcopy(), pickle.loads(pickle.dumps(outer))):
            joint = copied.flattened_joints[0]
            assert joint.parent.path[0] is copied.placements[0]
            copied.posed({joint: Revolute(10)})
            assert copied.check_motion(samples=3).passed

    def test_failed_name_registration_leaves_joint_records_unchanged(self, turntable):
        model, base, _ = turntable()
        before = model.placements, model.joints
        with pytest.raises(ValueError):
            model.connect(
                Element("3679", Color.RED),
                "turntable_pin",
                to=base.find_connector("turntable_socket"),
                name="top",
            )
        assert (model.placements, model.joints) == before

    def test_enabling_replacing_and_disabling_motion(self, turntable):
        model, _, top = turntable()
        original = model.joint(top)
        enabled = model.set_motion(top, MotionRange(Revolute(-45), Revolute(45)))
        assert model.joint(top) is enabled
        assert model.flattened_joints == (enabled,)
        with pytest.raises(ValueError, match="belong"):
            model.set_motion(original, None)
        disabled = model.set_motion(enabled, None)
        assert disabled.motion is None

    def test_extend_remaps_joints_even_when_extending_itself(self, turntable):
        model, _, _ = turntable()
        model.extend(model, Position(10, 0, 0))
        first, second = model.joints
        assert second.parent.path == (model.placements[2],)
        assert second.child.path == (model.placements[3],)
        assert first.parent.path == (model.placements[0],)
        model.remove(model.placements[2])
        assert model.joints == (first,)

    def test_deleting_nested_child_removes_joint_from_shared_owners(self):
        child = LegoBuild()
        child.add_raw(Element("3679", Color.WHITE), name="top")
        outer = LegoBuild()
        base = outer.add_raw(Element("3680", Color.WHITE))
        outer.connect(
            child, "turntable_pin", to=base.find_connector("turntable_socket")
        )
        copied = outer.copy()
        child.remove("top")
        assert outer.joints == copied.joints == ()

    def test_mounting_is_static_by_default(self, turntable):
        model, base, top = turntable(mounting=Mounting(angle=37))
        (joint,) = model.joints
        assert joint.parent.path == (base,)
        assert joint.child.path == (top,)
        assert joint.kind is JointKind.REVOLUTE
        assert joint.motion is None
        with pytest.raises(ValueError, match="static"):
            model.posed({joint: Revolute(10)})

    @pytest.mark.parametrize("which", ["base", "top"])
    def test_remove_either_endpoint_removes_joint(self, turntable, which):
        model, _, _ = turntable()
        model.remove(which)
        assert model.joints == ()

    def test_nested_endpoint_deletion_removes_outer_joint(self):
        inner = LegoBuild()
        inner.add_raw(Element("3680", Color.WHITE), name="base")
        outer = LegoBuild()
        placed = outer.add_raw(inner)
        outer.connect(
            Element("3679", Color.RED),
            "turntable_pin",
            to=placed.find_connector("turntable_socket"),
        )
        assert len(outer.joints) == 1
        inner.remove("base")
        assert outer.joints == ()
        assert outer._joints == []

    def test_failed_connect_is_atomic(self, turntable):
        model, _, _ = turntable()
        before = model.placements, model.joints
        with pytest.raises(ValueError):
            model.connect(
                Element("3679", Color.RED),
                "turntable_pin",
                to=model.named("base").find_connector("turntable_socket"),
                motion=MotionRange(Prismatic(-1), Prismatic(1)),
            )
        assert (model.placements, model.joints) == before

    def test_copy_and_pickle_preserve_endpoint_identity(self, turntable):
        model, _, _ = turntable()
        for copied in [
            model.copy(),
            model.deepcopy(),
            pickle.loads(pickle.dumps(model)),
        ]:
            joint = copied.joints[0]
            assert joint.parent.path[0] is copied.named("base")
            assert joint.child.path[0] is copied.named("top")
            copied.remove("top")
            assert not copied.joints
        assert len(model.joints) == 1


class TestExtend:
    def test_reposes_each_placement_like_add(self, model, filled_region):
        # extend's pose composition matches what add() would give the whole
        # sub-model, for a non-zero position and a rotation.
        source = LegoBuild()
        source.add(brick(2, 1, color=Color.RED), Position(0, 0, 0))
        source.add(brick(1, 1, color=Color.BLUE), Position(2, 0, 0))

        model.extend(source, Position(5, 3, 0), Rotation.DEG_90)

        expected = LegoBuild()
        expected.add(source, Position(5, 3, 0), Rotation.DEG_90)
        assert filled_region(model) == filled_region(expected)

    def test_creates_no_sub_model_grouping(self, model):
        # extend inlines other's placements directly: no sub-file, and no
        # placement whose content is other itself.
        source = LegoBuild()
        source.add(brick(2, 1, color=Color.RED), Position(0, 0, 0))
        source.add(brick(1, 1, color=Color.BLUE), Position(2, 0, 0))

        model.extend(source, Position(1, 0, 0))

        assert len(model.placements) == 2
        assert all(isinstance(p.content, Element) for p in model.placements)
        assert "0 FILE" not in to_ldraw(model)

    def test_preserves_nesting_inside_the_extended_model(self, model):
        inner = LegoBuild()
        inner.add(brick(2, 2, color=Color.RED))
        source = LegoBuild()
        source.add(inner, Position(0, 0, 0))

        model.extend(source)

        assert model.placements[0].content is inner
        assert model.brick_count == 1
        inner.add(brick(2, 2, color=Color.BLUE), Position(4, 0, 0))
        assert model.brick_count == 2  # the nested model is held live

    def test_does_not_carry_over_the_extended_models_names(self, model):
        source = LegoBuild()
        source.add(brick(2, 2, color=Color.RED), name="cell")

        model.extend(source)

        assert "cell" not in model.names

    def test_is_a_snapshot_of_the_placement_list(self, model):
        # Unlike add(), extend does not hold other itself: growing it
        # afterwards does not grow this model.
        source = LegoBuild()
        source.add(brick(2, 2, color=Color.RED))

        model.extend(source)
        source.add(brick(2, 2, color=Color.BLUE), Position(4, 0, 0))

        assert model.brick_count == 1

    def test_extend_does_not_keep_the_donor_alive(self, model):
        # extend() takes a snapshot, so nothing should keep the donor
        # reachable once the caller drops it.
        donor = LegoBuild()
        donor.add(brick(1, 1, color=Color.BLUE))
        alive = weakref.ref(donor)

        model.extend(donor)
        del donor
        gc.collect()

        assert alive() is None

    def test_returns_the_new_placements_in_order(self, model):
        source = LegoBuild()
        p1 = source.add(brick(2, 1, color=Color.RED), Position(0, 0, 0))
        p2 = source.add(brick(1, 1, color=Color.BLUE), Position(2, 0, 0))

        result = model.extend(source, Position(1, 0, 0))

        assert result == model.placements
        assert [p.content for p in result] == [p1.content, p2.content]

    def test_extending_a_model_with_itself_duplicates_its_snapshot(self, model):
        model.add(brick(2, 2, color=Color.RED))
        before = model.placements

        result = model.extend(model, Position(10, 0, 0))

        assert model.placements[: len(before)] == before
        assert len(result) == len(before)
        assert model.brick_count == 2 * len(before)

    def test_a_rejected_extend_leaves_the_host_untouched(self, model):
        # `other` holds a brick, then `model` itself (nesting `model` closes a
        # cycle), then another brick: extending should reject the whole batch
        # before recording any of it, not just stop partway through.
        model.add(brick(2, 2, color=Color.RED))
        before = model.placements

        other = LegoBuild()
        other.add(brick(1, 1, color=Color.BLUE))
        other.add(model)
        other.add(brick(1, 1, color=Color.GREEN))

        with pytest.raises(ValueError, match="cannot contain itself"):
            model.extend(other)

        assert model.placements == before

    def test_extend_does_not_carry_the_markers(self, model):
        other = LegoBuild()
        other.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        other.add_step()
        model.extend(other)
        assert model.step_markers == ()


class TestAddStep:
    def test_add_step_records_a_marker_at_the_current_end(self, model):
        model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        model.add_step()
        model.add(brick(1, 1, color=Color.BLUE), Position(2, 0, 0))
        assert model.step_markers == (1,)
        assert model.steps == (model.placements[:1], model.placements[1:])

    def test_add_step_twice_closes_an_empty_step(self, model):
        # An instruction page with nothing to place: how a finished model is showcased.
        model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        model.add_step()
        model.add_step()
        assert model.step_markers == (1, 1)
        assert model.steps == (model.placements, ())

    def test_add_step_before_any_placement_closes_an_empty_first_step(self, model):
        model.add_step()
        model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        assert model.step_markers == (0,)
        assert model.steps == ((), model.placements)

    def test_add_step_keeps_the_geometry_caches(self, model):
        # A step is not geometry, so recording one must not drop what is cached.
        model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        assert model.bounding_box
        model.add_step()
        assert "bounding_box" in model.__dict__

    def test_add_step_docstring_does_not_name_a_private_method(self):
        # Published via api_reference(): it must describe what add_step does,
        # not point users at an internal implementation detail like _record.
        doc = LegoBuild.add_step.__doc__
        assert doc is not None
        assert "_record" not in doc

    def test_add_step_takes_a_placement_count(self, model):
        model.add(brick(4, 2), name="a")
        model.add(brick(4, 2), Position(0, 0, 1), name="b")
        model.add_step(1)

        assert model.step_markers == (1,)
        assert [model.name_of(p) for p in model.steps[0]] == ["a"]
        assert [model.name_of(p) for p in model.steps[1]] == ["b"]

    def test_markers_stay_sorted_however_they_are_added(self, model):
        for _ in range(6):
            model.add(brick(4, 2), Position(0, 0, len(model.placements)))
        model.add_step(5)
        model.add_step(2)

        assert model.step_markers == (2, 5)

    def test_add_step_accepts_a_negative_count(self, model):
        model.add(brick(4, 2))
        model.add(brick(4, 2), Position(0, 0, 1))
        model.add_step(-1)

        assert model.step_markers == (1,)


class TestRemoveStep:
    def test_remove_step_drops_the_marker_at_that_count(self, model):
        model.add(brick(4, 2))
        model.add(brick(4, 2), Position(0, 0, 1))
        model.add_step(1)
        model.add_step(2)

        model.remove_step(1)

        assert model.step_markers == (2,)

    def test_remove_step_drops_one_of_a_repeated_marker(self, model):
        model.add(brick(4, 2))
        model.add_step(1)
        model.add_step(1)

        model.remove_step(1)

        assert model.step_markers == (1,)

    def test_add_then_remove_round_trips(self, model):
        model.add(brick(4, 2))
        model.add_step()
        before = model.step_markers
        model.add_step(0)
        model.remove_step(0)

        assert model.step_markers == before

    def test_remove_step_without_a_marker_there_raises(self, model):
        model.add(brick(4, 2))
        model.add_step(1)

        with pytest.raises(ValueError, match="no build-step marker"):
            model.remove_step(0)

    @pytest.mark.parametrize("index", (2, -3, 99))
    def test_step_index_outside_the_placements_raises(self, model, index):
        model.add(brick(4, 2))

        with pytest.raises(IndexError, match="out of range"):
            model.add_step(index)
        with pytest.raises(IndexError, match="out of range"):
            model.remove_step(index)


class TestCopy:
    def test_copy_is_independent(self, model):
        model.add(brick(2, 2, color=Color.RED), name="base")
        duplicate = model.copy()
        model.add(brick(2, 2, color=Color.BLUE), Position(4, 0, 0))
        assert duplicate.brick_count == 1
        assert duplicate.named("base") is model.named("base")

    def test_copy_preserves_the_subclass(self):
        class Subclass(LegoBuild):
            pass

        model = Subclass()
        model.add(brick(2, 2, color=Color.RED))
        assert type(model.copy()) is Subclass

    def test_deepcopy_preserves_internal_sharing_but_isolates_mutations(self):
        child = LegoBuild()
        child.add(brick(1, 1), name="leaf")
        child.add_step()
        model = LegoBuild()
        model.add(child, name="left")
        model.add(child, (4, 0, 0), name="right")
        model.add_step()
        model.named(["left", "leaf"])
        assert model.brick_count == 2
        original_box = model.bounding_box
        clone = model.deepcopy()
        assert to_ldraw(clone) == to_ldraw(model)
        cloned_child = clone.named("left").content
        assert isinstance(cloned_child, LegoBuild)
        assert cloned_child is clone.named("right").content
        assert cloned_child is not child
        assert clone.named("left") is not model.named("left")
        assert cloned_child.step_markers == child.step_markers
        assert clone.step_markers == model.step_markers
        assert clone.brick_count == 2
        assert clone.bounding_box == original_box
        child.add(brick(1, 1), (0, 0, 1))
        assert model.brick_count == 4
        assert clone.brick_count == 2
        cloned_child.remove("leaf")
        assert clone.brick_count == 0
        assert model.brick_count == 4

    def test_copy_carries_the_markers(self, model):
        model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        model.add_step()
        assert model.copy().step_markers == (1,)

    def test_adding_to_a_copy_leaves_the_original_markers_alone(self, model):
        model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        copy = model.copy()
        copy.add_step()
        assert model.step_markers == ()
        assert copy.step_markers == (1,)


class TestRepr:
    def test_model_summary(self, model):
        # Height reports the physical extent: 3 bricks plus the stud layer.
        model.add(brick(2, 2, 3, color=Color.RED))
        assert repr(model) == "LegoBuild(1 brick, 2x2x3.167)"

    def test_empty_model(self):
        assert repr(LegoBuild()) == "LegoBuild(0 bricks, 0x0x0)"


class TestReferences:
    """How a part is referenced: by name, by the placement add()/stack()
    returned, or rejected when it names something this model does not hold."""

    class TestNaming:
        """`LegoBuild`'s own name table: lookup, reverse lookup, and the read-only view."""

        @pytest.fixture
        def model(self, model):
            model.add(brick(4, 2, color=Color.RED), name="base")
            model.add(brick(2, 1, color=Color.BLUE), Position(0, 0, 1))  # unnamed
            return model

        def test_named_returns_the_registered_placement(self, model):
            assert model.named("base") is model.placements[0]

        def test_name_of_reverses_the_lookup(self, model):
            assert model.name_of(model.named("base")) == "base"

        def test_name_of_an_unnamed_placement_is_none(self, model):
            assert model.name_of(model.placements[1]) is None

        def test_unknown_name_raises(self):
            with pytest.raises(KeyError, match="no part named 'nope'"):
                LegoBuild().named("nope")

        def test_names_maps_each_name_to_its_placement(self, model):
            assert dict(model.names) == {"base": model.placements[0]}

        def test_names_is_a_read_only_view(self, model):
            # `names` is a read-only view over the name table.
            with pytest.raises(TypeError):
                model.names["other"] = model.placements[1]
            assert "other" not in model.names

        def test_names_are_kept_by_identity_not_value(self, model):
            # Two equal-looking bricks placed separately keep their own names.
            model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0), name="left")
            model.add(brick(1, 1, color=Color.RED), Position(4, 0, 0), name="right")
            assert model.name_of(model.named("left")) == "left"
            assert model.name_of(model.named("right")) == "right"

    def test_stacking_accepts_a_returned_placement(self, model):
        base = model.add(brick(4, 2, color=Color.RED))
        on_top = model.stack(brick(2, 2, color=Color.BLUE), on=base)
        assert on_top.bounding_box[0].z == base.alignment_height

    def test_stacking_accepts_a_name(self, model):
        base = model.add(brick(4, 2, color=Color.RED), name="base")
        on_top = model.stack(brick(2, 2, color=Color.BLUE), on="base")
        assert on_top.bounding_box[0].z == base.alignment_height

    def test_a_placement_from_another_model_is_used_as_geometry(self, model):
        other = LegoBuild()
        stray = other.add(brick(2, 2, color=Color.RED))
        placed = model.stack(brick(2, 2, color=Color.BLUE), on=stray)
        assert placed.alignment_box[0].z == stray.alignment_box[1].z
        assert model.brick_count == 1

    def test_a_duplicate_name_leaves_the_model_unchanged(self, model):
        model.add(brick(2, 2, color=Color.RED), name="base")
        with pytest.raises(ValueError):
            model.add(brick(2, 2, color=Color.BLUE), name="base")
        assert model.brick_count == 1

    def test_unknown_reference_raises(self, model):
        with pytest.raises(KeyError):
            model.add(
                brick(1, 1, color=Color.RED), Position(0, 0, 1), relative_to="missing"
            )

    def test_stack_unknown_reference_raises(self, model):
        with pytest.raises(KeyError):
            model.stack(brick(1, 1, color=Color.RED), "ghost")

    def test_named_returns_the_object_add_returned(self):
        # named() and name_of() see add()'s returned placement immediately, by
        # identity.
        m = LegoBuild()
        named = m.add(brick(4, 2, color=Color.RED), name="base")
        unnamed = m.add(brick(2, 1, color=Color.BLUE), Position(0, 0, 1))
        assert m.named("base") is named
        assert m.name_of(named) == "base"
        assert m.name_of(unnamed) is None


class TestNestedNames:
    @pytest.fixture
    def nested(self):
        """A model holding a sub-model that holds a sub-model."""
        inner = LegoBuild()
        inner.add(brick(4, 2), name="core")
        middle = LegoBuild()
        middle.add(inner, name="inner")
        outer = LegoBuild()
        outer.add(middle, Position(4, 0, 0), name="middle")
        return outer, middle, inner

    def test_resolves_a_two_step_path(self, nested):
        outer, middle, _ = nested

        assert outer.named(["middle", "inner"]).content is middle.named("inner").content

    def test_resolves_an_arbitrarily_deep_path(self, nested):
        outer, _, inner = nested

        assert (
            outer.named(["middle", "inner", "core"]).content
            is inner.named("core").content
        )

    def test_a_nested_placement_is_posed_in_the_outer_frame(self, nested):
        outer, _, _ = nested
        nested_leaf = outer.named(["middle", "inner", "core"])

        assert nested_leaf.bounding_box[0].x == pytest.approx(outer.bounding_box[0].x)

    def test_a_single_element_path_matches_a_plain_name(self, nested):
        outer, _, _ = nested

        assert outer.named(["middle"]) is outer.named("middle")

    def test_a_path_is_memoized(self, nested):
        outer, _, _ = nested

        assert outer.named(["middle", "inner"]) is outer.named(["middle", "inner"])

    @pytest.mark.parametrize("path", (["middle", "inner"], ["middle", "inner", "core"]))
    def test_a_resolved_path_is_the_flattened_leaf(self, nested, path):
        """Identity is a ``Placement``'s only equality, so a leaf reached by
        name has to be the same object as the matching flattened one at every
        depth -- otherwise ``named(path) in model.colliding_placements[0]``
        answers wrongly for deep paths only."""
        outer, _, _ = nested
        resolved = outer.named(path)
        leaf = outer.flattened_placements[0]

        if isinstance(resolved.content, Element):
            assert resolved is leaf
        else:
            assert outer.named([*path, "core"]) is leaf

    def test_editing_a_sub_model_does_not_grow_the_host_cache(self):
        """A host caches its compositions against the sub-model's placements.
        Those keys are weak, so a placement the sub-model drops takes its
        entry with it instead of accumulating for the host's lifetime."""
        inner = LegoBuild()
        inner.add(brick(4, 2), name="core")
        outer = LegoBuild()
        outer.add(inner, name="sub")

        for _ in range(50):
            assert outer.brick_count == 1
            inner.remove(0)
            inner.add(brick(4, 2), name="core")
        gc.collect()

        cached = outer.__dict__["_compose_cache"][outer.named("sub")]
        assert len(cached) <= 2

    def test_relative_to_accepts_a_path(self, nested):
        outer, _, _ = nested
        placed = outer.add(
            brick(4, 2), Position(0, 0, 1), relative_to=["middle", "inner"]
        )

        lo, _ = placed.bounding_box
        assert (lo.x, lo.y, lo.z) == pytest.approx((4, 0, 1))

    def test_stack_accepts_a_path(self, nested):
        outer, _, _ = nested
        stacked = outer.stack(brick(4, 2), ["middle", "inner", "core"])

        assert stacked.alignment_box[0].z == pytest.approx(1)

    def test_a_composed_placement_is_accepted_back_as_a_reference(self, nested):
        outer, _, _ = nested
        reference = outer.named(["middle", "inner"])

        placed = outer.add(brick(4, 2), Position(0, 0, 1), relative_to=reference)

        lo, _ = placed.bounding_box
        assert (lo.x, lo.y, lo.z) == pytest.approx((4, 0, 1))

    def test_a_saved_composed_placement_is_accepted_after_removal(self, nested):
        outer, _, _ = nested
        depth_two = outer.named(["middle", "inner"])
        depth_three = outer.named(["middle", "inner", "core"])

        outer.remove("middle")

        assert outer.add(brick(4, 2), Position(0, 0, 1), relative_to=depth_two)
        assert outer.add(brick(4, 2), Position(0, 0, 1), relative_to=depth_three)

    def test_a_string_is_not_treated_as_a_path(self, model):
        model.add(brick(4, 2), name="abc")

        assert model.named("abc") is model.placements[0]

    def test_an_empty_path_raises(self, model):
        with pytest.raises(ValueError, match="at least one name"):
            model.named([])

    def test_a_path_through_an_element_raises(self, model):
        model.add(brick(4, 2), name="solid")

        with pytest.raises(ValueError, match="not a sub-model"):
            model.named(["solid", "deeper"])

    def test_an_unknown_name_in_a_path_raises(self, nested):
        outer, _, _ = nested

        with pytest.raises(KeyError, match="nope"):
            outer.named(["middle", "nope"])

    def test_name_of_a_composed_placement_is_none(self, nested):
        outer, _, _ = nested

        assert outer.name_of(outer.named(["middle", "inner"])) is None

    def test_pickling_drops_the_composition_cache(self, nested):
        outer, _, _ = nested
        outer.named(["middle", "inner"])

        revived = pickle.loads(pickle.dumps(outer))

        assert not revived._compose_cache
        assert revived.named(["middle", "inner"]) is not None

    def test_a_reference_resolves_on_a_model_that_never_composed(self, model):
        """Using a plain placement reference requires no composition cache."""
        placed = model.add(brick(4, 2), name="a")
        revived = pickle.loads(pickle.dumps(model))

        assert model.add(brick(4, 2), Position(0, 0, 1), relative_to=placed)
        assert revived.add(
            brick(4, 2), Position(0, 0, 1), relative_to=revived.placements[0]
        )

    @pytest.mark.parametrize("remove_from", ["inner", "outer"])
    @pytest.mark.parametrize("operation", ["add", "stack"])
    def test_saved_nested_reference_survives_removal(self, remove_from, operation):
        sub = LegoBuild()
        leaf = sub.add(brick(1, 1), name="leaf")
        model = LegoBuild()
        assembly = model.add(sub, (3, 4, 0), name="assembly")
        saved = model.named(["assembly", "leaf"])
        if remove_from == "inner":
            sub.remove(leaf)
        else:
            model.remove(assembly)
        if operation == "add":
            placed = model.add(brick(1, 1), relative_to=saved)
            assert placed.pose == saved.pose
        else:
            placed = model.stack(brick(1, 1), on=saved)
            assert placed.alignment_box[0].z == saved.alignment_box[1].z
        assert model.brick_count == 1
        assert not model.floating_placements


class TestExposedConnectors:
    def test_a_mated_stud_is_hidden(self, model):
        model.add(brick(4, 2), name="base")
        model.stack(brick(4, 2), "base", name="top")

        exposed = model.connectors
        seam = model.named("top").bounding_box[0].z

        assert not any(
            c.type is STUD and c.position.z == pytest.approx(seam) for c in exposed
        )

    def test_free_connectors_are_still_exposed(self, model):
        model.add(brick(4, 2), name="base")
        model.stack(brick(4, 2), "base", name="top")

        assert any(c.type is STUD for c in model.connectors)
        assert any(c.type is ANTISTUD for c in model.connectors)

    def test_a_lone_part_exposes_everything(self, model):
        solo = brick(4, 2)
        model.add(solo, name="solo")

        assert len(model.connectors) == len(model.placements[0].connectors)

    def test_hiding_reaches_across_a_sub_model_boundary(self, model):
        sub = LegoBuild()
        sub.add(brick(4, 2), name="inner")
        model.add(sub, name="sub")
        model.stack(brick(4, 2), ["sub", "inner"], name="top")

        seam = model.named("top").bounding_box[0].z
        assert not any(
            c.type is STUD and c.position.z == pytest.approx(seam)
            for c in model.connectors
        )

    def test_the_coupling_graph_is_unaffected(self, model):
        model.add(brick(4, 2), name="base")
        model.stack(brick(4, 2), "base", name="top")

        assert model.is_connected()
        assert model.is_valid()

    def test_removing_the_mate_exposes_the_connector_again(self, model):
        model.add(brick(4, 2), name="base")
        alone = len(model.connectors)
        model.stack(brick(4, 2), "base", name="top")
        assert len(model.connectors) < alone + len(model.named("top").connectors)

        model.remove("top")

        assert len(model.connectors) == alone

    def test_connectors_and_couplings_share_one_mating_scan(self, model, monkeypatch):
        """`connectors` and the coupling queries share one `_mating` scan."""
        calls = []

        def spy(*args, **kwargs):
            calls.append(1)
            return mated(*args, **kwargs)

        monkeypatch.setattr("bricklayer.modeling.build.mated", spy)

        model.add(brick(4, 2), name="base")
        model.stack(brick(4, 2), "base", name="top")

        _ = model.connectors
        _ = model.connected_components

        assert calls == [1]


class TestModelGeometry:
    def test_model_of_brick_alignment_box_footprint_equals_bounding_box_footprint(
        self, model
    ):
        """For standard bricks, the alignment box footprint is the same as the bounding box footprint."""
        model.add(brick(4, 2, 1, color=Color.RED), name="brick1")
        model.stack(brick(4, 2, 1, color=Color.RED), "brick1")
        assert (
            (model.alignment_width, model.alignment_depth)
            == (model.width, model.depth)
            == (4, 2)
        )

    def test_empty_model_has_zero_extents(self, model):
        assert (model.width, model.depth, model.height) == (0, 0, 0)

    def test_extents_measure_the_span_not_the_position(self, model):
        # A part placed away from the origin keeps its own size.
        model.add(brick(1, 1, color=Color.RED), Position(2, 3, 1))
        assert (model.width, model.depth, model.height) == pytest.approx(
            (1, 1, 1 + STUD_HEIGHT)
        )

    def test_empty_model_has_a_degenerate_box_at_the_origin(self, model):
        assert model.bounding_box == (Position(0, 0, 0), Position(0, 0, 0))
        assert model.alignment_box == (Position(0, 0, 0), Position(0, 0, 0))

    @pytest.mark.parametrize(
        "positions, lo, hi",
        [
            # One 2x2 brick at the origin: x/y span 0..2 studs, z the body plus
            # the stud protrusion layer.
            ([Position(0, 0, 0)], Position(0, 0, 0), Position(2, 2, 1 + STUD_HEIGHT)),
            # Two apart along x: the box spans both, gap included.
            (
                [Position(0, 0, 0), Position(5, 0, 0)],
                Position(0, 0, 0),
                Position(7, 2, 1 + STUD_HEIGHT),
            ),
            # Raised a brick: z is measured in bricks from the ground up.
            ([Position(0, 0, 1)], Position(0, 0, 1), Position(2, 2, 2 + STUD_HEIGHT)),
        ],
        ids=["single_part", "spans_every_part", "elevated_part"],
    )
    def test_box_spans_the_placed_bricks(self, model, positions, lo, hi):
        for position in positions:
            model.add(brick(2, 2, color=Color.RED), position)
        _assert_box(model.bounding_box, lo, hi)

    def test_alignment_box_spans_the_stud_seating_planes(self, model):
        # A 4x2x1 brick's alignment box is 4x2x1.
        model.add(brick(4, 2, 1, color=Color.RED))
        assert model.alignment_box == (Position(0, 0, 0), Position(4, 2, 1))

    def test_center_of_a_single_brick_is_its_midpoint(self, model):
        # The bounding box includes the stud layer, so z spans 0..(1 + STUD_HEIGHT).
        model.add(brick(3, 2, 1, color=Color.RED), Position(0, 0, 0))
        assert tuple(model.center) == pytest.approx((3 / 2, 1, (1 + STUD_HEIGHT) / 2))

    def test_named_part_center_matches_whole_model_when_single(self, model):
        model.add(brick(2, 2, color=Color.RED), Position(0, 0, 0), name="solo")
        assert model.named("solo").center == model.center

    def test_center_of_empty_model_is_zero(self, model):
        assert model.center == Position(0, 0, 0)

    def test_signed_delta_along_x(self, model):
        # "a" centers at x=1/2, "b" (placed at x=4) centers at x=9/2 -> dx=-4.
        model.add(brick(2, 2, color=Color.RED), Position(0, 0, 0), name="a")
        model.add(brick(2, 2, color=Color.BLUE), Position(4, 0, 0), name="b")
        assert model.named("a").center - model.named("b").center == Position(-4, 0, 0)


class TestLiveGeometry:
    """Derived geometry recomputes after every mutation -- through a nested
    model, a shared sub-model, and cached properties alike."""

    def test_derived_geometry_follows_an_add(self, model):
        assert model.brick_count == 0
        model.add(brick(2, 2, color=Color.RED))
        assert model.brick_count == 1
        model.add(brick(2, 2, color=Color.RED), Position(4, 0, 0))
        assert model.brick_count == 2
        assert model.width == 6

    def test_a_parents_geometry_follows_a_nested_model(self, model):
        child = LegoBuild()
        model.add(child)
        assert model.brick_count == 0
        child.add(brick(2, 2, color=Color.RED))
        assert model.brick_count == 1

    def test_a_grandparents_geometry_follows_the_innermost_model(self, model):
        parent, child = LegoBuild(), LegoBuild()
        parent.add(child)
        model.add(parent)
        before = model.bounding_box
        child.add(brick(2, 2, color=Color.RED))
        assert model.brick_count == 1
        assert model.bounding_box != before

    def test_a_shared_sub_model_updates_every_placement_of_it(self, model):
        child = LegoBuild()
        model.add(child)
        model.add(child, Position(8, 0, 0))
        child.add(brick(2, 2, color=Color.RED))
        assert model.brick_count == 2

    def test_a_derived_value_is_computed_once_per_change(self):
        class Counted(LegoBuild):
            """A model counting how often one derived value is computed."""

            computes = 0

            @cached_property
            def part_count(self) -> int:
                type(self).computes += 1
                return len(self.placements)

        model = Counted()
        model.add(brick(2, 2, color=Color.RED))
        assert model.part_count == 1
        assert model.part_count == 1
        assert Counted.computes == 1

        model.add(brick(2, 2, color=Color.BLUE), Position(4, 0, 0))
        assert model.part_count == 2
        assert Counted.computes == 2

    def test_a_subclass_cached_property_is_discovered(self):
        class Counted(LegoBuild):
            @cached_property
            def part_count(self) -> int:
                return len(self.placements)

        assert "part_count" in Counted._CACHED
        assert "flattened_placements" in Counted._CACHED

    def test_placements_reflects_additions_immediately(self, model):
        assert model.placements == ()
        p = model.add(brick(1, 1, color=Color.RED))
        assert model.placements == (p,)


class TestModelSummary:
    """`list_elements`/`brick_count` (read the flattened leaves) and `repr`:
    what the model reports about itself."""

    @pytest.fixture
    def nested(self):
        """An outer model holding one inner sub-model twice, plus a loose brick."""
        part = brick(2, 2, color=Color.YELLOW)
        cap = plate(2, 2, color=Color.YELLOW)
        inner = LegoBuild()
        inner.add(part, name="b")
        inner.stack(cap, "b")

        outer = LegoBuild()
        outer.add(inner)
        outer.add(inner, Position(5, 0, 0))
        outer.add(part, Position(10, 0, 0))  # one more of the same brick
        return outer, part, cap

    def test_an_empty_model_has_no_parts(self, model):
        assert model.list_elements() == {}
        assert model.brick_count == 0

    def test_a_single_part(self, model):
        part = brick(4, 2, color=Color.RED)
        model.add(part)
        assert model.list_elements() == {part: 1}
        assert model.brick_count == 1

    def test_identical_parts_share_one_entry(self, model):
        model.add(brick(4, 2, color=Color.RED), Position(0, 0, 0))
        model.add(brick(4, 2, color=Color.RED), Position(5, 0, 0))
        model.add(plate(4, 2, color=Color.BLUE), Position(0, 0, 1))
        # Separately-built elements naming the same part in the same colour are
        # one key: the count is what an order form needs -- how many of that
        # part to buy, whatever the build did to make them.
        assert model.list_elements() == {
            brick(4, 2, color=Color.RED): 2,
            plate(4, 2, color=Color.BLUE): 1,
        }
        assert model.brick_count == 3

    def test_different_parts_get_their_own_entries(self, model):
        b1 = brick(4, 2, color=Color.RED)
        b2 = brick(4, 2, color=Color.BLUE)  # same part, different colour
        p = plate(1, 1, color=Color.BLACK)
        for i, part in enumerate((b1, b2, p)):
            model.add(part, Position(5 * i, 0, 0))
        assert model.list_elements() == {b1: 1, b2: 1, p: 1}
        assert model.brick_count == 3

    def test_the_counts_add_up_to_the_brick_count(self, model):
        model.add(brick(4, 2, color=Color.RED), Position(0, 0, 0))
        model.add(brick(4, 2, color=Color.RED), Position(5, 0, 0))
        model.add(plate(1, 1, color=Color.BLACK), Position(10, 0, 0))
        assert sum(model.list_elements().values()) == model.brick_count

    def test_sub_models_are_counted_by_their_parts(self, nested):
        m, part, cap = nested
        assert m.list_elements() == {
            part: 3,  # 2 from the two inners, 1 top-level
            cap: 2,  # 2 from the two inners
        }
        assert m.brick_count == 5


class TestCollisions:
    def test_stacked_bricks_do_not_collide(self, model):
        model.add(brick(4, 2, color=Color.RED), Position(0, 0, 0))
        model.add(
            brick(4, 2, color=Color.BLUE), Position(0, 0, 1)
        )  # one brick up, resting on top
        assert model.colliding_placements == ()

    def test_partial_body_overlap_collides(self, model):
        model.add(
            brick(1, 1, color=Color.RED), Position(0, 0, 0)
        )  # body plates 0..2, stud at 3
        model.add(
            brick(1, 1, color=Color.BLUE), Position(0, 0, PLATE)
        )  # one plate up: bodies overlap at plates 1-2, unmated
        assert model.colliding_placements == (tuple(model.placements),)

    def test_colliding_placements_names_the_culprit_pair(self, model):
        model.add(brick(4, 2, color=Color.RED), Position(0, 0, 0))
        model.add(brick(4, 2, color=Color.BLUE), Position(0, 0, 0))
        a, b = model.placements
        assert model.colliding_placements == ((a, b),)
        assert not model.is_valid()  # a collision alone makes a model invalid

    def test_three_way_overlap_yields_every_pairing(self, model):
        model.add(brick(2, 2, color=Color.RED), Position(0, 0, 0))
        model.add(brick(2, 2, color=Color.BLUE), Position(0, 0, 0))
        model.add(brick(2, 2, color=Color.GREEN), Position(0, 0, 0))
        a, b, c = model.placements
        pairs = model.colliding_placements
        assert set(pairs) == {(a, b), (a, c), (b, c)}

    def test_spinning_a_valid_model_introduces_no_collisions(self):
        # Rigidly rotating a collision-free model off the build grid must stay collision-free.
        valid = fill_box(Position.ZERO, Position(3, 3, 3))
        assert valid.is_valid()
        spin = rotation_about(Vec3(0, 0, 1), 37)
        spun = LegoBuild([Placement(valid, Pose(spin))])
        assert spun.colliding_placements == ()
        assert spun.is_valid()

    def test_nested_sub_model_self_collision_is_detected(self):
        overlap = LegoBuild()
        overlap.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        overlap.add(brick(1, 1, color=Color.BLUE), Position(0, 0, 0))  # same cells
        outer = LegoBuild()
        outer.add(overlap, Position(0, 0, 0))
        # The nested bricks' bodies (and studs) overlap each other.
        assert outer.colliding_placements

    def test_stacked_bricks_do_not_collide_despite_stud_overlap(self, model):
        model.add(brick(2, 2, color=Color.RED), name="base")
        model.stack(brick(2, 2, color=Color.BLUE), "base")
        assert not model.colliding_placements
        assert model.is_valid()

    def test_tile_on_brick_does_not_collide_despite_stud_overlap(self, model):
        model.add(brick(2, 2, color=Color.RED))
        model.add(tile(2, 2, color=Color.BLUE), Position(0, 0, 1))
        assert not model.colliding_placements
        assert model.is_valid()

    def test_uncoupled_overlap_at_stud_layer_collides(self, model):
        model.add(brick(2, 2, color=Color.RED))
        model.add(brick(2, 2, color=Color.BLUE), Position(0, 0, PLATE))
        assert model.colliding_placements == (tuple(model.placements),)

    def test_two_stacked_plates_over_a_brick_collide(self, model):
        model.add(brick(2, 2, color=Color.RED), name="base")
        model.stack(plate(2, 2, color=Color.BLUE), "base")
        model.add(plate(2, 2, color=Color.GREEN), Position(0, 0, 1))
        assert model.colliding_placements

    def _spun(self, content, degrees, translation):
        """``content`` turned ``degrees`` about z, its origin at ``translation``."""
        rotation = rotation_about(Vec3(0, 0, 1), degrees)
        return Placement(content, Pose(rotation, translation))

    def test_spun_brick_collides_where_its_volume_reaches(self):
        # A 45-degree spin points the 2x2 brick's corner at the base: brought
        # near enough, the corner's mesh interpenetrates the base's.
        base = Placement(brick(2, 2, color=Color.RED))  # body (-1, -1)..(1, 1)
        poking = self._spun(brick(2, 2, color=Color.BLUE), 45, Position(2.0, 0, 0))
        m = LegoBuild([base, poking])
        assert m.colliding_placements == ((base, poking),)

    def test_spun_brick_clears_a_corner_its_aabb_overlaps(self):
        # The spun brick presents a flat face to the base's corner diagonally:
        # bounding boxes overlap, the actual volumes do not.
        base = Placement(brick(2, 2, color=Color.RED))  # body (-1, -1)..(1, 1)
        clear = self._spun(brick(2, 2, color=Color.BLUE), 45, Position(2.3, 2.3, 0))
        m = LegoBuild([base, clear])
        lo, _ = clear.bounding_box
        assert lo.x < 1 and lo.y < 1  # the AABBs do overlap
        assert m.colliding_placements == ()


class TestGrounding:
    """Parts reach the ground through connectors and directed surface contacts."""

    def test_grounded_brick_is_supported(self, model):
        model.add(brick(4, 2, color=Color.RED), Position(0, 0, 0))
        assert model.floating_placements == ()
        assert model.is_valid()

    def test_floating_brick_detected(self, model):
        model.add(brick(1, 1, color=Color.BLUE), Position(20, 0, 0))
        model.add(brick(4, 2, color=Color.RED), Position(0, 0, 3))
        assert model.placements[1] in model.floating_placements
        assert not model.is_valid()

    def test_supported_through_a_stack(self, model):
        model.add(brick(4, 2, color=Color.RED), Position(0, 0, 0), name="base")
        model.add(brick(4, 2, color=Color.BLUE), Position(0, 0, 1), relative_to="base")
        model.add(brick(4, 2, color=Color.GREEN), Position(0, 0, 2), relative_to="base")
        assert model.floating_placements == ()
        assert model.is_valid()

    def test_disconnected_brick_floats(self, model):
        model.add(brick(4, 2, color=Color.RED), Position(0, 0, 0))  # grounded
        model.add(brick(4, 2, color=Color.BLUE), Position(20, 20, 3))  # disconnected
        assert model.placements[1] in model.floating_placements
        assert not model.is_valid()

    def test_part_hovering_one_plate_up_floats(self, model):
        # Nearly grounded is still floating: nothing couples to its underside.
        model.add(plate(1, 1, color=Color.BLUE), Position(10, 0, 0))
        model.add(plate(1, 1, color=Color.WHITE), Position(0, 0, PLATE))
        assert model.floating_placements == (model.placements[1],)
        assert not model.is_valid()

    def test_support_reached_through_multiple_paths(self, model):
        # Two grounded 1x1s jointly support a bridging 1x2, which supports a
        # 1x1 on top -- the search must keep going past already-visited parts.
        model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        model.add(brick(1, 1, color=Color.RED), Position(1, 0, 0))
        model.add(brick(2, 1, color=Color.BLUE), Position(0, 0, 1))  # rests on both
        model.add(brick(1, 1, color=Color.GREEN), Position(0, 0, 2))
        assert model.floating_placements == ()
        assert model.is_valid()

    def test_geometry_less_part_without_connectors_floats(self, element_with):
        # A part with no connectors and a degenerate bounding box cannot be
        # grounded or supported.
        ghost = element_with(frozenset(), (Position.ZERO, Position.ZERO))
        m = LegoBuild([Placement(brick(1, 1, color=Color.RED)), Placement(ghost)])
        assert m.floating_placements == (m.placements[1],)
        assert not m.is_connected()

    def test_floating_part_inside_a_sub_model_is_detected(self):
        sub = LegoBuild()
        sub.add(brick(2, 1, color=Color.RED), Position(0, 0, 0))  # grounded
        sub.add(brick(1, 1, color=Color.BLUE), Position(10, 0, 3))  # hovering, alone
        outer = LegoBuild()
        outer.add(sub, Position(0, 0, 0))
        floating = outer.floating_placements
        assert len(floating) == 1
        placement = floating[0]
        assert placement.content.color == Color.BLUE

    @pytest.fixture
    def block(self, element_with):
        """A placement spanning ``(lo, hi)`` with no connectors."""

        def _fn(lo: Position, hi: Position) -> Placement:
            return Placement(element_with(frozenset(), (lo, hi)))

        return _fn

    def test_touching_bounding_boxes_alone_do_not_support(self, block):
        ground = block(Position(0, 0, 0), Position(1, 1, 1))  # crosses z = 0
        resting = block(Position(0, 0, 1), Position(1, 1, 2))  # bottom meets top
        m = LegoBuild([ground, resting])
        assert m.floating_placements == (resting,)

    def test_overlapping_boxes_without_connections_do_not_ground(self, block):
        ground = block(Position(0, 0, 0), Position(2, 2, 2))
        overlapping = block(Position(1, 1, 1), Position(3, 3, 3))
        assert LegoBuild([ground, overlapping]).floating_placements == (overlapping,)

    def test_brick_resting_on_tile_is_supported(self, model):
        model.add(Element("3068b", Color.WHITE), name="tile")
        model.stack(brick(2, 2, color=Color.BLUE), "tile")
        assert model.floating_placements == ()
        assert not model.is_connected()

    def test_ground_support_can_mix_contacts_and_connectors(self, model):
        model.add(Element("3068b", Color.WHITE), name="tile")
        model.stack(brick(2, 2, color=Color.BLUE), "tile", name="middle")
        model.stack(brick(2, 2, color=Color.RED), "middle")
        reversed_model = LegoBuild(reversed(model.placements))
        assert reversed_model.floating_placements == ()

    def test_touching_grounded_roof_from_below_does_not_support(self, model):
        model.add(brick(2, 2, color=Color.RED), name="base")
        model.stack(brick(2, 2, color=Color.RED), "base", name="column")
        model.stack(plate(4, 2, color=Color.WHITE), "column")
        loose = model.add(Element("3068b", Color.BLUE), Position(2, 0, 5 * PLATE))
        assert model.colliding_placements == ()
        assert model.floating_placements == (loose,)

    def test_side_contact_with_grounded_brick_does_not_support(self, model):
        model.add(brick(2, 2, color=Color.RED))
        loose = model.add(plate(2, 2, color=Color.BLUE), Position(2, 0, PLATE))
        assert model.colliding_placements == ()
        assert model.floating_placements == (loose,)

    def test_tile_support_is_invalidated_after_removal(self, model):
        model.add(brick(1, 1, color=Color.RED), Position(10, 0, 0))
        base = model.add(Element("3068b", Color.WHITE), name="tile")
        top = model.stack(brick(2, 2, color=Color.BLUE), "tile")
        assert model.floating_placements == ()
        model.remove(base)
        assert model.floating_placements == (top,)

    def test_part_resting_on_a_floating_part_still_floats(self, block):
        base = block(Position(10, 0, 0), Position(11, 1, 1))
        hovering = block(Position(0, 0, 1), Position(1, 1, 2))  # nothing below it
        resting = block(Position(0, 0, 2), Position(1, 1, 3))
        m = LegoBuild([base, hovering, resting])
        assert set(m.floating_placements) == {hovering, resting}

    def test_support_requires_overlapping_footprints(self, block):
        ground = block(Position(0, 0, 0), Position(1, 1, 1))
        # Bottom is level with the ground's top, but offset in x with no overlap.
        aside = block(Position(5, 0, 1), Position(6, 1, 2))
        m = LegoBuild([ground, aside])
        assert m.floating_placements == (aside,)

    def test_a_gap_between_faces_is_not_support(self, block):
        ground = block(Position(0, 0, 0), Position(1, 1, 1))
        hovering = block(Position(0, 0, 1 + PLATE), Position(1, 1, 2))  # gap below
        m = LegoBuild([ground, hovering])
        assert m.floating_placements == (hovering,)


@pytest.mark.usefixtures("patch_connector_rules_registry")
class TestConnectivity:
    """is_connected(), connected_components(), and the coupling graph they
    both read: an edge is a stud of one part joined to an antistud of
    another, including across a sliding (prismatic) pair."""

    def test_single_part_is_connected(self, model):
        model.add(brick(2, 2, color=Color.RED))
        assert model.is_connected()

    def test_stacked_parts_are_connected(self, model):
        model.add(brick(4, 2, color=Color.RED), name="base")
        model.stack(brick(4, 2, color=Color.BLUE), "base")
        assert model.is_connected()

    def test_side_by_side_parts_are_not_connected(self, model):
        # Touching faces don't join parts; only stud/antistud couplings do.
        model.add(brick(2, 2, color=Color.RED), Position(0, 0, 0))
        model.add(brick(2, 2, color=Color.BLUE), Position(2, 0, 0))
        assert not model.is_connected()

    def test_two_separate_stacks_are_not_connected(self, model):
        model.add(brick(2, 2, color=Color.RED), Position(0, 0, 0), name="a")
        model.stack(brick(2, 2, color=Color.RED), "a")
        model.add(brick(2, 2, color=Color.BLUE), Position(10, 10, 0), name="b")
        model.stack(brick(2, 2, color=Color.BLUE), "b")
        assert not model.is_connected()
        assert model.num_connected_components == 2

    def test_bridge_joins_two_pillars(self, model):
        model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        model.add(brick(1, 1, color=Color.RED), Position(1, 0, 0))
        model.add(brick(2, 1, color=Color.BLUE), Position(0, 0, 1))  # spans both
        assert model.is_connected()

    def test_connected_stack_is_supported_at_any_height(self, model):
        model.add(brick(2, 2, color=Color.RED), Position(0, 0, 2), name="hover")
        model.stack(brick(2, 2, color=Color.BLUE), "hover")
        assert model.is_connected()
        assert not model.floating_placements

    def test_internally_disconnected_sub_model_is_disconnected(self):
        sub = LegoBuild()
        sub.add(brick(2, 1, color=Color.RED), Position(0, 0, 0))
        sub.add(brick(2, 1, color=Color.BLUE), Position(10, 0, 0))
        outer = LegoBuild()
        outer.add(sub, Position(0, 0, 0))
        assert not outer.is_connected()
        assert outer.num_connected_components == 2

    def test_external_bridge_connects_a_split_sub_model(self):
        # A sub-model's two bricks are disconnected from each other, but both rest
        # on a plate placed outside the sub-model. Connectivity must cross the
        # sub-model boundary, so the whole assembly is one component.
        split = LegoBuild()
        split.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        split.add(brick(1, 1, color=Color.BLUE), Position(3, 0, 0))
        outer = LegoBuild()
        outer.add(plate(4, 1, color=Color.WHITE), Position(0, 0, 0))
        outer.add(split, Position(0, 0, PLATE))  # both bricks rest on the plate
        assert outer.is_connected()
        assert outer.num_connected_components == 1

    # components(): the parts grouped by connected component.
    def test_empty_model_has_no_components(self, model):
        assert model.connected_components == ()

    def test_single_part_is_one_component(self, model):
        model.add(brick(2, 2, color=Color.RED))
        assert model.connected_components == ((model.placements[0],),)

    def test_connected_parts_share_a_component(self, model):
        model.add(brick(4, 2, color=Color.RED), name="base")
        model.stack(brick(4, 2, color=Color.BLUE), "base")
        base, top = model.placements
        assert model.connected_components == ((base, top),)

    def test_separate_stacks_are_separate_components(self, model):
        model.add(brick(2, 2, color=Color.RED), Position(0, 0, 0), name="a")
        model.stack(brick(2, 2, color=Color.RED), "a")
        model.add(brick(2, 2, color=Color.BLUE), Position(10, 10, 0), name="b")
        model.stack(brick(2, 2, color=Color.BLUE), "b")
        a, a_top, b, b_top = model.placements
        components = model.connected_components
        assert components == ((a, a_top), (b, b_top))

    def test_components_partition_every_part(self, model):
        model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        model.add(brick(1, 1, color=Color.BLUE), Position(10, 0, 0))
        model.add(brick(1, 1, color=Color.GREEN), Position(20, 0, 0))
        flattened = [p for component in model.connected_components for p in component]
        assert sorted(flattened, key=id) == sorted(model.placements, key=id)
        assert len(model.connected_components) == model.num_connected_components

    # The coupling graph is built with a spatial hash for speed; these tests
    # guard that it still matches the brute-force definition.
    def test_matches_brute_force_on_a_mixed_build(self, model):
        # A mix of every coupling shape: two pillars jointly bridged, a rotated
        # course on top, a stacked pad, and a disconnected floater.
        model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        model.add(brick(1, 1, color=Color.RED), Position(1, 0, 0))
        model.add(brick(2, 1, color=Color.BLUE), Position(0, 0, 1))  # bridges both
        model.add(brick(2, 1, color=Color.GREEN), Position(0, 0, 2), Rotation.DEG_90)
        model.add(plate(2, 2, color=Color.WHITE), Position(5, 5, 0), name="pad")
        model.stack(brick(2, 2, color=Color.YELLOW), "pad")
        model.add(brick(1, 1, color=Color.BLACK), Position(20, 20, 4))  # floater
        pairs = model._mating.pairs
        assert {frozenset(e) for e in pairs} == _brute_force_edges(model.placements)

    def test_isolated_parts_are_nodes_without_edges(self, model):
        model.add(brick(2, 2, color=Color.RED), Position(0, 0, 0))
        model.add(brick(2, 2, color=Color.BLUE), Position(10, 0, 0))  # far apart
        assert model._mating.pairs == ()
        assert model.num_connected_components == 2

    def test_a_part_does_not_couple_to_itself(self, model):
        # A single brick has both studs (top) and antistuds (bottom); the hash
        # must not pair it with itself.
        model.add(brick(2, 2, color=Color.RED))
        assert model._mating.pairs == ()

    def test_stacked_bricks_couple(self, model):
        model.add(brick(2, 2, color=Color.RED), name="base")
        model.stack(brick(2, 2, color=Color.BLUE), "base")
        assert coupled(model.placements[0], model.placements[1])
        assert model.is_connected()

    def test_incompatible_types_at_same_point_do_not_couple(self, model, element_with):
        unknown_conn = ConnectorType("unknown")
        base = element_with(
            {Connector(unknown_conn, Position(0.5, 0.5, 1), Direction.UP)}
        )
        model.add(base, name="base")
        model.stack(brick(1, 1, color=Color.BLUE), "base")
        assert not coupled(model.placements[0], model.placements[1])
        assert model.floating_placements == (model.placements[1],)
        assert not model.is_connected()

    # Prismatic pairs couple across a slide, so coincidence buckets alone
    # cannot find them; these tests guard the extra sweep along the axis.
    @pytest.fixture
    def rail_and_shoe(self, element_with):
        rail_t, shoe_t = ConnectorType("rail"), ConnectorType("shoe")
        mark_compatible(rail_t, shoe_t, joint=JointKind.PRISMATIC)
        rail = element_with(
            {
                Connector(
                    rail_t,
                    Position(0, 0.5, 0.5),
                    Direction.LEFT,
                    Direction.UP,
                    length=4,
                )
            }
        )
        shoe = element_with(
            {Connector(shoe_t, Position(0, 0.5, 0.5), Direction.LEFT, Direction.UP)}
        )
        return rail, shoe

    def test_offset_prismatic_pair_couples(self, model, rail_and_shoe):
        rail, shoe = rail_and_shoe
        model.add(rail, Position(0, 0, 0))
        model.add(shoe, Position(3, 0, 0))
        assert coupled(model.placements[0], model.placements[1])
        assert model.is_connected()

    def test_slide_beyond_the_length_does_not_couple(self, model, rail_and_shoe):
        rail, shoe = rail_and_shoe
        model.add(rail, Position(0, 0, 0))
        model.add(shoe, Position(5, 0, 0))
        assert not coupled(model.placements[0], model.placements[1])
        assert not model.is_connected()

    def test_graph_matches_brute_force_with_sliding_pairs(self, model, rail_and_shoe):
        rail, shoe = rail_and_shoe
        model.add(rail, Position(0, 0, 0))
        model.add(shoe, Position(3, 0, 0))
        model.add(brick(1, 1, color=Color.RED), Position(0, 3, 0), name="base")
        model.stack(brick(1, 1, color=Color.BLUE), "base")
        edges = {frozenset(e) for e in model._mating.pairs}
        assert edges == _brute_force_edges(model.placements)

    def test_off_grid_rotated_brick_couples_and_stays_valid(self):
        # A 2x1 brick spun by a non-quarter-turn angle is seated so one of its
        # antistuds (half a stud off the spin axis, so the spin leaves float
        # noise in its world position) lands on the base brick's stud. That mate
        # is off the build grid, yet coincidence detection tolerates the noise:
        # the bricks still couple, so the model is valid and connected.
        base = Placement(brick(1, 1, color=Color.RED))  # stud at (0, 0, 1)
        spin = rotation_about(Vec3(0, 0, 1), 37)
        seat = Position(0, 0, 1)  # the base's stud, in world coordinates
        anti = Pose(spin).apply(Position(-0.5, 0, 0))  # a spun antistud
        top = Placement(brick(2, 1, color=Color.BLUE), Pose(spin, seat - anti))
        m = LegoBuild([base, top])
        assert not top.pose.is_grid_preserving  # genuinely off the grid
        assert m.colliding_placements == ()
        assert m.is_valid()
        assert m.is_connected()


class TestPerformance:
    """Validation of a ~1000-brick model stays interactive.

    Both cases run in well under a second today, and the ceiling sits a few
    times above that, so a slowdown of a few times over trips it.
    """

    # A spun model is the expensive case for two measured reasons: its fatter
    # world AABBs yield ~3.5x more broad-phase candidate pairs, and float noise
    # in the composed rotations defeats the narrow phase's relative-pose cache,
    # so many more distinct pairs reach exact triangle intersection.
    @staticmethod
    def _flat():
        return fill_box(Position.ZERO, Position(30, 30, 30))

    @staticmethod
    def _spun():
        spin = rotation_about(Vec3(0, 0, 1), 37)
        model = LegoBuild(
            [Placement(fill_box(Position.ZERO, Position(24, 24, 24)), Pose(spin))]
        )
        assert not model.flattened_placements[0].pose.is_grid_preserving
        return model

    @pytest.mark.integration
    @pytest.mark.parametrize("make_model", [_flat, _spun], ids=["flat", "spun"])
    def test_validating_a_large_model_is_fast(self, make_model):
        model = make_model()
        assert model.brick_count >= 1000
        start = time.perf_counter()
        assert model.is_valid()
        assert model.is_connected()
        assert model.num_connected_components == 1
        assert time.perf_counter() - start < 3.0
