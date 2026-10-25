"""Recorded connections and sampled motion of LEGO assemblies.

Mounting fixes the reference pose. A joint moves only after a ``MotionRange``
is assigned. ``posed`` evaluates coordinates without changing the build, and
``check_motion`` checks collisions, floating parts, and connector engagement over
the Cartesian product of sampled coordinates, including zero and both limits.
A clear report describes those samples, not a continuous guarantee. Angles are
degrees and sliding distances are studs.

Rigid groups follow static recorded connections and connector matings in the
reference pose. Sub-model nesting is organizational: disconnected parts do not
move together merely because they share a sub-model. This optional check can flag
motions that would be possible if other, unannotated connections could move.

```python
import bricklayer as bl

model = bl.LegoBuild()
base = model.add(bl.Element("3680", bl.Color.WHITE))
top = model.connect(
    bl.Element("3679", bl.Color.RED), "turntable_pin",
    to=base.find_connector("turntable_socket"),
    mounting=bl.Mounting(angle=20),
    motion=bl.MotionRange(bl.Revolute(-45), bl.Revolute(45)),
)
preview = model.posed({model.joint(top): bl.Revolute(30)})
report = model.check_motion(samples=5)
assert report.passed
```
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, fields, replace
from functools import cached_property
from itertools import product
from math import prod
from typing import TYPE_CHECKING

from ..geometry import (
    Ball,
    Connector,
    JointCoordinates,
    JointKind,
    Pose,
    Revolute,
)
from ..geometry.collision import colliding_pairs
from ..geometry.connections import (
    connectors_mate,
    joint_pose,
    mating_rule,
    same_connector,
)
from ._graph import component_roots
from .placement import Placement, leaf_paths, path_pose

if TYPE_CHECKING:
    from ..parts import Element
    from .build import LegoBuild


@dataclass(frozen=True)
class MotionRange:
    """Inclusive lower/upper coordinates of one kind, each containing zero.

    For example ``MotionRange(Revolute(-45), Revolute(90))`` or
    ``MotionRange(Prismatic(-0.5), Prismatic(0.5))``. Multi-coordinate ranges
    describe every combination, not a diagonal path between the endpoints.
    Equal bounds at zero lock that coordinate.
    """

    lower: JointCoordinates
    upper: JointCoordinates

    def __post_init__(self) -> None:
        if type(self.lower) is not type(self.upper):
            raise ValueError("motion range endpoints must have the same joint kind")
        for f in fields(self.lower):
            if not getattr(self.lower, f.name) <= 0 <= getattr(self.upper, f.name):
                raise ValueError("each motion range must contain zero")
        if isinstance(self.lower, Ball):
            assert isinstance(self.upper, Ball)
            # The rectangular domain must fit inside the swing coordinate chart.
            x = max(abs(self.lower.swing_x), abs(self.upper.swing_x))
            y = max(abs(self.lower.swing_y), abs(self.upper.swing_y))
            Ball(swing_x=x, swing_y=y)

    def contains(self, coordinates: JointCoordinates) -> bool:
        """Whether the coordinate kind and every coordinate lie in this range."""
        return type(coordinates) is type(self.lower) and all(
            getattr(self.lower, f.name)
            <= getattr(coordinates, f.name)
            <= getattr(self.upper, f.name)
            for f in fields(self.lower)
        )

    def sample(
        self, samples: int = 5, *, max_samples: int = 10000
    ) -> tuple[JointCoordinates, ...]:
        """Even samples on every free coordinate, plus zero; bounded by a budget."""
        _positive_integer(samples, "samples", minimum=2)
        _positive_integer(max_samples, "max_samples")
        axes = []
        count = 1
        for f in fields(self.lower):
            lo, hi = getattr(self.lower, f.name), getattr(self.upper, f.name)
            values = (
                [lo]
                if lo == hi
                else [
                    lo * (1 - i / (samples - 1)) + hi * (i / (samples - 1))
                    for i in range(samples)
                ]
            )
            values[0], values[-1] = lo, hi
            values.append(0.0)
            axes.append(sorted(set(values)))
            count *= len(axes[-1])
        if count > max_samples:
            raise ValueError("motion sample budget exceeded")
        return tuple(type(self.lower)(*values) for values in product(*axes))


@dataclass(frozen=True)
class JointEndpoint:
    """One leaf occurrence, its local connector, and its local joint frame.

    ``path`` contains placements from the owning model down to an element. The
    joint frame includes the mounting choice, so both endpoint frames coincide
    at zero even when connector axes oppose or the axle is clocked.
    """

    path: tuple[Placement, ...]
    connector: Connector
    frame: Pose

    @cached_property
    def pose(self) -> Pose:
        """The leaf's reference pose in the owning model."""
        return path_pose(self.path)

    @cached_property
    def world_frame(self) -> Pose:
        """The mounted joint frame in the owning model's coordinates."""
        return self.pose.compose(self.frame)


@dataclass(frozen=True, eq=False)
class Joint:
    """A connection between two occurrences; ``motion=None`` holds it static.

    ``kind`` describes allowed motion; ``motion`` declares its range. Use
    ``model.set_motion`` to change it and ``model.check_motion`` to validate it.
    """

    parent: JointEndpoint
    child: JointEndpoint
    motion: MotionRange | None = None

    def __post_init__(self) -> None:
        if self.motion is not None and self.motion.lower.kind is not self.kind:
            raise ValueError(
                f"motion coordinates must match joint kind {self.kind.name}"
            )

    @property
    def is_mobile(self) -> bool:
        """At least one coordinate has a nonzero declared range."""
        return self.motion is not None and self.motion.lower != self.motion.upper

    @cached_property
    def kind(self) -> JointKind:
        rule = mating_rule(self.parent.connector.type, self.child.connector.type)
        if rule is None:
            raise ValueError("joint connectors cannot mate")
        if rule.joint is not JointKind.CYLINDRICAL:
            return rule.joint
        parent = Placement(self.parent.path[-1].content, self.parent.pose)
        child = Placement(self.child.path[-1].content, self.child.pose)
        if colliding_pairs([parent.collision_body, child.collision_body]):
            raise ValueError(
                "cannot classify a sliding joint whose mounted parts collide"
            )
        frame = self.parent.world_frame
        inverse = frame.inverse
        for direction in (1, -1):
            for angle in (5, 10, 15):
                delta = frame.compose(joint_pose(Revolute(direction * angle))).compose(
                    inverse
                )
                moved = child.transformed(delta)
                if colliding_pairs([parent.collision_body, moved.collision_body]):
                    break
            else:
                return JointKind.CYLINDRICAL
        return JointKind.PRISMATIC

    def with_motion(self, motion: MotionRange | None) -> Joint:
        """A record with validated motion limits, or with motion disabled."""
        return replace(self, motion=motion)


@dataclass(frozen=True)
class MotionCollision:
    """An intersecting pair of reference leaves and the sampled joint positions."""

    positions: tuple[tuple[Joint, JointCoordinates], ...]
    placements: tuple[Placement, Placement]


@dataclass(frozen=True)
class MotionDisconnection:
    """A recorded connection that no longer mates at a sampled configuration."""

    positions: tuple[tuple[Joint, JointCoordinates], ...]
    joint: Joint


@dataclass(frozen=True)
class MotionFloating:
    """Unsupported reference leaves and the sampled joint positions."""

    positions: tuple[tuple[Joint, JointCoordinates], ...]
    placements: tuple[Placement, ...]


@dataclass(frozen=True)
class MotionReport:
    """Collision, support, and engagement results at all requested samples."""

    samples_checked: int
    collisions: tuple[MotionCollision, ...]
    disconnections: tuple[MotionDisconnection, ...]
    floating: tuple[MotionFloating, ...] = ()

    @property
    def passed(self) -> bool:
        """Every sample is collision-free, supported, and retains its connections."""
        return not self.collisions and not self.disconnections and not self.floating


def posed(model: LegoBuild, positions: Mapping[Joint, JointCoordinates]) -> LegoBuild:
    """A flat geometry snapshot at joint coordinates; the source stays unchanged.

    Unspecified coordinates stay at zero. The snapshot has no motion records;
    all coordinates remain relative to the original build. Top-level leaf
    names survive, as with ``flatten``.
    """
    from .build import LegoBuild

    topology = MotionTopology(model)
    placements = topology.evaluate(positions)
    names = {
        name: placements[(p,)] for name, p in model.names.items() if (p,) in placements
    }
    return LegoBuild(placements.values(), names)


def check_motion(
    model: LegoBuild, *, samples: int = 5, max_samples: int = 10000
) -> MotionReport:
    """Check the full sampled product of enabled joint ranges, including rest.

    Tests every leaf pair, including joint endpoints, with the existing inset
    collision meshes. Also checks ground support and recorded connector engagement.
    Unannotated connections stay rigid; this can flag otherwise possible motions.
    A budget overflow raises before any configuration is checked. Closed or
    overconstrained motion graphs raise rather than silently breaking a link.
    """
    from .build import LegoBuild

    _positive_integer(samples, "samples", minimum=2)
    _positive_integer(max_samples, "max_samples")
    topology = MotionTopology(model)
    joints = [j for j in topology.joints if j.motion is not None]
    grids = [
        j.motion.sample(samples, max_samples=max_samples)
        for j in joints
        if j.motion is not None
    ]
    count = prod(len(grid) for grid in grids)
    if count > max_samples:
        raise ValueError(f"motion sample budget exceeded: {count} > {max_samples}")
    reference = tuple(topology.leaves.values())
    collisions = []
    disconnections = []
    floating = []
    for values in product(*grids):
        positions = dict(zip(joints, values))
        placed = topology.evaluate(positions)
        leaves = list(placed.values())
        configuration = tuple(positions.items())
        collisions.extend(
            MotionCollision(configuration, (reference[i], reference[j]))
            for i, j in colliding_pairs([p.collision_body for p in leaves])
        )
        unsupported = LegoBuild(leaves).floating_placements
        if unsupported:
            originals = dict(zip(leaves, reference))
            floating.append(
                MotionFloating(configuration, tuple(originals[p] for p in unsupported))
            )
        for joint in topology.joints:
            a = joint.parent.connector.transformed(placed[joint.parent.path].pose)
            b = joint.child.connector.transformed(placed[joint.child.path].pose)
            if not connectors_mate(a, b):
                disconnections.append(MotionDisconnection(configuration, joint))
    return MotionReport(
        count, tuple(collisions), tuple(disconnections), tuple(floating)
    )


def record_connection(
    model: LegoBuild,
    placement: Placement,
    source: Connector,
    target: Connector,
    motion: MotionRange | None,
) -> Joint | None:
    """Resolve leaf ownership and preserve the mounted endpoint frames."""
    # Each leaf's cached world connectors rule out most leaves cheaply.
    candidates = (
        path
        for path, leaf in zip(leaf_paths(model.placements), model.flattened_placements)
        if any(same_connector(c, target) for c in leaf.connectors)
    )
    parents = _find_endpoints(candidates, target)
    if not parents:
        if motion is not None:
            raise ValueError(
                "motion requires a target connector belonging to this model"
            )
        return None
    children = _find_endpoints(
        leaf_paths((placement,)), source.transformed(placement.pose)
    )
    if len(parents) != 1 or len(children) != 1:
        raise ValueError("joint connector ownership is ambiguous")
    frame = Pose(target.frame, target.position)
    parent, child = (
        JointEndpoint(path, connector, pose.inverse.compose(frame))
        for path, connector, pose in (parents[0], children[0])
    )
    return Joint(parent, child, motion)


def prefixed(joint: Joint, prefix: tuple[Placement, ...]) -> Joint:
    if not prefix:
        return joint
    return _repathed(joint, lambda path: prefix + path)


def remap_joint(
    joint: Joint, paths: Mapping[tuple[Placement, ...], tuple[Placement, ...]]
) -> Joint:
    return _repathed(joint, paths.__getitem__)


def _repathed(
    joint: Joint,
    path_of: Callable[[tuple[Placement, ...]], tuple[Placement, ...]],
) -> Joint:
    return replace(
        joint,
        parent=replace(joint.parent, path=path_of(joint.parent.path)),
        child=replace(joint.child, path=path_of(joint.child.path)),
    )


def _find_endpoints(
    paths: Iterable[tuple[Placement, ...]], target: Connector
) -> list[tuple[tuple[Placement, ...], Connector, Pose]]:
    result = []
    for path in paths:
        pose = path_pose(path)
        for connector in path[-1].content.connectors:
            if same_connector(connector.transformed(pose), target):
                result.append((path, connector, pose))
    return result


@dataclass(frozen=True)
class JointStep:
    """A joint traversed between rigid groups in a kinematic forest."""

    parent: int
    child: int
    joint: Joint
    forward: bool


class MotionTopology:
    """The shared rigid groups and joint traversal used by posing and export."""

    def __init__(self, model: LegoBuild) -> None:
        self.joints = model.flattened_joints
        paths = list(leaf_paths(model.placements))
        if len(paths) != len(set(paths)):
            raise ValueError("motion requires distinct placement occurrences")
        self.leaves = dict(zip(paths, model.flattened_placements))
        indices = {path: i for i, path in enumerate(paths)}
        self.mobile_joints = tuple(j for j in self.joints if j.is_mobile)
        pairs = {
            j: (indices[j.parent.path], indices[j.child.path]) for j in self.joints
        }
        moving_pairs = {frozenset(pairs[j]) for j in self.mobile_joints}
        static = [
            pair for pair in model._mating.pairs if frozenset(pair) not in moving_pairs
        ]
        static.extend(pair for j, pair in pairs.items() if not j.is_mobile)
        self.groups = dict(zip(paths, component_roots(len(paths), static)))
        self.roots, self.steps = _motion_order(self.mobile_joints, self.groups)
        self.frames = {}
        for joint in self.mobile_joints:
            frame = joint.parent.world_frame
            self.frames[joint] = frame, frame.inverse

    def evaluate(
        self, positions: Mapping[Joint, JointCoordinates]
    ) -> dict[tuple[Placement, ...], Placement[Element]]:
        for joint, coordinates in positions.items():
            if joint not in self.joints:
                raise ValueError("joint does not belong to this model")
            if joint.motion is None:
                raise ValueError("joint is static; assign a motion range first")
            if not joint.motion.contains(coordinates):
                raise ValueError(
                    "joint coordinates are outside the motion range or have the wrong kind"
                )
        deltas = dict.fromkeys(self.roots, Pose.IDENTITY)
        for step in self.steps:
            coordinates = positions.get(step.joint)
            motion = Pose.IDENTITY if coordinates is None else joint_pose(coordinates)
            delta = Pose.IDENTITY
            if motion != Pose.IDENTITY:
                frame, inverse = self.frames[step.joint]
                delta = frame.compose(
                    motion if step.forward else motion.inverse
                ).compose(inverse)
            deltas[step.child] = deltas[step.parent].compose(delta)
        return {
            path: leaf
            if deltas[self.groups[path]] == Pose.IDENTITY
            else leaf.transformed(deltas[self.groups[path]])
            for path, leaf in self.leaves.items()
        }


def _motion_order(
    joints: tuple[Joint, ...], groups: Mapping[tuple[Placement, ...], int]
) -> tuple[list[int], list[JointStep]]:
    """Orient a joint forest once, visiting each parent group before its children."""
    edges: dict[int, list[tuple[int, Joint, bool]]] = {}
    parents, children = [], set()
    for joint in joints:
        a, b = groups[joint.parent.path], groups[joint.child.path]
        edges.setdefault(a, []).append((b, joint, True))
        edges.setdefault(b, []).append((a, joint, False))
        parents.append(a)
        children.add(b)
    candidates = [p for p in parents if p not in children] + list(groups.values())
    roots, steps = [], []
    seen: set[int] = set()
    for root in candidates:
        if root in seen:
            continue
        roots.append(root)
        seen.add(root)
        stack: list[tuple[int, Joint | None]] = [(root, None)]
        while stack:
            parent, incoming = stack.pop()
            for child, joint, forward in edges.get(parent, []):
                if joint is incoming:
                    continue
                if child in seen:
                    raise ValueError(
                        "articulation closes a rigid or kinematic loop; loop solving is not supported"
                    )
                seen.add(child)
                steps.append(JointStep(parent, child, joint, forward))
                stack.append((child, joint))
    return roots, steps


def _positive_integer(value: int, name: str, *, minimum: int = 1) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


__all__ = [
    "Joint",
    "JointEndpoint",
    "MotionCollision",
    "MotionDisconnection",
    "MotionFloating",
    "MotionRange",
    "MotionReport",
]
