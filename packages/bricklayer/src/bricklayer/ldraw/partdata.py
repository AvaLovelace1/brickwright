"""Everything the committed data files say about a part.

Its **geometry** -- a measured bounding box, an offset rotation, BrickNet's
connectors, and a collision mesh -- is merged out of the files listed in
:data:`_DATA_FILES` and read through :func:`record`, or, when a part's size is
all that is wanted, the cheaper :func:`measured_extents`.

Everything else comes from a file of its own, outside that merge: the part's
LDraw description (:func:`taxonomy`, plus :func:`part_ids` for the id set that
membership is checked against), how many LEGO sets it appears in
(:func:`popularity`, from Rebrickable's catalogue), its hand-authored shape (:func:`shape_override`) and
which shape class its LDraw category reads as (:func:`shape_classes`), and the
connector-type registry its connectors decode against
(:func:`get_connector_type`).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache, cached_property
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..geometry import Connector, ConnectorType, Mat3, Pose, Position, Rotation
from ..geometry.collision import PartCollider, build_collider
from ..geometry.linalg import vec_max, vec_min
from .connectivity import (
    ConnectorRaw,
    ConnectorTypesRaw,
    decode_connectors,
    expand_grouped_rows,
    load_connector_groups,
    load_connector_types,
)
from .conversion import LDrawVec
from .meshes import DATA_DIR, Mesh, mesh
from .naming import (
    TaxonomyRecord,
    mirrored_description,
    parse_description,
    part_name,
)

STUD_HEIGHT = 1 / 6  # height of a stud in bricks

# Raw LDraw descriptions; every taxonomy field is parsed from one at load, by
# :mod:`.naming`.
_TAXONOMY = "part_taxonomy.json"

_Vec = tuple[float, float, float]
_FlattenedMat3 = tuple[float, float, float, float, float, float, float, float, float]


class _RawRecord(BaseModel):
    """Schema for one raw part record across the JSON data files.

    ``connectors`` are the generated ones and ``extra_connectors`` the authored ones.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    bbox: tuple[_Vec, _Vec] | None = None
    connectors: tuple[ConnectorRaw, ...] = ()
    extra_connectors: tuple[ConnectorRaw, ...] = ()
    offset_rotation: str | _FlattenedMat3 | None = None


@dataclass(frozen=True)
class PartRecord:
    """LDraw geometry, collision mesh, and connectivity for one catalogued part.

    All coordinates are in BrickLayer coords (``Position``), in the part's local frame.
    ``_bbox`` is the measured bounding box (min, max) or ``None`` if the part was
    never measured. ``_connectors`` are the raw connectors decoded on demand.
    ``offset_rotation`` is an extra rotation for parts whose default pose differs
    between LDraw and BrickLayer.
    """

    part_id: str
    offset_rotation: Mat3 = Mat3.IDENTITY
    _bbox: tuple[LDrawVec, LDrawVec] | None = None
    _connectors: tuple[ConnectorRaw, ...] = ()

    @classmethod
    def from_raw(cls, part_id: str, raw: dict) -> PartRecord:
        parsed = _RawRecord.model_validate(_normalized(raw))
        return cls(
            part_id,
            offset_rotation=_to_mat3(parsed.offset_rotation),
            _bbox=_to_bbox(parsed.bbox),
            _connectors=parsed.connectors + parsed.extra_connectors,
        )

    @cached_property
    def offset(self) -> Position:
        """Offset that seats the grid-marked alignment box's bottom-center on the origin.

        Most LDraw parts are modeled with this origin already.
        Falls back to (0,0,0) when the part has no grid-marked connectors.
        """
        marked = self._grid_marked_positions
        if marked:
            lo, hi = vec_min(marked), vec_max(marked)
            bottom_center = Position((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z)
            return -bottom_center
        return Position.ZERO

    @cached_property
    def ldraw_to_element_pose(self) -> Pose:
        """The pose that turns the part's raw LDraw frame into its element frame.

        This is the composition of :attr:`offset` and any :attr:`offset_rotation`.
        """
        seat = Pose(translation=self.offset)
        turn = Pose(self.offset_rotation)
        return turn.compose(seat)

    def ldraw_pose(self, element_pose: Pose) -> Pose:
        """The pose of the part's raw LDraw frame when its element sits at
        ``element_pose``."""
        return element_pose.compose(self.ldraw_to_element_pose)

    def element_pose(self, ldraw_pose: Pose) -> Pose:
        """The element pose whose :meth:`ldraw_pose` is ``ldraw_pose``."""
        return ldraw_pose.compose(self._element_to_ldraw_pose)

    @cached_property
    def _element_to_ldraw_pose(self) -> Pose:
        return self.ldraw_to_element_pose.inverse

    @property
    def ldraw_bounds(self) -> tuple[LDrawVec, LDrawVec] | None:
        """The measured bounding box ``(min, max)`` in the part's **raw LDraw
        frame (LDU)**, or ``None`` if the part was never measured.

        The frame the part's own geometry lives in, so this is what a caller
        drawing or projecting that geometry wants; :attr:`bounding_box` answers
        the same question in the element frame, in studs.
        """
        return self._bbox

    @cached_property
    def bounding_box(self) -> tuple[Position, Position]:
        """The measured bounding box in the part's element frame.

        Degenerate at the origin when the part was never measured.
        """
        corners = self._corners(self.ldraw_to_element_pose)
        return corners or (Position.ZERO, Position.ZERO)

    @cached_property
    def measured_extents(self) -> Position:
        """The measured box's size along each axis (zero if unmeasured).

        Applies only :attr:`offset_rotation` -- a translation cancels in
        ``hi - lo`` -- so it needs no connector data.
        """
        corners = self._corners(Pose(self.offset_rotation))
        if corners is None:
            return Position.ZERO
        lo, hi = corners
        return hi - lo

    def _corners(self, pose: Pose) -> tuple[Position, Position] | None:
        """The measured box's corners through ``pose``, or ``None`` if unmeasured."""
        if self._bbox is None:
            return None
        a, b = (pose.apply(v.to_position()) for v in self._bbox)
        return vec_min((a, b)), vec_max((a, b))

    @property
    def collision_mesh(self) -> Mesh:
        """The part's collision mesh, in its **raw LDraw frame (LDU)**.

        Collision poses the mesh, so one mesh serves every placement of the part.
        """
        return mesh(self.part_id)

    @cached_property
    def collider(self) -> PartCollider:
        """Collision geometry over :attr:`collision_mesh`, built once per part."""
        return build_collider(self.collision_mesh)

    @cached_property
    def connectors(self) -> tuple[Connector, ...]:
        """The part's typed connectors in its element frame."""
        return tuple(
            c.transformed(self.ldraw_to_element_pose)
            for c in self._connectors_raw_frame
        )

    @cached_property
    def connector_set(self) -> frozenset[Connector]:
        """:attr:`connectors` as a set, shared by every element of this part."""
        return frozenset(self.connectors)

    @cached_property
    def _connectors_raw_frame(self) -> tuple[Connector, ...]:
        """The part's typed connectors in its raw LDraw frame."""
        return tuple(decode_connectors(self._connectors, all_connector_types()))

    @cached_property
    def _grid_marked_positions(self) -> tuple[Position, ...]:
        """Positions of the grid-oriented connectors, in the raw LDraw part frame.

        Grid alignment is not required: :attr:`offset` is computed from these.
        """
        return tuple(
            c.position for c in self._connectors_raw_frame if c.is_grid_oriented
        )


def _to_mat3(value: str | _FlattenedMat3 | None) -> Mat3:
    """A record's ``offset_rotation``: a :class:`Rotation` name, a flattened
    3x3, or absent."""
    if value is None:
        return Mat3.IDENTITY
    if isinstance(value, str):
        return Rotation[value].matrix
    return Mat3.from_flattened(value)


def _to_bbox(value: tuple[_Vec, _Vec] | None) -> tuple[LDrawVec, LDrawVec] | None:
    """A record's ``bbox`` corner pair as LDraw-frame vectors."""
    return None if value is None else (LDrawVec(*value[0]), LDrawVec(*value[1]))


def _load_data_file(name: str) -> dict[str, Any]:
    return json.loads((DATA_DIR / name).read_text())


@cache
def _parts(name: str) -> dict[str, Any]:
    """The ``parts`` table of one committed data file, parsed lazily, once."""
    return _load_data_file(name)["parts"]


# The geometry files, in merge order: ``bbox``, ``offset_rotation``, and any
# hand-authored geometry connectors. The flag marks an override file: its
# ``connectors`` accumulate into ``extra_connectors``, and every other key it
# carries replaces the generated one.
_GEOMETRY_DATA_FILES = (
    ("part_geometry.json", False),
    ("part_geometry_overrides.json", True),
    ("part_offset_rotations.json", True),
)

# Every data file :func:`record` merges, in merge order.
_DATA_FILES = (
    *_GEOMETRY_DATA_FILES,
    ("part_connectivity.json", False),
    ("part_connectivity_overrides.json", True),
)


def _merged(part_id: str, files: tuple[tuple[str, bool], ...]) -> dict[str, Any] | None:
    """``part_id``'s raw records in ``files`` merged in order, unvalidated, or
    ``None`` if no file lists it.

    Validation is deferred to :class:`PartRecord`. Keys beginning with ``_`` are
    the data files' own annotations (``_part``, ``_note``) and are not part of a
    record.
    """
    rows = [
        (row, is_override)
        for name, is_override in files
        if (row := _parts(name).get(part_id)) is not None
    ]
    if not rows:
        return None
    merged: dict[str, Any] = {}
    for row, is_override in rows:
        for key, value in row.items():
            if key.startswith("_"):
                continue
            if is_override and key == "connectors":
                merged.setdefault("extra_connectors", []).extend(value)
            else:
                merged[key] = value
    return merged


@cache
def record(part_id: str) -> PartRecord:
    """The :class:`PartRecord` for ``part_id`` (empty if the part is unknown).

    Merges every data file, connectivity included, so reach for it only when
    a part's connectors or collision mesh are what you need. For its measured
    size, call :func:`measured_extents`.
    """
    raw = _merged(part_id, _DATA_FILES)
    return PartRecord(part_id) if raw is None else PartRecord.from_raw(part_id, raw)


@cache
def measured_extents(part_id: str) -> Position:
    """How big ``part_id`` measures along each axis -- zero if it was never
    measured, or is unknown. Reads only the geometry files.
    """
    raw = _merged(part_id, _GEOMETRY_DATA_FILES)
    if raw is None:
        return Position.ZERO
    return PartRecord.from_raw(part_id, raw).measured_extents


@cache
def part_ids() -> frozenset[str]:
    """Every part the catalog holds: each taxonomy row with a measured ``bbox``.

    Redirect-only rows have no geometry and are excluded, though
    :func:`taxonomy` still answers for them. Read from the geometry files only.
    """
    return frozenset(
        pid
        for pid in _parts(_TAXONOMY)
        if (_merged(pid, _GEOMETRY_DATA_FILES) or {}).get("bbox") is not None
    )


@cache
def taxonomy(part_id: str) -> TaxonomyRecord | None:
    """``part_id``'s LDraw description, parsed on demand, or ``None`` if we have
    none."""
    description = _parts(_TAXONOMY).get(part_id)
    return None if description is None else _parse_row(part_id, description)


@cache
def mirrored_part_id(part_id: str) -> str | None:
    """The catalogued part that is ``part_id``'s mirror image, or ``None``.

    The mirror image is the part whose description matches ``part_id``'s with
    the handedness word swapped (see
    :func:`~bricklayer.ldraw.naming.mirrored_description`). ``None`` when
    ``part_id`` is achiral, when no catalogued part carries that description,
    or when several do and neither the mould/decoration suffix nor connector
    provenance identifies a unique counterpart.
    """
    row = taxonomy(part_id)
    if row is None:
        return None
    description = mirrored_description(row)
    candidates = _ids_by_name().get(description, ()) if description is not None else ()
    if len(candidates) > 1:
        suffix = part_id.lstrip("0123456789")
        candidates = tuple(
            pid for pid in candidates if pid.lstrip("0123456789") == suffix
        )
    if len(candidates) > 1:
        records = _parts("part_connectivity.json")
        donors = {records.get(pid, {}).get("_source", pid) for pid in candidates}
        if len(donors) == 1 and (donor := next(iter(donors))) in candidates:
            return donor
    return candidates[0] if len(candidates) == 1 else None


@cache
def _ids_by_name() -> dict[str, tuple[str, ...]]:
    """Every catalogued part id grouped by the name its description gives it.

    Read off the raw descriptions: a name needs trimming, not a full parse.
    """
    descriptions = _parts(_TAXONOMY)
    index: dict[str, list[str]] = {}
    for part_id in part_ids():
        name = part_name(descriptions[part_id])
        index.setdefault(name, []).append(part_id)
    return {name: tuple(sorted(ids)) for name, ids in index.items()}


def _parse_row(part_id: str, description: str) -> TaxonomyRecord:
    """``description`` parsed into a taxonomy row; a parse failure names
    ``part_id``."""
    try:
        return parse_description(description)
    except Exception as e:
        raise ValueError(f"{part_id!r} ({description!r}): {e}") from e


def shape_override(part_id: str) -> dict[str, Any] | None:
    """The hand-authored shape for ``part_id``, or ``None`` if it derives.

    Returned as the raw ``{"type": ..., <field>: ...}`` mapping the file holds:
    :mod:`bricklayer.ldraw` must not import the catalog.
    """
    row = _parts("part_shape_overrides.json").get(part_id)
    return None if row is None else row["shape"]


def popularity(part_id: str) -> int:
    """How many LEGO sets contain ``part_id``, or 0 if we have no count.

    Search uses this to order equally-good matches, so a 0 means "rank last",
    never "error" -- roughly a third of the catalog is unscored, and those are
    overwhelmingly the obscure tail.
    """
    return _parts("part_popularity.json").get(part_id, 0)


@cache
def shape_classes() -> dict[str, dict[str, Any]]:
    """Raw ``category -> {"default": ..., "keywords": {...}}`` rows, by LDraw
    category -- which :class:`~bricklayer.parts.shape.PartShape` class a
    part of that category reads as. Raw mapping: :mod:`bricklayer.ldraw` must
    not import the catalog.
    """
    return _load_data_file("part_shape_classes.json")["categories"]


@cache
def connector_config() -> ConnectorTypesRaw:
    """The validated connector-type config, read and checked once per process.

    Public so the extraction pipeline resolves names through the same registry.
    """
    return ConnectorTypesRaw.model_validate(
        _load_data_file("part_connector_types.json")
    )


@cache
def all_connector_types() -> dict[str, ConnectorType]:
    """The connector-type registry, keyed by type name."""
    return load_connector_types(connector_config())


def get_connector_type(name: str) -> ConnectorType:
    """The :class:`ConnectorType` registered under ``name``; e.g. ``"stud"``."""
    return all_connector_types()[name]


@cache
def _connector_groups() -> dict[str, frozenset[ConnectorType]]:
    """The query names that stand for more than one type."""
    return load_connector_groups(connector_config(), all_connector_types())


def _resolve_query(name: str) -> frozenset[ConnectorType]:
    """Every type ``name`` stands for: a group if there is one (so a group can
    widen an existing name), else the type registered under it."""
    groups = _connector_groups()
    if name in groups:
        return groups[name]
    return frozenset({all_connector_types()[name]})


def resolve_connector_types(
    connector_type: ConnectorType | str | Iterable[ConnectorType | str],
) -> frozenset[ConnectorType]:
    """Every connector type a caller's type argument matches.

    One name can stand for several types (see :func:`_connector_groups`); anything
    already a :class:`ConnectorType` stands for itself.

    Raises:
        KeyError: if a name is neither a registered type nor a group.
    """
    items: Iterable[ConnectorType | str] = (
        (connector_type,)
        if isinstance(connector_type, str) or not isinstance(connector_type, Iterable)
        else connector_type
    )
    return frozenset(
        resolved
        for item in items
        for resolved in (_resolve_query(item) if isinstance(item, str) else (item,))
    )


def _normalized(raw: dict[str, Any]) -> dict[str, Any]:
    """``raw`` with grouped connector rows expanded to ``ConnectorRaw`` mappings."""
    grouped = raw.get("connectors")
    if not isinstance(grouped, dict):
        return raw
    return raw | {"connectors": expand_grouped_rows(grouped, all_connector_types())}
