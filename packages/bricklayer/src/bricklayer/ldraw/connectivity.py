"""Decode BrickNet connectors (part_connectivity.json) into connector geometry.

BrickNet labels every connector with a ``(family, subtype, polarity)`` triple, where
``family`` is one of ``stud``, ``hole``, ``axle``, ``hinge``, ``ball``, or ``fixed``
and only the last three carry a polarity (``in``/``on``). There are 196 such
triples across the LDraw library, far too many to name by hand, so a triple's
connector type is named mechanically -- ``hinge_9_in`` -- unless
``part_connector_types.json`` aliases it to something friendlier.

Mating rules are generated. The unpolarized families come from
BrickNet's own mate tables; a polarized subtype carrying both polarities mates
``in`` to ``on``, with the joint taken from its family.
"""

from collections.abc import Iterable
from functools import cache
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..geometry import Connector, Direction, JointKind, Vec3, rotation_about
from ..geometry.connections import (
    GRID_FAMILIES,
    ConnectorType,
    mark_compatible,
)
from .conversion import LDRAW_TO_STUD, LDU_PER_STUD, LDrawVec

# A connector facing: a Direction name ("UP", "DOWN", ...) or a raw unit vector.
_Facing = str | tuple[float, float, float]

# A BrickNet connector triple: family, subtype, and polarity where the family
# has one.
_Triple = tuple[str, str, str | None]

# The LDraw frame's own axes, which BrickNet's pitch, roll, and yaw turn about.
_LDRAW_X = Vec3(1.0, 0.0, 0.0)
_LDRAW_Y = Vec3(0.0, 1.0, 0.0)
_LDRAW_Z = Vec3(0.0, 0.0, 1.0)

# Families whose sixth row column is a frame yaw; for the rest it is a slide span.
YAW_FAMILIES = frozenset({"fixed"})


class DuplicateConnectorName(ValueError):
    """Two BrickNet triples resolved to the same connector type name."""


class _AuthoredPairRaw(BaseModel):
    """One hand-written connector pair, with no BrickNet triple behind it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    types: tuple[str, str]
    joint: str


class ConnectorTypesRaw(BaseModel):
    """Schema for part_connector_types.json."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    note: str = ""
    aliases: dict[str, str] = {}
    groups: dict[str, tuple[str, ...]] = {}
    triples: tuple[str, ...] = ()
    stud_mates: tuple[tuple[str, str], ...] = ()
    axle_mates: tuple[tuple[str, str], ...] = ()
    family_joints: dict[str, str] = {}
    oriented_subtypes: dict[str, tuple[str, ...]] = {}
    authored: tuple[_AuthoredPairRaw, ...] = ()


class ConnectorRaw(BaseModel):
    """One raw connector entry from a connectivity data file.

    ``pos`` is raw LDraw-frame LDU and ``length`` is the slide span in LDU. The
    connector's frame is written either as BrickNet's ``pitch``/``roll``/``yaw``
    degrees (what extraction emits) or as ``axis``/``side``, each a
    :class:`Direction` name or a unit vector (what an override author writes).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: str
    pos: tuple[float, float, float]
    pitch: float = 0.0
    roll: float = 0.0
    yaw: float = 0.0
    axis: _Facing | None = None
    side: _Facing | None = None
    length: float = 0.0


def load_connector_types(parsed: ConnectorTypesRaw) -> dict[str, ConnectorType]:
    """Build the ConnectorType registry and register every mating rule.

    A fresh :class:`ConnectorType` is built per name on every call.

    Raises:
        DuplicateConnectorName: if two triples resolve to one name.
        ValueError: if an alias names a triple that does not exist.
    """
    known = {_split(key) for key in parsed.triples}
    for key in parsed.aliases:
        if _split(key) not in known:
            raise ValueError(f"alias names a triple that does not exist: {key}")

    types: dict[str, ConnectorType] = {}
    origin: dict[str, str] = {}
    for family, subtype, polarity in sorted(known, key=_triple_order):
        name = resolve_name(family, subtype, polarity, parsed.aliases)
        key = alias_key(family, subtype, polarity)
        if name in types:
            raise DuplicateConnectorName(
                f"{key} and {origin[name]} both resolve to {name!r}"
            )
        types[name] = ConnectorType(
            name, family=family, uses_grid=family in GRID_FAMILIES
        )
        origin[name] = key
    for pair in parsed.authored:
        for name in pair.types:
            types.setdefault(name, ConnectorType(name))

    _register_rules(types, parsed, known)
    return types


def load_connector_groups(
    parsed: ConnectorTypesRaw, types: dict[str, ConnectorType]
) -> dict[str, frozenset[ConnectorType]]:
    """Query-name to connector types, for names that stand for more than one type.

    BrickNet splits some features BrickLayer callers think of as one: a hollow
    stud is ``stud/open``, not ``stud/stud``, though it seats in an antistud
    exactly the same way. A group lets ``find_connectors("stud")`` match both
    without every caller having to know.

    Raises:
        ValueError: if a group names a type that is not registered.
    """
    groups: dict[str, frozenset[ConnectorType]] = {}
    for name, members in parsed.groups.items():
        missing = sorted(m for m in members if m not in types)
        if missing:
            raise ValueError(f"group {name!r} names unregistered types: {missing}")
        groups[name] = frozenset(types[m] for m in members)
    return groups


def expand_grouped_rows(
    grouped: dict[str, list[list[float]]], types: dict[str, ConnectorType]
) -> list[dict[str, Any]]:
    """Grouped connector rows as :class:`ConnectorRaw` mappings.

    Extraction groups a part's rows under their connector type name; an override
    file spells each connector out instead.

    A row is ``[x, y, z, pitch, roll, extra]`` with trailing zeros omitted, where
    ``extra`` is the frame yaw for the families in :data:`YAW_FAMILIES` and the
    slide span for the rest -- the split BrickNet's own loader makes.
    """
    entries: list[dict[str, Any]] = []
    for type_name_, rows in grouped.items():
        extra = "yaw" if types[type_name_].family in YAW_FAMILIES else "length"
        for row in rows:
            entry: dict[str, Any] = {"type": type_name_, "pos": tuple(row[:3])}
            for key, index in (("pitch", 3), ("roll", 4), (extra, 5)):
                if len(row) > index:
                    entry[key] = row[index]
            entries.append(entry)
    return entries


def decode_connectors(
    connectors: Iterable[ConnectorRaw], types: dict[str, ConnectorType]
) -> list[Connector]:
    """One part's raw connectors as typed connectors in its raw LDraw frame."""
    return [
        Connector(
            types[c.type],
            LDrawVec(*c.pos).to_position(),
            *_facing_pair(c),
            c.length / LDU_PER_STUD,
        )
        for c in connectors
    ]


def type_name(family: str, subtype: str, polarity: str | None) -> str:
    """The mechanical connector type name for a BrickNet triple."""
    return f"{family}_{subtype}_{polarity}" if polarity else f"{family}_{subtype}"


def alias_key(family: str, subtype: str, polarity: str | None) -> str:
    """The key a triple is written under in ``part_connector_types.json``."""
    return f"{family}/{subtype}/{polarity}" if polarity else f"{family}/{subtype}"


def resolve_name(
    family: str, subtype: str, polarity: str | None, aliases: dict[str, str]
) -> str:
    """``aliases``' name for a triple, or its mechanical name."""
    return aliases.get(alias_key(family, subtype, polarity)) or type_name(
        family, subtype, polarity
    )


@cache
def frame_axes(pitch: float, roll: float, yaw: float) -> tuple[Vec3, Vec3]:
    """``(axis, side)`` in the stud frame for a BrickNet connector frame.

    "Stud frame" is :data:`LDRAW_TO_STUD`'s target: LDraw's axes remapped to
    BrickLayer's, but *not* yet shifted by the part's own seating -- a part's
    :attr:`~bricklayer.ldraw.partdata.PartRecord.ldraw_to_element_pose` does
    that afterwards, to the decoded connectors.

    Cached: the whole catalogue uses only a couple of dozen distinct frames, and
    the overwhelming majority of rows are the identity ``(0, 0, 0)``.

    BrickNet composes a frame as ``Ry(yaw) @ Rx(pitch) @ Rz(roll)`` in degrees
    (see its ``data.py``), and **a frame's mating axis is its -Y**. ``side`` is
    the frame's +X: the reference BrickNet's yaw rotation sweeps, and the roll
    reference BrickLayer mates on.

    Composed through :func:`~..geometry.linalg.rotation_about`, which keeps right
    angles exact: connector axes are compared *exactly* against
    :class:`Direction`, so a 6e-17 residue would unmark grid connectors.
    """
    frame = (
        rotation_about(_LDRAW_Y, yaw)
        @ rotation_about(_LDRAW_X, pitch)
        @ rotation_about(_LDRAW_Z, roll)
    )
    return _ldraw_direction(-(frame @ _LDRAW_Y)), _ldraw_direction(frame @ _LDRAW_X)


def _register_rules(
    types: dict[str, ConnectorType],
    parsed: ConnectorTypesRaw,
    known: set[_Triple],
) -> None:
    """Register every mating rule implied by ``parsed``: the mate tables, each
    polarized ``in``/``on`` pair, and the authored pairs."""
    # Each unpolarized mate table is paired with the family whose joint it
    # uses. The joint comes from the table, not from either end's family: a
    # stud-grid pair crosses families (``antistud`` is a ``hole``, ``stud`` is
    # a ``stud``), so reading it off one end would pick by accident of order.
    for table, family in ((parsed.stud_mates, "stud"), (parsed.axle_mates, "axle")):
        if not table:
            continue  # an unused table needs no joint declared for its family
        joint = _family_joint(parsed, family)
        for a, b in table:
            mark_compatible(types[a], types[b], joint=joint)

    for family, subtype in sorted({(f, s) for f, s, p in known if p is not None}):
        names = [
            resolve_name(family, subtype, polarity, parsed.aliases)
            for polarity in ("in", "on")
            if (family, subtype, polarity) in known
        ]
        if len(names) != 2:
            continue  # a lone polarity has nothing to mate with
        mark_compatible(
            types[names[0]],
            types[names[1]],
            joint=_polarized_joint(parsed, family, subtype),
        )

    for pair in parsed.authored:
        a, b = pair.types
        mark_compatible(types[a], types[b], joint=JointKind[pair.joint])


def _polarized_joint(parsed: ConnectorTypesRaw, family: str, subtype: str) -> JointKind:
    """The joint a polarized subtype mates under.

    A family may list the subtypes whose orientation is strict; the rest of that
    family pairs on position alone in BrickNet, so they are free to roll.
    """
    oriented = parsed.oriented_subtypes.get(family)
    if oriented is not None and subtype not in oriented:
        return JointKind.REVOLUTE
    return _family_joint(parsed, family)


def _family_joint(parsed: ConnectorTypesRaw, family: str) -> JointKind:
    try:
        return JointKind[parsed.family_joints[family]]
    except KeyError:
        raise ValueError(f"no joint declared for connector family {family!r}") from None


def _split(key: str) -> _Triple:
    """A ``family/subtype[/polarity]`` key as a triple."""
    parts = key.split("/")
    if len(parts) == 2:
        return parts[0], parts[1], None
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    raise ValueError(f"not a connector triple key: {key!r}")


def _triple_order(triple: _Triple) -> tuple[str, int, str, str]:
    """Sort triples with integer subtypes in numeric order, not lexical."""
    family, subtype, polarity = triple
    return family, int(subtype) if subtype.isdigit() else -1, subtype, polarity or ""


def _facing_pair(connector: ConnectorRaw) -> tuple[Vec3, Vec3]:
    """A connector's ``(axis, side)``, from whichever spelling it carries."""
    if connector.axis is not None and connector.side is not None:
        return _facing(connector.axis), _facing(connector.side)
    return frame_axes(connector.pitch, connector.roll, connector.yaw)


def _facing(value: _Facing) -> Vec3:
    """A connector axis/side from a Direction name or a raw unit vector."""
    return Direction[value].value if isinstance(value, str) else Vec3(*value)


def _ldraw_direction(vec: Vec3) -> Vec3:
    """An LDraw-frame direction as a stud-frame unit vector."""
    mapped = LDRAW_TO_STUD @ vec
    return mapped / mapped.norm()
