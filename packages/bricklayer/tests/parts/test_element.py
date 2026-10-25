"""Tests for element construction and physical part geometry."""

import math

import pytest

from bricklayer import (
    PLATE,
    Box,
    Chirality,
    Color,
    Direction,
    Disc,
    Element,
    Ell,
    Footprint,
    InvalidPartError,
    LegoBuild,
    LegoGeometry,
    Length,
    Mounting,
    PartSpec,
    Pose,
    Position,
    Rod,
    to_ldraw,
)
from bricklayer.geometry.spatial import BRICKS_PER_STUD
from bricklayer.ldraw import partdata
from bricklayer.ldraw.partdata import STUD_HEIGHT
from bricklayer.parts.catalog import all_parts

UNCATALOGUED = "not-a-catalogued-part"


A_BRICK = "3005"  # Brick  1 x  1


A_WIDE_BRICK = "3001"  # Brick  2 x  4


_STAIRS = "30134"


_CURVED_STAIRS = "28466"


_LADDER = "4175"


_LAMP_POST = "11062"


def _assert_catalog_connectors(elem: Element, *connector_types: str) -> None:
    """A part built from the catalog has connectors, and the connector types the
    part is expected to carry."""
    assert elem.connectors, elem.spec
    for connector_type in connector_types:
        assert elem.find_connectors(connector_type), elem.spec


@pytest.fixture
def assert_has_stud_wall(anchored, assert_contains_connectors):
    """Assert that the given geometry has a 1-stud-spaced grid of studs (or antistuds) on the ``facing`` face.

    The wall is expected to be ``face_width`` studs across and ``face_height``
    studs tall, with the min-stud at ``offset`` from its default position on the given face.
    """

    def _assert_has_stud_wall(
        geom: LegoGeometry,
        facing: Direction,
        face_width: int,
        face_height: int,
        offset: Position = Position.ZERO,
        conn_type: str = "stud",
    ):
        geom = anchored(geom)
        w, d = geom.alignment_width, geom.alignment_depth
        min_pos, step = {
            Direction.FRONT: (
                Position(0.5, 0, 0.5 * BRICKS_PER_STUD),
                Position(1, 0, 0),
            ),
            Direction.BACK: (
                Position(0.5, d, 0.5 * BRICKS_PER_STUD),
                Position(1, 0, 0),
            ),
            Direction.RIGHT: (
                Position(0, 0.5, 0.5 * BRICKS_PER_STUD),
                Position(0, 1, 0),
            ),
            Direction.LEFT: (
                Position(w, 0.5, 0.5 * BRICKS_PER_STUD),
                Position(0, 1, 0),
            ),
        }[facing]
        expected = tuple(
            (
                min_pos
                + offset
                + Position(step.x * n, step.y * n, z * BRICKS_PER_STUD),
                facing.value if conn_type == "stud" else -facing.value,
            )
            for n in range(face_width)
            for z in range(face_height)
        )
        assert expected
        assert_contains_connectors(geom, conn_type, expected)

    return _assert_has_stud_wall


class TestElement:
    def test_direct_construction_needs_only_an_id_and_a_colour(self):
        spec = all_parts()[0]
        element = Element(spec.ldraw_id, Color.RED)
        assert element.spec == spec
        assert element.color is Color.RED

    def test_element_constructs_from_id(self):
        element = Element(ldraw_id=A_BRICK, color=Color.RED)
        assert element.spec == PartSpec(A_BRICK)
        assert element == Element("3005", Color.RED)
        assert hash(element) == hash(Element("3005", Color.RED))
        assert element.bounding_box == Element("3005", Color.RED).bounding_box

    def test_element_rejects_unknown_id(self):
        with pytest.raises(InvalidPartError, match="not a catalogued LDraw part"):
            Element(UNCATALOGUED, Color.RED)

    def test_parts_without_nominal_shapes_are_constructible(self):
        # Any catalogued part with no shape will do; which one is beside the
        # point. Asserting the ``next(...)`` selector found one is the only
        # thing this test needs to check for itself; the rest is just building
        # an Element from it.
        spec = next((spec for spec in all_parts() if spec.shape is None), None)
        assert spec is not None
        assert Element(spec.ldraw_id, Color.RED)

    def test_an_element_can_be_built_from_any_catalogued_id(self) -> None:
        """The headline requirement: an id is enough."""
        for part_id in sorted(partdata.part_ids())[:50]:
            element = Element(part_id, Color.RED)
            assert element.spec.ldraw_id == part_id

    @pytest.mark.parametrize(
        "part_id",
        [
            "43722a",
            "43723a",
            "41769a",
            "41770a",
            "2853a",
            "3004p0i",
            "92245",
            "16000p06",
        ],
    )
    def test_parts_with_inherited_data_keep_their_own_identity_and_geometry(
        self, part_id
    ):
        element = Element(part_id, Color.RED)
        assert element.connectors
        lo, hi = element.bounding_box
        assert lo != hi
        assert len(partdata.record(part_id).collision_mesh.faces) > 0
        model = LegoBuild()
        model.add(element)
        assert to_ldraw(model).splitlines()[-1].endswith(f" {part_id}.dat")

    def test_patterned_brick_with_inherited_data_stacks_without_colliding(self):
        model = LegoBuild()
        base = model.add(Element("3004p0i", Color.RED))
        model.stack(Element("3004", Color.BLUE), base)
        assert model.is_valid()

    def test_equality_is_by_value(self):
        assert Element("3001", Color.RED) == Element("3001", Color.RED)
        assert Element("3001", Color.RED) != Element("3001", Color.BLUE)
        assert Element("3001", Color.RED) != Element("3020", Color.RED)
        assert len({Element("3001", Color.RED), Element("3001", Color.RED)}) == 1

    def test_geometry_is_derived_from_the_ldraw_id(self):
        part = Element("3001", Color.RED)
        assert isinstance(part.spec.shape, Box)
        # A stud sits at every grid position on top: width x depth of them.
        studs = part.find_connectors("stud")
        assert len(studs) == part.spec.shape.width * part.spec.shape.depth
        # The measured footprint matches the part's own catalogued shape.
        low, high = part.bounding_box
        assert high.x - low.x == part.spec.shape.width
        assert high.y - low.y == part.spec.shape.depth

    def test_element(self):
        assert repr(Element("3005", Color.RED)) == "Element(Brick  1 x  1, Red)"


class TestWedge:
    def test_selected_wedge_plate_builds(self, assert_cuboid_geometry):
        for spec in tuple(PartSpec(part_id) for part_id in ("54384", "3544", "30504")):
            assert isinstance(spec.shape, Footprint)
            w, d = spec.shape.dimensions
            assert_cuboid_geometry(spec, w, d, PLATE, tol=0.11)

    def test_selected_wedge_brick_builds(self, assert_cuboid_geometry):
        for spec in tuple(PartSpec(part_id) for part_id in ("30505",)):
            assert isinstance(spec.shape, Box)
            w, d, h = spec.shape.dimensions
            assert_cuboid_geometry(spec, w, d, h)

    def test_wedge_has_studs_on_its_straight_side(
        self, anchored, assert_contains_connectors
    ):
        part = anchored(Element("3545", Color.WHITE))
        expected = [(Position(2.5, y + 0.5, PLATE), Direction.UP.value) for y in (1, 2)]
        assert_contains_connectors(part, "stud", expected)


class TestInvertedTile:
    def test_selected_inverted_tile_builds(self, assert_cuboid_geometry):
        for spec in tuple(PartSpec(part_id) for part_id in ("11203", "35459", "3395")):
            assert isinstance(spec.shape, Footprint)
            w, d = spec.shape.dimensions
            assert_cuboid_geometry(spec, w, d, PLATE, has_antistuds=False)


class TestBaseplate:
    def test_selected_baseplate_builds(self, assert_cuboid_geometry):
        for spec in tuple(PartSpec(part_id) for part_id in ("3857", "3811", "4186")):
            assert isinstance(spec.shape, Footprint)
            w, d = spec.shape.dimensions
            assert_cuboid_geometry(spec, w, d, PLATE / 2, has_antistuds=False)


class TestFence:
    def test_selected_fence_builds(self, part_from_spec):
        for spec in tuple(PartSpec(part_id) for part_id in ("3633", "19121", "30055")):
            assert isinstance(spec.shape, Box)
            w, d, _ = spec.shape.dimensions
            elem = part_from_spec(spec)
            _assert_catalog_connectors(elem, "antistud")
            assert (elem.alignment_box[0][:2], elem.alignment_box[1][:2]) == (
                pytest.approx((-w / 2, -d / 2)),
                pytest.approx((w / 2, d / 2)),
            ), spec


class TestPanelDoor:
    def test_selected_panel_door_builds(self, part_from_spec):
        for spec in tuple(PartSpec(part_id) for part_id in ("3822", "60657", "4182")):
            assert spec.chirality in (Chirality.LEFT, Chirality.RIGHT)
            _assert_catalog_connectors(part_from_spec(spec), "stud", "antistud")


class TestGirder:
    def test_inclined_girder_leans_toward_the_back(self):
        elem = Element("4476", Color.WHITE)
        base_back = max(c.position.y for c in elem.find_connectors("antistud"))
        top_back = max(c.position.y for c in elem.find_connectors("stud"))
        assert top_back > base_back


class TestArchitecturalElements:
    """Dimensions and connections of stairs, ladders, and lamp posts."""

    @pytest.mark.parametrize(
        "part_id, dims, exceptions",
        [
            (_STAIRS, (4, 7, 6), {}),
            (
                _CURVED_STAIRS,
                (6, 6, 4),
                {"has_studs": False, "check_alignment_box": False},
            ),
            (_LADDER, (2, 1, PLATE), {"check_bounding_box": False}),
            (_LAMP_POST, (2, 2, 7), {}),
        ],
        ids=["stairs", "curved_stairs", "ladder", "lamp_post"],
    )
    def test_dimensions_match_the_part_geometry(
        self, part_id, dims, exceptions, assert_cuboid_geometry
    ):
        assert_cuboid_geometry(Element(part_id, Color.WHITE), *dims, **exceptions)

    @pytest.mark.parametrize(
        "part_id", (_STAIRS, _CURVED_STAIRS, _LADDER, _LAMP_POST), ids=str
    )
    def test_elements_carry_antistuds(self, part_id):
        assert Element(part_id, Color.WHITE).find_connectors("antistud"), part_id


class TestStairs:
    def test_stair_treads_and_landing_have_studs(
        self, anchored, assert_contains_connectors
    ):
        step_width = 4
        n_steps = 6
        elem = anchored(Element(_STAIRS, Color.WHITE))
        step_studs = tuple(
            (Position(x + 0.5, n + 0.5, n + 1), Direction.UP.value)
            for x in range(step_width)
            for n in range(n_steps)
        )
        landing_studs = tuple(
            (Position(x + 0.5, n_steps + 0.5, n_steps - PLATE), Direction.UP.value)
            for x in (1, 2)
        )
        assert_contains_connectors(elem, "stud", step_studs + landing_studs)

    def test_curved_stairs_are_smooth_on_top(self):
        assert not Element(_CURVED_STAIRS, Color.WHITE).find_connectors("stud")


class TestLadder:
    def test_ladder_rungs_stand_off_toward_the_front(self):
        lo, hi = Element(_LADDER, Color.WHITE).bounding_box
        assert lo.y < -0.5
        assert hi.y == pytest.approx(0.5, abs=0.01)


class TestLampPost:
    def test_lamp_post_has_centered_top_stud(self):
        elem = Element(_LAMP_POST, Color.WHITE)
        top_stud = elem.find_connectors("stud", Direction.UP)[0]
        assert top_stud.position == Position(0, 0, 7)
        assert top_stud.axis == Direction.UP.value


class TestCylinder:
    def test_selected_cylinder_builds(self, assert_cuboid_geometry):
        for spec in tuple(PartSpec(part_id) for part_id in ("3062b", "92947", "87081")):
            assert isinstance(spec.shape, Rod)
            d, h = spec.shape.dimensions
            assert_cuboid_geometry(spec, d, d, h)


class TestRoundPlate:
    def test_selected_round_plate_builds(self, assert_cuboid_geometry):
        for spec in tuple(PartSpec(part_id) for part_id in ("6141", "60474", "74611")):
            assert isinstance(spec.shape, Disc)
            d = spec.shape.diameter
            assert_cuboid_geometry(spec, d, d, PLATE)


class TestRoundTile:
    def test_selected_round_tile_builds(self, assert_cuboid_geometry):
        for spec in tuple(PartSpec(part_id) for part_id in ("98138", "14769", "67095")):
            assert isinstance(spec.shape, Disc)
            d = spec.shape.diameter
            assert_cuboid_geometry(spec, d, d, PLATE, has_studs=False)


class TestCone:
    def test_selected_cone_builds(self, assert_cuboid_geometry):
        for spec in tuple(PartSpec(part_id) for part_id in ("85975", "3942c", "3943a")):
            assert isinstance(spec.shape, Rod)
            d, h = spec.shape.dimensions
            # The fez cone is slightly wider than 1x1
            assert_cuboid_geometry(spec, d, d, h, tol=0.07)

    def test_cones_have_expected_top_studs(
        self, part_from_spec, assert_contains_connectors
    ):
        for spec in tuple(PartSpec(part_id) for part_id in ("85975", "3942c", "3943a")):
            assert isinstance(spec.shape, Rod)
            d, h = spec.shape.dimensions
            elem = part_from_spec(spec)
            if d <= 2:
                expected = [(Position(0, 0, float(h)), Direction.UP.value)]
            else:
                expected = [
                    (Position(x, y, float(h)), Direction.UP.value)
                    for x in (-0.5, 0.5)
                    for y in (-0.5, 0.5)
                ]
            assert_contains_connectors(elem, "stud", expected)


class TestDish:
    def test_selected_dish_builds(self, part_from_spec):
        for spec in tuple(
            PartSpec(part_id) for part_id in ("43898", "4285b", "50990a")
        ):
            assert isinstance(spec.shape, Disc)
            (d,) = spec.shape.dimensions
            elem = part_from_spec(spec)
            assert elem.connectors, spec
            assert elem.find_connectors("stud"), spec
            assert elem.find_connectors("antistud"), spec
            assert (elem.width, elem.depth) == pytest.approx((d, d)), spec

    def test_dishes_have_expected_top_studs(
        self, part_from_spec, assert_contains_connectors
    ):
        for spec in tuple(
            PartSpec(part_id) for part_id in ("43898", "4285b", "50990a")
        ):
            assert isinstance(spec.shape, Disc)
            (d,) = spec.shape.dimensions
            elem = part_from_spec(spec)
            h = elem.bounding_box[1].z - STUD_HEIGHT
            if d <= 4:
                expected = [(Position(0, 0, h), Direction.UP.value)]
            else:
                expected = [
                    (Position(x, y, h), Direction.UP.value)
                    for x in (-0.5, 0.5)
                    for y in (-0.5, 0.5)
                ]
            assert_contains_connectors(elem, "stud", expected)


class TestArch:
    def test_selected_arch_builds(self, assert_cuboid_geometry):
        for spec in tuple(PartSpec(part_id) for part_id in ("4490", "92950", "16577")):
            assert isinstance(spec.shape, Box)
            w, d, h = spec.shape.dimensions
            assert_cuboid_geometry(spec, w, d, h)

    def test_arches_connect_by_their_feet(
        self, part_from_spec, anchored, assert_contains_connectors
    ):
        for spec in tuple(PartSpec(part_id) for part_id in ("4490", "92950", "16577")):
            assert isinstance(spec.shape, Box)
            w, _, _ = spec.shape.dimensions
            elem = anchored(part_from_spec(spec))

            expected_feet = (
                (Position(0.5, 0.5, 0), Direction.UP.value),
                (Position(w - 0.5, 0.5, 0), Direction.UP.value),
            )
            assert_contains_connectors(elem, "antistud", expected_feet)

    def test_arches_have_open_span(self, part_from_spec, anchored):
        for spec in tuple(PartSpec(part_id) for part_id in ("4490", "92950", "16577")):
            assert isinstance(spec.shape, Box)
            arch = anchored(part_from_spec(spec))
            lo, hi = arch.alignment_box
            span_center = Position((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, 0)

            model = LegoBuild()
            model.add_raw(arch.content, arch.pose)
            # Plate centered directly under the open span, not grid-snapped to a side
            model.add_raw(Element("6141", Color.WHITE), Pose(translation=span_center))

            assert model.is_valid(), spec


class TestTowballJoint:
    def test_selected_towball_joint_builds(self, assert_cuboid_geometry):
        for spec in tuple(PartSpec(part_id) for part_id in ("14417", "14419", "63082")):
            assert isinstance(spec.shape, Footprint)
            w, d = spec.shape.dimensions
            assert_cuboid_geometry(spec, w, d, PLATE, check_bounding_box=False)

    def test_towball_and_socket_mate_with_ball_joint(self, model):
        model.add(Element("14418", Color.WHITE), name="socket")
        model.connect(
            Element("22890", Color.WHITE),
            "towball",
            to=model.named("socket").find_connector("towball_socket"),
            mounting=Mounting(angle=180, swing_x=5),
        )
        assert model.is_valid()
        assert model.is_connected()


class TestTurntable:
    def test_base_and_top_mate_with_revolute_joint(self, model):
        model.add(Element("3680", Color.WHITE), name="base")
        model.connect(
            Element("3679", Color.WHITE),
            "turntable_pin",
            to=model.named("base").find_connector("turntable_socket"),
            mounting=Mounting(37),
        )
        assert model.is_valid()
        assert model.is_connected()


class TestSnotBrick:
    def test_selected_snot_brick_builds(self, assert_cuboid_geometry):
        for spec in tuple(PartSpec(part_id) for part_id in ("4070", "7729", "30414")):
            assert isinstance(spec.shape, Box)
            w, d, h = spec.shape.dimensions
            assert_cuboid_geometry(spec, w, d, h, tol=0.2)

    def test_headlight_has_recessed_front_stud_and_back_antistud(
        self, assert_has_stud_wall
    ):
        elem = Element("4070", Color.WHITE)
        assert_has_stud_wall(
            elem, Direction.FRONT, 1, 1, offset=Position(0, 0.2, 1 / 6)
        )
        assert_has_stud_wall(
            elem,
            Direction.BACK,
            1,
            1,
            offset=Position(0, 0, 1 / 6),
            conn_type="antistud",
        )

    def test_part_mates_onto_side_stud(self, model):
        post = Element("30414", Color.WHITE)
        (side,) = post.find_connectors(
            "stud", facing=Direction.FRONT, toward=Direction.LEFT, count=1
        )
        wing = Element("3024", Color.WHITE)
        (mount,) = wing.find_connectors("antistud")

        model.add(post, name="post")
        model.connect(wing, mount, to=side.transformed(model.named("post").pose))
        assert model.is_valid()
        assert model.is_connected()


class TestBracket:
    def test_selected_inverted_snot_bracket_builds(self, assert_cuboid_geometry):
        for spec in tuple(PartSpec(part_id) for part_id in ("36840", "99780", "99207")):
            assert isinstance(spec.shape, Ell)
            w, d, _, _ = spec.shape.dimensions
            assert_cuboid_geometry(spec, w, d, PLATE, check_bounding_box=False)

    def test_selected_snot_bracket_builds(self, assert_cuboid_geometry):
        for spec in tuple(PartSpec(part_id) for part_id in ("36841", "99781", "44728")):
            assert isinstance(spec.shape, Ell)
            w, d, _, _ = spec.shape.dimensions
            assert_cuboid_geometry(spec, w, d, PLATE, check_bounding_box=False)

    def test_each_bracket_has_front_facing_stud_grid_of_the_expected_size(
        self, part_from_spec, assert_has_stud_wall
    ):
        bracket_specs = tuple(
            PartSpec(part_id) for part_id in ("36841", "99781", "44728")
        )
        inverted_bracket_specs = tuple(
            PartSpec(part_id) for part_id in ("36840", "99780", "99207")
        )
        for spec in bracket_specs + inverted_bracket_specs:
            elem = part_from_spec(spec)
            assert isinstance(spec.shape, Ell)
            w, _, fw, fh = spec.shape.dimensions
            offset_x = -max(0, (w - fw) // 2)
            offset_y = -1 / 5
            offset_z = -(fh * BRICKS_PER_STUD - PLATE) if spec in bracket_specs else 0
            assert_has_stud_wall(
                elem,
                Direction.FRONT,
                fw,
                fh,
                offset=Position(offset_x, offset_y, offset_z),
            )


class TestBeam:
    def test_selected_beam_builds_with_geometry(self, part_from_spec):
        for spec in tuple(PartSpec(part_id) for part_id in ("18654", "32063", "32278")):
            assert isinstance(spec.shape, Length)
            elem = part_from_spec(spec)
            assert elem.connectors

    def test_all_beams_have_n_downward_facing_holes(self, part_from_spec):
        for spec in tuple(PartSpec(part_id) for part_id in ("18654", "32063", "32278")):
            elem = part_from_spec(spec)
            assert isinstance(spec.shape, Length)
            n = math.floor(spec.shape.length)
            conn_types = ("pin_hole", "axle_hole")
            holes = elem.find_connectors(conn_types, facing=Direction.DOWN)
            assert len(holes) == n, spec


class TestAxle:
    def test_selected_axle_builds_with_geometry(self, part_from_spec):
        for spec in tuple(PartSpec(part_id) for part_id in ("32062", "3707", "50451")):
            assert isinstance(spec.shape, Length)
            elem = part_from_spec(spec)
            assert elem.connectors

    def test_all_axles_carry_one_shaft_connector_spanning_its_length(
        self, part_from_spec
    ):
        for spec in tuple(PartSpec(part_id) for part_id in ("32062", "3707", "50451")):
            elem = part_from_spec(spec)
            assert isinstance(spec.shape, Length)
            length = spec.shape.length
            (conn,) = elem.find_connectors("axle")
            assert conn.axis == pytest.approx(
                Direction.RIGHT.value
            ) or conn.axis == pytest.approx(Direction.LEFT.value)
            assert length / 2 - 0.15 <= conn.length <= length / 2, spec


class TestPin:
    def test_selected_pin_builds_with_geometry(self, part_from_spec):
        for spec in tuple(PartSpec(part_id) for part_id in ("89678", "2780", "32556a")):
            assert isinstance(spec.shape, Length)
            elem = part_from_spec(spec)
            assert elem.connectors

    def test_all_pins_have_one_or_two_shaft_connectors(self, part_from_spec):
        for spec in tuple(PartSpec(part_id) for part_id in ("89678", "2780", "32556a")):
            elem = part_from_spec(spec)
            assert isinstance(spec.shape, Length)
            length = spec.shape.length
            n = 2 if length > 1 else 1
            conns = elem.find_connectors("pin")
            assert len(conns) == n
            for conn in conns:
                assert conn.axis == pytest.approx(
                    Direction.RIGHT.value
                ) or conn.axis == pytest.approx(Direction.LEFT.value)


class TestTechnicConnections:
    def test_pin_joins_two_beams(self, model):
        lower = Element("32316", Color.WHITE)
        model.add(lower, name="lower")
        connecting_pin = Element("2780", Color.WHITE)
        near_end, far_end = connecting_pin.find_connectors("pin")
        model.connect(
            connecting_pin,
            near_end,
            to=lower.find_connectors("pin_hole")[0].transformed(
                model.named("lower").pose
            ),
            name="pin",
        )
        upper = Element("32316", Color.WHITE)
        model.connect(
            upper,
            upper.find_connectors("pin_hole")[0],
            to=far_end.transformed(model.named("pin").pose),
        )
        assert model.is_valid()
        assert model.is_connected()

    def test_axle_slid_through_cross_hole_stays_valid(self, model):
        model.add(Element("7229", Color.WHITE), name="beam")
        model.connect(
            Element("3705", Color.WHITE),
            "axle",
            to=model.named("beam").find_connector("axle_hole"),
            mounting=Mounting(offset=0.2),
        )
        assert model.is_valid()
        assert model.is_connected()

    def test_pin_turned_in_its_hole_stays_valid(self, model):
        turning_beam = Element("32316", Color.WHITE)
        model.add(turning_beam, name="beam")
        turning_pin = Element("2780", Color.WHITE)
        end, _ = turning_pin.find_connectors("pin")
        model.connect(
            turning_pin,
            end,
            to=turning_beam.find_connectors("pin_hole")[0].transformed(
                model.named("beam").pose
            ),
            mounting=Mounting(angle=45),
        )
        assert model.is_valid()
        assert model.is_connected()


class TestJumper:
    @pytest.mark.parametrize(
        "part_id, positions",
        [
            ("15573", {(0, 0)}),
            ("87580", {(0, 0)}),
            ("34103", {(-0.5, 0), (0.5, 0)}),
        ],
    )
    def test_studs_sit_at_half_stud_offsets(self, part_id, positions):
        part = Element(part_id, Color.WHITE)
        studs = part.find_connectors("stud", facing=Direction.UP)
        assert {tuple(stud.position) for stud in studs} == {
            (x, y, PLATE) for x, y in positions
        }

    def test_a_plate_mates_onto_the_offset_stud(self, model):
        post = Element("15573", Color.WHITE)
        wing = Element("3024", Color.WHITE)
        placed = model.add(post)
        model.connect(
            wing, "antistud", to=placed.find_connector("stud", facing=Direction.UP)
        )
        assert model.is_valid()
        assert model.is_connected()
