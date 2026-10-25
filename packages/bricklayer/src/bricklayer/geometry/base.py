"""The geometric base class and alignment measurements for LEGO parts and models."""

from collections.abc import Iterable
from functools import cached_property
from math import ceil, floor

from .connections import (
    STUD_FAMILY,
    Connector,
    ConnectorType,
    snap_to_half_stud_grid,
)
from .linalg import Scalar, Vec3, dot, is_aligned, is_unit, vec_max, vec_min
from .spatial import Direction, Position, Rotation, as_position


class LegoGeometry:
    """Geometry shared by elements, placements, and models.

    Elements use local coordinates; placements use the containing model's frame.
    Models use the frame they were built in. Measurements update when content changes.
    """

    @property
    def connectors(self) -> frozenset[Connector]:
        """Points where a connection can be made."""
        raise NotImplementedError

    @property
    def bounding_box(self) -> tuple[Position, Position]:
        """The physically-measured `(min, max)` box."""
        raise NotImplementedError

    @cached_property
    def alignment_box(self) -> tuple[Position, Position]:
        """The `(min, max)` box used for grid placement and stacking.

        Grid-aligned connectors contribute 1x1 stud footprints and determine the bottom.
        The highest upward stud sets the top; without one (e.g. a tile), the physical
        bounding box sets the top. Models use only their unoccupied connectors.

        Without grid-marked connectors, it is derived from the physical bounding box.
        Width/depth are whole studs and height is in whole plates; thin parts can
        have zero alignment extent. Inspect the box rather than guessing offsets.
        """
        return alignment_box_of(self.connectors, self.bounding_box)

    @cached_property
    def width(self) -> Scalar:
        """Extent along X (studs) of the bounding box."""
        return self._extent(0)

    @cached_property
    def depth(self) -> Scalar:
        """Extent along Y (studs) of the bounding box."""
        return self._extent(1)

    @cached_property
    def height(self) -> Scalar:
        """Extent along Z (bricks) of the bounding box."""
        return self._extent(2)

    @cached_property
    def alignment_width(self) -> int:
        """Extent along X (studs) of the alignment box. Always an integer."""
        return int(self._extent(0, alignment_box=True))

    @cached_property
    def alignment_depth(self) -> int:
        """Extent along Y (studs) of the alignment box. Always an integer."""
        return int(self._extent(1, alignment_box=True))

    @cached_property
    def alignment_height(self) -> float:
        """Extent along Z (bricks) of the alignment box. Always an integer multiple of PLATE."""
        return float(self._extent(2, alignment_box=True))

    def rotated_footprint(self, rotation: Rotation) -> tuple[int, int]:
        """The alignment box's ``(width, depth)`` in studs after ``rotation``.

        An odd quarter turn swaps the two; a half turn leaves them as they are.
        """
        if rotation.quarter_turns % 2 == 1:
            return self.alignment_depth, self.alignment_width
        return self.alignment_width, self.alignment_depth

    @cached_property
    def center(self) -> Position:
        """The midpoint of the bounding box, in BrickLayer coordinates.

        Empty geometry returns ``Position(0, 0, 0)``.
        """
        bbox_min, bbox_max = self.bounding_box
        return (bbox_min + bbox_max) / 2

    def _extent(self, axis: int, *, alignment_box: bool = False) -> Scalar:
        bbox = self.alignment_box if alignment_box else self.bounding_box
        return bbox[1][axis] - bbox[0][axis]

    def find_connectors(
        self,
        connector_type: (
            ConnectorType | str | Iterable[ConnectorType | str] | None
        ) = None,
        toward: Position | tuple[float, float, float] | Direction | None = None,
        *,
        facing: Direction | Vec3 | None = None,
        count: int | None = None,
    ) -> list[Connector]:
        """The geometry's connectors, filtered and ordered by the given criteria.

        ``connector_type`` filters types; ``facing`` filters axis direction.
        ``toward`` orders nearest a position or furthest in a direction; ``None``
        uses a stable geometric order. ``count`` caps the results (default: all).
        Coordinates are local for an element, world for a placement.
        """
        from ..ldraw.partdata import resolve_connector_types

        if isinstance(toward, tuple):
            toward = as_position(toward)
        allowed_types = (
            None if connector_type is None else resolve_connector_types(connector_type)
        )
        if count is not None and count < 1:
            raise ValueError(f"count must be at least 1, got {count}")
        if isinstance(facing, Direction):
            facing = facing.value
        if facing is not None and not is_unit(facing):
            raise ValueError(f"facing must be a unit vector, got {facing!r}")
        candidates = sorted(
            (
                c
                for c in self.connectors
                if (allowed_types is None or c.type in allowed_types)
                and (facing is None or is_aligned(c.axis, facing))
            ),
            key=_connector_order,
        )
        if isinstance(toward, Direction):
            direction = toward.value
            candidates.sort(key=lambda c: -dot(c.position.to_stud_units(), direction))
        elif toward is not None:
            target = toward
            candidates.sort(key=lambda c: (c.position - target).to_stud_units().norm())
        return candidates[:count]

    def find_connector(
        self,
        connector_type: ConnectorType
        | str
        | Iterable[ConnectorType | str]
        | None = None,
        toward: Position | tuple[float, float, float] | Direction | None = None,
        *,
        facing: Direction | Vec3 | None = None,
    ) -> Connector:
        """Find one connector using the filters and ordering of :meth:`find_connectors`.

        With ``toward``, return the first ranked match. Otherwise require exactly
        one match. Raises ``ValueError`` if none match or the choice is ambiguous.
        ``connect`` takes a world-frame target connector from a placement.
        """
        from ..ldraw.partdata import resolve_connector_types

        types = (
            None if connector_type is None else resolve_connector_types(connector_type)
        )
        matches = self.find_connectors(types, toward=toward, facing=facing)
        label = (
            "matching" if types is None else " or ".join(sorted(t.name for t in types))
        )
        if not matches:
            raise ValueError(f"{self!r} has no {label} connector")
        if len(matches) > 1 and toward is None:
            raise ValueError(
                f"{label} is ambiguous on {self!r}: it has {len(matches)} such connectors"
            )
        return matches[0]


def _connector_order(c: Connector) -> tuple[Scalar, ...]:
    """A stable geometric sort key for a connector."""
    return *c.position, *c.axis, *c.side, c.length


def alignment_box_of(
    connectors: Iterable[Connector], bounding_box: tuple[Position, Position]
) -> tuple[Position, Position]:
    """The :attr:`LegoGeometry.alignment_box` of these connectors and bounding box."""
    marked = [c for c in connectors if c.is_grid_marked]
    if not marked:
        lo, hi = bounding_box
        lo = -(-lo).align_to_grid()
        return lo, vec_max((lo, hi.align_to_grid()))
    positions = [c.position for c in marked]
    lo, hi = vec_min(positions), vec_max(positions)
    studs = [c.position.z for c in marked if c.type.family == STUD_FAMILY]
    top = max(studs) if studs else bounding_box[1].align_to_grid().z
    low = snap_to_half_stud_grid(Position(lo.x - 0.5, lo.y - 0.5, lo.z))
    high = snap_to_half_stud_grid(Position(hi.x + 0.5, hi.y + 0.5, max(top, lo.z)))
    x0, x1 = _whole_stud_span(low.x, high.x)
    y0, y1 = _whole_stud_span(low.y, high.y)
    return Position(x0, y0, low.z), Position(x1, y1, high.z)


def _whole_stud_span(lo: Scalar, hi: Scalar) -> tuple[Scalar, Scalar]:
    """``lo``/``hi`` on the half-stud grid, widened outward to whole studs when
    they span a fractional number of studs."""
    if (hi - lo) % 1 == 0:
        return lo, hi
    return floor(lo), ceil(hi)
