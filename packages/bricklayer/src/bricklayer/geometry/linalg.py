"""Math utilities for 3D geometry."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from functools import cache, cached_property
from typing import (
    ClassVar,
    Generic,
    Self,
    TypeVar,
    overload,
)

import numpy as np

from bricklayer._mixins import ReprEnum

Scalar = int | float
_T = TypeVar("_T", int, float, Scalar)


def _require_same_class(a: VecType, b: VecType) -> None:
    if type(a) is not type(b):
        raise TypeError(
            f"cannot combine {type(a).__name__} and {type(b).__name__}: "
            "they are different coordinate systems"
        )


def format_scalar(v: Scalar) -> Scalar:
    """Render integral values without a trailing ``.0`` (for tidy reprs)."""
    f = float(v)
    return int(f) if f.is_integer() else round(f, 3)


@dataclass(frozen=True, slots=True)
class Vec3(Generic[_T]):
    """A 3-component vector with componentwise arithmetic.

    Concrete coordinate classes subclass this, one per coordinate system;
    ``+``/``-`` require both operands to be the *same* class, so vectors from
    different coordinate systems cannot be combined by accident.
    """

    x: _T
    y: _T
    z: _T

    def __iter__(self) -> Iterator[_T]:
        yield self.x
        yield self.y
        yield self.z

    def __getitem__(self, i: int) -> _T:
        return (self.x, self.y, self.z)[i]

    def __len__(self) -> int:
        return 3

    def __repr__(self) -> str:
        return f"{type(self).__name__}({format_scalar(self.x)}, {format_scalar(self.y)}, {format_scalar(self.z)})"

    def __add__(self, other: Self) -> Self:
        _require_same_class(self, other)
        return type(self)(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Self) -> Self:
        _require_same_class(self, other)
        return type(self)(self.x - other.x, self.y - other.y, self.z - other.z)

    def __neg__(self) -> Self:
        return type(self)(-self.x, -self.y, -self.z)

    def __mul__(self, k: Scalar) -> Self:
        return type(self)(self.x * k, self.y * k, self.z * k)

    __rmul__ = __mul__

    def __truediv__(self, k: Scalar) -> Self:
        return type(self)(self.x / k, self.y / k, self.z / k)

    @property
    def array(self) -> np.ndarray:
        """This vector as a length-3 ``float64`` array."""
        return np.array((self.x, self.y, self.z), dtype=float)

    def norm(self) -> float:
        """The Euclidean norm (length) of this vector."""
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)


VecType = TypeVar("VecType", bound=Vec3)


def _componentwise(
    op: Callable[[Iterable[_T]], _T], vecs: Sequence[VecType], name: str
) -> VecType:
    if not vecs:
        raise ValueError(f"{name}() requires at least one vector")
    first = vecs[0]
    for v in vecs[1:]:
        _require_same_class(v, first)
    return type(first)(
        op(v.x for v in vecs), op(v.y for v in vecs), op(v.z for v in vecs)
    )


def vec_min(vecs: Sequence[VecType]) -> VecType:
    return _componentwise(min, vecs, "vec_min")


def vec_max(vecs: Sequence[VecType]) -> VecType:
    return _componentwise(max, vecs, "vec_max")


def dot(a: Vec3[_T], b: Vec3[_T]) -> _T:
    """Dot product of two 3-vectors."""
    return a.x * b.x + a.y * b.y + a.z * b.z


def cross(a: VecType, b: VecType) -> VecType:
    """Cross product of two 3-vectors."""
    return type(a)(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    )


# Dot-product comparisons treat a value within this of the target as exact,
# absorbing the float error left by rotations and normalization.
EPSILON = 1e-6


def is_unit(v: Vec3) -> bool:
    """Whether ``v`` is a unit vector, within :data:`EPSILON`."""
    return abs(dot(v, v) - 1) <= EPSILON


def is_orthogonal(a: Vec3, b: Vec3) -> bool:
    """Whether ``a`` and ``b`` are orthogonal, within :data:`EPSILON`."""
    return abs(dot(a, b)) <= EPSILON


def is_opposing(a: Vec3, b: Vec3) -> bool:
    """Whether unit vectors ``a`` and ``b`` point in opposite directions:
    their dot product is within :data:`EPSILON` of -1."""
    return dot(a, b) <= -1 + EPSILON


def is_aligned(a: Vec3, b: Vec3) -> bool:
    """Whether unit vectors ``a`` and ``b`` point in the same direction:
    their dot product is within :data:`EPSILON` of 1."""
    return dot(a, b) >= 1 - EPSILON


@dataclass(frozen=True)
class Mat3:
    """A 3x3 matrix."""

    entries: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ] = field(metadata={"doc": "The matrix rows, top to bottom."})
    IDENTITY: ClassVar[Mat3]

    def __post_init__(self):
        if len(self.entries) != 3 or any(len(row) != 3 for row in self.entries):
            raise ValueError("Mat3 must be initialized with a 3x3 sequence")

    @classmethod
    def from_flattened(cls, entries: Sequence[float]) -> Mat3:
        """Create a Mat3 from a flattened row-major sequence of 9 entries."""
        if len(entries) != 9:
            raise ValueError("Flattened entries must have length 9")
        return cls(
            (
                (entries[0], entries[1], entries[2]),
                (entries[3], entries[4], entries[5]),
                (entries[6], entries[7], entries[8]),
            )
        )

    @classmethod
    def from_array(cls, arr: np.ndarray) -> Mat3:
        """Create a Mat3 from a 3x3 array."""
        if arr.shape != (3, 3):
            raise ValueError("Array must be 3x3")
        return cls(
            (
                (float(arr[0, 0]), float(arr[0, 1]), float(arr[0, 2])),
                (float(arr[1, 0]), float(arr[1, 1]), float(arr[1, 2])),
                (float(arr[2, 0]), float(arr[2, 1]), float(arr[2, 2])),
            )
        )

    def __repr__(self):
        if self == Mat3.IDENTITY:
            return "Mat3.IDENTITY"
        return f"Mat3({self.entries[0]}, {self.entries[1]}, {self.entries[2]})"

    def __iter__(self):
        yield from self.entries

    def __getitem__(self, i: int | tuple[int, int]) -> Vec3[float] | float:
        return (
            Vec3(*self.entries[i]) if isinstance(i, int) else self.entries[i[0]][i[1]]
        )

    @cached_property
    def array(self) -> np.ndarray:
        """This matrix as a 3x3 ``float64`` array."""
        arr = np.array(self.entries, dtype=float)
        arr.flags.writeable = False
        return arr

    @property
    def transpose(self) -> Mat3:
        """This matrix with its rows and columns swapped."""
        (a00, a01, a02), (a10, a11, a12), (a20, a21, a22) = self.entries
        return Mat3(((a00, a10, a20), (a01, a11, a21), (a02, a12, a22)))

    def __add__(self, other: Mat3) -> Mat3:
        (a00, a01, a02), (a10, a11, a12), (a20, a21, a22) = self.entries
        (b00, b01, b02), (b10, b11, b12), (b20, b21, b22) = other.entries
        return Mat3(
            (
                (a00 + b00, a01 + b01, a02 + b02),
                (a10 + b10, a11 + b11, a12 + b12),
                (a20 + b20, a21 + b21, a22 + b22),
            )
        )

    def __sub__(self, other):
        (a00, a01, a02), (a10, a11, a12), (a20, a21, a22) = self.entries
        (b00, b01, b02), (b10, b11, b12), (b20, b21, b22) = other.entries
        return Mat3(
            (
                (a00 - b00, a01 - b01, a02 - b02),
                (a10 - b10, a11 - b11, a12 - b12),
                (a20 - b20, a21 - b21, a22 - b22),
            )
        )

    def __mul__(self, k: Scalar) -> Mat3:
        (a00, a01, a02), (a10, a11, a12), (a20, a21, a22) = self.entries
        return Mat3(
            (
                (a00 * k, a01 * k, a02 * k),
                (a10 * k, a11 * k, a12 * k),
                (a20 * k, a21 * k, a22 * k),
            )
        )

    def __neg__(self):
        (a00, a01, a02), (a10, a11, a12), (a20, a21, a22) = self.entries
        return Mat3(
            (
                (-a00, -a01, -a02),
                (-a10, -a11, -a12),
                (-a20, -a21, -a22),
            )
        )

    __rmul__ = __mul__

    @overload
    def __matmul__(self, other: VecType) -> VecType: ...

    @overload
    def __matmul__(self, other: Mat3) -> Mat3: ...

    def __matmul__(self, other: VecType | Mat3) -> VecType | Mat3:
        if isinstance(other, Mat3):
            if self is Mat3.IDENTITY:
                return other
            if other is Mat3.IDENTITY:
                return self
            (a00, a01, a02), (a10, a11, a12), (a20, a21, a22) = self.entries
            (b00, b01, b02), (b10, b11, b12), (b20, b21, b22) = other.entries
            return Mat3(
                (
                    (
                        a00 * b00 + a01 * b10 + a02 * b20,
                        a00 * b01 + a01 * b11 + a02 * b21,
                        a00 * b02 + a01 * b12 + a02 * b22,
                    ),
                    (
                        a10 * b00 + a11 * b10 + a12 * b20,
                        a10 * b01 + a11 * b11 + a12 * b21,
                        a10 * b02 + a11 * b12 + a12 * b22,
                    ),
                    (
                        a20 * b00 + a21 * b10 + a22 * b20,
                        a20 * b01 + a21 * b11 + a22 * b21,
                        a20 * b02 + a21 * b12 + a22 * b22,
                    ),
                )
            )
        elif isinstance(other, Vec3):
            if self is Mat3.IDENTITY:
                return other
            (a, b, c), (d, e, f), (g, h, i) = self.entries
            x, y, z = other.x, other.y, other.z
            return type(other)(
                a * x + b * y + c * z,
                d * x + e * y + f * z,
                g * x + h * y + i * z,
            )
        else:
            raise TypeError(
                f"unsupported operand type(s) for @: {type(self)} and {type(other)}"
            )

    def det(self):
        """The matrix's determinant."""
        (a, b, c), (d, e, f), (g, h, i) = self.entries
        return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)

    def flatten(self) -> tuple[float, ...]:
        """The entries as a flattened row-major tuple."""
        return tuple(float(e) for row in self.entries for e in row)


Mat3.IDENTITY = Mat3.from_array(np.eye(3))


def all_close(a: Mat3, b: Mat3, tol: float = EPSILON) -> bool:
    """Whether all entries of ``a`` and ``b`` are within ``tol``."""
    return all(abs(aij - bij) <= tol for aij, bij in zip(a.flatten(), b.flatten()))


# cos/sin of k quarter turns, keeping right-angle rotations exact.
_RIGHT_ANGLE_COS_SIN = ((1, 0), (0, 1), (-1, 0), (0, -1))


def rotation_about(axis: Vec3, degrees: float) -> Mat3:
    """The right-handed rotation by ``degrees`` about the unit vector ``axis``.

    Multiples of 90 degrees produce exact (integer) matrices; other angles use
    floats (Rodrigues' rotation formula).
    """
    if degrees % 90 == 0:
        c, s = _RIGHT_ANGLE_COS_SIN[int(degrees // 90) % 4]
    else:
        c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    x, y, z = axis
    d = 1 - c
    return Mat3(
        (
            (c + x * x * d, x * y * d - z * s, x * z * d + y * s),
            (y * x * d + z * s, c + y * y * d, y * z * d - x * s),
            (z * x * d - y * s, z * y * d + x * s, c + z * z * d),
        )
    )


@cache
def rotation_between(a: Vec3, b: Vec3) -> Mat3:
    """The rotation taking unit vector ``a`` to unit vector ``b``.

    The shortest arc between them; antipodal vectors turn half a revolution
    about an arbitrary perpendicular. Memoized: most connectors share a handful
    of axes (studs point up, antistuds down), so the matrix is built once each.
    """
    c = float(dot(a, b))
    k = cross(a, b)
    sin_sq = float(dot(k, k))
    if c < 0 and sin_sq <= _ANTIPODAL_SIN_SQ:
        n = perpendicular(a)
        return _skew(n) @ _skew(n) * 2 + Mat3.IDENTITY
    # 1 / (1 + c), taken as (1 - c) / sin^2 past a right angle, where 1 + c
    # cancels catastrophically.
    scale = 1.0 / (1 + c) if c >= 0 else (1 - c) / sin_sq
    skew = _skew(k)
    return Mat3.IDENTITY + skew + skew @ skew * scale


# Below this squared sine, an obtuse pair is a half turn apart to within 1e-8.
_ANTIPODAL_SIN_SQ = 1e-16


def perpendicular(v: Vec3) -> Vec3:
    """A unit vector perpendicular to the unit vector ``v``."""
    pole = Vec3(1, 0, 0) if abs(v.x) <= 0.9 else Vec3(0, 1, 0)
    n = cross(v, pole)
    length_sq = dot(n, n)
    return n if length_sq == 1 else n / math.sqrt(length_sq)


def _skew(v: Vec3) -> Mat3:
    """The cross-product matrix of ``v``: ``_skew(v) @ u == cross(v, u)``."""
    return Mat3(((0, -v.z, v.y), (v.z, 0, -v.x), (-v.y, v.x, 0)))


class Axis(ReprEnum):
    """A horizontal axis."""

    X = 0  # width (left <-> right)
    Y = 1  # depth (front <-> back)


def reflection_matrix(axis: Axis) -> Mat3:
    """The matrix reflecting a vector across the plane perpendicular to ``axis``."""
    diagonal = [1.0, 1.0, 1.0]
    diagonal[axis.value] = -1.0
    return Mat3(((diagonal[0], 0, 0), (0, diagonal[1], 0), (0, 0, diagonal[2])))
