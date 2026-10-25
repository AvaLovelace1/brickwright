"""Geometry and coordinate conventions.

The coordinate system is right-handed: +x points left, +y back, and +z up.
The ground is z=0. Width/depth are in studs; height is in bricks.
`PLATE` is one third of a brick. One brick is 6/5 of a stud: use
`Position.to_stud_units()` for uniform units when doing geometric calculations.

`add` and `stack` require integer x/y, z in whole plates, and quarter-turn
`Rotation`s about z. Use `connect` for sideways or offset connections;
`add_raw(content, pose)` accepts an arbitrary pose without grid checks.

### Local frames

Grid-marked parts are seated at their connector-defined bottom-center: a 4x2
brick's alignment box spans `(-2, -1, 0)` to `(2, 1, 1)`. For other parts,
inspect their connectors and boxes. A sub-model keeps the frame it was built in.
`add` rotates content, then anchors its rotated alignment box at the requested
position. `add_raw` applies the pose directly, without this re-anchoring.
`placement.pose.translation` is the placed local origin, which can differ from
the alignment-box corner passed to `add`.

The bounding box measures physical extent, including overhangs. The alignment
box determines grid placement and stacking; its rules are documented on
`LegoGeometry.alignment_box`. A model exposes only connectors not already mated
inside it, so covering its studs can change its alignment box.

Collisions use the parts' actual meshes. Touching or correctly mated surfaces
are allowed; intersecting parts are reported by `colliding_placements`.
"""

from .base import LegoGeometry
from .connections import (
    Ball,
    Connector,
    ConnectorType,
    Cylindrical,
    Fixed,
    JointCoordinates,
    JointKind,
    Mounting,
    Prismatic,
    Revolute,
)
from .linalg import Axis, Mat3, Vec3, rotation_about
from .spatial import (
    PLATE,
    Anchor,
    Cuboid,
    Direction,
    HeightLike,
    Pose,
    Position,
    Rotation,
    to_bricks,
    to_exact_height,
    to_plates,
)

__all__ = [
    "PLATE",
    "Anchor",
    "Axis",
    "Ball",
    "Connector",
    "ConnectorType",
    "Cuboid",
    "Cylindrical",
    "Direction",
    "Fixed",
    "HeightLike",
    "JointCoordinates",
    "JointKind",
    "LegoGeometry",
    "Mat3",
    "Mounting",
    "Pose",
    "Position",
    "Prismatic",
    "Revolute",
    "Rotation",
    "Vec3",
    "rotation_about",
    "to_bricks",
    "to_exact_height",
    "to_plates",
]
