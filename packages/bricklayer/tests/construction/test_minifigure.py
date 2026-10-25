"""Minifigure pose validation and the head, body, legs, and full-figure builders."""

import dataclasses
from collections.abc import Callable, Collection

import pytest

from bricklayer import (
    PLATE,
    Anchor,
    Color,
    Direction,
    Element,
    InvalidPartError,
    LegoBuild,
    Mat3,
    MinifigPose,
    Placement,
    Position,
    minifig,
    minifig_body,
    minifig_head,
    minifig_legs,
    plate,
    tile,
    to_ldraw,
)
from bricklayer.construction.minifigure import _ARM, _HAND, _HEAD, _HIPS, _LEG, _TORSO
from bricklayer.geometry.connections import same_connector
from bricklayer.geometry.linalg import all_close, rotation_about
from bricklayer.parts.catalog import PartSpec

_ARMS = (_ARM, PartSpec(_ARM).mirrored.ldraw_id)
_LEGS = (_LEG, PartSpec(_LEG).mirrored.ldraw_id)


def _placements_of(
    model: LegoBuild,
    part_ids: Collection[str],
    sort_key: Callable = lambda p: tuple(p.center),
) -> tuple[Placement, ...]:
    """The model's element placements drawing one of ``part_ids``, sorted."""
    return tuple(
        sorted(
            (
                p
                for p in model.flattened_placements
                if isinstance(p.content, Element)
                and p.content.spec.ldraw_id in part_ids
            ),
            key=sort_key,
        )
    )


class TestMinifigPose:
    @pytest.mark.parametrize("leg", ["left_leg", "right_leg"])
    def test_leg_swing_at_limits_is_allowed(self, leg):
        MinifigPose(**{leg: 90})
        MinifigPose(**{leg: -45})

    @pytest.mark.parametrize("leg", ["left_leg", "right_leg"])
    def test_leg_forward_beyond_limit_raises(self, leg):
        with pytest.raises(ValueError, match=leg):
            MinifigPose(**{leg: 91})

    @pytest.mark.parametrize("leg", ["left_leg", "right_leg"])
    def test_leg_backward_beyond_limit_raises(self, leg):
        with pytest.raises(ValueError, match=leg):
            MinifigPose(**{leg: -46})

    def test_non_leg_joints_are_unrestricted(self):
        MinifigPose(head=180, left_arm=-720, right_hand=360)


class TestMinifigHead:
    def test_has_bricklike_1x1x1_geometry(self, assert_cuboid_geometry):
        model = minifig_head()
        # Specify tol=0.5 as the head is slightly bigger than 1x1x1.
        assert_cuboid_geometry(model, 1, 1, 1, tol=0.5)

    def test_selects_a_printed_head(self, element_of):
        head = minifig_head(head_id="3626bp02", color=Color.TAN)
        assert element_of(head, "head") == Element("3626bp02", Color.TAN)
        assert head.is_valid() and head.is_connected()

    def test_selects_headwear_and_color(self, element_of):
        worn = Element("3878", Color.BLACK)
        model = minifig_head(headwear_id="3878", headwear_color=Color.BLACK)

        assert model.is_valid()
        assert model.is_connected()
        assert len(model.placements) == 2
        assert element_of(model, "head").spec.ldraw_id == _HEAD
        assert model.named("headwear").content == worn

    def test_headwear_color_defaults_to_white(self, element_of):
        head = minifig_head(headwear_id="3878")
        assert element_of(head, "headwear") == Element("3878", Color.WHITE)

    def test_centers_headwear_facing_forward_on_head(self):
        for part_id in ("61183", "3878", "3833"):
            model = minifig_head(headwear_id=part_id)
            head_pose = model.named("head").pose
            worn_pose = model.named("headwear").pose

            assert model.is_valid(), part_id
            assert model.is_connected(), part_id
            assert worn_pose.rotation == Mat3.IDENTITY, part_id
            assert worn_pose.translation == pytest.approx(
                head_pose.translation + Position(0, 0, 1)
            ), part_id

    def test_a_bare_head_still_exposes_its_neck_socket(self):
        head = minifig_head()

        assert head.find_connectors("pin_hole")

    def test_headwear_hides_the_crown_stud(self):
        bare = minifig_head()
        dressed = minifig_head(headwear_id="3878", headwear_color=Color.WHITE)

        assert bare.find_connectors("stud")
        assert not dressed.find_connectors("stud")

    def test_rejects_a_head_without_a_neck_socket(self):
        with pytest.raises(ValueError, match="Head"):
            minifig_head(head_id="3001")

    def test_rejects_non_headwear(self):
        with pytest.raises(ValueError, match="Headwear"):
            minifig_head(headwear_id="2587", headwear_color=Color.WHITE)


class TestMinifigBody:
    def test_alignment_footprint(self):
        model = minifig_body()
        assert model.alignment_width == 2
        assert model.alignment_depth == 1

    def test_includes_torso_arms_and_hands(self, element_of):
        model = minifig_body()

        assert model.is_valid()
        assert model.is_connected()
        assert len(model.placements) == 5
        for name, part_ids in (
            ("torso", (_TORSO,)),
            ("left_arm", _ARMS),
            ("right_arm", _ARMS),
            ("left_hand", (_HAND,)),
            ("right_hand", (_HAND,)),
        ):
            assert element_of(model, name).spec.ldraw_id in part_ids, name

    def test_selects_a_printed_torso(self, element_of):
        body = minifig_body(torso_id="973p03", torso_color=Color.RED)
        assert element_of(body, "torso") == Element("973p03", Color.RED)
        assert body.is_valid() and body.is_connected()

    def test_colors_torso_arms_and_hands_separately(self, assert_named_has_color):
        model = minifig_body(
            torso_color=Color.RED, arm_color=Color.GREEN, hand_color=Color.BLUE
        )
        for name, color in (
            ("torso", Color.RED),
            ("left_arm", Color.GREEN),
            ("right_arm", Color.GREEN),
            ("left_hand", Color.BLUE),
            ("right_hand", Color.BLUE),
        ):
            assert_named_has_color(model, name, color)

    def test_arm_color_defaults_to_torso_color(self, assert_named_has_color):
        model = minifig_body(torso_color=Color.RED)
        for name in ("left_arm", "right_arm"):
            assert_named_has_color(model, name, Color.RED)

    def test_selects_bodywear_and_color(self):
        worn = Element("2587", Color.BLUE)
        model = minifig_body(bodywear_id="2587", bodywear_color=Color.BLUE)

        assert model.is_valid()
        assert model.is_connected()
        assert len(model.placements) == 6
        assert model.named("bodywear").content == worn

    def test_centers_bodywear_facing_forward_on_torso(self):
        for part_id in ("2587", "15619", "2526"):
            model = minifig_body(bodywear_id=part_id)
            torso_pose = model.named("torso").pose
            worn_pose = model.named("bodywear").pose

            assert model.is_valid(), part_id
            assert model.is_connected(), part_id
            assert worn_pose.rotation == Mat3.IDENTITY, part_id
            brackets = model.named("torso").find_connectors("neck_bracket")
            loops = model.named("bodywear").find_connectors("neck_loop")
            assert brackets and loops, part_id
            assert any(
                loop.position == pytest.approx(bracket.position)
                for bracket in brackets
                for loop in loops
            ), part_id
            assert torso_pose.translation.x == pytest.approx(worn_pose.translation.x)

    def test_rejects_a_torso_without_attachment_connectors(self):
        with pytest.raises(ValueError, match="Torso"):
            minifig_body(torso_id="3001")

    def test_rejects_non_bodywear(self):
        with pytest.raises(ValueError, match="Bodywear"):
            minifig_body(bodywear_id="3878", bodywear_color=Color.WHITE)


class TestMinifigLegs:
    def test_alignment_footprint(self):
        model = minifig_legs()
        assert model.alignment_width == 2
        assert model.alignment_depth == 1

    def test_standard_legs_include_hips_and_two_legs(self, element_of):
        model = minifig_legs()
        assert model.is_valid()
        assert model.is_connected()
        assert len(model.placements) == 3
        for name, part_ids in (
            ("hips", (_HIPS,)),
            ("right_leg", _LEGS),
            ("left_leg", _LEGS),
        ):
            assert element_of(model, name).spec.ldraw_id in part_ids, name

    def test_selects_printed_hips_and_individual_legs(self, element_of):
        lower = minifig_legs(
            hips_id="3815bp04", left_leg_id="3817cp01", right_leg_id="3816cp02"
        )
        for name, part_id in (
            ("hips", "3815bp04"),
            ("left_leg", "3817cp01"),
            ("right_leg", "3816cp02"),
        ):
            assert element_of(lower, name) == Element(part_id, Color.WHITE)
        assert lower.is_valid() and lower.is_connected()

    def test_selecting_one_leg_keeps_the_other_standard(self, element_of):
        lower = minifig_legs(left_leg_id="3817cp01")
        assert element_of(lower, "left_leg").ldraw_id == "3817cp01"
        assert element_of(lower, "right_leg").ldraw_id == "3816c"
        assert element_of(lower, "hips").ldraw_id == "3815b"
        assert lower.is_valid() and lower.is_connected()

    def test_hips_color_can_be_set_separately(self, assert_named_has_color):
        model = minifig_legs(leg_color=Color.RED, hips_color=Color.BLUE)
        for name, color in (
            ("hips", Color.BLUE),
            ("left_leg", Color.RED),
            ("right_leg", Color.RED),
        ):
            assert_named_has_color(model, name, color)

    def test_hips_color_defaults_to_leg_color(self, assert_named_has_color):
        model = minifig_legs(leg_color=Color.RED)
        assert_named_has_color(model, "hips", Color.RED)

    @pytest.mark.parametrize("part_id", ("41879a", "36036", "41879ap01", "36036p00"))
    def test_single_piece_lower_body_uses_leg_color(self, part_id, element_of):
        lower = minifig_legs(
            legs_id=part_id, leg_color=Color.RED, hips_color=Color.BLUE
        )
        assert len(lower.placements) == 1
        assert element_of(lower, "legs") == Element(part_id, Color.RED)
        assert lower.is_valid() and lower.is_connected()

    def test_selects_footwear_and_color_for_both_feet(self):
        worn = Element("11253", Color.RED)
        model = minifig_legs(footwear_id="11253", footwear_color=Color.RED)

        assert model.is_valid()
        assert model.is_connected()
        assert len(model.placements) == 5
        assert model.named("footwear_left").content == worn
        assert model.named("footwear_right").content == worn

    def test_centers_footwear_on_each_leg(self):
        for part_id, outward_angle in (("11253", 0), ("59275a", 5), ("30284", 8)):
            model = minifig_legs(footwear_id=part_id, footwear_color=Color.WHITE)
            assert model.is_valid(), part_id
            assert model.is_connected(), part_id
            for side in "left", "right":
                leg_pose = model.named(f"{side}_leg").pose
                worn_pose = model.named(f"footwear_{side}").pose
                angle = outward_angle if side == "left" else -outward_angle
                assert all_close(
                    worn_pose.rotation,
                    rotation_about(Direction.UP.value, angle),
                ), part_id
                assert worn_pose.translation.x == pytest.approx(
                    leg_pose.translation.x
                ), part_id

    def test_rejects_non_footwear(self):
        with pytest.raises(ValueError, match="Footwear"):
            minifig_legs(footwear_id="3878", footwear_color=Color.WHITE)

    @pytest.mark.parametrize("part_id", ("36036", "36036p00"))
    def test_rejects_footwear_without_two_soles(self, part_id):
        with pytest.raises(ValueError, match="two.*sole"):
            minifig_legs(legs_id=part_id, footwear_id="11253")

    @pytest.mark.parametrize(
        "part_id, leg",
        [
            ("41879a", "left_leg"),
            ("36036", "left_leg"),
            ("41879ap01", "right_leg"),
            ("36036p00", "right_leg"),
        ],
    )
    def test_single_piece_legs_cannot_articulate(self, part_id, leg):
        with pytest.raises(ValueError, match="cannot articulate"):
            minifig_legs(legs_id=part_id, pose=MinifigPose(**{leg: 30}))

    @pytest.mark.parametrize(
        "selection",
        [
            {"hips_id": "3815bp04"},
            {"left_leg_id": "3817cp01"},
            {"right_leg_id": "3816cp02"},
        ],
    )
    def test_single_piece_legs_and_separate_parts_are_exclusive(self, selection):
        with pytest.raises(ValueError, match="legs_id.*separate"):
            minifig_legs(legs_id="41879a", **selection)

    @pytest.mark.parametrize(
        "selection, role",
        [
            ({"hips_id": "3001"}, "Hips"),
            ({"left_leg_id": "3001"}, "narrow_hole"),
            ({"legs_id": "3001"}, "Lower body"),
        ],
    )
    def test_parts_require_attachment_connectors(self, selection, role):
        with pytest.raises(ValueError, match=role):
            minifig_legs(**selection)

    def test_unknown_lower_body_id_is_rejected(self):
        with pytest.raises(InvalidPartError, match="not a catalogued LDraw part"):
            minifig_legs(legs_id="unknown-lower-body")


class TestMinifig:
    def test_alignment_footprint(self):
        model = minifig()
        assert model.alignment_width == 2
        assert model.alignment_depth == 1

    def test_dimensions(self):
        model = minifig()
        assert 2 < model.width < 4
        assert 1 < model.depth < 3
        assert 4 < model.height < 5

    def test_stacks_legs_body_and_head(self):
        model = minifig()

        assert model.is_valid()
        assert model.is_connected()
        assert len(model.placements) == 3
        legs_pos = model.named("legs").pose.translation
        body_pos = model.named("body").pose.translation
        head_pos = model.named("head").pose.translation
        assert body_pos.x == pytest.approx(legs_pos.x)
        assert head_pos.x == pytest.approx(body_pos.x)
        assert body_pos.z == pytest.approx(legs_pos.z + 5 * PLATE)
        assert head_pos.z == pytest.approx(body_pos.z + 4 * PLATE, abs=0.05)

    def test_printed_parts_assemble_and_keep_their_ids(self, element_of):
        figure = minifig(
            head_id="3626bp02",
            torso_id="973p03",
            hips_id="3815bp04",
            left_leg_id="3817cp01",
            right_leg_id="3816cp02",
            torso_color=Color.RED,
            leg_color=Color.BLUE,
            hips_color=Color.BLACK,
            pose=MinifigPose(head=25, left_leg=30),
        )
        for path, part_id, color in (
            (("head", "head"), "3626bp02", Color.YELLOW),
            (("body", "torso"), "973p03", Color.RED),
            (("legs", "hips"), "3815bp04", Color.BLACK),
            (("legs", "left_leg"), "3817cp01", Color.BLUE),
            (("legs", "right_leg"), "3816cp02", Color.BLUE),
        ):
            assert element_of(figure, path) == Element(part_id, color)
        assert figure.is_valid()
        assert figure.is_connected()

    def test_printed_single_piece_legs_support_footwear(self, element_of):
        figure = minifig(
            legs_id="41879ap01", footwear_id="11253", footwear_color=Color.BLACK
        )
        assert element_of(figure, ("legs", "legs")).ldraw_id == "41879ap01"
        assert figure.is_valid()
        assert figure.is_connected()

    @pytest.mark.parametrize("part_id", ["36036", "36036p00"])
    def test_skirts_assemble_without_footwear(self, part_id, element_of):
        figure = minifig(legs_id=part_id)
        assert element_of(figure, ("legs", "legs")).ldraw_id == part_id
        assert figure.is_valid()
        assert figure.is_connected()

    def test_colors_parts_separately(self, assert_named_has_color):
        model = minifig(
            skin_color=Color.MAGENTA,
            torso_color=Color.RED,
            arm_color=Color.GREEN,
            hand_color=Color.BLUE,
            leg_color=Color.YELLOW,
            hips_color=Color.ORANGE,
        )
        head_model = model.named("head").content
        body_model = model.named("body").content
        legs_model = model.named("legs").content
        for submodel, name, color in (
            (head_model, "head", Color.MAGENTA),
            (body_model, "torso", Color.RED),
            (body_model, "left_arm", Color.GREEN),
            (body_model, "right_arm", Color.GREEN),
            (body_model, "left_hand", Color.BLUE),
            (body_model, "right_hand", Color.BLUE),
            (legs_model, "left_leg", Color.YELLOW),
            (legs_model, "right_leg", Color.YELLOW),
            (legs_model, "hips", Color.ORANGE),
        ):
            assert isinstance(submodel, LegoBuild)
            assert_named_has_color(submodel, name, color)

    def test_hands_default_to_skin_color(self, assert_named_has_color):
        model = minifig(skin_color=Color.MAGENTA)
        body_model = model.named("body").content
        for name in ("left_hand", "right_hand"):
            assert isinstance(body_model, LegoBuild)
            assert_named_has_color(body_model, name, Color.MAGENTA)

    def test_selects_accessories_and_colors(self, element_of):
        figure = minifig(
            headwear_id="3878",
            headwear_color=Color.BLACK,
            bodywear_id="2587",
            bodywear_color=Color.BLUE,
            footwear_id="11253",
            footwear_color=Color.RED,
        )
        assert element_of(figure, ("head", "headwear")) == Element("3878", Color.BLACK)
        assert element_of(figure, ("body", "bodywear")) == Element("2587", Color.BLUE)
        for side in ("left", "right"):
            assert element_of(figure, ("legs", f"footwear_{side}")) == Element(
                "11253", Color.RED
            )
        assert figure.is_valid() and figure.is_connected()

    def test_sample_headwear_is_valid_and_coupled(self):
        for part_id in ("61183", "3878", "3833"):
            fig = minifig(headwear_id=part_id, headwear_color=Color.WHITE)
            assert fig.is_valid(), part_id
            assert fig.is_connected(), part_id

    def test_sample_bodywear_is_valid_and_coupled(self):
        for part_id in ("2587", "15619", "2526"):
            fig = minifig(bodywear_id=part_id, bodywear_color=Color.WHITE)
            assert fig.is_valid(), part_id
            assert fig.is_connected(), part_id

    @pytest.mark.parametrize("legs_id", (None, "41879a"))
    def test_leg_styles_with_sample_footwear_are_valid_and_coupled(self, legs_id):
        for part_id in ("11253", "59275a", "30284"):
            fig = minifig(
                legs_id=legs_id,
                footwear_id=part_id,
                footwear_color=Color.WHITE,
            )
            assert fig.is_valid(), part_id
            assert fig.is_connected(), part_id

    def test_accessory_attaches_through_its_connector(self):
        accessory = Element("98138", Color.RED)
        assert isinstance(accessory.color, Color)
        figure = minifig(headwear_id=accessory.ldraw_id, headwear_color=accessory.color)
        assert figure.is_valid()
        assert figure.is_connected()
        assert figure.named(("head", "headwear")).content == accessory

    def test_head_only_rises_for_bodywear_that_actually_reaches_it(self):
        # Neither BANDANA nor EPAULETTES fits in the bare torso's own bounding
        # box, but only EPAULETTES' mesh actually reaches into the head's.
        bare = minifig()
        flat = minifig(bodywear_id="15619", bodywear_color=Color.WHITE)
        tall = minifig(bodywear_id="2526", bodywear_color=Color.WHITE)

        assert flat.named("head").pose.translation == pytest.approx(
            bare.named("head").pose.translation
        )
        assert (
            tall.named("head").pose.translation.z
            > bare.named("head").pose.translation.z + 1e-6
        )
        assert tall.is_valid()

    def test_positive_head_turn_rotates_head_left(self):
        fig = minifig(pose=MinifigPose(head=90))
        (head_elem,) = _placements_of(fig, {_HEAD})
        assert all_close(
            head_elem.pose.rotation, rotation_about(Direction.UP.value, 90)
        )

    def test_headwear_follows_head_turn(self):
        fig = minifig(
            pose=MinifigPose(head=45),
            headwear_id="61183",
            headwear_color=Color.WHITE,
        )
        (hair,) = _placements_of(fig, {"61183"})
        (head_elem,) = _placements_of(fig, {_HEAD})
        assert hair.pose.rotation == head_elem.pose.rotation

    def test_positive_arm_angles_swing_arms_forward(self):
        rest = minifig()
        posed = minifig(pose=MinifigPose(left_arm=90, right_arm=90))
        rest_hands, posed_hands = (
            _placements_of(m, {_HAND}, sort_key=lambda p: p.center.x)
            for m in (rest, posed)
        )
        for before, after in zip(rest_hands, posed_hands):
            assert after.center.y < before.center.y - 0.3
            assert after.center.z > before.center.z + 0.2

    def test_positive_leg_angles_kick_legs_forward(self):
        rest = minifig()
        posed = minifig(pose=MinifigPose(left_leg=90, right_leg=90))
        rest_legs, posed_legs = (
            _placements_of(m, _LEGS, sort_key=lambda p: p.center.x)
            for m in (rest, posed)
        )
        for before, after in zip(rest_legs, posed_legs):
            assert after.center.y < before.center.y - 0.3

    @pytest.mark.parametrize("leg", ("left_leg", "right_leg"))
    def test_leg_at_forward_limit_clears_the_hand(self, leg):
        fig = minifig(pose=MinifigPose(**{leg: MinifigPose.LEG_FORWARD_LIMIT}))
        assert fig.is_valid()

    def test_hands_follow_their_arm(self):
        # Swinging only the right arm moves only the right hand.
        rest = minifig()
        posed = minifig(pose=MinifigPose(right_arm=45))

        def hand_centers(fig):
            return sorted(
                (p.center for p in _placements_of(fig, {_HAND})),
                key=lambda c: c.x,
            )

        (rest_right, rest_left) = hand_centers(rest)
        (posed_right, posed_left) = hand_centers(posed)
        assert tuple(posed_left) == pytest.approx(tuple(rest_left), abs=1e-9)
        assert tuple(posed_right) != pytest.approx(tuple(rest_right), abs=1e-3)

    def test_an_assembled_figure_hides_its_neck_joint(self):
        figure = minifig()
        neck = figure.named("head").find_connector("pin_hole")

        assert figure.connectors
        assert not any(same_connector(c, neck) for c in figure.connectors)

    def test_minifig_connects_to_a_base(self):
        model = LegoBuild()
        model.add(plate(8, 8), name="plate")
        model.stack(
            minifig(), on="plate", anchor=Anchor.CENTER, target_anchor=Anchor.CENTER
        )
        assert model.is_valid()
        assert model.is_connected()

    def test_minifig_with_footwear_stacked_on_tile_is_supported(self):
        """A tile tops out at its own surface, so a plain stack lands the
        figure on it."""
        model = LegoBuild()
        model.add(tile(6, 6), name="tile")
        model.stack(
            minifig(footwear_id="11253", footwear_color=Color.WHITE),
            on="tile",
            anchor=Anchor.CENTER,
            target_anchor=Anchor.CENTER,
        )
        assert not model.colliding_placements
        assert not model.floating_placements
        assert model.is_valid()
        assert not model.is_connected()

    @pytest.fixture
    def pose_grid(self, make_grid) -> LegoBuild:
        """A grid of figures: one row per joint, one column per swept angle."""

        angles = (-90, -45, 0, 45, 90)
        joints = [field.name for field in dataclasses.fields(MinifigPose)]

        def clamp(joint: str, angle: float) -> float:
            if joint in ("left_leg", "right_leg"):
                return max(
                    -MinifigPose.LEG_BACKWARD_LIMIT,
                    min(MinifigPose.LEG_FORWARD_LIMIT, angle),
                )
            return angle

        def _posed_figure(joint: str, angle: float) -> LegoBuild:
            """A figure with a single ``joint`` driven to ``angle``, others neutral."""
            return minifig(
                skin_color=Color.YELLOW,
                torso_color=Color.RED,
                arm_color=Color.RED,
                leg_color=Color.BLUE,
                pose=MinifigPose(**{joint: angle}),
            )

        figures = [
            _posed_figure(joint, clamp(joint, angle))
            for joint in joints
            for angle in angles
        ]
        for fig in figures:
            assert fig.is_valid()
            assert fig.is_connected()
        return make_grid(figures, n_cols=len(angles), include_anchor_bricks=False)

    def test_posing_visualization(self, pose_grid, file_regression):
        file_regression.check(to_ldraw(pose_grid), extension=".ldr", basename="posing")
