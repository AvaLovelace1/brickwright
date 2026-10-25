"""Model transformations.

These functions return new objects, leaving their inputs intact.
Use `translate_to_ground(model)` to put the lowest physical extent on z=0.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import fields
from typing import overload

from ..geometry import (
    Connector,
    JointCoordinates,
    LegoGeometry,
    Mat3,
    Pose,
    Position,
    Vec3,
)
from ..geometry.linalg import Axis, Scalar, reflection_matrix
from ..geometry.spatial import as_position
from ..parts.catalog import HANDEDNESS_AXIS
from ..parts.element import Element
from .articulation import Joint, JointEndpoint, MotionRange, remap_joint
from .build import LegoBuild
from .placement import Placement, leaf_paths, path_pose


def flatten(model: LegoBuild) -> LegoBuild:
    """Return a new model containing only leaf element placements.

    Preserves names of existing top-level leaves; drops build-step markers.
    """
    leaves = model.flattened_placements
    already_a_leaf = set(leaves)
    names = {
        name: placement
        for name, placement in model.names.items()
        if placement in already_a_leaf
    }
    paths = {path: (leaf,) for path, leaf in zip(leaf_paths(model.placements), leaves)}
    return type(model)(
        leaves, names, joints=[remap_joint(j, paths) for j in model.flattened_joints]
    )


def translate_to_ground(model: LegoBuild) -> LegoBuild:
    """Translate ``model`` so its lowest volume rests on z = 0. Returns a new :class:`LegoBuild`.

    This can help you ground a floating model.
    """
    return translate(model, Position(0, 0, -model._ground))


def translate(
    model: LegoBuild, delta: Position | tuple[float, float, float]
) -> LegoBuild:
    """Translate ``model`` by ``(dx, dy, dz)`` -- x/y in studs, z in bricks. Returns a new :class:`LegoBuild`."""
    delta = as_position(delta)
    if delta == Position.ZERO:
        return model.copy()
    shift = Pose(translation=delta)
    return _rebuild(model, lambda p: p.transformed(shift))


@overload
def mirror(geometry: LegoBuild, axis: Axis, plane: Scalar) -> LegoBuild: ...


@overload
def mirror(geometry: Placement, axis: Axis, plane: Scalar) -> Placement: ...


@overload
def mirror(geometry: Element, axis: Axis, plane: Scalar = 0) -> Element: ...


def mirror(
    geometry: LegoBuild | Placement | Element, axis: Axis, plane: Scalar = 0
) -> LegoBuild | Placement | Element:
    """Reflect ``geometry`` across the plane ``plane`` on ``axis`` -- ``x =
    plane`` for ``Axis.X`` (left/right), ``y = plane`` for ``Axis.Y``
    (front/back). ``plane`` is in studs. Returns a new object of the same kind.

    Models and placements reflect positions and orientations, keeping names,
    colors, grounding, and shared sub-models. To mirror a model where it stands,
    use its alignment-box center on ``axis`` as the plane.

    Handed elements swap for their opposite-handed part; for a standalone
    element, ``axis`` and ``plane`` are ignored. Parts without a counterpart,
    or with differently measured counterparts, retain their original shape.
    """
    return _mirrored(geometry, axis, plane, {})


def _mirrored(
    geometry: LegoBuild | Placement | Element,
    axis: Axis,
    plane: Scalar,
    done: dict[LegoBuild, LegoBuild],
) -> LegoBuild | Placement | Element:
    """:func:`mirror`, dispatched on what it was handed, carrying ``done``."""
    if isinstance(geometry, Element):
        return geometry.mirrored
    if isinstance(geometry, Placement):
        return _mirrored_model(LegoBuild([geometry]), axis, plane, done).placements[0]
    return _mirrored_model(geometry, axis, plane, done)


def _mirrored_model(
    model: LegoBuild, axis: Axis, plane: Scalar, done: dict[LegoBuild, LegoBuild]
) -> LegoBuild:
    """``model`` reflected across ``plane`` on ``axis``, reflecting each
    sub-model once.

    ``done`` memoizes by model identity: a sub-model's reflection is fixed by
    the model and the axis alone -- it is always taken about its own origin, so
    it cannot depend on where the model was placed -- and a sub-assembly
    reached by several paths comes back shared, keeping the LDraw writer (which
    keys sub-files by identity) to one sub-file for it. Only the outermost call
    reflects about ``plane``, so ``done`` need not key on it.
    """
    if model in done:
        return done[model]
    flip = reflection_matrix(axis)
    handedness_flip = reflection_matrix(HANDEDNESS_AXIS)
    world_offset = _axis_vector(axis, 2 * plane)

    def reflect(p: Placement) -> Placement:
        content = _mirrored(p.content, axis, 0, done)
        rotation = p.pose.rotation
        placed = p.pose.translation.to_stud_units()
        # A swapped part arrives reflected through the handedness plane. A part
        # with no counterpart stands in as its own image through that plane,
        # its box reflected onto itself there: exact for an achiral part, while
        # a handed one keeps its hand.
        inner = handedness_flip if isinstance(content, Element) else flip
        if content is p.content:
            placed = rotation @ _in_place_offset(content) + placed
        return Placement(
            content,
            Pose(
                flip @ rotation @ inner,
                Position.from_stud_units(flip @ placed + world_offset),
            ),
        )

    done[model] = result = _rebuild(
        model,
        reflect,
        joint_transform=lambda joint, paths: _mirror_joint(
            joint, paths, flip, world_offset
        ),
    )
    return result


def _in_place_offset(geometry: LegoGeometry) -> Vec3:
    """The shift reflecting ``geometry``'s alignment box onto itself through
    the handedness plane: twice the box's center along that axis.

    Used for a part with no mirror image, so its box lands where its
    reflection's would and only the geometry inside keeps its handedness.
    """
    lo, hi = geometry.alignment_box
    i = HANDEDNESS_AXIS.value
    return _axis_vector(HANDEDNESS_AXIS, lo[i] + hi[i])


def _axis_vector(axis: Axis, length: Scalar) -> Vec3:
    """``length`` as a vector along ``axis`` alone."""
    shift = [0.0, 0.0, 0.0]
    shift[axis.value] = float(length)
    return Vec3(*shift)


def _mirror_joint(
    joint: Joint,
    paths: Mapping[tuple[Placement, ...], tuple[Placement, ...]],
    reflection: Mat3,
    offset: Vec3,
) -> Joint:
    # Reflecting a frame changes handedness. Reverse its transverse x axis
    # to restore a proper rotation, and change coordinate signs accordingly.
    transverse = reflection_matrix(Axis.X)

    def reflected(p: Position) -> Position:
        return Position.from_stud_units(reflection @ p.to_stud_units() + offset)

    def endpoint(old: JointEndpoint) -> JointEndpoint:
        path = paths[old.path]
        body = path_pose(path)
        world = old.world_frame
        frame = Pose(
            reflection @ world.rotation @ transverse, reflected(world.translation)
        )
        connector = old.connector.transformed(old.pose)
        mirrored = Connector(
            connector.type,
            reflected(connector.position),
            reflection @ connector.axis,
            reflection @ connector.side,
            connector.length,
        ).transformed(body.inverse)
        return JointEndpoint(path, mirrored, body.inverse.compose(frame))

    def bounds(lower: JointCoordinates, upper: JointCoordinates) -> JointCoordinates:
        return type(lower)(
            **{
                f.name: -getattr(upper, f.name)
                if f.name in ("angle", "swing_y", "twist")
                else getattr(lower, f.name)
                for f in fields(lower)
            }
        )

    motion = joint.motion
    if motion is not None:
        motion = MotionRange(
            bounds(motion.lower, motion.upper), bounds(motion.upper, motion.lower)
        )
    return Joint(endpoint(joint.parent), endpoint(joint.child), motion)


def _rebuild(
    model: LegoBuild,
    transform: Callable[[Placement], Placement],
    *,
    joint_transform: Callable[
        [Joint, Mapping[tuple[Placement, ...], tuple[Placement, ...]]], Joint
    ] = remap_joint,
) -> LegoBuild:
    """A copy of ``model`` with ``transform`` applied to every placement, keeping
    the names pointed at the transformed parts and the step markers in place.

    ``transform`` must be applied one-to-one, in order, or the markers -- plain
    placement counts -- would no longer point at the same places.
    """
    new = {p: transform(p) for p in model.placements}
    names = {name: new[p] for name, p in model.names.items()}
    placements = tuple(new[p] for p in model.placements)
    paths = dict(zip(leaf_paths(model.placements), leaf_paths(placements)))
    return type(model)(
        placements,
        names,
        model.step_markers,
        joints=(joint_transform(j, paths) for j in model.joints),
    )


#: The model-to-model transforms, in API-reference order; both the generated
#: docs and ``__all__`` read this list.
BUILD_TRANSFORMATIONS = [translate, translate_to_ground, flatten, mirror]

__all__ = [transform.__name__ for transform in BUILD_TRANSFORMATIONS]
