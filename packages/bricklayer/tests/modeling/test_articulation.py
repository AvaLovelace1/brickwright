"""Persistent joints, motion evaluation, and range collision checks."""

from dataclasses import replace

import pytest

from bricklayer import (
    Ball,
    Color,
    Connector,
    ConnectorType,
    Cylindrical,
    Direction,
    Element,
    Fixed,
    JointKind,
    LegoBuild,
    MotionRange,
    Mounting,
    Pose,
    Position,
    Prismatic,
    Revolute,
    Rotation,
    brick,
    plate,
    rotation_about,
    tile,
)
from bricklayer.geometry.connections import mark_compatible


class TestMotionRange:
    def test_exact_limits_are_preserved_and_all_samples_are_in_range(self):
        limit = 2**53 + 3
        motion = MotionRange(Prismatic(-limit), Prismatic(limit))
        samples = motion.sample(5)
        assert samples[0] == motion.lower
        assert samples[-1] == motion.upper
        assert all(motion.contains(position) for position in samples)

    def test_large_finite_bounds_do_not_overflow_during_sampling(self):
        motion = MotionRange(Revolute(-1e308), Revolute(1e308))
        samples = motion.sample(5)
        assert samples[0] == motion.lower
        assert samples[-1] == motion.upper
        assert len(samples) == 5
        assert all(motion.contains(position) for position in samples)

    def test_ball_samples_include_all_coordinate_combinations(self):
        motion = MotionRange(Ball(-10, -20, -30), Ball(10, 20, 30))
        assert len(motion.sample(3)) == 27
        assert Ball(-10, 20, -30) in motion.sample(3)

    def test_range_must_include_reference_and_match_kind(self):
        with pytest.raises(ValueError, match="zero"):
            MotionRange(Revolute(1), Revolute(90))
        with pytest.raises(ValueError, match="kind"):
            MotionRange(Revolute(0), Prismatic(1))

    def test_cylindrical_samples_cover_combinations(self):
        motion = MotionRange(Cylindrical(-1, -30), Cylindrical(1, 30))
        samples = motion.sample(3)
        assert len(samples) == 9
        assert Cylindrical(0, 30) in samples
        assert Cylindrical(1, -30) in samples


class TestJointKind:
    def test_constructed_records_validate_their_motion_kind(self, turntable):
        model, _, _ = turntable()
        with pytest.raises(ValueError, match="kind"):
            replace(model.joints[0], motion=MotionRange(Prismatic(-1), Prismatic(1)))

    @pytest.mark.parametrize(
        "angle,limits", [(90, (0, 30)), (180, (-30, 30)), (270, (-30, 0))]
    )
    def test_round_bar_with_rotation_stops_is_still_cylindrical(self, angle, limits):
        model = LegoBuild()
        clip = model.add_raw(Element("30237", Color.WHITE))
        bars = Element("30031", Color.RED)
        handle = model.connect(
            bars,
            bars.find_connectors("bar")[0],
            to=clip.find_connector("clip"),
            mounting=Mounting(angle=angle),
            motion=MotionRange(
                Cylindrical(angle=limits[0]), Cylindrical(angle=limits[1])
            ),
        )
        assert model.joint(handle).kind is JointKind.CYLINDRICAL
        assert model.check_motion(samples=7).passed
        model.set_motion(
            handle, MotionRange(Cylindrical(angle=0), Cylindrical(angle=360))
        )
        assert model.check_motion(samples=25).collisions

    @pytest.mark.parametrize("angle", [0, 90, 180, 270])
    @pytest.mark.parametrize("flip", [False, True])
    def test_cross_axle_keeps_its_mounting_branch(self, angle, flip):
        model = LegoBuild()
        beam = model.add_raw(Element("7229", Color.WHITE))
        axle = model.connect(
            Element("3705", Color.RED),
            "axle",
            to=beam.find_connector("axle_hole"),
            mounting=Mounting(angle=angle, flip=flip),
            motion=MotionRange(Prismatic(-0.2), Prismatic(0.2)),
        )
        joint = model.joint(axle)
        assert joint.kind is JointKind.PRISMATIC
        moved = model.posed({joint: Prismatic(0.2)})
        assert moved.placements[-1].pose.rotation == axle.pose.rotation
        assert model.check_motion(samples=3).passed

    def test_round_hole_permits_axle_rotation(self):
        model = LegoBuild()
        beam = model.add_raw(Element("32316", Color.WHITE))
        axle = model.connect(
            Element("3705", Color.RED), "axle", to=beam.find_connectors("pin_hole")[0]
        )
        assert model.joint(axle).kind is JointKind.CYLINDRICAL

    def test_rejects_rotation_of_a_keyed_axle(self):
        model = LegoBuild()
        beam = model.add_raw(Element("7229", Color.WHITE))
        with pytest.raises(ValueError, match="PRISMATIC"):
            model.connect(
                Element("3705", Color.RED),
                "axle",
                to=beam.find_connector("axle_hole"),
                motion=MotionRange(Cylindrical(angle=-90), Cylindrical(angle=90)),
            )
        assert model.placements == (beam,)

    def test_ambiguous_colliding_mounting_cannot_be_classified(self):
        model = LegoBuild()
        beam = model.add_raw(Element("7229", Color.WHITE))
        with pytest.raises(ValueError, match="mounted parts collide"):
            model.connect(
                Element("3705", Color.RED),
                "axle",
                to=beam.find_connector("axle_hole"),
                mounting=Mounting(angle=45),
                motion=MotionRange(Prismatic(-0.2), Prismatic(0.2)),
            )


class TestPosed:
    def test_joint_chain_moves_in_order_when_placements_are_reversed(
        self, element_with
    ):
        pin, socket = ConnectorType("pin"), ConnectorType("socket")
        mark_compatible(pin, socket, joint=JointKind.REVOLUTE)
        base = element_with([Connector(pin, Position.ZERO, Direction.UP)])
        arm = element_with(
            [
                Connector(socket, Position.ZERO, Direction.UP),
                Connector(pin, Position(2, 0, 0), Direction.UP),
            ]
        )
        tip = element_with([Connector(socket, Position.ZERO, Direction.UP)])
        model = LegoBuild()
        base = model.add_raw(base, name="base")
        limits = MotionRange(Revolute(-90), Revolute(90))
        arm = model.connect(
            arm, socket, to=base.find_connector(pin), motion=limits, index=0, name="arm"
        )
        tip = model.connect(
            tip, socket, to=arm.find_connector(pin), motion=limits, index=0, name="tip"
        )
        moved = model.posed(
            {model.joint(arm): Revolute(90), model.joint(tip): Revolute(-90)}
        )
        assert moved.named("base").pose == base.pose
        assert tuple(moved.named("tip").pose.translation) == pytest.approx((0, 2, 0))
        assert moved.named("tip").pose.rotation.flatten() == pytest.approx(
            Pose.IDENTITY.rotation.flatten()
        )

    def test_ball_coordinates_follow_a_rotated_parent(self):
        model = LegoBuild()
        socket = model.add_raw(Element("14418", Color.WHITE))
        model.connect(
            Element("22890", Color.RED),
            "towball",
            to=socket.find_connector("towball_socket"),
            motion=MotionRange(Ball(-20, -20, -30), Ball(20, 20, 30)),
        )
        rotation = Pose(rotation_about(Direction.LEFT.value, 35), Position(4, 5, 2))
        nested = LegoBuild()
        nested.add_raw(model, rotation)
        q = Ball(10, 15, 25)
        local = model.posed({model.joints[0]: q})
        world = nested.posed({nested.flattened_joints[0]: q})
        for a, b in zip(local.placements, world.placements):
            expected = rotation.compose(a.pose)
            assert b.pose.rotation.flatten() == pytest.approx(
                expected.rotation.flatten()
            )
            assert tuple(b.pose.translation) == pytest.approx(
                tuple(expected.translation)
            )

    def test_fixed_range_is_a_single_static_configuration(
        self, element_with, compatible_connector_types
    ):
        a, b = compatible_connector_types
        model = LegoBuild()
        parent = model.add_raw(
            element_with([Connector(a, Position.ZERO, Direction.UP)])
        )
        child = model.connect(
            element_with([Connector(b, Position.ZERO, Direction.UP)]),
            b,
            to=parent.find_connector(a),
            motion=MotionRange(Fixed(), Fixed()),
        )
        assert model.joint(child).kind is JointKind.FIXED
        assert model.posed({model.joint(child): Fixed()}).placements == model.placements

    def test_motion_that_is_locked_by_another_connection_is_rejected(
        self, element_with
    ):
        a, b, c, d = (ConnectorType(n) for n in ("pivot", "socket", "tab", "slot"))
        mark_compatible(a, b, joint=JointKind.REVOLUTE)
        mark_compatible(c, d)
        root = element_with(
            [
                Connector(a, Position.ZERO, Direction.UP),
                Connector(c, Position(2, 0, 0), Direction.UP),
            ]
        )
        bridge = element_with(
            [
                Connector(d, Position(2, 0, 0), Direction.UP),
                Connector(c, Position(4, 0, 0), Direction.UP),
            ]
        )
        moving = element_with(
            [
                Connector(b, Position.ZERO, Direction.UP),
                Connector(d, Position(4, 0, 0), Direction.UP),
            ]
        )
        model = LegoBuild()
        base = model.add_raw(root)
        model.add_raw(bridge)
        model.connect(
            moving,
            b,
            to=base.find_connector(a),
            motion=MotionRange(Revolute(-90), Revolute(90)),
        )
        with pytest.raises(ValueError, match="loop"):
            model.check_motion()

    def test_zero_reproduces_mounting_and_nonzero_is_relative(self, turntable):
        model, base, top = turntable(
            mounting=Mounting(angle=37),
            motion=MotionRange(Revolute(-90), Revolute(90)),
        )
        joint = model.joints[0]
        zero = model.posed({joint: Revolute(0)})
        assert zero.named("top").pose == top.pose
        moved = model.posed({joint: Revolute(20)})
        _, _, expected_top = turntable(mounting=Mounting(angle=57))
        assert moved.named("top").pose.rotation.flatten() == pytest.approx(
            expected_top.pose.rotation.flatten()
        )
        assert moved.named("base").pose == base.pose
        assert model.named("top") is top

    def test_rejects_out_of_range_and_foreign_joint(self, turntable):
        model, _, _ = turntable(motion=MotionRange(Revolute(0), Revolute(90)))
        with pytest.raises(ValueError, match="range"):
            model.posed({model.joints[0]: Revolute(91)})
        other, _, _ = turntable()
        with pytest.raises(ValueError, match="belong"):
            model.posed({other.joints[0]: Revolute(0)})


class TestCheckMotion:
    def test_reports_parts_that_lose_contact_during_motion(self, turntable):
        model, _, top = turntable(motion=MotionRange(Revolute(0), Revolute(180)))
        arm = model.stack(plate(6, 1), on=top, name="arm")
        # Use a smooth support so the resting part does not join the rigid arm.
        cap = model.stack(tile(6, 1), on=arm)
        resting = model.stack(brick(1, 1), on=cap, offset=(4, 0, 0))
        assert not model.floating_placements
        report = model.check_motion(samples=3)
        assert not report.passed
        assert any(resting in failure.placements for failure in report.floating)
        assert all(failure.positions for failure in report.floating)

    def test_static_model_still_checks_ground_support(self):
        model = LegoBuild()
        model.add(brick(1, 1), (10, 0, 0))
        part = model.add(brick(1, 1), (0, 0, 3))
        report = model.check_motion()
        assert report.samples_checked == 1
        assert not report.passed
        assert report.floating[0].placements == (part,)

    def test_intermediate_collision_includes_attached_parts(self, turntable):
        model, _, top = turntable(motion=MotionRange(Revolute(0), Revolute(180)))
        model.stack(plate(6, 1), on=top, rotation=Rotation.DEG_90, name="arm")
        joint = model.joint(top)
        middle = model.posed({joint: Revolute(90)})
        point = middle.named("arm").to_world(Position(2.5, 0, 0))
        obstacle = model.add_raw(brick(1, 1), Pose(translation=point))
        assert not model.posed({joint: Revolute(0)}).colliding_placements
        assert not model.posed({joint: Revolute(180)}).colliding_placements
        report = model.check_motion(samples=3)
        assert not report.passed
        assert any(
            f.positions == ((joint, Revolute(90)),)
            and obstacle in f.placements
            and model.named("arm") in f.placements
            for f in report.collisions
        )

    def test_combined_joint_positions_are_checked(self, turntable):
        left, _, top = turntable(motion=MotionRange(Revolute(0), Revolute(90)))
        left.stack(plate(6, 1), on=top, rotation=Rotation.DEG_90)
        right, _, top = turntable(motion=MotionRange(Revolute(-90), Revolute(0)))
        right.stack(plate(6, 1), on=top, rotation=Rotation.DEG_90)
        outer = LegoBuild()
        outer.add_raw(left)
        outer.add_raw(right, Pose(translation=Position(8, 1, 0)))
        a, b = outer.flattened_joints
        for angle in (0, 45, 90):
            assert not outer.posed({a: Revolute(angle)}).colliding_placements
        for angle in (-90, -45, 0):
            assert not outer.posed({b: Revolute(angle)}).colliding_placements
        report = outer.check_motion(samples=3)
        assert report.samples_checked == 9
        assert report.collisions

    def test_turntable_range_is_clear(self, turntable):
        model, _, _ = turntable(motion=MotionRange(Revolute(-45), Revolute(45)))
        report = model.check_motion(samples=5)
        assert report.passed
        assert report.samples_checked == 5
        assert report.collisions == ()

    def test_sample_budget_does_not_silently_drop_coverage(self, turntable):
        model, _, _ = turntable(motion=MotionRange(Revolute(-45), Revolute(45)))
        with pytest.raises(ValueError, match="budget"):
            model.check_motion(samples=5, max_samples=2)

    def test_sliding_out_of_engagement_is_reported(self):
        model = LegoBuild()
        beam = model.add_raw(Element("7229", Color.WHITE))
        axle = model.connect(
            Element("3705", Color.RED),
            "axle",
            to=beam.find_connector("axle_hole"),
            motion=MotionRange(Prismatic(0), Prismatic(10)),
        )
        report = model.check_motion(samples=3)
        assert not report.passed
        assert any(f.joint is model.joint(axle) for f in report.disconnections)
