"""Diagnostic LDraw renders of each part's geometry.

Two file-regression baselines draw the catalogued pieces in a grid, then overlay
their geometry as raw LDraw primitives so the bounding box and connector frames
can be eyeballed.

- **Bounding box** files wireframe each part's bounding box.
- **Connector** files mark every connector point with a small sphere and draw
  a ray for its ``axis``, its ``side``, and -- when non-zero -- a bar for its
  slide ``length``, straddling the point because the reach is symmetric.
  The sphere is colored by the connector's *family* (studs one color, holes
  another, ...) so like connectors read alike across the grid; a comment legend
  spliced into the main block names the color of every family present.
"""

from collections.abc import Callable, Iterable

import pytest

from bricklayer import Color, Cuboid, Element, LegoBuild, Position, Vec3
from bricklayer.construction import minifigure
from bricklayer.construction.architecture import _FRAMES
from bricklayer.construction.registry import COMPONENT_FACTORIES
from bricklayer.geometry.connections import Connector
from bricklayer.geometry.linalg import cross, perpendicular
from bricklayer.io.writer import _MAIN_NAME, to_ldraw
from bricklayer.ldraw.conversion import LDrawVec, format_ldu
from bricklayer.modeling.placement import Placement

# Inserts are covered by window/door assemblies; minifig parts by the showcase.
_VISUALIZED_COMPONENTS = {
    factory.__name__: factory
    for factory in COMPONENT_FACTORIES
    if factory not in {f for f, _ in minifigure._FACTORIES}
}
_VISUALIZED_COMPONENTS["frame"] = _FRAMES

# LDraw color for the bounding-box wireframe
_BOUNDING_BOX_COLOR = 4

# For a connector whose family has no assigned color.
_FALLBACK_COLOR = Color.WHITE

_FAMILY_COLORS: dict[str, Color] = {
    "stud": Color.VIBRANT_YELLOW,
    "hole": Color.DARK_BLUE,
    "axle": Color.RED,
    "hinge": Color.GREEN,
    "ball": Color.REDDISH_ORANGE,
    "fixed": Color.SKY_BLUE,
    "authored": Color.MEDIUM_BROWN,
}


# Connector-frame ray colors (LDraw color ids): the mating ``axis``, the
# ``side`` roll reference, and the slide ``length``.
_AXIS_COLOR = 4
_SIDE_COLOR = 2
_LENGTH_COLOR = 1

# Overlay sizing, chosen just large enough to read against a stud (20 LDU).
_SPHERE_RADIUS = 3.0  # LDU
_LINE_RADIUS = 1.0  # LDU
_AXIS_STUDS = 0.6  # ray length for the (unit) axis direction
_SIDE_STUDS = 0.35  # ray length for the (unit) side direction

# The LDraw unit-cylinder primitive: radius 1 in the X-Z plane, running along
# +Y from y=0 to y=1.
_CYLINDER = "4-4cyli.dat"

# The eight cuboid corners are generated as ``z`` fastest-varying then ``y``
# then ``x`` (see :attr:`Cuboid.corners`); these index pairs are the 12 edges,
# each joining two corners that differ along a single axis.
_BOX_EDGES = (
    (0, 4), (1, 5), (2, 6), (3, 7),  # along x
    (0, 2), (1, 3), (4, 6), (5, 7),  # along y
    (0, 1), (2, 3), (4, 5), (6, 7),  # along z
)  # fmt: skip


def _point(v: LDrawVec) -> str:
    return f"{format_ldu(v.x)} {format_ldu(v.y)} {format_ldu(v.z)}"


def _cylinder(start: LDrawVec, end: LDrawVec, radius: float, color: int) -> str | None:
    """A type-1 reference to ``_CYLINDER`` spanning ``start`` to ``end``.

    ``None`` for a degenerate zero-length segment, which has no direction to orient.
    """
    axis = end - start
    length = axis.norm()
    if length == 0:
        return None
    unit = axis / length
    perp = perpendicular(unit)
    u = perp * radius  # local x, a radius across the tube
    w = cross(unit, perp) * radius  # local z, the remaining radius
    # Columns of the orientation matrix are the images of local x, y, z.
    matrix = (u.x, axis.x, w.x, u.y, axis.y, w.y, u.z, axis.z, w.z)
    entries = " ".join(format_ldu(v) for v in matrix)
    return f"1 {color} {_point(start)} {entries} {_CYLINDER}"


def _wire_box(box: Cuboid, color: int) -> list[str]:
    """The 12 edge cylinders outlining ``box`` in ``color``."""
    corners = [LDrawVec.from_position(c) for c in box.corners]
    edges = (
        _cylinder(corners[i], corners[j], _LINE_RADIUS, color) for i, j in _BOX_EDGES
    )
    return [edge for edge in edges if edge is not None]


def _ray(start: Position, direction: Vec3, studs: float, color: int) -> str | None:
    """A cylinder ``studs`` long from ``start`` along the unit ``direction``."""
    end = start + Position.from_stud_units(direction * studs)
    a, b = LDrawVec.from_position(start), LDrawVec.from_position(end)
    return _cylinder(a, b, _LINE_RADIUS, color)


def _span(center: Position, direction: Vec3, studs: float, color: int) -> str | None:
    """A cylinder centered on ``center``, reaching ``studs`` each way along ``direction``.

    A connector's slide reach is symmetric about its point, so a
    :attr:`~bricklayer.geometry.connections.Connector.length` draws as a bar
    straddling the point.
    """
    start = center - Position.from_stud_units(direction * studs)
    return _ray(start, direction, 2 * studs, color)


def _sphere(center: Position, radius: float, color: int) -> str:
    """A type-1 reference to the unit sphere primitive, scaled to ``radius`` LDU."""
    p = LDrawVec.from_position(center)
    return f"1 {color} {_point(p)} {radius} 0 0 0 {radius} 0 0 0 {radius} 8-8sphe.dat"


def _conn_key(conn: Connector) -> tuple:
    return (
        tuple(conn.position),
        tuple(conn.axis),
        tuple(conn.side),
        conn.length,
        conn.type.name,
    )


def _bounding_box_overlay(placements: Iterable[Placement]) -> list[str]:
    """Wireframes of every part's bounding box."""
    lines: list[str] = []
    for placement in placements:
        lines += _wire_box(
            Cuboid.spanning(*placement.bounding_box), _BOUNDING_BOX_COLOR
        )
    return lines


def _sphere_color(conn: Connector) -> int:
    """The palette LDraw color for ``conn``'s family (fallback for unknowns)."""
    return _FAMILY_COLORS.get(conn.type.family, _FALLBACK_COLOR).ldraw_id


def _legend(model: LegoBuild) -> list[str]:
    """Comment lines naming the sphere color of each connector family present."""
    present = {
        conn.type.family
        for placement in model.flattened_placements
        for conn in placement.connectors
    }
    if not present:
        return []
    lines = ["0 // connector sphere colors (by family):"]
    for family in sorted(present):
        color = _FAMILY_COLORS.get(family, _FALLBACK_COLOR)
        lines.append(f"0 //   {family}: {color.ldraw_id} ({color.display_name})")
    return lines


def _connector_overlay(placements: Iterable[Placement]) -> list[str]:
    """A sphere (colored by type), axis/side rays, and a slide-length bar for every
    connector point. The type legend is emitted once, globally, by :func:`_grouped`."""
    lines: list[str] = []
    for placement in placements:
        for conn in sorted(placement.connectors, key=_conn_key):
            rays = [
                _sphere(conn.position, _SPHERE_RADIUS, _sphere_color(conn)),
                _ray(conn.position, conn.axis, _AXIS_STUDS, _AXIS_COLOR),
                _ray(conn.position, conn.side, _SIDE_STUDS, _SIDE_COLOR),
            ]
            if conn.length > 0:
                rays.append(_span(conn.position, conn.axis, conn.length, _LENGTH_COLOR))
            lines += [ray for ray in rays if ray is not None]
    return lines


def _blocks(text: str) -> list[tuple[str, list[str]]]:
    """Split MPD ``text`` into ``(sub-file name, lines)`` blocks in order."""
    blocks: list[tuple[str, list[str]]] = []
    name, lines = _MAIN_NAME, []
    for line in text.splitlines():
        if line.startswith("0 FILE "):
            if lines:
                blocks.append((name, lines))
            name, lines = line.removeprefix("0 FILE "), [line]
        else:
            lines.append(line)
    blocks.append((name, lines))
    return blocks


def _leaf_key(placement: Placement) -> tuple:
    """A signature identifying a part's id, color, and piece-local pose, so
    repeats of the same part in the same place share a key."""
    element = placement.content
    assert isinstance(element, Element)
    pose = placement.pose
    return (
        element.spec.ldraw_id,
        element.color.ldraw_id,
        tuple(round(v, 4) for v in pose.translation),
        tuple(round(v, 4) for v in pose.rotation.flatten()),
    )


def _grouped(
    model: LegoBuild,
    overlay_fn: Callable[[Iterable[Placement]], list[str]],
    legend: list[str] | None = None,
    dedup: bool = False,
) -> str:
    """``to_ldraw(model)`` with each part's overlay spliced into that part's
    sub-model, and ``legend`` (if any) into the main block.

    ``model`` must be a grouped grid (``make_grid(pieces, group=True)``): each
    grid cell is a sub-model of one-part sub-models, one per individual part.
    ``overlay_fn`` is called with a part's single leaf placement to produce that
    part's primitives in the part sub-model's own frame.

    With ``dedup=True``, a part whose id/color/pose already appeared contributes
    no overlay -- so geometry shared across cells (e.g. the standard minifig body
    recurring in every figure) is drawn once while parts unique to one cell keep
    their overlay."""
    seen: set[tuple] = set()
    per_part: dict[str, list[str]] = {}
    for cell_placement in model.placements:
        cell = cell_placement.content
        assert isinstance(cell, LegoBuild), "grouped grid cells must be sub-models"
        for part_placement in cell.placements:
            solo = part_placement.content
            assert isinstance(solo, LegoBuild), "grouped grid parts must be sub-models"
            (leaf,) = solo.flattened_placements
            name = f"{cell.name_of(part_placement)}.ldr"
            key = _leaf_key(leaf)
            if dedup and key in seen:
                per_part[name] = []
            else:
                seen.add(key)
                per_part[name] = overlay_fn([leaf])
    out: list[str] = []
    for name, lines in _blocks(to_ldraw(model)):
        if name == _MAIN_NAME:
            if legend:  # after the block's `0 FILE`/`0`/`0 Name:` header
                lines[3:3] = legend
        else:
            lines += per_part.get(name, [])
        out += lines
    return "".join(line + "\n" for line in out)


class TestComponents:
    @pytest.mark.parametrize(
        "name,component", _VISUALIZED_COMPONENTS.items(), ids=_VISUALIZED_COMPONENTS
    )
    def test_component(
        self, name, component, file_regression, make_grid, components_in
    ):
        pieces = components_in(component)
        file_regression.check(
            to_ldraw(make_grid(pieces)),
            extension=".ldr",
            basename=f"components_{name}",
        )

    def test_minifigs(self, file_regression, make_grid, minifig_showcase):
        file_regression.check(
            to_ldraw(make_grid(minifig_showcase())),
            extension=".ldr",
            basename="components_minifigs",
        )


class TestBoundingBoxes:
    @pytest.mark.parametrize(
        "name,component", _VISUALIZED_COMPONENTS.items(), ids=_VISUALIZED_COMPONENTS
    )
    def test_component(
        self, name, component, file_regression, make_grid, components_in
    ):
        model = make_grid(components_in(component, color=Color.TRANS_CLEAR), group=True)
        file_regression.check(
            _grouped(model, _bounding_box_overlay),
            extension=".ldr",
            basename=f"bounding_box_{name}",
        )

    def test_minifigs(self, file_regression, make_grid, minifig_showcase):
        model = make_grid(minifig_showcase(color=Color.TRANS_CLEAR), group=True)
        file_regression.check(
            _grouped(model, _bounding_box_overlay, dedup=True),
            extension=".ldr",
            basename="bounding_box_minifigs",
        )


class TestConnectors:
    @pytest.mark.parametrize(
        "name,component", _VISUALIZED_COMPONENTS.items(), ids=_VISUALIZED_COMPONENTS
    )
    def test_component(
        self, name, component, file_regression, make_grid, components_in
    ):
        model = make_grid(components_in(component, color=Color.TRANS_CLEAR), group=True)
        file_regression.check(
            _grouped(model, _connector_overlay, _legend(model)),
            extension=".ldr",
            basename=f"connectors_{name}",
        )

    def test_minifigs(self, file_regression, make_grid, minifig_showcase):
        model = make_grid(minifig_showcase(color=Color.TRANS_CLEAR), group=True)
        file_regression.check(
            _grouped(model, _connector_overlay, _legend(model), dedup=True),
            extension=".ldr",
            basename="connectors_minifigs",
        )
