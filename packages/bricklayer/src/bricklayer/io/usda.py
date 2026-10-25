"""Export LEGO geometry and articulated rigid bodies as self-contained USDA.

``write_usda(model, "model.usda")`` writes a Z-up asset in meters and kilograms.
The packaged BrickNet meshes supply geometry and collider inputs, including
their small collision inset; printed decorations are not included. Colors use
USD Preview Surface materials. No LDraw installation or OpenUSD runtime is
required to export.

Static connector groups become single rigid bodies. Enabled revolute and
prismatic joints retain their mounted frames and limits. Supported joint trees
receive articulation roots; cylindrical joints with both coordinates enabled
use regular D6 constraints between those trees. Ball joints use D6 swing/twist
limits. A two-axis ball swing box is approximated by enclosing pyramidal limits
with a warning; the original coordinate bounds are retained as metadata.

Collider cooking uses ``convexDecomposition``. Density defaults to a nominal
1050 kg/m³ and is configurable; resulting mass and inertia are estimates from
the simulator's cooked colliders, not measured LEGO part properties. Adjacent
body collisions use USD's default joint filtering. Motion validation remains
an explicit ``model.check_motion()`` call before export.

Set ``fixed_base=True`` to anchor each disconnected mechanism to the asset's
frame, so anchors follow its placement in a host stage. The host owns the
physics scene and gravity. Motion loops are rejected, as they are by
BrickLayer's motion evaluator.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, fields
from hashlib import sha256
from pathlib import Path

import numpy as np

from ..colors import Color, Finish, linear_rgb
from ..geometry import Ball, Cylindrical, Mat3, Pose, Position, Prismatic, Revolute
from ..ldraw.colors import LDrawColor
from ..ldraw.conversion import LDRAW_TO_STUD, LDU_PER_STUD
from ..ldraw.partdata import record
from ..modeling._graph import component_roots
from ..modeling.articulation import Joint, MotionTopology
from ..modeling.build import LegoBuild
from ..modeling.placement import Placement
from ..parts import Element

_METERS_PER_STUD = 0.008
_FLOAT32_MAX = float(np.finfo(np.float32).max)
_ROOT = "/Model"
_AXES = ("transX", "transY", "transZ", "rotX", "rotY", "rotZ")
# PhysX D6 uses x as its twist axis. Its y/z swing axes are BrickLayer's x/y.
_D6_FRAME = Pose(Mat3(((0, 1, 0), (0, 0, 1), (1, 0, 0))))


class UsdaExportWarning(UserWarning):
    """A simulator limit approximates the authored BrickLayer motion domain."""


def to_usda(
    model: LegoBuild, *, fixed_base: bool = False, density: float = 1050.0
) -> str:
    """Return self-contained USDA geometry, materials, rigid bodies, and joints.

    ``fixed_base`` anchors each mechanism's root; otherwise the asset floats.
    ``density`` is positive kg/m³, used for simulator-derived mass and inertia.
    Part names survive as display names and source indices/ids as metadata.
    Names must be valid UTF-8 and cannot contain NUL characters.

    Raises ``ValueError`` for invalid density, motion loops, values outside USD's
    32-bit physics range, or D6 angular bounds outside PhysX's supported domain.
    Missing packaged meshes raise ``MeshUnavailable``; no geometry is silently
    omitted.
    """
    if not math.isfinite(density) or density <= 0:
        raise ValueError("density must be finite and positive")
    density = _float32(density, preserve_nonzero=True)
    topology = MotionTopology(model)
    bodies = _bodies(topology)
    specs = [_joint_spec(j, bodies, topology) for j in topology.mobile_joints]
    roots = _articulation_roots(topology, specs)
    colors = sorted(
        {p.content.color for p in topology.leaves.values()}, key=_material_name
    )
    parts = sorted({p.content.ldraw_id for p in topology.leaves.values()})
    prototypes = {part: f"part_{i}" for i, part in enumerate(parts)}
    writer = _Writer()
    writer.line(
        '#usda 1.0\n(\n    defaultPrim = "Model"\n    upAxis = "Z"\n    metersPerUnit = 1\n    kilogramsPerUnit = 1\n)'
    )
    with writer.prim("Xform", "Model", metadata=('kind = "component"',)):
        with writer.prim("Scope", "Materials"):
            for color in colors:
                _material(writer, color)
        with writer.prim("Scope", "Geometry"):
            for part in parts:
                _mesh(writer, part, prototypes[part])
        with writer.prim("Scope", "Bodies"):
            for group, body in bodies.items():
                _body(
                    writer,
                    model,
                    body,
                    prototypes,
                    density,
                    articulation_root=group in roots
                    and not (fixed_base and group in topology.roots),
                )
        with writer.prim("Scope", "Joints"):
            for i, spec in enumerate(specs):
                _joint(writer, f"joint_{i}", spec)
            if fixed_base:
                for group in topology.roots:
                    _anchor(writer, bodies[group], articulation_root=group in roots)
    return "\n".join(writer.lines) + "\n"


def write_usda(
    model: LegoBuild,
    path: str | Path,
    *,
    fixed_base: bool = False,
    density: float = 1050.0,
) -> None:
    """Write ``model`` to a UTF-8 USDA file; options match ``to_usda``.

    Export validation completes before opening the destination file.
    """
    text = to_usda(model, fixed_base=fixed_base, density=density)
    Path(path).write_text(text, encoding="utf-8")


@dataclass
class _Body:
    name: str
    pose: Pose
    members: list[tuple[int, tuple[Placement, ...], Placement[Element]]]

    @property
    def path(self) -> str:
        return f"{_ROOT}/Bodies/{self.name}"


@dataclass(frozen=True)
class _JointSpec:
    source: Joint
    schema: str
    groups: tuple[int, int]
    bodies: tuple[_Body, _Body]
    frames: tuple[Pose, Pose]
    limits: dict[str, tuple[float, float]]
    excluded: bool = False
    approximate: bool = False


def _bodies(topology: MotionTopology) -> dict[int, _Body]:
    bodies: dict[int, _Body] = {}
    for i, (path, leaf) in enumerate(topology.leaves.items()):
        group = topology.groups[path]
        if group not in bodies:
            bodies[group] = _Body(f"body_{len(bodies)}", leaf.pose, [])
        bodies[group].members.append((i, path, leaf))
    return bodies


def _joint_spec(
    joint: Joint, bodies: dict[int, _Body], topology: MotionTopology
) -> _JointSpec:
    assert joint.motion is not None
    lo, hi = joint.motion.lower, joint.motion.upper
    groups = topology.groups[joint.parent.path], topology.groups[joint.child.path]
    parent, child = (bodies[g] for g in groups)
    frames = tuple(
        body.pose.inverse.compose(end.world_frame)
        for body, end in zip((parent, child), (joint.parent, joint.child))
    )
    schema = "PhysicsJoint"
    excluded = approximate = False
    match lo, hi:
        case Revolute(angle=low), Revolute(angle=high):
            schema, limits = "PhysicsRevoluteJoint", {"angle": (low, high)}
        case Prismatic(offset=low), Prismatic(offset=high):
            schema, limits = (
                "PhysicsPrismaticJoint",
                {
                    "offset": (
                        float(low) * _METERS_PER_STUD,
                        float(high) * _METERS_PER_STUD,
                    )
                },
            )
        case Cylindrical(), Cylindrical():
            linear = (
                float(lo.offset) * _METERS_PER_STUD,
                float(hi.offset) * _METERS_PER_STUD,
            )
            angular = (lo.angle, hi.angle)
            if lo.offset == hi.offset:
                schema, limits = "PhysicsRevoluteJoint", {"angle": angular}
            elif lo.angle == hi.angle:
                schema, limits = "PhysicsPrismaticJoint", {"offset": linear}
            else:
                limits = {"transX": linear, "rotX": angular}
                excluded = True
        case Ball(), Ball():
            limits, approximate = _ball_limits(lo, hi)
        case _:
            raise TypeError("mobile joint has no supported motion coordinates")
    if schema == "PhysicsJoint":
        _check_twist(limits["rotX"])
        frames = (frames[0].compose(_D6_FRAME), frames[1].compose(_D6_FRAME))
        limits = {axis: limits.get(axis, (0.0, 0.0)) for axis in _AXES}
    limits = {axis: _float_limits(bounds) for axis, bounds in limits.items()}
    if schema == "PhysicsJoint":
        _check_twist(limits["rotX"])
        if any(
            low <= -180 or high >= 180 for low, high in (limits["rotY"], limits["rotZ"])
        ):
            raise ValueError(
                "USDA ball swing bounds must stay below 180 degrees after 32-bit conversion"
            )
        if approximate:
            warnings.warn(
                "USDA ball swing limits use an enclosing pyramidal approximation; original bounds are retained in metadata",
                UsdaExportWarning,
                stacklevel=3,
            )
    return _JointSpec(
        joint,
        schema,
        groups,
        (parent, child),
        (frames[0], frames[1]),
        limits,
        excluded,
        approximate,
    )


def _ball_limits(lo: Ball, hi: Ball) -> tuple[dict[str, tuple[float, float]], bool]:
    x = max(abs(lo.swing_x), abs(hi.swing_x))
    y = max(abs(lo.swing_y), abs(hi.swing_y))
    if math.hypot(x, y) >= 180:
        raise ValueError("USDA ball swing bounds must stay below 180 degrees")
    return {
        "rotX": (lo.twist, hi.twist),
        "rotY": (_swing_limit(lo.swing_x, y), _swing_limit(hi.swing_x, y)),
        "rotZ": (_swing_limit(lo.swing_y, x), _swing_limit(hi.swing_y, x)),
    }, x > 0 and y > 0


def _check_twist(bounds: tuple[float, float]) -> None:
    if bounds[0] <= -360 or bounds[1] >= 360:
        raise ValueError(
            "USDA D6 twist bounds must be strictly between -360 and 360 degrees"
        )


def _swing_limit(value: float, other: float) -> float:
    if value == 0:
        return 0.0
    angle = math.hypot(value, other)
    half = math.radians(angle) / 2
    # PhysX measures each swing using the quaternion's quarter-angle tangent.
    return math.degrees(
        4 * math.atan2(value / angle * math.sin(half), 1 + math.cos(half))
    )


def _articulation_roots(topology: MotionTopology, joints: list[_JointSpec]) -> set[int]:
    supported = [spec.groups for spec in joints if not spec.excluded]
    connected = component_roots(len(topology.leaves), supported)
    used = {group for pair in supported for group in pair}
    order = [*topology.roots, *(step.child for step in topology.steps)]
    first: dict[int, int] = {}
    for group in order:
        if group in used:
            first.setdefault(connected[group], group)
    return set(first.values())


def _body(
    writer: _Writer,
    model: LegoBuild,
    body: _Body,
    prototypes: dict[str, str],
    density: float,
    *,
    articulation_root: bool,
) -> None:
    apis = ["PhysicsRigidBodyAPI", "PhysicsMassAPI"]
    if articulation_root:
        apis.append("PhysicsArticulationRootAPI")
    with writer.prim("Xform", body.name, apis=apis):
        _transform(writer, body.pose)
        writer.line("bool physics:rigidBodyEnabled = true")
        writer.line(f"float physics:density = {_number(density)}")
        for index, path, leaf in body.members:
            _instance(writer, model, index, path, leaf, body, prototypes)


def _anchor(writer: _Writer, body: _Body, *, articulation_root: bool) -> None:
    apis = ("PhysicsArticulationRootAPI",) if articulation_root else ()
    with writer.prim("PhysicsFixedJoint", f"anchor_{body.name}", apis=apis):
        writer.line(f"rel physics:body0 = <{_ROOT}>")
        writer.line(f"rel physics:body1 = <{body.path}>")
        _joint_frame(writer, 0, body.pose)
        _joint_frame(writer, 1, Pose.IDENTITY)


def _mesh(writer: _Writer, part_id: str, name: str) -> None:
    part = record(part_id)
    mesh = part.collision_mesh
    pose = part.ldraw_to_element_pose
    points = mesh.vertices @ LDRAW_TO_STUD.array.T / LDU_PER_STUD
    points = (
        points @ pose.rotation.array.T + pose.translation.to_stud_units().array
    ) * _METERS_PER_STUD
    if not len(points) or not len(mesh.faces):
        raise ValueError(f"part {part_id!r} has an empty mesh")
    if (
        not np.isfinite(points).all()
        or mesh.faces.min() < 0
        or mesh.faces.max() >= len(points)
    ):
        raise ValueError(f"part {part_id!r} has invalid mesh geometry")
    with writer.prim("Mesh", name, abstract=True):
        writer.line('uniform token subdivisionScheme = "none"')
        writer.line('uniform token orientation = "rightHanded"')
        writer.line("bool doubleSided = true")
        writer.line(
            "point3f[] points = [" + ", ".join(_vector(p) for p in points) + "]"
        )
        writer.line(
            "int[] faceVertexCounts = [" + ", ".join("3" for _ in mesh.faces) + "]"
        )
        writer.line(
            "int[] faceVertexIndices = ["
            + ", ".join(str(int(i)) for i in mesh.faces.flat)
            + "]"
        )
        writer.line(
            f"float3[] extent = [{_vector(points.min(axis=0))}, {_vector(points.max(axis=0))}]"
        )


def _instance(
    writer: _Writer,
    model: LegoBuild,
    index: int,
    path: tuple[Placement, ...],
    leaf: Placement[Element],
    body: _Body,
    prototypes: dict[str, str],
) -> None:
    part = leaf.content
    metadata = (
        f"prepend references = <{_ROOT}/Geometry/{prototypes[part.ldraw_id]}>",
        f"displayName = {_string(_display_name(model, path))}",
    )
    with writer.prim(
        "Mesh",
        f"part_{index}",
        metadata=metadata,
        apis=("PhysicsCollisionAPI", "PhysicsMeshCollisionAPI", "MaterialBindingAPI"),
    ):
        _transform(writer, body.pose.inverse.compose(leaf.pose))
        writer.line('uniform token physics:approximation = "convexDecomposition"')
        writer.line("bool physics:collisionEnabled = true")
        writer.line(
            f"rel material:binding = <{_ROOT}/Materials/{_material_name(part.color)}>"
        )
        writer.line(
            f"color3f[] primvars:displayColor = [{_vector(linear_rgb(part.color.rgb))}]"
        )
        writer.line(f"custom string bricklayer:partId = {_string(part.ldraw_id)}")
        writer.line(f"custom int bricklayer:colorId = {part.color.ldraw_id}")
        writer.line(f"custom int bricklayer:placementIndex = {index}")


def _display_name(model: LegoBuild, path: tuple[Placement, ...]) -> str:
    names = []
    for p in path:
        name = model.name_of(p)
        if name is not None:
            names.append(name)
        if isinstance(p.content, LegoBuild):
            model = p.content
    return "/".join(names) if names else repr(path[-1].content)


def _material_name(color: Color | LDrawColor) -> str:
    suffix = ""
    if isinstance(color, LDrawColor):
        suffix = "_" + sha256(repr(color).encode()).hexdigest()[:16]
    return f"color_{color.ldraw_id}{suffix}"


def _material(writer: _Writer, color: Color | LDrawColor) -> None:
    name = _material_name(color)
    rgb = linear_rgb(color.rgb)
    opacity = {
        Finish.TRANSPARENT: 0.3,
        Finish.OPALESCENT: 0.65,
        Finish.GLITTER: 0.7,
    }.get(color.finish, 1.0)
    if isinstance(color, LDrawColor):
        opacity = color.alpha / 255
    metallic = {Finish.METALLIC: 0.7, Finish.CHROME: 1.0, Finish.PEARL: 0.3}.get(
        color.finish, 0.0
    )
    with writer.prim("Material", name):
        writer.line(
            f"token outputs:surface.connect = <{_ROOT}/Materials/{name}/Surface.outputs:surface>"
        )
        with writer.prim("Shader", "Surface"):
            writer.line('uniform token info:id = "UsdPreviewSurface"')
            writer.line(f"color3f inputs:diffuseColor = {_vector(rgb)}")
            writer.line(f"float inputs:opacity = {_number(opacity)}")
            writer.line(f"float inputs:metallic = {_number(metallic)}")
            writer.line(f"float inputs:roughness = {0.1 if metallic else 0.3}")
            writer.line("token outputs:surface")


def _joint(writer: _Writer, name: str, spec: _JointSpec) -> None:
    apis = (
        [f"PhysicsLimitAPI:{axis}" for axis in _AXES]
        if spec.schema == "PhysicsJoint"
        else []
    )
    with writer.prim(spec.schema, name, apis=apis):
        for side, body in enumerate(spec.bodies):
            writer.line(f"rel physics:body{side} = <{body.path}>")
            _joint_frame(writer, side, spec.frames[side])
        if spec.excluded:
            writer.line("bool physics:excludeFromArticulation = true")
        if spec.schema == "PhysicsJoint":
            for axis, (low, high) in spec.limits.items():
                if low == high:
                    low, high = 1, -1
                writer.line(f"float limit:{axis}:physics:low = {_number(low)}")
                writer.line(f"float limit:{axis}:physics:high = {_number(high)}")
        else:
            low, high = next(iter(spec.limits.values()))
            writer.line('uniform token physics:axis = "Z"')
            writer.line(f"float physics:lowerLimit = {_number(low)}")
            writer.line(f"float physics:upperLimit = {_number(high)}")
        motion = spec.source.motion
        assert motion is not None
        writer.line(
            f"custom string bricklayer:jointKind = {_string(motion.lower.kind.name)}"
        )
        writer.line(
            f"custom bool bricklayer:approximatedLimits = {'true' if spec.approximate else 'false'}"
        )
        writer.line(
            "custom string[] bricklayer:coordinates = "
            + _string([f.name for f in fields(motion.lower)])
        )
        for label, endpoint in [
            ("lowerLimits", motion.lower),
            ("upperLimits", motion.upper),
        ]:
            writer.line(
                f"custom double[] bricklayer:{label} = ["
                + ", ".join(
                    _number(getattr(endpoint, f.name)) for f in fields(endpoint)
                )
                + "]"
            )


def _joint_frame(writer: _Writer, side: int, pose: Pose) -> None:
    writer.line(
        f"point3f physics:localPos{side} = {_vector(_meters(pose.translation))}"
    )
    writer.line(f"quatf physics:localRot{side} = {_vector(_quaternion(pose.rotation))}")


def _meters(position: Position) -> np.ndarray:
    return position.to_stud_units().array * _METERS_PER_STUD


def _quaternion(rotation: Mat3) -> tuple[float, ...]:
    m = rotation.array
    # The largest quaternion component gives a well-conditioned extraction,
    # including half turns where the trace-based formula would divide by zero.
    candidates = [
        1 + np.trace(m),
        1 + 2 * m[0, 0] - np.trace(m),
        1 + 2 * m[1, 1] - np.trace(m),
        1 + 2 * m[2, 2] - np.trace(m),
    ]
    largest = int(np.argmax(candidates))
    q = np.zeros(4)
    q[largest] = math.sqrt(max(0.0, candidates[largest])) / 2
    scale = 4 * q[largest]
    if largest == 0:
        q[1:] = [
            (m[2, 1] - m[1, 2]) / scale,
            (m[0, 2] - m[2, 0]) / scale,
            (m[1, 0] - m[0, 1]) / scale,
        ]
    else:
        i = largest - 1
        j, k = (i + 1) % 3, (i + 2) % 3
        q[0] = (m[k, j] - m[j, k]) / scale
        q[j + 1] = (m[j, i] + m[i, j]) / scale
        q[k + 1] = (m[k, i] + m[i, k]) / scale
    q /= np.linalg.norm(q)
    if q[0] < 0:
        q = -q
    return tuple(float(v) for v in q)


def _transform(writer: _Writer, pose: Pose) -> None:
    matrix = np.eye(4)
    matrix[:3, :3] = pose.rotation.array.T
    matrix[3, :3] = _meters(pose.translation)
    for coordinate in matrix[3, :3]:
        _float32(coordinate)
    writer.line(
        "matrix4d xformOp:transform = ("
        + ", ".join(_vector(row, single=False) for row in matrix)
        + ")"
    )
    writer.line('uniform token[] xformOpOrder = ["xformOp:transform"]')


def _number(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("USDA values must be finite")
    return format(float(value), ".17g")


def _float32(value: float, *, preserve_nonzero: bool = False) -> float:
    if not math.isfinite(value) or abs(value) > _FLOAT32_MAX:
        raise ValueError("USDA value is outside the finite 32-bit float range")
    narrowed = float(np.float32(value))
    if preserve_nonzero and value != 0 and narrowed == 0:
        raise ValueError("USDA value underflows the 32-bit float range")
    return narrowed


def _float_limits(bounds: tuple[float, float]) -> tuple[float, float]:
    low, high = bounds
    lower = _float32(low, preserve_nonzero=True)
    upper = _float32(high, preserve_nonzero=True)
    # Never shrink the allowed domain when the engine narrows limits to float.
    if lower > low:
        lower = float(np.nextafter(np.float32(lower), np.float32(-math.inf)))
    if upper < high:
        upper = float(np.nextafter(np.float32(upper), np.float32(math.inf)))
    return lower, upper


def _vector(values, *, single: bool = True) -> str:
    return (
        "("
        + ", ".join(
            format(_float32(value), ".9g") if single else _number(value)
            for value in values
        )
        + ")"
    )


def _string(value: str | Sequence[str]) -> str:
    if not isinstance(value, str):
        return "[" + ", ".join(_string(item) for item in value) + "]"
    if "\x00" in value:
        raise ValueError("USDA strings cannot contain NUL characters")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("USDA strings must be valid UTF-8") from error
    escaped = []
    for character in value:
        if character in ('"', "\\"):
            escaped.append("\\" + character)
        elif ord(character) < 32 or ord(character) == 127:
            escaped.append(f"\\x{ord(character):02x}")
        else:
            escaped.append(character)
    return '"' + "".join(escaped) + '"'


class _Writer:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.indent = 0

    def line(self, value: str) -> None:
        self.lines.append("    " * self.indent + value)

    @contextmanager
    def prim(
        self,
        schema: str,
        name: str,
        *,
        apis: Sequence[str] = (),
        metadata: Sequence[str] = (),
        abstract: bool = False,
    ) -> Generator[None]:
        declaration = f"{'class' if abstract else 'def'} {schema} {_string(name)}"
        meta = ([f"prepend apiSchemas = {_string(list(apis))}"] if apis else []) + list(
            metadata
        )
        if meta:
            self.line(declaration + " (")
            self.indent += 1
            for item in meta:
                self.line(item)
            self.indent -= 1
            self.line(")")
        else:
            self.line(declaration)
        self.line("{")
        self.indent += 1
        yield
        self.indent -= 1
        self.line("}")


__all__ = ["UsdaExportWarning", "to_usda", "write_usda"]
