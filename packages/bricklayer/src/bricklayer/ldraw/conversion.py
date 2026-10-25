"""Converting between BrickLayer coordinates and the LDraw frame (LDU)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache

import numpy as np

from ..geometry import PLATE, Mat3, Pose, Position, Vec3

# LDraw unit conversions.
LDU_PER_STUD = 20
LDU_PER_PLATE = 8
LDU_PER_BRICK = LDU_PER_PLATE * 3

# The orthogonal axis map from the LDraw frame to BrickLayer's (uniform-scale)
# stud frame: ``(x, y, z)_ldu -> (x, z, -y)``.
LDRAW_TO_STUD = Mat3(((1, 0, 0), (0, 0, 1), (0, -1, 0)))

# LDraw color 16 is "the current color": a referenced sub-file inherits the
# color of whatever places it, so its own parts keep the colors they declare.
INHERIT_COLOR = 16

# How far from orthogonal a type-1 matrix may be and still read as a rotation:
# Covers the three-decimal rotations in official minifigure assemblies.
ROTATION_TOLERANCE = 2e-3


@dataclass(frozen=True, slots=True, repr=False)
class LDrawVec(Vec3[float]):
    """A point or offset in the LDraw frame, in LDraw units (LDU).

    LDraw axes differ from BrickLayer's: X is still the width, but **Y is the
    inverted height** (up is negative) and **Z is the depth**.
    """

    @classmethod
    def from_position(cls, position: Position) -> LDrawVec:
        """Convert a BrickLayer position (studs, studs, bricks) to LDraw coordinates."""
        return cls(
            float(position.x) * LDU_PER_STUD,
            -float(position.z) * LDU_PER_PLATE / float(PLATE),
            float(position.y) * LDU_PER_STUD,
        )

    def to_position(self) -> Position:
        """Convert LDraw to BrickLayer coordinates (studs, studs, bricks).

        The result might not be on the stud/plate grid.
        """
        return Position(
            self.x / LDU_PER_STUD,
            self.z / LDU_PER_STUD,
            -self.y / LDU_PER_PLATE * PLATE,
        )


@cache
def rotation_to_ldraw(rotation: Mat3) -> Mat3:
    """``rotation`` conjugated from BrickLayer axes into LDraw axes.

    Cached: a build uses a handful of distinct rotations across thousands of
    placements, and both the collision path and the writer come through here.
    Callers must treat the result as shared and copy before mutating.
    """
    return LDRAW_TO_STUD.transpose @ rotation @ LDRAW_TO_STUD


def pose_to_ldraw(pose: Pose) -> tuple[np.ndarray, np.ndarray]:
    """``pose`` as a ``(rotation, translation)`` pair acting on LDraw coordinates."""
    return (
        rotation_to_ldraw(pose.rotation).array.copy(),
        LDrawVec.from_position(pose.translation).array,
    )


def pose_from_ldraw(rotation: Mat3, translation: LDrawVec) -> Pose:
    """The BrickLayer pose an LDraw ``(rotation, translation)`` pair describes.

    The inverse of :func:`pose_to_ldraw`, taking the two parts of a type-1
    line as the reader parses them rather than as arrays.

    A matrix within :data:`ROTATION_TOLERANCE` of a rotation, as rounded
    decimals leave one, is snapped to the nearest rotation.

    Raises:
        ValueError: if ``rotation`` is not a proper rotation. A type-1 line may
            carry a reflection or a scale, and a :class:`Pose` may not.
    """
    return Pose(
        _nearest_rotation(LDRAW_TO_STUD @ rotation @ LDRAW_TO_STUD.transpose),
        translation.to_position(),
    )


def pose_from_type1(numbers: Sequence[float]) -> Pose:
    """The pose a type-1 line's 12 numbers (``x y z a b c d e f g h i``) describe.

    Raises:
        ValueError: as :func:`pose_from_ldraw` does.
    """
    return pose_from_ldraw(Mat3.from_flattened(numbers[3:]), LDrawVec(*numbers[:3]))


def _nearest_rotation(matrix: Mat3) -> Mat3:
    """``matrix`` snapped onto the nearest rotation, if it is close to one."""
    a = matrix.array
    drift = np.abs(a.T @ a - np.eye(3)).max()
    if drift <= 1e-12 or drift > ROTATION_TOLERANCE or np.linalg.det(a) <= 0:
        return matrix
    u, _, vt = np.linalg.svd(a)
    return Mat3.from_array(u @ vt)


def format_ldu(value: float) -> str:
    """Format an LDraw number: integers stay bare, fixed-pose floats get up to 6 decimals."""
    rounded = float(round(value, 6))
    return str(int(rounded)) if rounded.is_integer() else f"{rounded:.6f}".rstrip("0")
