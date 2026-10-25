"""Core geometric primitives and unit conventions for BrickLayer.

**Coordinate system.** BrickLayer uses a right-handed coordinate system:

- ``x`` (**width**) increases from right to left,
- ``y`` (**depth**) increases from front to back,
- ``z`` (**height**) increases from ground to sky.

The ground (baseplate) is the ``z = 0`` plane. Rotations
(:class:`Rotation`) are counter-clockwise about the vertical (+z) axis as
seen from above.

**Units.** Horizontal placement is in **studs**; height is in **bricks**. A
*plate* is one third of a brick, so heights are given in multiples of
``PLATE`` (``1/3`` of a brick) when sub-brick precision is needed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from functools import cached_property
from math import floor
from typing import ClassVar, overload

from .._mixins import ReprEnum
from .linalg import Mat3, Scalar, Vec3, VecType, all_close, vec_max, vec_min

PLATES_PER_BRICK = 3
# One plate, expressed in bricks.
PLATE = 1 / PLATES_PER_BRICK
STUDS_PER_BRICK = 6 / 5
BRICKS_PER_STUD = 1 / STUDS_PER_BRICK

# Coordinates within this many studs of a grid value count as on it.
BUILD_TOLERANCE = 0.01

# Anything acceptable as a height in bricks. Normalized to an exact `Fraction` on the
# way in, so ``5/3``, ``1 + 2/3``, and ``Fraction(5, 3)`` all name the same height.
HeightLike = Scalar | Fraction


def to_plates(bricks: HeightLike, *, round_down: bool = False) -> int:
    """Convert a height/elevation in bricks to integer plate-heights.

    If ``round_down`` is True, the result is rounded down to the nearest plate;
    otherwise, ``bricks`` must be a multiple of 1/3 (1 plate).
    """
    plates = bricks * PLATES_PER_BRICK
    if round_down:
        return floor(plates + BUILD_TOLERANCE)
    if not _is_whole(plates):
        raise ValueError(
            f"height must be a multiple of 1/3 brick (a plate), got {bricks}"
        )
    return round(plates)


def _is_whole(value: HeightLike) -> bool:
    return abs(value - round(value)) <= BUILD_TOLERANCE


def to_bricks(plates: int) -> float:
    """Convert integer plate-heights to a height in bricks."""
    return plates / PLATES_PER_BRICK


def to_exact_height(value: HeightLike) -> Fraction:
    """Narrow a height in bricks to an exact multiple of 1/3 brick (one plate).

    ``value`` must already be a multiple of a plate, within tolerance, or ``ValueError`` is raised.
    """
    return Fraction(to_plates(value), PLATES_PER_BRICK)


def to_whole_studs(value: Scalar, *, round_down: bool = False) -> int:
    """Narrow a horizontal coordinate in studs to ``int``.

    If ``round_down`` is True, the result is rounded *down* to the nearest stud;
    otherwise, ``value`` must be a whole number of studs.
    """
    if round_down:
        return floor(value + BUILD_TOLERANCE)
    if not _is_whole(value):
        raise ValueError(f"expected a whole number of studs, got {value}")
    return round(value)


@dataclass(frozen=True, slots=True, repr=False)
class Position(Vec3[Scalar]):
    """A position or offset in BrickLayer coordinates: ``x``/``y`` in studs, ``z`` (height) in *bricks*."""

    ZERO: ClassVar[Position]

    @classmethod
    def from_stud_units(cls, v: Vec3 | Sequence[Scalar]) -> Position:
        """Convert a vector in uniform stud units to a position in BrickLayer coordinates."""
        if len(v) != 3:
            raise ValueError(f"expected a 3-component vector, got {v}")
        return cls(v[0], v[1], v[2] / STUDS_PER_BRICK)

    def to_stud_units(self) -> Vec3:
        """This position as a plain vector in uniform stud units.

        Scales z by 6/5 for lengths, rotations, and other geometric calculations.
        """
        return Vec3(self.x, self.y, self.z * STUDS_PER_BRICK)

    def align_to_grid(self) -> Position:
        """Return a new position aligned to the integer build grid, flooring each
        coordinate to the grid (``x``/``y`` to whole studs, ``z`` to whole plates)."""
        return Position(
            to_whole_studs(self.x, round_down=True),
            to_whole_studs(self.y, round_down=True),
            to_bricks(to_plates(self.z, round_down=True)),
        )

    def is_grid_aligned(self) -> bool:
        """Check if the position is on the integer build grid (within tolerance)."""
        return (
            _is_whole(self.x)
            and _is_whole(self.y)
            and _is_whole(self.z * PLATES_PER_BRICK)
        )


Position.ZERO = Position(0, 0, 0)


def as_position(position: Position | tuple[float, float, float]) -> Position:
    """Normalize BrickLayer coordinates without changing units or snapping to a grid."""
    return position if isinstance(position, Position) else Position(*position)


def require_grid_position(position: Position | tuple[float, float, float]) -> Position:
    """Validate that ``position`` is on the integer build grid."""
    position = as_position(position)
    if not position.is_grid_aligned():
        raise ValueError(f"placement must be on the integer grid, got {position}")
    return position.align_to_grid()


class Anchor(ReprEnum):
    """Which corner, edge midpoint, or center of a footprint pins to a position."""

    FRONT_RIGHT = (0, 0)  # min corner == default
    FRONT = (1, 0)
    FRONT_LEFT = (2, 0)
    RIGHT = (0, 1)
    CENTER = (1, 1)
    LEFT = (2, 1)
    BACK_RIGHT = (0, 2)
    BACK = (1, 2)
    BACK_LEFT = (2, 2)

    def offset(self, width: int, depth: int) -> tuple[int, int]:
        """Offset from a ``width`` x ``depth`` footprint's min corner to this anchor.

        In whole studs. An even extent's center floors toward the min
        (front/right) side, so a 4x2 footprint's CENTER is ``(1, 0)``.
        """
        half_x, half_y = self.value
        return (width - 1) * half_x // 2, (depth - 1) * half_y // 2


class Direction(ReprEnum):
    """A face direction on the grid, valued as a unit displacement vector.

    ``UP``/``DOWN`` are the common stud / antistud facings; the lateral
    directions describe side connectors (e.g. the studs on a bracket).
    ``LEFT`` is +x, ``BACK`` is +y.
    """

    UP = Vec3(0, 0, 1)
    DOWN = Vec3(0, 0, -1)
    BACK = Vec3(0, 1, 0)
    FRONT = Vec3(0, -1, 0)
    LEFT = Vec3(1, 0, 0)
    RIGHT = Vec3(-1, 0, 0)


_DIRECTION_BY_VECTOR = {direction.value: direction for direction in Direction}
_QUARTER_TURN_MATRICES = (
    Mat3.IDENTITY,
    Mat3(((0, -1, 0), (1, 0, 0), (0, 0, 1))),
    Mat3(((-1, 0, 0), (0, -1, 0), (0, 0, 1))),
    Mat3(((0, 1, 0), (-1, 0, 0), (0, 0, 1))),
)
_QUARTER_TURN_INDEX = {m: i for i, m in enumerate(_QUARTER_TURN_MATRICES)}


class Rotation(ReprEnum):
    """A rotation about the vertical axis, in 90-degree steps.

    The value is the number of quarter-turns counter-clockwise when viewed from
    above (down the +Z axis).

    The "facing" aliases ``FRONT``/``RIGHT``/``BACK``/``LEFT`` name where the
    side that usually faces front (-y) ends up: ``BACK`` is a half turn,
    ``LEFT`` a counter-clockwise quarter turn (which sends the front side to
    the left), and ``RIGHT`` the opposite quarter turn.
    """

    DEG_0 = 0
    DEG_90 = 1
    DEG_180 = 2
    DEG_270 = 3
    # Facing aliases (same members under friendlier names).
    FRONT = 0
    LEFT = 1
    BACK = 2
    RIGHT = 3

    @property
    def quarter_turns(self) -> int:
        """The number of 90-degree counter-clockwise turns (0 to 3)."""
        return self.value

    def __add__(self, other: Rotation) -> Rotation:
        return Rotation((self.value + other.value) % 4)

    def __sub__(self, other: Rotation) -> Rotation:
        return Rotation((self.value - other.value) % 4)

    def __neg__(self) -> Rotation:
        return Rotation(-self.value % 4)

    def __mul__(self, n: int) -> Rotation:
        return Rotation(self.value * n % 4)

    __rmul__ = __mul__

    @property
    def matrix(self) -> Mat3:
        """Return the 3x3 matrix representing this rotation."""
        return _QUARTER_TURN_MATRICES[self.quarter_turns]

    @classmethod
    def from_matrix(cls, matrix: Mat3) -> Rotation:
        """The :class:`Rotation` whose matrix is ``matrix``.

        Raises:
            ValueError: if ``matrix`` is not a quarter-turn about the vertical axis.
        """
        try:
            return cls(_QUARTER_TURN_INDEX[matrix])
        except KeyError:
            raise ValueError(
                f"{matrix!r} is not a quarter-turn about the vertical axis"
            ) from None

    def rotate(self, v: VecType) -> VecType:
        """Apply this rotation about the vertical (+z) axis to a vector."""
        return self.matrix @ v


def to_direction(v: Vec3) -> Direction | None:
    """The grid :class:`Direction` whose vector is ``v``, or ``None``."""
    return _DIRECTION_BY_VECTOR.get(v)


@dataclass(frozen=True, slots=True)
class Pose:
    """An arbitrary rotation-then-translation in BrickLayer coordinates."""

    rotation: Mat3 = Mat3.IDENTITY
    translation: Position = Position.ZERO

    IDENTITY: ClassVar[Pose]

    def __post_init__(self):
        if self.rotation in _QUARTER_TURN_INDEX:
            return
        if abs(self.rotation.det() - 1) > BUILD_TOLERANCE or not all_close(
            self.rotation @ self.rotation.transpose, Mat3.IDENTITY
        ):
            raise ValueError(
                f"rotation must be a valid rotation matrix, got {self.rotation!r}"
            )

    @classmethod
    def from_rotation(cls, rotation: Rotation) -> Pose:
        """A pose that applies ``rotation`` (a quarter-turn about z) with no translation."""
        return cls(rotation.matrix)

    def compose(self, other: Pose) -> Pose:
        """The pose applying ``other`` first, then ``self``."""
        if self == Pose.IDENTITY:
            return other
        if other == Pose.IDENTITY:
            return self
        return Pose(self.rotation @ other.rotation, self.apply(other.translation))

    @overload
    def apply(self, p: Position) -> Position: ...

    @overload
    def apply(self, p: Sequence[Position]) -> tuple[Position, ...]: ...

    def apply(
        self, p: Position | Sequence[Position]
    ) -> Position | tuple[Position, ...]:
        """Map position(s) through this pose."""
        if isinstance(p, Position):
            return self._apply((p,))[0]
        return self._apply(p)

    def _apply(self, p: Sequence[Position]) -> tuple[Position, ...]:
        if self == Pose.IDENTITY:
            return tuple(p)
        if self.rotation in _QUARTER_TURN_INDEX:
            # Does not touch z-axis, so no stud-unit round trip: more efficient & keeps grid arithmetic exact.
            t = self.translation
            return tuple(self.rotation @ pos + t for pos in p)
        t = self.translation.to_stud_units()
        return tuple(
            Position.from_stud_units(self.rotation @ pos.to_stud_units() + t)
            for pos in p
        )

    @property
    def is_grid_preserving(self) -> bool:
        """Whether parts related by this pose share one build grid."""
        return (
            self.rotation in _QUARTER_TURN_INDEX and self.translation.is_grid_aligned()
        )

    @property
    def inverse(self) -> Pose:
        """The pose that undoes this one: ``pose.inverse.compose(pose)`` is the identity."""
        rotation = self.rotation.transpose
        translation = rotation @ self.translation.to_stud_units()
        return Pose(rotation, Position.from_stud_units(-translation))


Pose.IDENTITY = Pose()


@dataclass(frozen=True)
class Cuboid:
    """An oriented rectangular volume: the image under ``pose`` of the
    axis-aligned box of extent ``size`` centered on the origin.
    """

    size: Position
    pose: Pose = Pose.IDENTITY

    def __post_init__(self):
        if self.size.x < 0 or self.size.y < 0 or self.size.z < 0:
            raise ValueError(f"size must be non-negative, got {self.size}")

    @classmethod
    def spanning(cls, lo: Position, hi: Position) -> Cuboid:
        """The axis-aligned cuboid with opposite corners ``lo`` and ``hi``."""
        return cls(hi - lo, Pose(translation=(lo + hi) * 0.5))

    def transformed(self, pose: Pose) -> Cuboid:
        """This cuboid mapped by ``pose``."""
        return Cuboid(self.size, pose.compose(self.pose))

    @cached_property
    def is_empty(self) -> bool:
        """Whether the volume has zero extent along any axis."""
        return self.size.x == 0 or self.size.y == 0 or self.size.z == 0

    @cached_property
    def center(self) -> Position:
        """The volume's midpoint, in the frame the pose maps into."""
        return self.pose.translation

    @cached_property
    def corners(self) -> tuple[Position, ...]:
        """The volume's eight corners, in the frame the pose maps into."""
        hx, hy, hz = self.size * 0.5
        return self.pose.apply(
            [Position(x, y, z) for x in (-hx, hx) for y in (-hy, hy) for z in (-hz, hz)]
        )

    @cached_property
    def aabb(self) -> tuple[Position, Position]:
        """The ``(min, max)`` axis-aligned bounding box of the volume."""
        return vec_min(self.corners), vec_max(self.corners)
