"""USDA geometry and physics, inspected with the OpenUSD parser and schemas."""

import math
from importlib import import_module
from typing import Any

import numpy as np
import pytest

from bricklayer import (
    Ball,
    Color,
    Cylindrical,
    Element,
    LegoBuild,
    MotionRange,
    Mounting,
    Pose,
    Position,
    Prismatic,
    Revolute,
    Vec3,
    brick,
    from_ldraw,
    rotation_about,
    to_usda,
    write_usda,
)
from bricklayer.io.usda import UsdaExportWarning
from bricklayer.ldraw.conversion import LDRAW_TO_STUD
from bricklayer.ldraw.partdata import record

# OpenUSD exposes its schema classes through compiled bindings without stubs.
Gf: Any = import_module("pxr.Gf")
Sdf: Any = import_module("pxr.Sdf")
Usd: Any = import_module("pxr.Usd")
UsdGeom: Any = import_module("pxr.UsdGeom")
UsdPhysics: Any = import_module("pxr.UsdPhysics")
UsdShade: Any = import_module("pxr.UsdShade")
UsdValidation: Any = import_module("pxr.UsdValidation")


def stage(model, **kwargs):
    layer = Sdf.Layer.CreateAnonymous("model.usda")
    assert layer.ImportFromString(to_usda(model, **kwargs))
    result = Usd.Stage.Open(layer)
    assert not result.GetCompositionErrors()
    return result


def bodies(value):
    return [p for p in value.Traverse() if p.HasAPI(UsdPhysics.RigidBodyAPI)]


def joints(value):
    return [UsdPhysics.Joint(p) for p in value.Traverse() if p.IsA(UsdPhysics.Joint)]


def assert_frames_coincide(value, joint):
    frames = []
    for side in (0, 1):
        targets = getattr(joint, f"GetBody{side}Rel")().GetTargets()
        body = (
            UsdGeom.Xformable(
                value.GetPrimAtPath(targets[0])
            ).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            if targets
            else Gf.Matrix4d(1)
        )
        position = getattr(joint, f"GetLocalPos{side}Attr")().Get()
        rotation = getattr(joint, f"GetLocalRot{side}Attr")().Get()
        local = Gf.Matrix4d().SetRotate(Gf.Quatd(rotation))
        local.SetTranslateOnly(Gf.Vec3d(position))
        frames.append(np.array(local * body))
    np.testing.assert_allclose(frames[0], frames[1], atol=1e-7)


def world_vertices(mesh):
    transform = mesh.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    return np.array(
        [transform.Transform(Gf.Vec3d(p)) for p in mesh.GetPointsAttr().Get()]
    )


def expected_vertices(leaf):
    source = record(leaf.content.ldraw_id).collision_mesh
    body = leaf.collision_body
    return (
        (source.vertices @ body.rotation.T + body.translation)
        @ LDRAW_TO_STUD.array.T
        * 0.0004
    )


def apply_joint_motion(value, joint, motion):
    frames = []
    for side in (0, 1):
        frame = Gf.Matrix4d().SetRotate(
            Gf.Quatd(getattr(joint, f"GetLocalRot{side}Attr")().Get())
        )
        frame.SetTranslateOnly(
            Gf.Vec3d(getattr(joint, f"GetLocalPos{side}Attr")().Get())
        )
        frames.append(frame)
    parent = UsdGeom.Xformable(value.GetPrimAtPath(joint.GetBody0Rel().GetTargets()[0]))
    child = UsdGeom.Xformable(value.GetPrimAtPath(joint.GetBody1Rel().GetTargets()[0]))
    child.MakeMatrixXform().Set(
        frames[1].GetInverse() * motion * frames[0] * parent.GetLocalTransformation()
    )


@pytest.fixture
def articulated_turntable(turntable):
    def build(*, mobile=True, angle=37):
        model, _, _ = turntable(
            mounting=Mounting(angle=angle),
            motion=MotionRange(Revolute(-45), Revolute(90)) if mobile else None,
        )
        return model

    return build


class TestToUsda:
    def test_imported_color_scopes_have_distinct_materials_and_preserve_alpha(self):
        model = from_ldraw(
            "0 !COLOUR Red CODE 999 VALUE #FF0000 EDGE #333333 ALPHA 64\n"
            "1 999 0 0 0 1 0 0 0 1 0 0 0 1 3005.dat\n"
            "0 !COLOUR Blue CODE 999 VALUE #0000FF EDGE #333333\n"
            "1 999 40 0 0 1 0 0 0 1 0 0 0 1 3005.dat\n"
        )
        value = stage(model)
        materials = [p for p in value.Traverse() if p.IsA(UsdShade.Material)]
        assert len(materials) == 2
        opacities = [
            UsdShade.Shader(p.GetChild("Surface")).GetInput("opacity").Get()
            for p in materials
        ]
        assert sorted(opacities) == pytest.approx([64 / 255, 1])
        bindings = [
            p.GetRelationship("material:binding").GetTargets()[0]
            for p in value.Traverse()
            if p.HasAttribute("bricklayer:placementIndex")
        ]
        assert len(set(bindings)) == 2

    def test_referenced_fixed_asset_follows_its_placement(self):
        model = LegoBuild()
        model.add_raw(Element("3005", Color.RED), Pose(translation=Position(2, 0, 1)))
        asset = Sdf.Layer.CreateAnonymous("asset.usda")
        asset.ImportFromString(to_usda(model, fixed_base=True))
        host = Usd.Stage.CreateInMemory()
        placed = UsdGeom.Xform.Define(host, "/Placed")
        placed.GetPrim().GetReferences().AddReference(asset.identifier)
        placed.AddTranslateOp().Set(Gf.Vec3d(1, 2, 3))
        placed.AddRotateZOp().Set(35)
        (joint,) = joints(host)
        assert_frames_coincide(host, joint)
        assert joint.GetBody0Rel().GetTargets() == [Sdf.Path("/Placed")]
        descriptions = UsdPhysics.UsdPhysicsLoadStageFromPrimRange(
            host, [Sdf.Path("/Placed")]
        )
        fixed = descriptions[UsdPhysics.ObjectType.FixedJoint][1][0]
        assert fixed.isValid
        assert not fixed.body0
        body = UsdGeom.Xformable(host.GetPrimAtPath(fixed.body1))
        expected = body.ComputeLocalToWorldTransform(
            Usd.TimeCode.Default()
        ).ExtractTranslation()
        np.testing.assert_allclose(fixed.localPose0Position, expected, atol=1e-6)

    def test_referencing_assets_preserves_the_host_physics_scene(
        self, articulated_turntable
    ):
        asset = Sdf.Layer.CreateAnonymous("asset.usda")
        asset.ImportFromString(to_usda(articulated_turntable()))
        host = Usd.Stage.CreateInMemory()
        physics = UsdPhysics.Scene.Define(host, "/Physics")
        physics.CreateGravityMagnitudeAttr(4.0)
        for name in ("A", "B"):
            UsdGeom.Xform.Define(
                host, "/" + name
            ).GetPrim().GetReferences().AddReference(asset.identifier)
        scenes = [p for p in host.Traverse() if p.IsA(UsdPhysics.Scene)]
        assert [p.GetPath() for p in scenes] == [Sdf.Path("/Physics")]
        assert physics.GetGravityMagnitudeAttr().Get() == 4.0
        assert len(bodies(host)) == 4

    @pytest.mark.parametrize("density", [1e100, 1e-100])
    def test_density_must_be_representable_by_usd_float(
        self, articulated_turntable, density
    ):
        with pytest.raises(ValueError, match="32-bit"):
            to_usda(articulated_turntable(), density=density)

    def test_body_positions_must_fit_the_physics_numeric_range(self):
        model = LegoBuild()
        model.add_raw(
            Element("3005", Color.RED), Pose(translation=Position(1e50, 0, 0))
        )
        with pytest.raises(ValueError, match="32-bit"):
            to_usda(model)

    @pytest.mark.parametrize("limit", [1e100, 1e-100])
    def test_joint_limits_must_be_representable_by_usd_float(
        self, articulated_turntable, limit
    ):
        model = articulated_turntable()
        model.set_motion(model.joints[0], MotionRange(Revolute(0), Revolute(limit)))
        with pytest.raises(ValueError, match="32-bit"):
            to_usda(model)

    def test_twist_limits_are_valid_after_float32_conversion(self):
        model = LegoBuild()
        hole = model.add_raw(Element("3700", Color.WHITE))
        model.connect(
            Element("3705", Color.RED),
            "axle",
            to=hole.find_connector("pin_hole"),
            motion=MotionRange(Cylindrical(-0.1, 0), Cylindrical(0.1, 360 - 1e-9)),
        )
        with pytest.raises(ValueError, match="twist bounds"):
            to_usda(model)

    def test_ball_swing_limits_are_valid_after_float32_conversion(self):
        model = LegoBuild()
        socket = model.add_raw(Element("14418", Color.WHITE))
        model.connect(
            Element("22890", Color.RED),
            "towball",
            to=socket.find_connector("towball_socket"),
            motion=MotionRange(Ball(), Ball(swing_x=180 - 1e-9)),
        )
        with pytest.raises(ValueError, match="swing bounds"):
            to_usda(model)

    def test_original_limit_metadata_preserves_double_precision(
        self, articulated_turntable
    ):
        limit = 1.2345678901234567
        model = articulated_turntable()
        model.set_motion(
            model.joints[0], MotionRange(Revolute(-limit), Revolute(limit))
        )
        value = stage(model)
        (joint,) = joints(value)
        assert joint.GetPrim().GetAttribute("bricklayer:lowerLimits").Get()[0] == -limit
        assert joint.GetPrim().GetAttribute("bricklayer:upperLimits").Get()[0] == limit

    def test_physics_limits_enclose_the_authored_range_after_rounding(
        self, articulated_turntable
    ):
        limit = 1 + 1e-9
        model = articulated_turntable()
        model.set_motion(
            model.joints[0], MotionRange(Revolute(-limit), Revolute(limit))
        )
        value = stage(model)
        joint = UsdPhysics.RevoluteJoint(joints(value)[0])
        assert joint.GetLowerLimitAttr().Get() <= -limit
        assert joint.GetUpperLimitAttr().Get() >= limit

    @pytest.mark.parametrize("ball", [False, True])
    def test_d6_motion_matches_bricklayer_coordinates(self, ball):
        model = LegoBuild()
        if ball:
            base = model.add_raw(Element("14418", Color.WHITE))
            model.connect(
                Element("22890", Color.RED),
                "towball",
                to=base.find_connector("towball_socket"),
                motion=MotionRange(Ball(-20, -25, -30), Ball(20, 25, 30)),
            )
            with pytest.warns(UsdaExportWarning):
                value = stage(model)
            coordinates = Ball(10, 15, 20)
            swing = Gf.Matrix4d().SetRotate(
                Gf.Rotation(Gf.Vec3d(0, 10, 15), math.hypot(10, 15))
            )
            twist = Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(1, 0, 0), 20))
            motion = twist * swing
        else:
            base = model.add_raw(Element("3700", Color.WHITE))
            model.connect(
                Element("3705", Color.RED),
                "axle",
                to=base.find_connector("pin_hole"),
                motion=MotionRange(Cylindrical(-0.2, -45), Cylindrical(0.2, 45)),
            )
            value = stage(model)
            coordinates = Cylindrical(0.1, 30)
            motion = Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(1, 0, 0), 30))
            motion.SetTranslateOnly(Gf.Vec3d(0.0008, 0, 0))
        apply_joint_motion(value, joints(value)[0], motion)
        expected = model.posed({model.joints[0]: coordinates})
        for prim in value.Traverse():
            if prim.IsA(UsdGeom.Mesh):
                index = prim.GetAttribute("bricklayer:placementIndex").Get()
                np.testing.assert_allclose(
                    world_vertices(UsdGeom.Mesh(prim)),
                    expected_vertices(expected.placements[index]),
                    atol=1e-8,
                )

    def test_joint_motion_in_usd_frames_matches_bricklayer(self, articulated_turntable):
        model = articulated_turntable()
        value = stage(model)
        (joint,) = joints(value)
        motion = Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(0, 0, 1), 30))
        apply_joint_motion(value, joint, motion)
        posed = model.posed({model.joints[0]: Revolute(30)})
        for prim in value.Traverse():
            if prim.IsA(UsdGeom.Mesh):
                index = prim.GetAttribute("bricklayer:placementIndex").Get()
                np.testing.assert_allclose(
                    world_vertices(UsdGeom.Mesh(prim)),
                    expected_vertices(posed.placements[index]),
                    atol=1e-8,
                )

    def test_mixed_joint_asset_has_valid_physics_descriptions(
        self, articulated_turntable
    ):
        model = articulated_turntable(angle=0)
        beam = model.stack(Element("3700", Color.BLUE), on=model.named("top"))
        model.connect(
            Element("3705", Color.RED),
            "axle",
            to=beam.find_connector("pin_hole"),
            motion=MotionRange(Cylindrical(-0.1, -30), Cylindrical(0.1, 30)),
        )
        value = stage(model)
        descriptors = UsdPhysics.UsdPhysicsLoadStageFromPrimRange(
            value, [value.GetDefaultPrim().GetPath()]
        )
        assert all(
            description.isValid
            for _, descriptions in descriptors.values()
            for description in descriptions
        )
        assert len(bodies(value)) == 3
        assert len(joints(value)) == 2

    def test_nested_repeated_assemblies_export_independent_joints(
        self, articulated_turntable
    ):
        inner = articulated_turntable()
        model = LegoBuild()
        model.add_raw(inner)
        model.add_raw(inner, Pose(translation=Position(5, 0, 0)))
        value = stage(model)
        assert len(bodies(value)) == 4
        assert len(joints(value)) == 2
        for joint in joints(value):
            assert_frames_coincide(value, joint)
        assert (
            sum(p.HasAPI(UsdPhysics.ArticulationRootAPI) for p in value.Traverse()) == 2
        )

    def test_deleting_a_joint_endpoint_leaves_no_dangling_usd_relationship(
        self, articulated_turntable
    ):
        model = articulated_turntable()
        model.remove("top")
        value = stage(model)
        assert len(bodies(value)) == 1
        assert not joints(value)

    def test_d6_twist_bounds_must_fit_physx(self):
        model = LegoBuild()
        hole = model.add_raw(Element("3700", Color.WHITE))
        model.connect(
            Element("3705", Color.RED),
            "axle",
            to=hole.find_connector("pin_hole"),
            motion=MotionRange(Cylindrical(-0.1, -360), Cylindrical(0.1, 360)),
        )
        with pytest.raises(ValueError, match="twist bounds"):
            to_usda(model)

    def test_empty_model_has_valid_stage_metadata(self):
        value = stage(LegoBuild())
        assert value.GetDefaultPrim().GetPath() == Sdf.Path("/Model")
        assert UsdGeom.GetStageUpAxis(value) == "Z"
        assert UsdGeom.GetStageMetersPerUnit(value) == 1
        assert bodies(value) == []

    def test_statically_connected_bricks_form_one_body(self):
        model = LegoBuild()
        base = model.add(brick(2, 2, color=Color.RED), name="base")
        model.stack(brick(2, 2, color=Color.BLUE), on=base)
        value = stage(model, density=1040)
        assert len(bodies(value)) == 1
        meshes = [UsdGeom.Mesh(p) for p in value.Traverse() if p.IsA(UsdGeom.Mesh)]
        assert len(meshes) == 2
        assert UsdPhysics.MassAPI(bodies(value)[0]).GetDensityAttr().Get() == 1040
        assert not joints(value)
        for mesh in meshes:
            assert mesh.GetSubdivisionSchemeAttr().Get() == "none"
            assert mesh.GetPrim().HasAPI(UsdPhysics.CollisionAPI)
            assert (
                UsdPhysics.MeshCollisionAPI(mesh).GetApproximationAttr().Get()
                == "convexDecomposition"
            )
            material, _ = UsdShade.MaterialBindingAPI(mesh).ComputeBoundMaterial()
            assert material

    def test_mesh_offsets_axes_and_meters_match_bricklayer(self):
        model = LegoBuild()
        part = model.add_raw(
            Element("973", Color.RED),
            Pose(rotation_about(Vec3(0.6, 0, 0.8), 37), Position(2, 3, 4)),
        )
        value = stage(model)
        mesh = next(UsdGeom.Mesh(p) for p in value.Traverse() if p.IsA(UsdGeom.Mesh))
        transform = mesh.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        actual = np.array(
            [transform.Transform(Gf.Vec3d(p)) for p in mesh.GetPointsAttr().Get()]
        )
        source = record(part.content.ldraw_id).collision_mesh
        body = part.collision_body
        ldraw = source.vertices @ body.rotation.T + body.translation
        expected = ldraw @ LDRAW_TO_STUD.array.T * 0.0004
        np.testing.assert_allclose(actual, expected, atol=1e-8)
        assert len(mesh.GetFaceVertexIndicesAttr().Get()) == 3 * len(source.faces)

    def test_mounted_connections_are_rigid_until_motion_is_enabled(
        self, articulated_turntable
    ):
        assert len(bodies(stage(articulated_turntable(mobile=False)))) == 1
        assert len(bodies(stage(articulated_turntable()))) == 2

    def test_revolute_limits_and_mounted_frames(self, articulated_turntable):
        value = stage(articulated_turntable())
        (joint,) = joints(value)
        hinge = UsdPhysics.RevoluteJoint(joint)
        assert hinge
        assert hinge.GetAxisAttr().Get() == "Z"
        assert hinge.GetLowerLimitAttr().Get() == -45
        assert hinge.GetUpperLimitAttr().Get() == 90
        assert_frames_coincide(value, joint)
        assert (
            sum(p.HasAPI(UsdPhysics.ArticulationRootAPI) for p in value.Traverse()) == 1
        )

    def test_prismatic_mounting_and_linear_limits(self):
        model = LegoBuild()
        hole = model.add_raw(Element("7229", Color.WHITE))
        model.connect(
            Element("3705", Color.RED),
            "axle",
            to=hole.find_connector("axle_hole"),
            mounting=Mounting(angle=90, flip=True, offset=0.1),
            motion=MotionRange(Prismatic(-0.2), Prismatic(0.3)),
        )
        value = stage(model)
        (joint,) = joints(value)
        slider = UsdPhysics.PrismaticJoint(joint)
        assert slider
        assert slider.GetLowerLimitAttr().Get() == pytest.approx(-0.0016)
        assert slider.GetUpperLimitAttr().Get() == pytest.approx(0.0024)
        assert_frames_coincide(value, joint)

    def test_cylindrical_joint_is_a_regular_d6_constraint(self):
        model = LegoBuild()
        hole = model.add_raw(Element("3700", Color.WHITE))
        model.connect(
            Element("3705", Color.RED),
            "axle",
            to=hole.find_connector("pin_hole"),
            motion=MotionRange(Cylindrical(-0.1, -30), Cylindrical(0.2, 45)),
        )
        value = stage(model)
        (joint,) = joints(value)
        assert joint.GetPrim().GetTypeName() == "PhysicsJoint"
        assert joint.GetExcludeFromArticulationAttr().Get()
        limits = {
            api.GetLowAttr().GetName().split(":")[1]: (
                api.GetLowAttr().Get(),
                api.GetHighAttr().Get(),
            )
            for api in UsdPhysics.LimitAPI.GetAll(joint.GetPrim())
        }
        assert limits["transX"] == pytest.approx((-0.0008, 0.0016))
        assert limits["rotX"] == (-30, 45)
        assert all(
            limits[a][0] > limits[a][1] for a in ["transY", "transZ", "rotY", "rotZ"]
        )
        assert_frames_coincide(value, joint)

    def test_ball_limits_preserve_original_coordinates_and_warn_about_approximation(
        self,
    ):
        model = LegoBuild()
        socket = model.add_raw(Element("14418", Color.WHITE))
        model.connect(
            Element("22890", Color.RED),
            "towball",
            to=socket.find_connector("towball_socket"),
            motion=MotionRange(Ball(-20, -10, -30), Ball(20, 10, 30)),
        )
        with pytest.warns(UsdaExportWarning, match="ball"):
            value = stage(model)
        (joint,) = joints(value)
        assert list(joint.GetPrim().GetAttribute("bricklayer:lowerLimits").Get()) == [
            -20,
            -10,
            -30,
        ]
        assert list(joint.GetPrim().GetAttribute("bricklayer:upperLimits").Get()) == [
            20,
            10,
            30,
        ]
        assert UsdPhysics.LimitAPI(joint.GetPrim(), "rotX").GetLowAttr().Get() == -30
        swing = Gf.Rotation(Gf.Vec3d(2, 1, 0), math.sqrt(500)).GetQuat()
        physx_swing_y = math.degrees(
            4 * math.atan2(swing.GetImaginary()[0], 1 + swing.GetReal())
        )
        assert UsdPhysics.LimitAPI(
            joint.GetPrim(), "rotY"
        ).GetHighAttr().Get() == pytest.approx(physx_swing_y)
        assert_frames_coincide(value, joint)

    def test_fixed_base_anchors_the_mechanism(self, articulated_turntable):
        value = stage(articulated_turntable(), fixed_base=True)
        fixed = [j for j in joints(value) if j.GetPrim().IsA(UsdPhysics.FixedJoint)]
        assert len(fixed) == 1
        assert fixed[0].GetBody0Rel().GetTargets() == [Sdf.Path("/Model")]
        assert fixed[0].GetBody1Rel().GetTargets()
        assert fixed[0].GetPrim().HasAPI(UsdPhysics.ArticulationRootAPI)
        assert_frames_coincide(value, fixed[0])

    @pytest.mark.parametrize("name", ["", 'a "quoted" / bracket] name\n雪'])
    def test_names_are_data_and_do_not_break_usda_syntax(self, name):
        model = LegoBuild()
        model.add_raw(Element("3005", Color.RED), name=name)
        value = stage(model)
        mesh = next(p for p in value.Traverse() if p.IsA(UsdGeom.Mesh))
        assert mesh.GetDisplayName() == name
        assert to_usda(model) == to_usda(model)

    @pytest.mark.parametrize(
        "name", ["bell\x07face", "one\x01abc", "literal\\u0007", "unit\x1fF"]
    )
    def test_control_characters_in_display_names_round_trip(self, name):
        model = LegoBuild()
        model.add_raw(Element("3005", Color.RED), name=name)
        value = stage(model)
        mesh = next(p for p in value.Traverse() if p.IsA(UsdGeom.Mesh))
        assert mesh.GetDisplayName() == name

    @pytest.mark.parametrize("density", [0, -1, float("nan"), float("inf")])
    def test_density_must_be_finite_and_positive(self, density):
        with pytest.raises(ValueError, match="density"):
            to_usda(LegoBuild(), density=density)

    def test_openusd_physics_validators_accept_the_asset(self, articulated_turntable):
        value = stage(articulated_turntable(), fixed_base=True)
        names = [
            "usdGeomValidators:StageMetadataChecker",
            "usdValidation:CompositionErrorTest",
            "usdPhysicsValidators:RigidBodyChecker",
            "usdPhysicsValidators:PhysicsJointChecker",
            "usdPhysicsValidators:ArticulationChecker",
        ]
        validators = UsdValidation.ValidationRegistry().GetOrLoadValidatorsByName(names)
        assert len(validators) == len(names)
        assert not UsdValidation.ValidationContext(validators).Validate(value)


class TestWriteUsda:
    @pytest.mark.parametrize("name", ["bad\ud800name", "nul\x00name"])
    def test_unrepresentable_names_preserve_an_existing_file(self, tmp_path, name):
        model = LegoBuild()
        model.add_raw(Element("3005", Color.RED), name=name)
        path = tmp_path / "model.usda"
        path.write_text("original")
        with pytest.raises(ValueError):
            write_usda(model, path)
        assert path.read_text() == "original"

    def test_missing_geometry_preserves_an_existing_file(self, tmp_path, monkeypatch):
        from bricklayer.io import usda
        from bricklayer.ldraw.meshes import MeshUnavailable

        model = LegoBuild()
        model.add_raw(Element("3005", Color.RED))
        path = tmp_path / "model.usda"
        path.write_text("original")

        def unavailable(part_id):
            raise MeshUnavailable(f"missing mesh for {part_id}")

        monkeypatch.setattr(usda, "record", unavailable)
        with pytest.raises(MeshUnavailable, match="3005"):
            write_usda(model, path)
        assert path.read_text() == "original"

    def test_file_round_trips_through_openusd(self, articulated_turntable, tmp_path):
        path = tmp_path / "turntable.usda"
        model = articulated_turntable()
        write_usda(model, path)
        assert path.read_text() == to_usda(model)
        assert Usd.Stage.Open(str(path))

    def test_validation_failure_preserves_an_existing_file(self, tmp_path):
        path = tmp_path / "model.usda"
        path.write_text("original")
        with pytest.raises(ValueError, match="density"):
            write_usda(LegoBuild(), path, density=-1)
        assert path.read_text() == "original"
