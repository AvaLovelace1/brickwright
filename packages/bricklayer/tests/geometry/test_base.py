from dataclasses import dataclass

import pytest

from bricklayer import Connector, Direction, Position, Rotation, Vec3, brick
from bricklayer.geometry.base import LegoGeometry
from bricklayer.geometry.connections import ConnectorType
from bricklayer.geometry.spatial import PLATE
from bricklayer.ldraw.partdata import get_connector_type

STUD = get_connector_type("stud")
ANTISTUD = get_connector_type("antistud")
OTHER = ConnectorType("test_other")


@dataclass(frozen=True)
class _Geometry(LegoGeometry):
    connectors: frozenset[Connector] = frozenset()
    bounding_box: tuple[Position, Position] = (Position.ZERO, Position.ZERO)


def _stud(x: float, y: float, z: float, type_: ConnectorType = STUD) -> Connector:
    return Connector(type_, Position(x, y, z), Direction.UP, Direction.FRONT)


def _facing_stud(direction: Direction, x: float = 0, y: float = 0) -> Connector:
    return Connector(STUD, Position(x, y, 0), direction)


class TestAlignmentBoxFallback:
    def test_grid_aligned_bounding_box_is_used_as_is(self):
        g = _Geometry(bounding_box=(Position(1, 2, 0), Position(3, 4, 1)))
        assert g.alignment_box == g.bounding_box

    def test_fractional_bounding_box_rounds_inward_to_the_grid(self):
        g = _Geometry(
            bounding_box=(Position(-0.75, -1, -0.1), Position(1.25, 1.5, 1.1))
        )
        assert g.alignment_box == (Position(0, -1, 0), Position(1, 1, 1))
        assert g.alignment_width == 1
        assert g.alignment_depth == 2
        assert g.alignment_height == 1

    def test_off_grid_connectors_do_not_contribute(self):
        off = Connector(STUD, Position(0.3, 0.5, 1), Direction.UP, Direction.FRONT)
        bbox = (Position.ZERO, Position(1, 1, 1))
        with_stud = _Geometry(connectors=frozenset({off}), bounding_box=bbox)
        body_only = _Geometry(bounding_box=bbox)
        assert not any(c.is_grid_marked for c in with_stud.connectors)
        assert with_stud.alignment_box == body_only.alignment_box

    def test_axis_thinner_than_a_grid_cell_collapses_to_the_rounded_min_corner(self):
        g = _Geometry(bounding_box=(Position(0.2, 0.2, 0), Position(0.8, 0.8, 1)))
        assert g.alignment_box == (Position(1, 1, 0), Position(1, 1, 1))

    def test_empty_geometry_stays_degenerate_at_the_origin(self):
        assert _Geometry().alignment_box == (Position.ZERO, Position(0, 0, 0))


class TestAlignmentBoxTop:
    """The top comes from the highest grid-marked stud, so what can be built
    on sets the height; a geometry showing none takes its own top instead."""

    def test_the_highest_stud_sets_the_top(self):
        g = _Geometry(
            connectors=frozenset({_stud(0.5, 0.5, 0, ANTISTUD), _stud(0.5, 0.5, 1)}),
            bounding_box=(Position.ZERO, Position(1, 1, 3)),
        )

        assert g.alignment_box[1].z == 1

    def test_a_lower_stud_does_not_lower_the_top(self):
        g = _Geometry(
            connectors=frozenset({_stud(0.5, 0.5, 1), _stud(1.5, 1.5, 2)}),
            bounding_box=(Position.ZERO, Position(2, 2, 5)),
        )

        assert g.alignment_box[1].z == 2

    def test_without_a_stud_the_bounding_box_sets_the_top(self):
        """An underside antistud is grid-marked and faces up, so a tile's
        only marked connector sits on its floor; the top comes from the
        bounding box, leaving the box a plate tall rather than a plane."""
        g = _Geometry(
            connectors=frozenset({_stud(0.5, 0.5, 0, ANTISTUD)}),
            bounding_box=(Position.ZERO, Position(1, 1, 2)),
        )

        assert g.alignment_box[1].z == 2
        assert g.alignment_height == 2

    def test_the_bounding_box_top_is_floored_to_the_grid(self):
        g = _Geometry(
            connectors=frozenset({_stud(0.5, 0.5, 0, ANTISTUD)}),
            bounding_box=(Position.ZERO, Position(1, 1, 1.9)),
        )

        assert g.alignment_box[1].z == pytest.approx(1 + 2 * PLATE)

    def test_the_top_never_falls_below_the_floor(self):
        g = _Geometry(
            connectors=frozenset({_stud(0.5, 0.5, 1, ANTISTUD)}),
            bounding_box=(Position.ZERO, Position(1, 1, 0)),
        )

        lo, hi = g.alignment_box
        assert hi.z == lo.z


class TestAlignmentBoxFootprint:
    def test_a_centered_odd_footprint_keeps_its_half_stud_corners(self):
        g = _Geometry(connectors=frozenset({_stud(0, 0, 0)}))

        assert g.alignment_box == (Position(-0.5, -0.5, 0), Position(0.5, 0.5, 0))
        assert g.alignment_width == 1

    def test_mixed_whole_and_half_stud_connectors_widen_to_whole_studs(self):
        g = _Geometry(
            connectors=frozenset({_stud(0.5, 0.5, 0), _stud(2, 1, 0)}),
            bounding_box=(Position.ZERO, Position(2.5, 1.5, 1)),
        )

        assert g.alignment_box == (Position(0, 0, 0), Position(3, 2, 0))
        assert g.alignment_width == 3
        assert g.alignment_depth == 2


class TestRotatedFootprint:
    """`rotated_footprint`: the alignment box's (width, depth) after a turn.
    An odd quarter turn swaps the pair; an even one leaves it alone."""

    @pytest.fixture
    def oblong(self):
        # 3 studs wide x 1 deep, grid-aligned so the alignment box matches.
        return _Geometry(bounding_box=(Position(0, 0, 0), Position(3, 1, 1)))

    @pytest.mark.parametrize("rotation", list(Rotation))
    def test_odd_quarter_turns_swap_width_and_depth(self, oblong, rotation):
        expected = (1, 3) if rotation.quarter_turns % 2 == 1 else (3, 1)
        assert oblong.rotated_footprint(rotation) == expected

    def test_a_square_footprint_is_unchanged_by_any_turn(self):
        square = _Geometry(bounding_box=(Position(0, 0, 0), Position(2, 2, 1)))
        assert {square.rotated_footprint(r) for r in Rotation} == {(2, 2)}


class TestFindConnectors:
    def test_returns_all_matches_ordered_by_nearness_to_a_position(self):
        a, b, c = _stud(0, 0, 0), _stud(2, 0, 0), _stud(5, 0, 0)
        g = _Geometry(connectors=frozenset({a, b, c}))
        assert g.find_connectors(toward=Position.ZERO) == [a, b, c]

    def test_count_limits_to_the_closest(self):
        near, far = _stud(0, 0, 0), _stud(5, 0, 0)
        g = _Geometry(connectors=frozenset({near, far}))
        assert g.find_connectors(toward=Position(1, 0, 0), count=1) == [near]

    def test_returns_fewer_than_requested_when_not_enough_connectors(self):
        a = _stud(0, 0, 0)
        g = _Geometry(connectors=frozenset({a}))
        assert g.find_connectors(toward=Position.ZERO, count=5) == [a]

    def test_measures_distance_in_stud_units_not_raw_coordinates(self):
        # z is in bricks: a 1-brick vertical gap is 6/5 studs, farther than a
        # 1-stud horizontal gap that would tie it in raw coordinates.
        horizontal, vertical = _stud(1, 0, 0), _stud(0, 0, 1)
        g = _Geometry(connectors=frozenset({horizontal, vertical}))
        assert g.find_connectors(toward=Position.ZERO) == [horizontal, vertical]

    def test_filters_by_connector_type(self):
        near_other = _stud(1, 0, 0, OTHER)
        far_stud = _stud(3, 0, 0, STUD)
        g = _Geometry(connectors=frozenset({near_other, far_stud}))
        assert g.find_connectors(STUD, Position.ZERO) == [far_stud]

    def test_filters_by_collection_of_connector_types(self):
        near_other = _stud(1, 0, 0, OTHER)
        far_stud = _stud(3, 0, 0, STUD)
        other = _stud(2, 0, 0, ConnectorType("other_type"))
        g = _Geometry(connectors=frozenset({near_other, far_stud, other}))
        assert g.find_connectors([OTHER, "stud"], Position.ZERO) == [
            near_other,
            far_stud,
        ]

    def test_returns_empty_when_no_connectors_match_the_type(self):
        g = _Geometry(connectors=frozenset({_stud(0, 0, 0, STUD)}))
        assert g.find_connectors(OTHER, Position.ZERO) == []

    def test_returns_empty_when_geometry_has_no_connectors(self):
        assert _Geometry().find_connectors(toward=Position.ZERO) == []

    def test_rejects_a_non_positive_count(self):
        g = _Geometry(connectors=frozenset({_stud(0, 0, 0)}))
        with pytest.raises(ValueError):
            g.find_connectors(toward=Position.ZERO, count=0)

    def test_orders_all_matches_by_extent_along_a_direction(self):
        # +x is LEFT, -x is RIGHT (see Direction).
        left, right = _stud(2, 0, 0), _stud(-2, 0, 0)
        g = _Geometry(connectors=frozenset({left, right}))
        assert g.find_connectors(toward=Direction.LEFT) == [left, right]
        assert g.find_connectors(toward=Direction.RIGHT) == [right, left]

    def test_orders_by_extent_along_a_direction(self):
        lo, mid, hi = _stud(0, 0, 0), _stud(0, 0, 1), _stud(0, 0, 2)
        g = _Geometry(connectors=frozenset({lo, mid, hi}))
        assert g.find_connectors(toward=Direction.UP) == [hi, mid, lo]
        assert g.find_connectors(toward=Direction.DOWN) == [lo, mid, hi]

    def test_extremal_search_honors_the_type_filter(self):
        far_stud, near_other = _stud(5, 0, 0, STUD), _stud(1, 0, 0, OTHER)
        g = _Geometry(connectors=frozenset({far_stud, near_other}))
        assert g.find_connectors(STUD, Direction.LEFT) == [far_stud]

    def test_toward_none_returns_every_matching_connector(self):
        a, b = _stud(0, 0, 0, STUD), _stud(5, 0, 0, STUD)
        other = _stud(2, 0, 0, OTHER)
        g = _Geometry(connectors=frozenset({a, b, other}))
        assert set(g.find_connectors(STUD)) == {a, b}
        assert set(g.find_connectors()) == {a, b, other}

    def test_toward_none_orders_deterministically_by_position(self):
        lo, mid, hi = _stud(0, 0, 0), _stud(1, 0, 0), _stud(2, 0, 0)
        g = _Geometry(connectors=frozenset({hi, lo, mid}))
        assert g.find_connectors() == [lo, mid, hi]

    def test_breaks_directional_ties_by_position(self):
        near, far = _stud(0, 0, 1), _stud(3, 0, 1)
        g = _Geometry(connectors=frozenset({far, near}))
        assert g.find_connectors(toward=Direction.UP) == [near, far]

    def test_count_limits_an_unordered_filter(self):
        conns = frozenset(_stud(i, 0, 0) for i in range(5))
        g = _Geometry(connectors=conns)
        assert len(g.find_connectors(count=2)) == 2


class TestFindConnectorsFacing:
    def test_keeps_only_connectors_pointing_that_way(self):
        front, back = _facing_stud(Direction.FRONT), _facing_stud(Direction.BACK)
        g = _Geometry(connectors=frozenset({front, back}))
        assert g.find_connectors(facing=Direction.FRONT) == [front]
        assert g.find_connectors(facing=Direction.BACK) == [back]

    def test_accepts_a_raw_unit_vector(self):
        up = _stud(0, 0, 0)
        g = _Geometry(connectors=frozenset({up, _facing_stud(Direction.FRONT)}))
        assert g.find_connectors(facing=Vec3(0, 0, 1)) == [up]

    def test_returns_empty_when_nothing_faces_that_way(self):
        g = _Geometry(connectors=frozenset({_facing_stud(Direction.FRONT)}))
        assert g.find_connectors(facing=Direction.LEFT) == []

    def test_combines_with_the_connector_type(self):
        stud = _facing_stud(Direction.FRONT)
        other = Connector(OTHER, Position(0, 1, 0), Direction.FRONT)
        g = _Geometry(connectors=frozenset({stud, other}))
        assert g.find_connectors(STUD, facing=Direction.FRONT) == [stud]

    def test_rejects_a_non_unit_facing_vector(self):
        g = _Geometry(connectors=frozenset({_stud(0, 0, 0)}))
        with pytest.raises(ValueError):
            g.find_connectors(facing=Vec3(0, 0, 2))


class TestFindConnector:
    """Search for a single connector by type and geometric criteria."""

    def test_resolves_by_connector_type(self):
        stud = _stud(0, 0, 0, STUD)
        g = _Geometry(connectors=frozenset({stud, _stud(1, 0, 0, OTHER)}))
        assert g.find_connector(STUD) is stud

    def test_resolves_by_type_name(self):
        stud = _stud(0, 0, 0, STUD)
        g = _Geometry(connectors=frozenset({stud}))
        assert g.find_connector("stud") is stud

    def test_no_connector_of_that_type_raises(self):
        g = _Geometry(connectors=frozenset({_stud(0, 0, 0, STUD)}))
        with pytest.raises(ValueError, match="has no test_other connector"):
            g.find_connector(OTHER)

    def test_ambiguous_type_raises(self):
        g = _Geometry(
            connectors=frozenset({_stud(0, 0, 0, STUD), _stud(1, 0, 0, STUD)})
        )
        with pytest.raises(ValueError, match="ambiguous"):
            g.find_connector(STUD)

    def test_find_connector_filters_and_orders(self):
        part = brick(2, 1)
        assert (
            part.find_connector("stud", toward=Direction.LEFT)
            == part.find_connectors("stud", toward=Direction.LEFT)[0]
        )
        assert (
            part.find_connector(["stud"], toward=(10, 0, 1), facing=Direction.UP)
            == part.find_connectors(
                "stud", toward=Position(10, 0, 1), facing=Direction.UP
            )[0]
        )
        with pytest.raises(ValueError, match="ambiguous"):
            part.find_connector("stud")
        with pytest.raises(ValueError, match="has no"):
            part.find_connector("stud", facing=Direction.DOWN)
