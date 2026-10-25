"""Shared fixtures for the bricklayer test suite."""

import math
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from math import ceil, floor

import numpy as np
import pytest

from bricklayer import (
    Color,
    Connector,
    ConnectorType,
    Element,
    LegoBuild,
    PartSpec,
    Placement,
    Pose,
    Position,
    Vec3,
    brick,
)
from bricklayer.geometry import LegoGeometry, connections
from bricklayer.geometry.base import alignment_box_of
from bricklayer.geometry.connections import mark_compatible
from bricklayer.geometry.spatial import BUILD_TOLERANCE
from bricklayer.ldraw.conversion import pose_to_ldraw
from bricklayer.ldraw.meshes import Mesh
from bricklayer.ldraw.partdata import STUD_HEIGHT
from bricklayer.modeling.build import NameRef


@pytest.fixture
def model():
    """A fresh, empty LegoBuild."""
    return LegoBuild()


@pytest.fixture
def turntable():
    def build(*, motion=None, mounting=None):
        model = LegoBuild()
        base = model.add_raw(Element("3680", Color.WHITE), name="base")
        top = model.connect(
            Element("3679", Color.RED),
            "turntable_pin",
            to=base.find_connector("turntable_socket"),
            mounting=mounting,
            motion=motion,
            name="top",
        )
        return model, base, top

    return build


@pytest.fixture
def anchored():
    """An element re-anchored with its alignment-box min corner at the origin.

    Elements are centered on their alignment box; geometry tests read more
    naturally in min-corner coordinates (stud cell (x, y) at x/y..x/y+1), so
    they assert on this anchored view instead of the raw element.
    """

    def _anchor(element: Element) -> Placement:
        return Placement.at(element)

    return _anchor


@dataclass(frozen=True, slots=True)
class HandAuthoredElement(Element):
    """An :class:`Element` whose geometry is stated rather than measured.

    A real element reads its geometry off its LDraw part, so a double carrying
    geometry no real part has must declare its own; the spec it borrows only
    names the part it pretends to be.
    """

    connectors: frozenset[Connector] = frozenset()
    bounding_box: tuple[Position, Position] = (Position(0, 0, 0), Position(1, 1, 1))

    @property
    def alignment_box(self) -> tuple[Position, Position]:
        return alignment_box_of(self.connectors, self.bounding_box)


@pytest.fixture
def element_with():
    """Factory for a custom element exposing just the given connectors, in a
    unit bounding box unless another is given.

    Each double gets its own color, because elements compare by spec and color:
    same-spec doubles would otherwise be equal and hash equal despite carrying
    different hand-authored geometry, and two of them would silently collapse
    into one in a set or in ``list_elements()``.
    """
    colors = iter(Color)

    def _make(
        connectors: Iterable[Connector],
        bounding_box: tuple[Position, Position] = (
            Position(0, 0, 0),
            Position(1, 1, 1),
        ),
    ) -> Element:
        return HandAuthoredElement(
            "3005",
            next(colors),
            frozenset(connectors),
            bounding_box,
        )

    return _make


@pytest.fixture
def compatible_connector_types():
    """A freshly registered, compatible ``(tab, slot)`` pair (fixed)."""
    tab = ConnectorType("tab")
    slot = ConnectorType("slot")
    mark_compatible(tab, slot)
    return tab, slot


@pytest.fixture
def patch_connector_rules_registry(monkeypatch):
    """Isolate the global connector-compatibility registry for one test."""
    monkeypatch.setattr(connections, "_RULES", dict(connections._RULES))
    monkeypatch.setattr(
        connections,
        "_SLIDING_PARTNERS",
        {t: set(ps) for t, ps in connections._SLIDING_PARTNERS.items()},
    )


@pytest.fixture
def connector_specs():
    """Project connectors to the value tuples :func:`same_connector` compares:
    ``(type, position, axis, side, length)``.

    Connectors compare by identity (each is a distinct point on a part), so
    tests that assert *which* connector points a part has compare these
    value projections instead of the connectors themselves. Accepts a
    :class:`LegoGeometry` (uses its ``connectors``) or any iterable of
    connectors.
    """

    def _round(v):
        # Quantize a vector's components so float noise from posed geometry
        # doesn't defeat set comparison.
        return tuple(round(c, 6) for c in v)

    def _project(source: LegoGeometry | Iterable[Connector]) -> frozenset:
        conns = source.connectors if isinstance(source, LegoGeometry) else source
        return frozenset(
            (c.type, _round(c.position), _round(c.axis), _round(c.side), c.length)
            for c in conns
        )

    return _project


@pytest.fixture
def filled_region():
    """The grid cells a model's parts occupy, by their alignment boxes.

    Reduces a model to the cells its parts claim on the build grid -- ``x``/``y``
    in studs, ``z`` in plates -- so tests can compare *layout* independently of
    how a region is decomposed into parts. This is deliberately grid-based rather
    than mesh-based: a collision mesh is a hollow shell, so voxelizing one would
    report a brick's underside cavity as empty.
    """

    def _covered(geometry) -> frozenset[tuple[int, int, int]]:
        if isinstance(geometry, LegoBuild):
            boxes = [p.alignment_box for p in geometry.flattened_placements]
        else:
            boxes = [geometry.alignment_box]
        cells: set[tuple[int, int, int]] = set()
        for lo, hi in boxes:
            cells.update(
                (x, y, z)
                for x in range(
                    floor(lo.x + BUILD_TOLERANCE), ceil(hi.x - BUILD_TOLERANCE)
                )
                for y in range(
                    floor(lo.y + BUILD_TOLERANCE), ceil(hi.y - BUILD_TOLERANCE)
                )
                for z in range(
                    floor(3 * lo.z + BUILD_TOLERANCE), ceil(3 * hi.z - BUILD_TOLERANCE)
                )
            )
        return frozenset(cells)

    return _covered


@pytest.fixture
def part_from_spec():
    """Build one catalogued part directly from its spec."""

    def fn(spec: PartSpec, color: Color = Color.WHITE) -> Element:
        return Element(spec.ldraw_id, color)

    return fn


@pytest.fixture
def assert_cuboid_geometry(part_from_spec):
    """Create an element from the spec, and assert its cuboid geometry is present and as expected."""

    def fn(
        geom: LegoGeometry | PartSpec,
        w: int,
        d: int,
        h: float,
        *,
        check_connectors: bool = True,
        has_studs: bool = True,
        has_antistuds: bool = True,
        check_bounding_box: bool = True,
        check_alignment_box: bool = True,
        tol: float = BUILD_TOLERANCE,
    ):
        if isinstance(geom, PartSpec):
            geom = part_from_spec(geom)

        lo = 0 if has_antistuds else -h
        hi = lo + h + (STUD_HEIGHT if has_studs else 0)
        # The alignment box floors on the antistuds and tops out at the
        # highest stud, or at the part's own top when it has none.
        align_h = h if has_antistuds else 0

        if check_connectors:
            assert geom.connectors, geom
        if has_studs:
            assert geom.find_connectors("stud"), geom
        if has_antistuds:
            assert geom.find_connectors("antistud"), geom
        if check_bounding_box:
            assert geom.bounding_box == (
                pytest.approx((-w / 2, -d / 2, lo), abs=tol),
                pytest.approx((w / 2, d / 2, hi), abs=tol),
            ), geom
        if check_alignment_box:
            assert geom.alignment_box == (
                pytest.approx((-w / 2, -d / 2, 0)),
                pytest.approx((w / 2, d / 2, align_h)),
            ), geom

    return fn


@pytest.fixture
def assert_contains_connectors():
    """Assert that a geometry contains connectors of the given type in the given positions and facings.

    The geometry may still contain other connectors, but the given set must be present.
    """

    def _assert_contains_connectors(
        geom: LegoGeometry,
        conn_type: str | Iterable[str],
        expected: Iterable[tuple[Position, Vec3]],
    ):
        for pos, axis in expected:
            closest = geom.find_connectors(conn_type, toward=pos, facing=axis)[0]
            assert closest.position == pytest.approx(pos, abs=BUILD_TOLERANCE), geom
            assert closest.axis == pytest.approx(axis), geom

    return _assert_contains_connectors


@pytest.fixture
def element_of():
    """Get the named Element from a LegoBuild, by name or by nested path."""

    def _element_of(model: LegoBuild, name: NameRef) -> Element:
        elem = model.named(name).content
        assert isinstance(elem, Element)
        return elem

    return _element_of


@pytest.fixture
def assert_named_has_color(element_of):
    def _assert_named_has_color(model: LegoBuild, name: str, color: Color) -> None:
        elem = element_of(model, name)
        assert elem.color is color

    return _assert_named_has_color


@pytest.fixture
def make_grid():
    """Place ``pieces`` on the ground in a roughly square, row-major grid and return the assembled model.

    Every cell is sized to the largest piece's footprint, so the grid is uniform and no two pieces overlap.

    If ``n_cols`` is given, the grid has that many columns; otherwise it is as square as possible.

    With ``include_anchor_bricks`` a 1x1 red brick is placed at the minimum corner of each piece,
    to test that ``add`` anchors the piece to the grid correctly.

    With ``group=True`` each individual part is wrapped in its own named one-part
    sub-model, so per-part geometry overlays can be attached to the exact part they belong to.
    """

    def _make_grid(
        pieces: Collection[Element | LegoBuild],
        *,
        n_cols: int | None = None,
        include_anchor_bricks: bool = True,
        group: bool = False,
    ) -> LegoBuild:
        n_cols = n_cols or math.ceil(math.sqrt(len(pieces)))
        col_pitch = math.ceil(max(piece.width for piece in pieces)) + 1
        row_pitch = math.ceil(max(piece.depth for piece in pieces)) + 1

        m = LegoBuild()
        for index, piece in enumerate(pieces):
            row, col = divmod(index, n_cols)
            position = Position(col * col_pitch, row * row_pitch, 0)
            name = str(index)
            if group:
                m.add(_isolated_cell(index, piece), position, name=name)
            else:
                m.add(piece, position, name=name)
                if include_anchor_bricks:
                    m.add(
                        brick(1, 1, color=Color.RED),
                        Position(-1, -1, 0),
                        relative_to=name,
                    )
        return m

    def _isolated_cell(index: int, piece: Element | LegoBuild) -> LegoBuild:
        """A grid cell holding each of ``piece``'s parts in its own uniquely named one-part sub-model.

        Isolating every part lets per-part geometry overlays attach to the sub-model
        of the exact part they belong to.
        """
        cell = LegoBuild()
        for part, leaf in enumerate(_leaves(piece)):
            cell.add_raw(LegoBuild((leaf,)), Pose.IDENTITY, name=f"p{index}_{part}")
        return cell

    def _leaves(piece: Element | LegoBuild) -> list[Placement]:
        """A piece's individual parts, each as a placement in the piece's own frame.

        A whole-model piece (e.g. a door or minifig) is flattened to its element
        leaves; a bare element is its own single leaf.
        """
        if isinstance(piece, Element):
            return [Placement(piece)]
        return list(piece.flattened_placements)

    return _make_grid


@pytest.fixture
def cube_mesh():
    """A factory for a closed triangulated cube of edge ``size``, centered on ``at``.

    Collision and mesh-store tests share this solid with known bounds.
    """

    def _make(size: float = 20.0, at: tuple[float, float, float] = (0, 0, 0)) -> Mesh:
        h = size / 2
        corners = np.array(
            [(x, y, z) for x in (-h, h) for y in (-h, h) for z in (-h, h)], dtype=float
        ) + np.array(at, dtype=float)
        faces = np.array(
            [
                (0, 1, 3), (0, 3, 2),  # x = -h
                (4, 7, 5), (4, 6, 7),  # x = +h
                (0, 4, 5), (0, 5, 1),  # y = -h
                (2, 3, 7), (2, 7, 6),  # y = +h
                (0, 2, 6), (0, 6, 4),  # z = -h
                (1, 5, 7), (1, 7, 3),  # z = +h
            ],
            dtype=np.int32,
        )  # fmt: skip
        return Mesh(corners, faces)

    return _make


@pytest.fixture
def assert_same_pose():
    """Assert two poses agree to the precision LDraw is written in.

    A ``Pose`` compares exactly, but a round trip through LDraw units turns
    integer and Fraction components into floats, so the comparison is made in
    the frame the numbers are written in.
    """

    def _assert_same_pose(actual: Pose, expected: Pose) -> None:
        actual_rotation, actual_translation = pose_to_ldraw(actual)
        expected_rotation, expected_translation = pose_to_ldraw(expected)
        assert actual_rotation == pytest.approx(expected_rotation)
        assert actual_translation == pytest.approx(expected_translation)

    return _assert_same_pose
