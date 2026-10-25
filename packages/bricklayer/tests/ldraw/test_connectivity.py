"""Connector type naming and registry loading."""

import pytest

from bricklayer import Direction, Position
from bricklayer.geometry.connections import (
    GRID_FAMILIES,
    Connector,
    ConnectorType,
    JointKind,
    mate_pose,
    mating_rule,
    same_connector,
)
from bricklayer.geometry.linalg import dot
from bricklayer.geometry.spatial import to_direction
from bricklayer.ldraw.connectivity import (
    ConnectorRaw,
    ConnectorTypesRaw,
    DuplicateConnectorName,
    alias_key,
    decode_connectors,
    frame_axes,
    load_connector_types,
    resolve_name,
    type_name,
)
from bricklayer.ldraw.partdata import get_connector_type


def _config(**overrides):
    """A validated type config holding only ``overrides``; the schema defaults the rest."""
    return ConnectorTypesRaw.model_validate(overrides)


def _full_config(**overrides):
    """A config exercising every rule-generation path."""
    raw = {
        "aliases": {
            "stud/stud": "stud",
            "hole/hole": "antistud",
            "axle/pin": "pin",
            "axle/socket": "pin_hole",
        },
        "triples": [
            "stud/stud", "hole/hole", "axle/pin", "axle/socket",
            "hinge/9/in", "hinge/9/on", "hinge/29/in", "hinge/29/on",
            "ball/1/in", "ball/1/on", "fixed/0/in", "fixed/0/on",
            "fixed/17/in", "fixed/17/on", "hinge/5/in",
        ],
        "stud_mates": [["antistud", "stud"]],
        "axle_mates": [["pin", "pin_hole"]],
        "family_joints": {
            "stud": "REVOLUTE", "hole": "REVOLUTE", "axle": "CYLINDRICAL",
            "hinge": "REVOLUTE", "ball": "BALL", "fixed": "FIXED",
        },
        "oriented_subtypes": {"fixed": ["0", "1", "2", "3"]},
        "authored": [{"types": ["pane_tab", "frame_slot"], "joint": "FIXED"}],
    }  # fmt: skip
    raw.update(overrides)
    return _config(**raw)


def _joint(a: ConnectorType, b: ConnectorType) -> JointKind:
    """The joint kind two types mate under; fails if they do not mate at all."""
    rule = mating_rule(a, b)
    assert rule is not None, f"{a.name} and {b.name} do not mate"
    return rule.joint


class TestLoadConnectorTypes:
    def test_returns_registry_keyed_by_resolved_name(
        self, patch_connector_rules_registry
    ):
        types = load_connector_types(
            _config(
                aliases={"stud/stud": "stud"},
                triples=["stud/stud", "hinge/9/in", "hinge/9/on"],
                family_joints={"hinge": "REVOLUTE"},
            )
        )
        assert set(types) == {"stud", "hinge_9_in", "hinge_9_on"}
        assert types["stud"].family == "stud"
        assert types["hinge_9_in"].family == "hinge"

    def test_grid_families_use_the_grid(self, patch_connector_rules_registry):
        types = load_connector_types(
            _config(triples=["stud/open", "hole/tube", "axle/bar"])
        )
        assert types["stud_open"].uses_grid is True
        assert types["hole_tube"].uses_grid is True
        assert types["axle_bar"].uses_grid is False
        assert GRID_FAMILIES == {"stud", "hole"}

    def test_duplicate_resolved_name_is_rejected(self, patch_connector_rules_registry):
        with pytest.raises(DuplicateConnectorName, match="axle_hole"):
            load_connector_types(
                _config(
                    aliases={"axle/cross": "axle_hole"},
                    triples=["axle/cross", "axle/hole"],
                )
            )

    def test_alias_for_a_missing_triple_is_rejected(
        self, patch_connector_rules_registry
    ):
        with pytest.raises(ValueError, match="hinge/99/in"):
            load_connector_types(
                _config(aliases={"hinge/99/in": "nope"}, triples=["stud/stud"])
            )

    def test_malformed_triple_key_is_rejected(self, patch_connector_rules_registry):
        with pytest.raises(ValueError, match="not a connector triple"):
            load_connector_types(_config(triples=["stud"]))


class TestShippedRegistry:
    """The registry as actually shipped, over all 196 of BrickNet's triples."""

    @pytest.fixture
    def types(self):
        from bricklayer.ldraw.partdata import all_connector_types

        return all_connector_types()

    def test_every_triple_resolves_to_its_own_name(self, types):
        # 196 triples plus the one authored pair.
        assert len(types) == 198
        assert all(name == conn_type.name for name, conn_type in types.items())

    def test_uses_grid_is_exactly_the_stud_and_hole_families(self, types):
        gridded = {name for name, t in types.items() if t.uses_grid}
        assert gridded == {"stud", "open_stud", "antistud", "tube", "post"}
        assert all(t.uses_grid == (t.family in GRID_FAMILIES) for t in types.values())

    @pytest.mark.parametrize(
        "name",
        [
            "stud", "open_stud", "antistud", "tube", "post",
            "bar", "clip", "axle", "axle_hole", "pin", "pin_hole", "axle_bore",
            "shoulder_socket", "shoulder_peg", "narrow_pin", "narrow_hole",
            "wrist_socket", "wrist_peg", "visor_socket", "visor_peg",
            "waist_socket", "waist_peg", "neck_bracket", "neck_loop",
            "towball", "towball_socket", "turntable_pin", "turntable_socket",
            "pane_tab", "frame_slot",
        ],
    )  # fmt: skip
    def test_the_names_our_code_and_docs_use_all_exist(self, name, types):
        assert name in types

    def test_fixed_subtypes_split_on_brick_nets_oriented_set(self, types):
        """BrickNet pairs a fixed subtype outside {0, 1, 2, 3} on position alone,
        so those are free to roll while the four strict ones are rigid."""
        oriented = {"0", "1", "2", "3"}
        checked = 0
        for name, conn_type in types.items():
            if conn_type.family != "fixed" or not name.endswith("_in"):
                continue
            subtype = name.split("_")[1]
            partner = types.get(f"fixed_{subtype}_on")
            if partner is None:
                continue
            rule = mating_rule(conn_type, partner)
            assert rule is not None, name
            expected = JointKind.FIXED if subtype in oriented else JointKind.REVOLUTE
            assert rule.joint is expected, name
            checked += 1
        assert checked, "no fixed subtype carried both polarities"


class TestMinifigureMatingRules:
    @pytest.mark.parametrize("peg", ("waist_peg", "pin"))
    def test_tall_pegs_do_not_mate_with_antistuds(self, peg):
        assert (
            mating_rule(get_connector_type(peg), get_connector_type("antistud")) is None
        )

    @pytest.mark.parametrize(
        "peg, socket, joint",
        [
            ("narrow_pin", "narrow_hole", JointKind.REVOLUTE),
            ("shoulder_peg", "shoulder_socket", JointKind.REVOLUTE),
            ("wrist_peg", "wrist_socket", JointKind.REVOLUTE),
            ("waist_peg", "waist_socket", JointKind.FIXED),
            ("pin", "pin_hole", JointKind.CYLINDRICAL),
            ("neck_loop", "neck_bracket", JointKind.FIXED),
        ],
    )
    def test_minifigure_joints(self, peg, socket, joint):
        assert _joint(get_connector_type(peg), get_connector_type(socket)) is joint


class TestDecodeConnectors:
    def test_euler_and_named_facing_agree(self):
        types = {"stud": ConnectorType("stud", family="stud", uses_grid=True)}
        (by_euler,) = decode_connectors(
            [ConnectorRaw(type="stud", pos=(20.0, 0.0, 0.0))], types
        )
        (by_name,) = decode_connectors(
            [ConnectorRaw(type="stud", pos=(20.0, 0.0, 0.0), axis="UP", side="LEFT")],
            types,
        )
        assert same_connector(by_euler, by_name)

    def test_position_converts_ldu_to_bricklayer_coordinates(self):
        types = {"stud": ConnectorType("stud", family="stud")}
        (conn,) = decode_connectors(
            [ConnectorRaw(type="stud", pos=(20.0, -24.0, 40.0))], types
        )
        assert conn.position == Position(1, 2, 1)

    def test_length_converts_ldu_to_studs(self):
        types = {"pin": ConnectorType("pin", family="axle")}
        (conn,) = decode_connectors(
            [ConnectorRaw(type="pin", pos=(0.0, 0.0, 0.0), length=10.0)], types
        )
        assert conn.length == 0.5

    def test_unknown_type_name_raises(self):
        with pytest.raises(KeyError):
            decode_connectors([ConnectorRaw(type="nope", pos=(0.0, 0.0, 0.0))], {})


class TestMechanicalNames:
    def test_unpolarized_joins_kind_and_subtype(self):
        assert type_name("axle", "cross", None) == "axle_cross"

    def test_polarized_appends_polarity(self):
        assert type_name("hinge", "9", "in") == "hinge_9_in"

    def test_alias_key_omits_polarity_when_absent(self):
        assert alias_key("stud", "stud", None) == "stud/stud"
        assert alias_key("hinge", "9", "on") == "hinge/9/on"

    def test_alias_wins_over_mechanical_name(self):
        aliases = {"axle/cross": "axle_hole"}
        assert resolve_name("axle", "cross", None, aliases) == "axle_hole"

    def test_unaliased_triple_keeps_mechanical_name(self):
        assert resolve_name("hinge", "42", "in", {}) == "hinge_42_in"

    def test_axle_hole_is_the_collision_the_alias_table_must_avoid(self):
        """``axle/hole``'s mechanical name is what we want to call ``axle/cross``."""
        assert resolve_name("axle", "hole", None, {}) == "axle_hole"
        assert resolve_name("axle", "cross", None, {"axle/cross": "axle_hole"}) == (
            "axle_hole"
        )


class TestFrameConversion:
    def test_zero_angles_face_up(self):
        """An unrotated frame is a stud: mating axis up, roll reference on +x."""
        axis, side = frame_axes(0.0, 0.0, 0.0)
        assert axis == Direction.UP.value
        assert side == Direction.LEFT.value  # LEFT is +x

    def test_mating_axis_is_the_negated_y_column(self):
        """Pitch 90 turns BrickNet's -Y onto LDraw -z, which is BrickLayer FRONT."""
        axis, _ = frame_axes(90.0, 0.0, 0.0)
        assert axis == Direction.FRONT.value

    @pytest.mark.parametrize(
        "angles",
        [(90.0, 0.0, 0.0), (-180.0, 0.0, 0.0), (0.0, 90.0, 0.0), (0.0, 0.0, 270.0)],
    )
    def test_right_angles_give_exact_cardinal_axes(self, angles):
        """Axes are compared exactly against Direction, so trig noise must not survive.

        Without snapping, cos(90 deg) leaves 6e-17 in a component and a stud
        stops counting as grid-marked.
        """
        axis, side = frame_axes(*angles)
        assert to_direction(axis) is not None, axis
        assert to_direction(side) is not None, side

    @pytest.mark.parametrize(
        "angles", [(17.0, -43.0, 61.0), (-180.0, 80.2, 0.0), (-90.0, 0.0, 270.0)]
    )
    def test_axis_and_side_stay_orthonormal(self, angles):
        axis, side = frame_axes(*angles)
        assert axis.norm() == pytest.approx(1.0)
        assert side.norm() == pytest.approx(1.0)
        assert dot(axis, side) == pytest.approx(0.0)


class TestGeneratedRules:
    @pytest.fixture
    def types(self, patch_connector_rules_registry):
        return load_connector_types(_full_config())

    def test_stud_mates_are_revolute(self, types):
        assert _joint(types["stud"], types["antistud"]) is JointKind.REVOLUTE

    def test_axle_mates_are_cylindrical(self, types):
        assert _joint(types["pin"], types["pin_hole"]) is JointKind.CYLINDRICAL

    def test_polarized_subtype_mates_its_own_polarity_only(self, types):
        assert _joint(types["hinge_9_in"], types["hinge_9_on"]) is JointKind.REVOLUTE
        assert mating_rule(types["hinge_9_in"], types["hinge_29_on"]) is None

    def test_ball_family_is_a_ball_joint(self, types):
        assert _joint(types["ball_1_in"], types["ball_1_on"]) is JointKind.BALL

    def test_oriented_fixed_subtype_is_fixed(self, types):
        assert _joint(types["fixed_0_in"], types["fixed_0_on"]) is JointKind.FIXED

    def test_unoriented_fixed_subtype_rotates(self, types):
        """BrickNet pairs these on position alone, so they are free to roll."""
        assert _joint(types["fixed_17_in"], types["fixed_17_on"]) is JointKind.REVOLUTE

    def test_lone_polarity_registers_no_rule(self, types):
        assert all(
            mating_rule(types["hinge_5_in"], other) is None
            for name, other in types.items()
            if name != "hinge_5_in"
        )

    def test_authored_pair_is_registered(self, types):
        assert _joint(types["pane_tab"], types["frame_slot"]) is JointKind.FIXED

    def test_family_without_a_declared_joint_is_rejected(
        self, patch_connector_rules_registry
    ):
        with pytest.raises(ValueError, match="no joint declared"):
            load_connector_types(_full_config(family_joints={"stud": "REVOLUTE"}))


class TestMatingReproducesBrickNet:
    def test_coincident_frames_mate_at_rest(self):
        """BrickNet mates at E = I: the frames coincide, so mate_pose is exact."""
        types = {
            "a": ConnectorType("a", family="hinge"),
            "b": ConnectorType("b", family="hinge"),
        }
        (target,) = decode_connectors(
            [ConnectorRaw(type="a", pos=(14.543, 9.051, 0.0), pitch=-180.0, roll=80.2)],
            types,
        )
        (moving,) = decode_connectors(
            [ConnectorRaw(type="b", pos=(1.0, 0.0, 0.0), roll=90.0)], types
        )
        seated = moving.transformed(mate_pose(moving, target))
        # Geometric coincidence is the claim; the two carry different types by design.
        assert same_connector(
            seated, Connector(types["b"], target.position, target.axis, target.side)
        )
