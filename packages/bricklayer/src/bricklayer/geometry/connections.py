"""Connections.

Parts attach through compatible connector types: studs/antistuds, clips/bars,
axles/holes, ball joints, and others. Use existing connectors rather than creating
types or mating rules. Common names include `stud`, `antistud`, `bar`, `clip`,
`axle`, `axle_hole`, `pin`, `pin_hole`, `towball`, and `towball_socket`.
`stud` also matches hollow studs; `antistud` includes underside tubes.
Inspect a part's `connectors` to discover other types.

### Mounting and motion

`connect` fits compatible connectors; incompatible types raise `ValueError`.
`Mounting(angle=..., offset=..., flip=...)` chooses a fixed assembly pose.
Angles are degrees and sliding offsets are studs. Ball mounting additionally
accepts `swing_x` and `swing_y` in the connector frame; `angle` is its twist.
`target_rotation` requests the part's orientation and `target_position` its
connector's world position. Explicit mounting is applied after fitting them.

Connections are static unless given a `MotionRange`. Joint coordinates describe
motion from the mounted pose; see the recorded connections and motion section
for range declarations, pose previews, and validation.

### Connecting parts

Use `LegoBuild.add` or `stack` for grid-aligned stud connections; couplings are
detected automatically.

`LegoBuild.connect` mates a local connector on `content` to a world-frame target
from a placement. The source can be a `Connector` or a type/name identifying
its unique connector.

```python
import bricklayer as bl

model = bl.LegoBuild()
socket_part = model.add(bl.Element("14418", bl.Color.WHITE), name="socket_part")
model.connect(
    bl.Element("22890", bl.Color.WHITE),
    "towball",  # the connector type on the ball part
    to=socket_part.find_connector("towball_socket"),
    target_rotation=bl.rotation_about(bl.Direction.UP.value, 180),
    mounting=bl.Mounting(swing_x=5),
)
assert model.is_valid() and model.is_connected()
```

When several source connectors share a type, select one with `find_connector`
and pass it directly:

```python
import bricklayer as bl

link = bl.Element("3170", bl.Color.WHITE)
far_conn = link.find_connector("towball", toward=bl.Direction.LEFT)  # the +x ball

model = bl.LegoBuild()
socket_part = model.add(bl.Element("14418", bl.Color.WHITE), name="socket_part")
model.connect(link, far_conn, to=socket_part.find_connector("towball_socket"))
```

### Breaking away from the stud build grid

Use `connect()` with SNOT (Studs Not On Top) bricks or brackets to build sideways.
Select side studs with `facing`; use `toward` to choose among several matches.

```python
import bricklayer as bl

base = bl.Element("11211", bl.Color.WHITE)
attachment = bl.plate(1, 1)
mount = attachment.find_connector("antistud")

model = bl.LegoBuild()
placed_base = model.add(base, name="base")
# Select the leftmost front-facing stud in the model's frame.
side_stud = placed_base.find_connector(
    "stud", facing=bl.Direction.FRONT, toward=bl.Direction.LEFT
)
model.connect(attachment, mount, to=side_stud)
assert model.is_valid() and model.is_connected()
```

Use `connect()` with jumper studs for half-stud offsets:

```python
import bricklayer as bl

base = bl.Element("15573", bl.Color.WHITE)
attachment = bl.plate(1, 1)
mount = attachment.find_connector("antistud")

model = bl.LegoBuild()
jumper = model.add(base, name="jumper")
# Select the offset top stud in the model's frame.
offset_stud = jumper.find_connector("stud", facing=bl.Direction.UP)
model.connect(attachment, mount, to=offset_stud)
assert model.is_valid() and model.is_connected()
```
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field, fields
from enum import Enum, auto
from functools import cached_property
from itertools import combinations, product
from math import floor
from typing import ClassVar, NamedTuple

from .._mixins import Immutable
from .linalg import (
    Mat3,
    Vec3,
    cross,
    dot,
    is_aligned,
    is_opposing,
    is_orthogonal,
    is_unit,
    rotation_about,
    rotation_between,
)
from .spatial import (
    BUILD_TOLERANCE,
    PLATES_PER_BRICK,
    Direction,
    Pose,
    Position,
    Scalar,
    to_direction,
)

#: The grid-using family that sits on top of a part and can be built on.
STUD_FAMILY = "stud"
#: The grid-using family that receives a stud, on a part's underside.
HOLE_FAMILY = "hole"
GRID_FAMILIES = frozenset({STUD_FAMILY, HOLE_FAMILY})

# How far two sliding connectors' spans must overlap before they grip, in studs.
# BrickNet's constant, 4 LDU.
MIN_SLIDE_OVERLAP = 0.2
# The span a connector is credited with when it records none, in studs. A bar hole
# records no length but still grips a bar, so a zero-length record means "at least
# this much". BrickNet's constant, also 4 LDU.
MIN_SLIDE_REACH = 0.2


@dataclass(frozen=True, slots=True, eq=False)
class ConnectorType:
    """A registered connector kind, identified by `name`.

    Use names or `get_connector_type(name)` to select existing types.
    """

    name: str
    family: str = field(
        default="authored",
        metadata={
            "doc": "The BrickNet kind this type came from, or `authored` if hand-written."
        },
    )
    uses_grid: bool = field(
        default=False,
        metadata={
            "doc": "If `True`, the connector (if grid-aligned) counts toward a geometry's alignment box."
        },
    )

    def __deepcopy__(self, memo: dict[int, object]) -> ConnectorType:
        return self

    def __reduce__(self):
        from ..ldraw.partdata import get_connector_type

        try:
            canonical = get_connector_type(self.name)
        except KeyError:
            canonical = None
        if canonical is self:
            return get_connector_type, (self.name,)
        return type(self), (self.name, self.family, self.uses_grid)


class Connector(Immutable):
    """A mating point obtained from a part or placement's connectors.

    `position` is in the queried geometry's frame. `axis` is its mating direction;
    `side` fixes its roll. Both directions use uniform stud units.
    `length` is the sliding reach in studs on either side of the point.
    """

    type: ConnectorType
    position: Position
    axis: Vec3
    side: Vec3
    length: Scalar

    def __init__(
        self,
        type: ConnectorType,
        position: Position,
        axis: Vec3 | Direction,
        side: Vec3 | Direction | None = None,
        length: Scalar = 0,
    ) -> None:
        if isinstance(axis, Direction):
            axis = axis.value
        if not is_unit(axis):
            raise ValueError(f"axis must be a unit vector, got {axis!r}")
        if side is None:
            side = rotation_between(Vec3(0, 0, 1), axis) @ Vec3(1, 0, 0)
        elif isinstance(side, Direction):
            side = side.value
        if not is_unit(side):
            raise ValueError(f"side must be a unit vector, got {side!r}")
        if not is_orthogonal(axis, side):
            raise ValueError(f"side must be orthogonal to axis, got {side!r}")
        if length < 0:
            raise ValueError(f"length must be non-negative, got {length!r}")
        self.type = type
        self.position = position
        self.axis = axis
        self.side = side
        self.length = length
        self._initialized = True

    def __repr__(self) -> str:
        x, y, z = self.position
        direction = to_direction(self.axis)
        facing = direction.name if direction is not None else repr(self.axis)
        return f"{type(self).__name__}({self.type.name} at ({x}, {y}, {z}), facing {facing})"

    @cached_property
    def frame(self) -> Mat3:
        """The connector's local frame: columns ``(side, axis x side, axis)``.

        A rotation whose third column is :attr:`axis` and whose first is
        :attr:`side`; it drives mating.
        """
        a = self.axis / self.axis.norm()
        s = self.side - a * dot(self.side, a)
        s = s / s.norm()
        f = cross(a, s)
        return Mat3(((s.x, f.x, a.x), (s.y, f.y, a.y), (s.z, f.z, a.z)))

    def transformed(self, pose: Pose) -> Connector:
        """A new connector: this one mapped by ``pose`` (position, axis, side).
        The identity pose returns ``self``, keeping its identity."""
        if pose is Pose.IDENTITY:
            return self
        # A rotation keeps both axes unit and orthogonal, so skip revalidating.
        moved = object.__new__(Connector)
        moved.__dict__.update(
            type=self.type,
            position=pose.apply(self.position),
            axis=pose.rotation @ self.axis,
            side=pose.rotation @ self.side,
            length=self.length,
            _initialized=True,
        )
        return moved

    @property
    def is_grid_oriented(self) -> bool:
        """Whether this connector has a grid-using type, an up-facing axis, and a
        ``side`` along a cardinal :class:`Direction`."""
        return (
            self.type.uses_grid
            and self.axis == Direction.UP.value
            and to_direction(self.side) is not None
        )

    @cached_property
    def is_grid_marked(self) -> bool:
        """Whether this connector counts toward the alignment box: it is
        :attr:`is_grid_oriented` and sits at a grid-aligned position."""
        if not self.is_grid_oriented:
            return False
        # A stud center sits at whole- or half-stud x/y depending on the frame
        # (a centered odd footprint puts it on whole studs); doubling x/y maps
        # both phases onto the integer grid.
        p = self.position
        return Position(2 * p.x, 2 * p.y, p.z).is_grid_aligned()


def same_connector(a: Connector, b: Connector) -> bool:
    """Whether two connectors describe the same point and frame, within tolerance."""
    return (
        a.type is b.type
        and _positions_coincide(a, b)
        and is_aligned(a.axis, b.axis)
        and is_aligned(a.side, b.side)
        and abs(a.length - b.length) <= BUILD_TOLERANCE
    )


# Half of a cell's 26 neighbors -- the lexicographically greater direction of
# each opposed pair. Two connectors count as coincident within BUILD_TOLERANCE and the
# cells are that size, so a coincident pair sits in one cell or in adjacent ones;
# visiting only one direction of each adjacency still finds every such pair,
# because the other cell of the pair covers the opposite direction itself.
_FORWARD_NEIGHBORS = tuple(
    offset for offset in product((-1, 0, 1), repeat=3) if offset > (0, 0, 0)
)


class Matings(NamedTuple):
    """What one mating scan found over a set of connector groups."""

    #: Group index pairs holding at least one mated connector pair, sorted.
    pairs: tuple[tuple[int, int], ...]
    #: Every connector mating with at least one connector in another group.
    connectors: frozenset[Connector]


def mated(groups: Sequence[Iterable[Connector]]) -> Matings:
    """Scan ``groups`` once for mated connector pairs across groups.

    Each group is one part's connectors, in a shared frame. A spatial hash culls
    the candidate connector pairs; :func:`connectors_mate` decides each survivor.
    Two parts joined by many connectors appear in :attr:`~Matings.pairs` once,
    while every connector joining them appears in :attr:`~Matings.connectors`.

    ``Connector`` hashes by identity, so the returned set holds the very objects
    ``groups`` supplied, and a caller differencing against it must supply those
    same objects.
    """
    entries = [
        (owner, connector) for owner, group in enumerate(groups) for connector in group
    ]
    pairs: set[tuple[int, int]] = set()
    in_use: set[Connector] = set()
    for n, m in _coincident_candidates(entries) | _sliding_candidates(entries):
        owner_a, a = entries[n]
        owner_b, b = entries[m]
        if owner_a != owner_b and connectors_mate(a, b):
            pairs.add((owner_a, owner_b) if owner_a < owner_b else (owner_b, owner_a))
            in_use.add(a)
            in_use.add(b)
    return Matings(tuple(sorted(pairs)), frozenset(in_use))


def _coincident_candidates(
    entries: Sequence[tuple[int, Connector]],
) -> set[tuple[int, int]]:
    """Entry-index pairs whose connectors sit within :data:`BUILD_TOLERANCE`.

    Cells are one tolerance across, so a coincident pair lands in one cell or in
    adjacent ones: connectors in a cell pair with each other, and each cell
    reaches into half its neighbors (see :data:`_FORWARD_NEIGHBORS`).
    """
    at_point: dict[tuple[int, int, int], list[int]] = {}
    for n, (_, connector) in enumerate(entries):
        at_point.setdefault(_tolerance_cell(connector.position), []).append(n)
    candidates: set[tuple[int, int]] = set()
    for (x, y, z), members in at_point.items():
        candidates.update(combinations(members, 2))
        for dx, dy, dz in _FORWARD_NEIGHBORS:
            neighbours = at_point.get((x + dx, y + dy, z + dz))
            if neighbours is None:
                continue
            candidates.update(
                (n, m) if n < m else (m, n) for n in members for m in neighbours
            )
    return candidates


def _sliding_candidates(
    entries: Sequence[tuple[int, Connector]],
) -> set[tuple[int, int]]:
    """Entry-index pairs that can mate away from their own point.

    A connector whose type carries a prismatic or cylindrical rule is indexed
    under every coarse cell its reach (see :func:`_reach`) crosses, so two such
    connectors whose spans overlap share a cell. Every other joint kind needs
    coincident positions, which :func:`_coincident_candidates` already covers.
    """
    active = _active_sliding_types({connector.type for _, connector in entries})
    if not active:
        return set()
    by_cell: dict[tuple[int, int, int], list[int]] = {}
    for n, (_, connector) in enumerate(entries):
        if connector.type not in active:
            continue
        reach = Position.from_stud_units(connector.axis * _reach(connector.length))
        for key in _unit_cells(connector.position - reach, connector.position + reach):
            by_cell.setdefault(key, []).append(n)
    return {pair for members in by_cell.values() for pair in combinations(members, 2)}


def _active_sliding_types(present: set[ConnectorType]) -> frozenset[ConnectorType]:
    """Of the types in ``present``, those that could actually slide-mate here.

    A prismatic or cylindrical coupling needs *both* endpoint types in the
    model, so a type whose partners are all absent can be skipped. This is the
    common case and worth the check: an ordinary brick carries a ``bar``
    connector with a slide span, so this is what confines the slide sweep to
    builds that hold both ends of some sliding pair.
    """
    partners = _SLIDING_PARTNERS
    return frozenset(t for t in present & partners.keys() if partners[t] & present)


def _tolerance_cell(p: Position) -> tuple[int, int, int]:
    """Quantize a world position into a cell one mating tolerance across."""
    return (
        floor(float(p.x) / BUILD_TOLERANCE),
        floor(float(p.y) / BUILD_TOLERANCE),
        floor(float(p.z) / BUILD_TOLERANCE),
    )


def _unit_cells(*positions: Position) -> Iterator[tuple[int, int, int]]:
    """The coarse grid cells covered by the AABB of ``positions``, padded by
    the mating tolerance. One-stud cells in x and y, one-brick cells in z."""
    pad = BUILD_TOLERANCE

    def span(values: list[float]) -> range:
        return range(floor(min(values) - pad), floor(max(values) + pad) + 1)

    return product(
        span([float(p.x) for p in positions]),
        span([float(p.y) for p in positions]),
        span([float(p.z) for p in positions]),
    )


def connectors_mate(a: Connector, b: Connector) -> bool:
    """Whether two connectors mate: compatible types, frames the joint accepts.

    The registered rule's joint kind decides which frame constraints apply. A
    fixed joint locks both frames, so the positions must coincide and both
    ``axis`` and ``side`` must align. A revolute joint spins about the axis, so
    the positions must coincide and the axes must align *or* oppose (``side``
    is free). A ball joint pivots freely (only the positions must coincide). Prismatic and cylindrical joints slide: each connector's
    :attr:`~Connector.length`-long segment along its axis must overlap the
    other's (see :func:`_slide_within_lengths`). A prismatic joint cannot spin,
    so its axes and ``side`` must align; a cylindrical joint spins freely, so
    its axes may align *or* oppose and ``side`` is free.
    """
    rule = mating_rule(a.type, b.type)
    if rule is None:
        return False
    match rule.joint:
        case JointKind.BALL:
            return _positions_coincide(a, b)
        case JointKind.REVOLUTE:
            axial = is_aligned(a.axis, b.axis) or is_opposing(a.axis, b.axis)
            return _positions_coincide(a, b) and axial
        case JointKind.FIXED:
            return (
                _positions_coincide(a, b)
                and is_aligned(a.axis, b.axis)
                and is_aligned(a.side, b.side)
            )
        case JointKind.CYLINDRICAL:
            axial = is_aligned(a.axis, b.axis) or is_opposing(a.axis, b.axis)
            return axial and _slide_within_lengths(a, b)
        case JointKind.PRISMATIC:
            return (
                is_aligned(a.axis, b.axis)
                and is_aligned(a.side, b.side)
                and _slide_within_lengths(a, b)
            )


def _positions_coincide(a: Connector, b: Connector) -> bool:
    """Whether two connectors' points coincide, within :data:`~.spatial.BUILD_TOLERANCE`."""
    d = (b.position - a.position).to_stud_units()
    return (
        abs(d.x) <= BUILD_TOLERANCE
        and abs(d.y) <= BUILD_TOLERANCE
        and abs(d.z) <= BUILD_TOLERANCE
    )


def _slide_within_lengths(a: Connector, b: Connector) -> bool:
    """Whether ``a``'s and ``b``'s slide extents overlap enough to grip.

    Each connector reaches :attr:`~Connector.length` studs *either way* along its
    ``axis`` from its point, so the two spans overlap by
    ``a.length + b.length - |offset|``. They mate when that exceeds
    :data:`MIN_SLIDE_OVERLAP`.

    The caller guarantees the axes are aligned or opposing, so both spans lie on
    one line; the line must also be shared, with no off-axis displacement.
    """
    delta = (b.position - a.position).to_stud_units()
    offset = dot(delta, a.axis)
    off_axis = delta - a.axis * offset
    if dot(off_axis, off_axis) > BUILD_TOLERANCE**2:
        return False
    overlap = _reach(a.length) + _reach(b.length) - abs(offset)
    return overlap >= MIN_SLIDE_OVERLAP - BUILD_TOLERANCE


def _reach(length: Scalar) -> float:
    """How far a connector of this span grips, in studs, either way from its point."""
    return max(float(length), MIN_SLIDE_REACH)


def mate_pose(conn: Connector, target: Connector) -> Pose:
    """The pose seating ``conn`` (local) onto the world connector ``target``:
    their points coincide and their frames align."""
    rotation = target.frame @ conn.frame.transpose
    seated = Pose(rotation)
    return Pose(rotation, target.position - seated.apply(conn.position))


class JointKind(Enum):
    """Continuous degrees of freedom of a joint."""

    FIXED = auto()
    REVOLUTE = auto()
    PRISMATIC = auto()
    CYLINDRICAL = auto()
    BALL = auto()


@dataclass(frozen=True, slots=True)
class Mounting:
    """Assembly choices, fixed once connected.

    ``angle`` is clocking about the connector axis (degrees), ``offset`` is
    insertion along it (studs), and ``flip`` turns an axial connection end for
    end. Ball mounting uses ``swing_x``/``swing_y`` as a rotation vector in the
    connector's transverse plane, followed by ``angle`` as twist, in degrees.
    """

    angle: float = 0.0
    offset: Scalar = 0
    flip: bool = False
    swing_x: float = 0.0
    swing_y: float = 0.0

    def __post_init__(self) -> None:
        _finite_coordinates(self)


@dataclass(frozen=True, slots=True)
class Fixed:
    """A joint with no motion coordinates."""

    kind: ClassVar[JointKind] = JointKind.FIXED


@dataclass(frozen=True, slots=True)
class Revolute:
    """Rotation from the mounted pose about the joint axis, in degrees."""

    kind: ClassVar[JointKind] = JointKind.REVOLUTE
    angle: float = 0.0

    def __post_init__(self) -> None:
        _finite_coordinates(self)


@dataclass(frozen=True, slots=True)
class Prismatic:
    """Translation from the mounted pose along the joint axis, in studs."""

    kind: ClassVar[JointKind] = JointKind.PRISMATIC
    offset: Scalar = 0

    def __post_init__(self) -> None:
        _finite_coordinates(self)


@dataclass(frozen=True, slots=True)
class Cylindrical:
    """Sliding (studs) and rotation (degrees) from the mounted pose."""

    kind: ClassVar[JointKind] = JointKind.CYLINDRICAL
    offset: Scalar = 0
    angle: float = 0.0

    def __post_init__(self) -> None:
        _finite_coordinates(self)


@dataclass(frozen=True, slots=True)
class Ball:
    """Joint-local swing and twist, in degrees, from the mounted pose.

    The swing is the rotation vector ``(swing_x, swing_y, 0)`` about the joint's
    transverse axes. Its length is the swing angle. The orientation is
    ``swing @ twist_about_z``. This convention follows the joint when the whole
    model turns; it does not use world Euler angles.
    """

    kind: ClassVar[JointKind] = JointKind.BALL
    swing_x: float = 0.0
    swing_y: float = 0.0
    twist: float = 0.0

    def __post_init__(self) -> None:
        _finite_coordinates(self)


JointCoordinates = Fixed | Revolute | Prismatic | Cylindrical | Ball


def joint_pose(coordinates: JointCoordinates) -> Pose:
    """Motion in a joint-local frame with its axis along +z, in uniform studs."""
    if isinstance(coordinates, Fixed):
        return Pose.IDENTITY
    if isinstance(coordinates, Ball):
        return Pose(
            _ball_rotation(coordinates.swing_x, coordinates.swing_y, coordinates.twist)
        )
    angle = coordinates.angle if isinstance(coordinates, (Revolute, Cylindrical)) else 0
    offset = (
        coordinates.offset if isinstance(coordinates, (Prismatic, Cylindrical)) else 0
    )
    return Pose(
        rotation_about(Vec3(0, 0, 1), angle),
        Position.from_stud_units(Vec3(0, 0, offset)),
    )


def mounting_pose(mounting: Mounting, at: Connector, kind: JointKind) -> Pose:
    """Assembly displacement about a connector in the containing model's frame."""
    allowed = {
        JointKind.FIXED: (),
        JointKind.REVOLUTE: ("angle", "flip"),
        JointKind.PRISMATIC: ("offset",),
        JointKind.CYLINDRICAL: ("offset", "angle", "flip"),
        JointKind.BALL: ("swing_x", "swing_y", "angle"),
    }[kind]
    if any(
        getattr(mounting, f.name) and f.name not in allowed for f in fields(mounting)
    ):
        raise ValueError(f"mounting parameters do not fit a {kind.name} connection")
    if kind is JointKind.BALL:
        local = _ball_rotation(mounting.swing_x, mounting.swing_y, mounting.angle)
        rotation = at.frame @ local @ at.frame.transpose
    else:
        rotation = _axial_rotation(at.axis, at.side, mounting.angle, mounting.flip)
    return Pose(translation=_studs_along(at.axis, mounting.offset)).compose(
        _pivot(rotation, at.position)
    )


def fit_mounting(
    joint: JointKind,
    conn: Connector,
    at: Connector,
    rest: Pose,
    *,
    target_rotation: Mat3,
    target_position: Position,
) -> Mounting:
    """Fit an assembly orientation and insertion, clamping sliding to engagement."""
    if joint is JointKind.FIXED:
        return Mounting()
    rotation = target_rotation @ rest.rotation.transpose
    if joint is JointKind.BALL:
        return _ball_mounting(at.frame.transpose @ rotation @ at.frame)
    angle, flip = _best_angle_and_flip(rotation, at)
    if joint is JointKind.REVOLUTE:
        return Mounting(angle=angle, flip=flip)
    offset = dot((target_position - at.position).to_stud_units(), at.axis)
    limit = _slide_limit(conn.length, at.length)
    slid = max(-limit, min(limit, offset))
    if joint is JointKind.PRISMATIC:
        return Mounting(offset=slid)
    return Mounting(offset=slid, angle=angle, flip=flip)


def _finite_coordinates(value: Mounting | JointCoordinates) -> None:
    if any(not math.isfinite(getattr(value, f.name)) for f in fields(value)):
        raise ValueError("joint coordinates must be finite")
    if (
        isinstance(value, (Mounting, Ball))
        and math.hypot(value.swing_x, value.swing_y) > 180
    ):
        raise ValueError("ball swing must be at most 180 degrees")


def _ball_rotation(swing_x: float, swing_y: float, twist: float) -> Mat3:
    return _swing_rotation(swing_x, swing_y) @ rotation_about(Vec3(0, 0, 1), twist)


def _swing_rotation(x: float, y: float) -> Mat3:
    angle = math.hypot(x, y)
    return (
        rotation_about(Vec3(x / angle, y / angle, 0), angle) if angle else Mat3.IDENTITY
    )


def _axial_rotation(axis: Vec3, side: Vec3, angle: float, flip: bool) -> Mat3:
    rotation = rotation_about(axis, angle)
    return rotation @ rotation_about(side, 180.0) if flip else rotation


def _pivot(rotation: Mat3, point: Position) -> Pose:
    return Pose(rotation, point - Pose(rotation).apply(point))


def _studs_along(axis: Vec3, offset: Scalar) -> Position:
    return Position.from_stud_units(axis * offset)


def _best_angle_and_flip(rotation: Mat3, at: Connector) -> tuple[float, bool]:
    def fit(flip: bool) -> tuple[float, float, bool]:
        base = rotation_about(at.side, 180.0) if flip else Mat3.IDENTITY
        angle = _twist_angle(rotation @ base.transpose, at.axis, at.side)
        residual = _rotation_residual(rotation_about(at.axis, angle) @ base, rotation)
        return residual, angle, flip

    _, angle, flip = min(fit(False), fit(True), key=lambda r: r[0])
    return angle, flip


def _twist_angle(desired: Mat3, axis: Vec3, side: Vec3) -> float:
    """The rotation angle (degrees) about ``axis`` that best matches ``desired``.

    Swing-twist: rotate the reference ``side`` (a unit vector orthogonal to
    ``axis``) by ``desired``, project onto the plane perpendicular to ``axis``,
    and measure the signed angle from ``side`` about ``axis``.
    """
    turned = desired @ side
    projected = turned - axis * dot(turned, axis)
    return math.degrees(
        math.atan2(dot(cross(side, projected), axis), dot(side, projected))
    )


def _ball_mounting(desired: Mat3) -> Mounting:
    axis = desired @ Vec3(0, 0, 1)
    angle = math.acos(max(-1.0, min(1.0, axis.z)))
    transverse = math.hypot(axis.x, axis.y)
    if transverse > 1e-10:
        x, y = (
            -axis.y / transverse * math.degrees(angle),
            axis.x / transverse * math.degrees(angle),
        )
    else:
        x, y = (180.0 if axis.z < 0 else 0.0), 0.0
    twist = _twist_angle(
        _swing_rotation(x, y).transpose @ desired, Vec3(0, 0, 1), Vec3(1, 0, 0)
    )
    return Mounting(swing_x=x, swing_y=y, angle=twist)


def _rotation_residual(a: Mat3, b: Mat3) -> float:
    """Sum of squared entrywise differences between two rotation matrices."""
    return sum((x - y) ** 2 for x, y in zip(a.flatten(), b.flatten()))


def _slide_limit(moving: Scalar, fixed: Scalar) -> float:
    """How far a slid connector of span ``moving`` may travel, in studs, and stay
    mated with a fixed connector of span ``fixed``.

    The mated range is symmetric about the fixed point, so this is its half-width.
    """
    return max(0.0, _reach(moving) + _reach(fixed) - MIN_SLIDE_OVERLAP)


@dataclass(frozen=True, slots=True)
class Rule:
    """How a compatible pair of connector types joins."""

    joint: JointKind = JointKind.FIXED


_RULES: dict[frozenset[ConnectorType], Rule] = {}
#: For each type in a prismatic or cylindrical rule, the types it slides against.
_SLIDING_PARTNERS: dict[ConnectorType, set[ConnectorType]] = {}


def mark_compatible(
    a: ConnectorType, b: ConnectorType, *, joint: JointKind = JointKind.FIXED
) -> None:
    """Register that ``a`` and ``b`` mate (order-insensitive).

    Raises:
        ValueError: if the pair is already registered.
    """
    key = frozenset({a, b})
    if key in _RULES:
        raise ValueError(f"{a.name} and {b.name} are already registered as compatible")
    _RULES[key] = Rule(joint)
    if joint in (JointKind.PRISMATIC, JointKind.CYLINDRICAL):
        _SLIDING_PARTNERS.setdefault(a, set()).add(b)
        _SLIDING_PARTNERS.setdefault(b, set()).add(a)


def mating_rule(a: ConnectorType, b: ConnectorType) -> Rule | None:
    """The mating rule for ``a`` and ``b``, or ``None`` if they cannot mate."""
    return _RULES.get(frozenset({a, b}))


def snap_to_half_stud_grid(p: Position) -> Position:
    """Snap a position to the nearest point on the half-stud grid.

    Generally, this is used to remove float noise from grid-aligned connectors.
    """
    return Position(
        round(p.x * 2) / 2,
        round(p.y * 2) / 2,
        round(p.z * PLATES_PER_BRICK) / PLATES_PER_BRICK,
    )
