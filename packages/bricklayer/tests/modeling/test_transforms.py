"""Tests for the model-to-model transforms: flatten, translate, mirror."""

from functools import cache

import pytest

from bricklayer import (
    PLATE,
    Axis,
    Color,
    Element,
    JointKind,
    LegoBuild,
    MotionRange,
    Mounting,
    Placement,
    Pose,
    Position,
    Revolute,
    Rotation,
    Vec3,
    brick,
    flatten,
    mirror,
    plate,
    to_ldraw,
    translate,
    translate_to_ground,
    window,
)
from bricklayer.geometry.linalg import all_close, rotation_about
from bricklayer.ldraw.naming import Chirality
from bricklayer.parts.catalog import all_parts


def in_place(geometry, axis):
    """The plane that reflects ``geometry`` where it stands: the center of its
    alignment box on ``axis``."""
    lo, hi = geometry.alignment_box
    return (lo[axis.value] + hi[axis.value]) / 2


def mirrored_in_place(geometry, axis=Axis.X):
    """``geometry`` mirrored about the plane that leaves it where it stands."""
    return mirror(geometry, axis, in_place(geometry, axis))


@cache
def a_handed_part_without_a_counterpart():
    """A handed part the catalog holds only one hand of."""
    return next(
        spec
        for spec in all_parts()
        if spec.chirality is not None and spec.mirrored is spec
    )


@cache
def an_off_centre_handed_part():
    """A handed part whose alignment box does not straddle the left/right
    plane, so swapping in its counterpart moves the geometry itself."""

    def off_centre(spec):
        lo, hi = Element(spec.ldraw_id, Color.RED).alignment_box
        return lo.x + hi.x != 0

    return next(
        spec
        for spec in all_parts()
        if spec.chirality is not None and spec.mirrored is not spec and off_centre(spec)
    )


class TestFlatten:
    @pytest.fixture
    def model(self):
        inner = LegoBuild()
        inner.add(brick(2, 2, color=Color.RED), Position(0, 0, 0), name="brick")
        inner.stack(plate(2, 2, color=Color.BLUE), "brick")
        outer = LegoBuild()
        outer.add(inner)
        outer.add(inner, Position(5, 0, 0), Rotation.DEG_90)
        outer.add(brick(1, 1, color=Color.BLUE), Position(10, 0, 0), name="top")
        return outer

    def test_flatten_function_returns_a_flattened_model(self, model):
        flattened = flatten(model)
        assert flattened.placements == model.flattened_placements
        assert all(isinstance(p.content, Element) for p in flattened.placements)

    def test_flattened_model_occupies_same_volumes_as_original(
        self, model, filled_region
    ):
        flattened = flatten(model)
        assert filled_region(flattened) == filled_region(model)

    def test_flatten_preserves_top_level_names(self, model):
        flattened = flatten(model)
        top = flattened.named("top").content
        assert isinstance(top, Element)
        other = brick(1, 1, color=Color.BLUE)
        assert (top.spec.ldraw_id, top.color) == (other.spec.ldraw_id, other.color)
        assert flattened.name_of(flattened.named("top")) == "top"

    def test_flatten_composes_poses_through_sub_models(
        self, connector_specs, filled_region
    ):
        tilt = Pose(rotation_about(Vec3(1, 0, 0), 90))
        sub = LegoBuild([Placement(brick(1, 1, color=Color.RED), tilt)])
        host = LegoBuild([Placement.at(sub, Position(3, 3, 0), Rotation.DEG_90)])
        assert filled_region(flatten(host)) == filled_region(host)
        assert connector_specs(flatten(host)) == connector_specs(host)

    def test_flatten_preserves_the_subclass(self):
        class Subclass(LegoBuild):
            pass

        model = Subclass()
        model.add(brick(2, 2, color=Color.RED))
        assert type(flatten(model)) is Subclass

    def test_flatten_drops_step_markers(self):
        # Flattening changes the placement count, so markers -- indices into
        # that list -- no longer index anything meaningful. Uses a fresh
        # model rather than the class fixture, whose placement count would
        # make a fixed marker index misleading.
        fresh = LegoBuild()
        fresh.add(brick(2, 2, color=Color.RED))
        fresh.add_step()
        fresh.add(brick(1, 1, color=Color.BLUE))
        assert fresh.step_markers == (1,)
        assert flatten(fresh).step_markers == ()


class TestTranslateToGround:
    """`translate_to_ground` drops a model so its lowest volume sits at z = 0."""

    @pytest.mark.parametrize("start_z", [1, 2, 5])
    def test_a_floating_model_is_dropped_to_zero(self, model, start_z):
        model.add(brick(2, 1, color=Color.RED), Position(0, 0, start_z))
        grounded = translate_to_ground(model)
        assert grounded.bounding_box[0].z == pytest.approx(0)

    def test_an_already_grounded_model_does_not_move(self, model):
        model.add(brick(2, 1, color=Color.RED), Position(0, 0, 0))
        result = translate_to_ground(model)
        assert result is not model
        assert result.bounding_box == model.bounding_box

    def test_x_and_y_are_left_alone(self, model):
        model.add(brick(2, 1, color=Color.RED), Position(4, 3, 2))
        lo, _ = translate_to_ground(model).bounding_box
        assert (lo.x, lo.y) == (4, 3)

    def test_grounding_changes_coordinates_without_changing_validity(self, model):
        model.add(brick(2, 1, color=Color.RED), Position(0, 0, 3))
        assert model.is_valid()
        grounded = translate_to_ground(model)
        assert grounded.is_valid()
        assert model.bounding_box[0].z == 3
        assert grounded.bounding_box[0].z == 0

    def test_relative_layout_is_preserved(self, model):
        model.add(brick(2, 1, color=Color.RED), Position(0, 0, 2), name="base")
        model.stack(plate(1, 1, color=Color.BLUE), "base", name="cap")
        grounded = translate_to_ground(model)
        assert tuple(
            grounded.named("cap").center - grounded.named("base").center
        ) == pytest.approx(
            tuple(model.named("cap").center - model.named("base").center)
        )

    def test_rotation_is_preserved(self, model):
        model.add(
            brick(2, 1, color=Color.RED), Position(0, 0, 3), Rotation.DEG_90, name="bar"
        )
        grounded = translate_to_ground(model)
        assert grounded.named("bar").pose.rotation == Rotation.DEG_90.matrix
        assert grounded.named("bar").alignment_box[0] == Position(0, 0, 0)

    def test_an_empty_model_returns_an_empty_copy(self):
        empty = LegoBuild()
        result = translate_to_ground(empty)
        assert result is not empty
        assert result.placements == empty.placements == ()

    def test_lifts_every_part_when_the_model_reaches_underground(self, model):
        # A part below the base lifts the whole model up.
        model.add(brick(2, 2, color=Color.RED), Position(0, 0, 0), name="first")
        model.add(brick(2, 2, color=Color.BLUE), Position(0, 0, -1))
        grounded = translate_to_ground(model)
        assert [p.alignment_box[0] for p in grounded.placements] == [
            Position(0, 0, 1),
            Position(0, 0, 0),
        ]
        assert grounded.is_valid()  # still stacked, now resting on the ground

    def test_lowers_a_hovering_stack(self, model):
        model.add(brick(2, 2, color=Color.RED), Position(3, 4, 2), name="base")
        model.stack(brick(2, 2, color=Color.BLUE), "base")
        grounded = translate_to_ground(model)
        # x/y untouched, bottom lowered onto z = 0.
        assert tuple(grounded.named("base").alignment_box[0]) == pytest.approx(
            (3, 4, 0)
        )
        assert grounded.floating_placements == ()

    def test_translates_by_sub_brick_amounts(self, model):
        model.add(plate(1, 1, color=Color.WHITE), Position(0, 0, PLATE))
        (placement,) = translate_to_ground(model).placements
        assert tuple(placement.alignment_box[0]) == pytest.approx((0, 0, 0))

    def test_named_references_keep_working(self, model):
        model.add(brick(2, 2, color=Color.RED), Position(0, 0, -2), name="basement")
        model.stack(brick(2, 2, color=Color.BLUE), "basement", name="top")
        grounded = translate_to_ground(model)
        assert grounded.named("basement").alignment_box[0] == Position(0, 0, 0)
        assert grounded.named("top").alignment_box[0] == Position(0, 0, 1)

    def test_grounding_does_not_imply_support(self, model):
        # Only the lowest part is guaranteed to touch the ground; a separate
        # higher component still floats.
        model.add(brick(2, 2, color=Color.RED), Position(0, 0, 1))
        model.add(brick(2, 2, color=Color.BLUE), Position(10, 10, 5), name="floater")
        grounded = translate_to_ground(model)
        assert grounded.floating_placements == (grounded.named("floater"),)
        assert grounded.named("floater").alignment_box[0] == Position(10, 10, 4)

    def test_rotated_submodel_grounds_leaf_bounds_and_preserves_hierarchy(self):
        child = LegoBuild()
        child.add(brick(1, 1), Position(0, 0, 0), name="lower")
        child.add(brick(1, 1), Position(3, 0, 3), name="upper")
        parent = LegoBuild()
        parent.add_raw(child, Pose(rotation_about(Vec3(0, 1, 0), 45)), name="tilted")
        parent.add_step()
        grounded = translate_to_ground(parent)
        assert min(
            p.bounding_box[0].z for p in grounded.flattened_placements
        ) == pytest.approx(0)
        assert grounded.named("tilted").content is child
        assert grounded.step_markers == (1,)


class TestTranslate:
    """`translate` shifts every placement by a delta and returns a new model."""

    @pytest.fixture
    def model(self, model):
        model.add(brick(2, 1, color=Color.RED), Position(1, 2, 0), name="base")
        model.stack(plate(1, 1, color=Color.BLUE), "base", name="cap")
        return model

    @pytest.mark.parametrize(
        "delta",
        [
            Position(3, 0, 0),
            Position(0, -2, 0),
            Position(0, 0, 2),
            Position(1, 1, PLATE),
        ],
    )
    def test_every_part_shifts_by_the_delta(self, model, delta):
        moved = translate(model, delta)
        for before, after in zip(model.placements, moved.placements, strict=True):
            assert after.pose.translation == before.pose.translation + delta

    def test_the_bounding_box_shifts_with_the_model(self, model):
        delta = Position(3, -1, 1)
        lo, hi = model.bounding_box
        moved = translate(model, delta).bounding_box
        assert moved == (lo + delta, hi + delta)

    def test_names_follow_the_translated_parts(self, model):
        moved = translate(model, Position(2, 0, 0))
        assert set(moved.names) == {"base", "cap"}
        assert moved.named("cap") in moved.placements
        assert moved.named("cap") not in model.placements

    def test_rotation_is_preserved(self, model):
        # The class fixture pre-populates "base"/"cap", so the rotated part
        # added here is not placements[0] -- assert against the literal
        # rotation, not a self-comparison that would pass even if translate
        # discarded rotation entirely.
        model.add(brick(2, 1, color=Color.RED), Position(0, 0, 0), Rotation.DEG_90)
        moved = translate(model, Position(1, 0, 0))
        assert moved.placements[-1].pose.rotation == Rotation.DEG_90.matrix

    def test_an_off_grid_delta_is_applied_verbatim(self, model):
        model.add(brick(2, 1, color=Color.RED))
        moved = translate(model, Position(0.25, 0, 0))
        assert moved.placements[-1].pose.translation.x - model.placements[
            -1
        ].pose.translation.x == pytest.approx(0.25)

    def test_translating_an_empty_model_is_empty(self):
        assert translate(LegoBuild(), Position(1, 1, 1)).placements == ()

    def test_translate_preserves_the_subclass(self):
        # translate is routed through `_rebuild`, which every non-flatten
        # transform shares -- this is the one place that path is checked.
        class Subclass(LegoBuild):
            pass

        model = Subclass()
        model.add(brick(2, 2, color=Color.RED))
        assert type(translate(model, Position(1, 0, 0))) is Subclass

    def test_a_non_zero_delta_preserves_step_markers(self):
        # A fresh model, not the class fixture: that one pre-populates
        # placements, which would make a fixed marker index misleading.
        fresh = LegoBuild()
        fresh.add(brick(2, 1, color=Color.RED))
        fresh.add_step()
        fresh.add(brick(2, 1, color=Color.BLUE))
        moved = translate(fresh, Position(1, 0, 0))
        assert moved.step_markers == fresh.step_markers == (1,)

    def test_translate_accepts_tuple_delta(self):
        part = brick(2, 1)
        model = LegoBuild()
        model.add(part)
        assert to_ldraw(translate(model, (1, 2, 1 / 3))) == to_ldraw(
            translate(model, Position(1, 2, 1 / 3))
        )


class TestMirror:
    @staticmethod
    def _two_brick_row(model):
        # A 2-wide brick at the right and a 1x1 plate at the left: an
        # asymmetric layout along X, so mirroring is observable.
        model.add(brick(2, 1, color=Color.RED), Position(0, 0, 0))
        model.add(plate(1, 1, color=Color.BLUE), Position(3, 0, 0))
        return model

    def test_mirror_x_flips_the_layout(self, model, filled_region):
        m = self._two_brick_row(model)
        mirrored = mirrored_in_place(m, Axis.X)
        # The 2-wide brick (was x 0-1) reflects to x 2-3; the plate (x 3)
        # reflects to x 0. The footprint (x 0-3) is unchanged.
        assert filled_region(mirrored) == {(0, 0, 0)} | {
            (x, 0, z) for x in (2, 3) for z in range(3)
        }

    def test_mirror_y_flips_the_depth(self, model, filled_region):
        # A 2x1 brick turned to run 2 deep along Y, plus a plate further back.
        model.add(brick(2, 1, color=Color.RED), Position(0, 0, 0), Rotation.DEG_90)
        model.add(plate(1, 1, color=Color.BLUE), Position(0, 3, 0))
        mirrored = mirrored_in_place(model, Axis.Y)
        assert filled_region(mirrored) == {(0, 0, 0)} | {
            (0, y, z) for y in (2, 3) for z in range(3)
        }

    def test_mirroring_twice_restores_the_original(self, model, filled_region):
        m = self._two_brick_row(model)
        assert filled_region(
            mirrored_in_place(mirrored_in_place(m, Axis.X), Axis.X)
        ) == filled_region(m)

    def test_mirror_inverts_rotation(self, model):
        model.add(brick(2, 1, color=Color.RED), Position(0, 0, 0), Rotation.DEG_90)
        mirrored = mirrored_in_place(model, Axis.X)
        assert mirrored.placements[0].pose.rotation == Rotation.DEG_270.matrix

    def test_mirror_leaves_symmetric_rotations_unchanged(self, model):
        model.add(brick(2, 1, color=Color.RED), Position(0, 0, 0), Rotation.DEG_180)
        mirrored = mirrored_in_place(model, Axis.X)
        assert mirrored.placements[0].pose.rotation == Rotation.DEG_180.matrix

    def test_mirror_preserves_names_pointing_at_the_mirrored_parts(self, model):
        model.add(brick(2, 1, color=Color.RED), Position(0, 0, 0), name="wide")
        model.add(plate(1, 1, color=Color.BLUE), Position(3, 0, 0), name="dot")
        mirrored = mirrored_in_place(model, Axis.X)
        assert mirrored.named("wide").alignment_box[0] == Position(2, 0, 0)
        assert mirrored.named("dot").alignment_box[0] == Position(0, 0, 0)
        assert mirrored.name_of(mirrored.placements[0]) == "wide"

    def test_mirror_preserves_footprint(self, model):
        m = self._two_brick_row(model)
        mirrored = mirrored_in_place(m, Axis.X)
        assert (mirrored.width, mirrored.depth) == (m.width, m.depth)
        assert mirrored.bounding_box == m.bounding_box

    def test_mirror_preserves_validity(self, model):
        model.add(brick(2, 2, color=Color.RED), name="base")
        model.stack(brick(2, 2, color=Color.BLUE), "base")
        assert model.is_valid()
        assert mirrored_in_place(model, Axis.X).is_valid()

    def test_mirror_of_empty_model_is_empty(self, model):
        mirrored = mirrored_in_place(model, Axis.X)
        assert mirrored.placements == ()
        assert mirrored.is_valid()

    def test_mirror_preserves_empty_build_steps(self):
        model = LegoBuild(steps=(0, 0))
        mirrored = mirror(model, Axis.X, 0)
        assert mirrored is not model
        assert mirrored.step_markers == (0, 0)
        assert to_ldraw(mirrored) == "0 STEP\n0 STEP\n"

    @staticmethod
    def _asymmetric_sub():
        # A 2-wide brick and a plate set apart along X: asymmetric, so its own
        # mirror image differs from itself.
        sub = LegoBuild()
        sub.add(brick(2, 1, color=Color.RED), Position(0, 0, 0), name="body")
        sub.add(plate(1, 1, color=Color.BLUE), Position(3, 0, 0), name="tip")
        return sub

    def test_mirror_recurses_into_sub_models(self, model, filled_region):
        sub = self._asymmetric_sub()
        model.add(sub, Position(0, 0, 0))
        mirrored = mirrored_in_place(model, Axis.X)
        # The sub-model's placement flips and its internal layout mirrors too.
        assert filled_region(mirrored) == filled_region(mirrored_in_place(sub, Axis.X))
        assert filled_region(mirrored) != filled_region(sub)

    def test_mirror_round_trips_with_a_rotated_sub_model(self, model, filled_region):
        model.add(self._asymmetric_sub(), Position(0, 0, 0), Rotation.DEG_90)
        assert filled_region(
            mirror(
                mirrored_in_place(model, Axis.X),
                Axis.X,
                in_place(model, Axis.X),
            )
        ) == filled_region(model)

    def test_mirror_preserves_sub_model_names(self, model):
        model.add(self._asymmetric_sub(), Position(0, 0, 0), name="sub")

        mirrored = mirrored_in_place(model, Axis.X)

        assert isinstance(mirrored.named("sub").content, LegoBuild)
        # Read through the parent: a sub-model reflects about its own
        # origin, so its placement takes up the difference.
        assert mirrored.named(["sub", "body"]).alignment_box[0] == Position(2, 0, 0)
        assert mirrored.named(["sub", "tip"]).alignment_box[0] == Position(0, 0, 0)

    def test_mirror_preserves_validity_with_sub_models(self, model):
        sub = LegoBuild()
        sub.add(brick(2, 2, color=Color.RED), name="base")
        sub.stack(brick(2, 2, color=Color.BLUE), "base")
        model.add(sub, Position(0, 0, 0))
        assert model.is_valid()
        assert mirrored_in_place(model, Axis.X).is_valid()

    def test_mirror_preserves_step_markers(self, model):
        model.add(brick(2, 1, color=Color.RED))
        model.add_step()
        model.add(plate(1, 1, color=Color.BLUE))
        mirrored = mirrored_in_place(model, Axis.X)
        assert mirrored.step_markers == model.step_markers == (1,)

    def test_mirror_preserves_sub_model_step_markers(self, model):
        sub = self._asymmetric_sub()
        sub.add_step()
        sub.add(brick(1, 1, color=Color.RED))
        model.add(sub, Position(0, 0, 0))
        mirrored_sub = mirrored_in_place(model, Axis.X).placements[0].content
        assert isinstance(mirrored_sub, LegoBuild)
        assert mirrored_sub.step_markers == sub.step_markers

    def test_mirror_reflects_a_shared_sub_model_once(self, model):
        # One sub-model placed twice must stay one sub-model afterwards: the
        # result is what the LDraw writer keys sub-files by identity on, so a
        # copy per placement would emit the same sub-file twice.
        sub = self._asymmetric_sub()
        model.add(sub, Position(0, 0, 0))
        model.add(sub, Position(0, 4, 0))
        mirrored = mirrored_in_place(model, Axis.X)
        first, second = (p.content for p in mirrored.placements)
        assert first is second

    def test_mirror_reflects_each_distinct_sub_model_once(self, model):
        # Sharing nested two deep: the inner sub-model is reachable by four
        # paths but is one model, and must stay one.
        inner = self._asymmetric_sub()
        middle = LegoBuild()
        middle.add(inner, Position(0, 0, 0))
        middle.add(inner, Position(0, 4, 0))
        model.add(middle, Position(0, 0, 0))
        model.add(middle, Position(0, 8, 0))

        mirrored = mirrored_in_place(model, Axis.X)

        middles = {id(p.content) for p in mirrored.placements}
        inners = {
            id(q.content) for m in mirrored.placements for q in m.content.placements
        }
        assert len(middles) == 1
        assert len(inners) == 1


class TestMirrorPlane:
    """`mirror` reflects about the plane it is given, not one derived from the
    geometry."""

    @pytest.mark.parametrize("plane", [0, 7.5, -3])
    def test_mirror_reflects_the_alignment_box_across_the_plane(self, model, plane):
        m = TestMirror._two_brick_row(model)
        lo, hi = m.alignment_box

        low, high = mirror(m, Axis.X, plane).alignment_box

        assert (low.x, high.x) == pytest.approx((2 * plane - hi.x, 2 * plane - lo.x))

    def test_mirror_reflects_across_a_depth_plane(self, model):
        model.add(brick(2, 1, color=Color.RED), Position(0, 0, 0), Rotation.DEG_90)
        lo, hi = model.alignment_box

        low, high = mirror(model, Axis.Y, 6).alignment_box

        assert (low.y, high.y) == pytest.approx((12 - hi.y, 12 - lo.y))

    @pytest.mark.parametrize("plane", [0, 2.5, -4])
    def test_mirroring_twice_about_one_plane_is_the_identity(
        self, model, plane, filled_region
    ):
        m = TestMirror._two_brick_row(model)
        twice = mirror(mirror(m, Axis.X, plane), Axis.X, plane)
        assert filled_region(twice) == filled_region(m)

    def test_mirroring_about_the_alignment_center_leaves_the_model_where_it_is(
        self, model
    ):
        m = TestMirror._two_brick_row(model)
        assert mirrored_in_place(m, Axis.X).alignment_box == m.alignment_box

    def test_a_half_mirrors_into_a_symmetric_whole(self, model):
        # What a chosen plane is for: reflect a half about its own outer edge
        # and the two halves meet, with no re-anchoring by the caller.
        half = LegoBuild()
        half.add(brick(2, 1, color=Color.RED), Position(0, 0, 0))
        half.add(plate(1, 1, color=Color.BLUE), Position(2, 0, 0))
        seam = half.alignment_box[1].x

        whole = model
        whole.add_raw(half)
        whole.add_raw(mirror(half, Axis.X, seam))

        lo, hi = whole.alignment_box
        assert (lo.x, hi.x) == (0, 2 * seam)
        assert whole.brick_count == 2 * half.brick_count


class TestMirrorChirality:
    """Mirroring swaps a handed part for its opposite-handed counterpart."""

    @staticmethod
    def _wing(chirality, color=Color.RED):
        part_id = "30356" if chirality is Chirality.RIGHT else "30355"
        return Element(part_id, color)

    def test_mirror_swaps_a_handed_element(self):
        right = self._wing(Chirality.RIGHT)
        assert mirror(right, Axis.X) == self._wing(Chirality.LEFT)

    def test_mirror_keeps_an_elements_color(self):
        right = self._wing(Chirality.RIGHT, Color.BLUE)
        assert mirror(right, Axis.X).color is Color.BLUE

    def test_mirror_leaves_an_achiral_element_alone(self):
        element = brick(2, 1, color=Color.RED)
        assert mirror(element, Axis.X) is element

    def test_mirroring_an_element_twice_returns_it(self):
        right = self._wing(Chirality.RIGHT)
        assert mirror(mirror(right, Axis.X), Axis.X) == right

    def test_an_elements_mirror_does_not_depend_on_the_axis(self):
        # A part's counterpart is a catalog fact, not a direction: there is
        # one opposite hand, whichever plane the reflection is across.
        right = self._wing(Chirality.RIGHT)
        assert mirror(right, Axis.X) == mirror(right, Axis.Y)

    def test_mirror_swaps_handed_parts_inside_a_model(self, model):
        model.add(self._wing(Chirality.RIGHT), name="wing")
        mirrored = mirrored_in_place(model, Axis.X)
        assert mirrored.named("wing").content == self._wing(Chirality.LEFT)

    def test_mirror_swaps_handed_parts_inside_a_sub_model(self, model):
        sub = LegoBuild()
        sub.add(self._wing(Chirality.RIGHT), name="wing")
        model.add(sub, Position(0, 0, 0))
        mirrored_sub = mirrored_in_place(model, Axis.X).placements[0].content
        assert isinstance(mirrored_sub, LegoBuild)
        assert mirrored_sub.named("wing").content == self._wing(Chirality.LEFT)

    def test_mirroring_a_handed_model_twice_restores_it(self, model, filled_region):
        model.add(self._wing(Chirality.RIGHT), name="wing")
        model.add(brick(2, 1, color=Color.BLUE), Position(4, 0, 0))
        twice = mirror(
            mirrored_in_place(model, Axis.X),
            Axis.X,
            in_place(model, Axis.X),
        )
        assert twice.named("wing").content == self._wing(Chirality.RIGHT)
        assert filled_region(twice) == filled_region(model)

    def test_mirror_preserves_the_footprint_of_a_handed_part(self, model):
        model.add(self._wing(Chirality.RIGHT))
        mirrored = mirrored_in_place(model, Axis.X)
        assert mirrored.bounding_box == model.bounding_box

    @pytest.mark.parametrize("axis", [Axis.X, Axis.Y])
    def test_mirror_preserves_the_footprint_of_an_off_centre_handed_part(
        self, model, axis
    ):
        # Across Y as much as across X: a counterpart is the reflection across
        # the left/right plane whichever plane is being mirrored across, so a
        # front/back reflection has to turn it back through that plane.
        spec = an_off_centre_handed_part()
        model.add(Element(spec.ldraw_id, Color.RED), name="handed")

        mirrored = mirrored_in_place(model, axis)

        assert mirrored.named("handed").content.spec == spec.mirrored
        assert mirrored.alignment_box == model.alignment_box

    @pytest.mark.parametrize("axis", [Axis.X, Axis.Y])
    def test_mirroring_an_off_centre_handed_part_twice_restores_it(self, model, axis):
        spec = an_off_centre_handed_part()
        placement = model.add(Element(spec.ldraw_id, Color.RED), name="handed")

        twice = mirror(mirrored_in_place(model, axis), axis, in_place(model, axis))

        assert twice.named("handed").content.spec == spec
        assert twice.named("handed").pose == placement.pose

    def test_mirror_keeps_a_handed_part_with_no_counterpart(self, model):
        # A part with only one hand is placed like any other and left alone.
        lonely = a_handed_part_without_a_counterpart()
        element = Element(lonely.ldraw_id, Color.RED)
        model.add(element)
        assert mirrored_in_place(model, Axis.X).placements[0].content is element

    @staticmethod
    def _slope():
        # 3039, Slope Brick 45 2 x 2: achiral, symmetric left/right only.
        return Element("3039", Color.RED)

    @staticmethod
    def _connector_points(model):
        return sorted(
            (c.type.name, *(round(v, 6) + 0.0 for v in c.position))
            for c in model.connectors
        )

    def test_a_symmetric_roof_mirrors_front_to_back_onto_itself(self, model):
        model.add(self._slope(), Position(0, 0, 0))
        model.add(self._slope(), Position(0, 2, 0), Rotation.DEG_180)

        mirrored = mirrored_in_place(model, Axis.Y)

        assert self._connector_points(mirrored) == self._connector_points(model)
        assert mirrored.bounding_box == model.bounding_box

    @pytest.mark.parametrize("axis", [Axis.X, Axis.Y])
    @pytest.mark.parametrize("rotation", list(Rotation))
    def test_an_achiral_part_mirrors_onto_its_reflection(self, model, axis, rotation):
        model.add(self._slope(), Position(2, 3, 0), rotation)

        mirrored = mirror(model, axis, 0)

        reflected = sorted(
            (name, *(-v + 0.0 if i == axis.value else v for i, v in enumerate(point)))
            for name, *point in self._connector_points(model)
        )
        assert self._connector_points(mirrored) == reflected
        (lo, hi), (low, high) = model.bounding_box, mirrored.bounding_box
        assert (low[axis.value], high[axis.value]) == pytest.approx(
            (-hi[axis.value], -lo[axis.value])
        )

    @pytest.mark.parametrize("rotation", list(Rotation))
    def test_a_part_with_no_counterpart_mirrors_front_to_back_turned_half_round(
        self, model, rotation
    ):
        # A part left in its own hand is off by one reflection in its own frame,
        # the same one whichever plane it is mirrored across.
        element = Element(a_handed_part_without_a_counterpart().ldraw_id, Color.RED)
        model.add(element, Position(2, 3, 0), rotation)

        across_x = mirrored_in_place(model, Axis.X).placements[0]
        across_y = mirrored_in_place(model, Axis.Y).placements[0]

        assert all_close(
            across_y.pose.rotation, Rotation.DEG_180.matrix @ across_x.pose.rotation
        )
        assert across_y.alignment_box == model.alignment_box


class TestMirrorPlacement:
    """`mirror` accepts a placement, reflecting its pose across the plane."""

    @staticmethod
    def _placement():
        sub = LegoBuild()
        sub.add(brick(2, 1, color=Color.RED), Position(0, 0, 0))
        sub.add(plate(1, 1, color=Color.BLUE), Position(3, 0, 0))
        return Placement(sub, Pose(translation=Position(5, 0, 0)))

    def test_mirror_reflects_a_placement_across_the_plane(self):
        placement = self._placement()
        lo, hi = placement.bounding_box

        mirrored = mirror(placement, Axis.X, 0)

        low, high = mirrored.bounding_box
        assert (low.x, high.x) == pytest.approx((-hi.x, -lo.x))

    def test_mirroring_a_placement_about_its_own_center_keeps_it_in_place(self):
        placement = self._placement()
        mirrored = mirrored_in_place(placement, Axis.X)
        assert mirrored.bounding_box == placement.bounding_box

    def test_mirroring_a_placement_matches_mirroring_it_in_a_model(self):
        placement = self._placement()

        alone = mirror(placement, Axis.X, 3)
        in_model = mirror(LegoBuild([placement]), Axis.X, 3).placements[0]

        assert alone.pose == in_model.pose

    def test_mirror_swaps_a_handed_element_under_a_placement(self):
        right = Element("30356", Color.RED)
        mirrored = mirror(Placement(right), Axis.X, 0)
        assert mirrored.content == Element("30355", Color.RED)

    def test_mirroring_a_placement_twice_restores_its_pose(self):
        placement = self._placement()
        once = mirror(placement, Axis.X, 3)
        assert mirror(once, Axis.X, 3).pose == placement.pose


class TestMirrorOffGrid:
    def test_mirror_reflects_an_off_grid_translation(self):
        # Two parts nudged half a stud off the grid (fractional x): a wide brick
        # at x [0.5, 2.5] on the right and a plate at x [3.5, 4.5] on the left.
        # Reflecting about the model's center plane (x = 2.5) swaps them and
        # keeps the half-stud offsets exactly: brick to x [2.5, 4.5], plate to
        # x [0.5, 1.5].
        m = LegoBuild(
            [
                Placement(
                    brick(2, 1, color=Color.RED), Pose(translation=Position(1.5, 0, 0))
                ),
                Placement(
                    plate(1, 1, color=Color.BLUE), Pose(translation=Position(4, 0, 0))
                ),
            ]
        )
        mirrored = mirrored_in_place(m, Axis.X)
        assert mirrored.placements[0].bounding_box[0].x == pytest.approx(2.5)
        assert mirrored.placements[1].bounding_box[0].x == pytest.approx(0.5)

    def test_mirror_inverts_an_off_grid_rotation(self):
        # A 30-degree turn is off the quarter-turn grid, so this exercises the
        # arbitrary-rotation path. Mirroring across X inverts it to -30 degrees.
        m = LegoBuild(
            [
                Placement(
                    brick(2, 1, color=Color.RED),
                    Pose(rotation_about(Vec3(0, 0, 1), 30)),
                )
            ]
        )
        mirrored_pose = mirrored_in_place(m, Axis.X).placements[0].pose
        assert all_close(mirrored_pose.rotation, rotation_about(Vec3(0, 0, 1), -30))

    def test_mirror_round_trips_an_off_grid_model(self, filled_region):
        m = LegoBuild(
            [
                Placement(
                    brick(2, 1, color=Color.RED),
                    Pose(rotation_about(Vec3(0, 0, 1), 30), Position(1.5, 0.5, 0)),
                ),
                Placement(
                    plate(1, 1, color=Color.BLUE), Pose(translation=Position(4, 0, 0))
                ),
            ]
        )
        mirrored = mirrored_in_place(m, Axis.X)
        assert filled_region(mirrored) != filled_region(m)
        assert filled_region(mirrored_in_place(mirrored, Axis.X)) == filled_region(m)

    def test_mirror_handles_an_off_grid_submodel_with_non_grid_connectors(self):
        # A window is a sub-model: a frame + a pane seated in it by horizontal,
        # off-grid tab/slot connectors. Placed off the grid (fractional shift
        # plus a 30-degree turn), mirroring must recurse into it, keep the pane
        # seated in the frame, and round-trip. The fractional shift here is
        # sub-stud, so filled_region's grid quantization can't tell mirrored
        # apart from the original; compare exact leaf bounding boxes instead.
        win = window(4, 1, 3)
        assert win.is_connected()
        m = LegoBuild(
            [
                Placement(
                    win, Pose(rotation_about(Vec3(0, 0, 1), 30), Position(1.5, 0.5, 0))
                )
            ]
        )
        mirrored = mirrored_in_place(m, Axis.X)
        inner = mirrored.placements[0].content
        assert isinstance(inner, LegoBuild)
        assert inner.is_connected()  # the pane is still seated in the frame

        def leaf_boxes(model):
            return {p.bounding_box for p in model.flattened_placements}

        assert leaf_boxes(mirrored) != leaf_boxes(m)
        assert leaf_boxes(mirrored_in_place(mirrored, Axis.X)) == leaf_boxes(m)


class TestTransformAliasing:
    """A transform's result is independent of its input, but a nested
    sub-model stays the same shared, live object."""

    def test_a_zero_delta_returns_a_fresh_copy(self, model):
        model.add(brick(2, 1, color=Color.RED), Position(1, 2, 0), name="base")
        model.stack(plate(1, 1, color=Color.BLUE), "base", name="cap")
        result = translate(model, Position.ZERO)
        assert result is not model
        assert result.placements == model.placements

    def test_the_original_is_left_untouched(self, model):
        model.add(brick(2, 1, color=Color.RED), Position(1, 2, 0), name="base")
        model.stack(plate(1, 1, color=Color.BLUE), "base", name="cap")
        before = [p.pose.translation for p in model.placements]
        translate(model, Position(5, 5, 5))
        assert [p.pose.translation for p in model.placements] == before

    def test_mutating_a_zero_delta_result_leaves_the_original_alone(self, model):
        model.add(brick(2, 1, color=Color.RED), Position(1, 2, 0), name="base")
        model.stack(plate(1, 1, color=Color.BLUE), "base", name="cap")
        result = translate(model, Position.ZERO)
        before = model.brick_count
        result.add(brick(1, 1, color=Color.RED))
        assert model.brick_count == before

    def test_mutating_an_already_grounded_result_leaves_the_original_alone(self, model):
        model.add(brick(2, 1, color=Color.RED), Position(0, 0, 0))
        result = translate_to_ground(model)
        before = model.brick_count
        result.add(brick(1, 1, color=Color.RED))
        assert model.brick_count == before

    def test_a_mirrored_model_still_tracks_its_sub_models(self):
        parent, child = LegoBuild(), LegoBuild()
        child.add(brick(2, 2, color=Color.RED))
        parent.add(child)
        mirrored = mirrored_in_place(parent, Axis.X)
        nested = mirrored.placements[0].content
        before = mirrored.brick_count
        nested.add(brick(2, 2, color=Color.BLUE), Position(4, 0, 0))
        assert mirrored.brick_count == before + 1

    def test_a_transformed_model_still_tracks_its_sub_models(self):
        parent, child = LegoBuild(), LegoBuild()
        child.add(brick(2, 2, color=Color.RED))
        parent.add(child)
        moved = translate(parent, Position(4, 0, 0))
        before = moved.brick_count
        child.add(brick(2, 2, color=Color.BLUE), Position(4, 0, 0))
        assert moved.brick_count == before + 1


def test_mirror_preserves_articulated_motion_and_nested_endpoints(turntable):
    inner, _, _ = turntable(
        mounting=Mounting(angle=25),
        motion=MotionRange(Revolute(-10), Revolute(60)),
    )
    model = LegoBuild()
    model.add_raw(inner)
    mirrored = mirror(model, Axis.X, 0)
    (joint,) = mirrored.flattened_joints
    assert joint.kind is JointKind.REVOLUTE
    assert joint.motion == MotionRange(Revolute(-60), Revolute(10))
    actual = mirrored.posed({joint: Revolute(-35)})
    expected = mirror(model.posed({model.flattened_joints[0]: Revolute(35)}), Axis.X, 0)
    for a, b in zip(actual.placements, expected.placements):
        assert a.pose.rotation.flatten() == pytest.approx(b.pose.rotation.flatten())
        assert tuple(a.pose.translation) == pytest.approx(tuple(b.pose.translation))


def test_flatten_preserves_motion_when_a_submodel_has_disconnected_geometry():
    sub = LegoBuild()
    sub.add_raw(Element("3679", Color.RED))
    sub.add_raw(Element("3005", Color.BLUE), Pose(translation=Position(10, 0, 0)))
    model = LegoBuild()
    base = model.add_raw(Element("3680", Color.WHITE))
    model.connect(
        sub,
        "turntable_pin",
        to=base.find_connector("turntable_socket"),
        motion=MotionRange(Revolute(-45), Revolute(45)),
    )
    flat = flatten(model)
    a = model.posed({model.joints[0]: Revolute(30)})
    b = flat.posed({flat.joints[0]: Revolute(30)})
    assert [p.pose for p in a.placements] == [p.pose for p in b.placements]


def test_translate_and_flatten_preserve_motion(turntable):
    model, _, _ = turntable(motion=MotionRange(Revolute(-30), Revolute(30)))
    shifted = translate(model, Position(4, 0, 2))
    assert len(shifted.joints) == 1
    nested = LegoBuild()
    nested.add_raw(shifted)
    flat = flatten(nested)
    assert len(flat.joints) == 1
    report = flat.check_motion(samples=3)
    assert not report.floating
    assert not report.collisions and not report.disconnections
    assert translate_to_ground(flat).check_motion(samples=3).passed
