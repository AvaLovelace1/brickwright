"""Minifigures and associated accessories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from ..colors import Color
from ..geometry import (
    PLATE,
    Connector,
    ConnectorType,
    Direction,
    LegoGeometry,
    Mounting,
    Pose,
    Position,
)
from ..geometry.connections import MIN_SLIDE_OVERLAP, mate_pose
from ..modeling.build import LegoBuild
from ..modeling.transforms import translate_to_ground
from ..parts.catalog import Chirality, PartSpec
from ..parts.element import Element


@dataclass(frozen=True)
class MinifigPose:
    """Joint angles articulating a minifigure, in degrees; zero is the neutral
    standing pose.

    ``head`` turns the head about the neck peg (positive toward the figure's
    own left). Arms swing about the shoulder axes and legs about the hip pins
    (positive swings the limb forward). Hands rotate about their wrist pegs
    (positive swings the fingers outward, away from the body).

    A hip pin only travels so far: a leg may swing up to
    :data:`LEG_FORWARD_LIMIT` degrees forward and :data:`LEG_BACKWARD_LIMIT`
    degrees back; angles outside that range raise :class:`ValueError`.
    """

    LEG_FORWARD_LIMIT: ClassVar[float] = 90.0
    LEG_BACKWARD_LIMIT: ClassVar[float] = 45.0

    head: float = 0.0
    left_arm: float = 0.0
    right_arm: float = 0.0
    left_hand: float = 0.0
    right_hand: float = 0.0
    left_leg: float = 0.0
    right_leg: float = 0.0

    def __post_init__(self) -> None:
        for name in ("left_leg", "right_leg"):
            angle = getattr(self, name)
            if not -self.LEG_BACKWARD_LIMIT <= angle <= self.LEG_FORWARD_LIMIT:
                raise ValueError(
                    f"{name} angle {angle} is out of range "
                    f"[-{self.LEG_BACKWARD_LIMIT}, {self.LEG_FORWARD_LIMIT}]"
                )


# An arm and a leg are named in one hand; the other is their LDraw mirror.
_HEAD = "3626bp01"
_TORSO = "973"
_HIPS = "3815b"
_HAND = "3820"
_ARM = "3818"
_LEG = "3816c"


# A shoulder socket faces the torso, so an arm at rest sits half a turn from its
# connector's zero; a pose's arm angle is measured from there.
_ARM_STAND = 180.0
_SIDE_DIRECTION = {Chirality.RIGHT: Direction.RIGHT, Chirality.LEFT: Direction.LEFT}


def minifig_head(
    color: Color = Color.YELLOW,
    *,
    head_id: str = _HEAD,
    headwear_id: str | None = None,
    headwear_color: Color = Color.WHITE,
) -> LegoBuild:
    """A minifig head piece with an optional accessory worn on its crown stud.

    Select the head with ``head_id`` and its accessory with ``headwear_id``.
    ``headwear_color`` defaults to white; printed faces are ordinary catalog parts.
    To build a full minifig, use :func:`minifig`.

    Raises:
        ValueError: if the head lacks a neck socket or the accessory lacks an antistud connector.
    """
    wearing = None if headwear_id is None else Element(headwear_id, headwear_color)
    _check_attachment(wearing, "antistud", "Headwear")
    m = LegoBuild()
    head = Element(head_id, color)
    _check_attachment(head, "pin_hole", "Head")
    m.add_raw(head, Pose.IDENTITY, name="head")
    if wearing is not None:
        m.connect(
            wearing,
            "antistud",
            to=m.named("head").find_connector("stud"),
            name="headwear",
            target_rotation=Pose.IDENTITY.rotation,
            target_position=Position.ZERO,
        )
    return m


def minifig_body(
    torso_color: Color = Color.WHITE,
    arm_color: Color | None = None,
    hand_color: Color = Color.YELLOW,
    pose: MinifigPose | None = None,
    *,
    torso_id: str = _TORSO,
    bodywear_id: str | None = None,
    bodywear_color: Color = Color.WHITE,
) -> LegoBuild:
    """A minifig body (torso, arms, and hands), plus an optional body accessory worn around the neck peg.

    Select printed clothing with ``torso_id`` and an accessory with ``bodywear_id``.
    ``bodywear_color`` defaults to white.
    To build a full minifig, use :func:`minifig`.

    Raises:
        ValueError: if the torso or accessory lacks a required attachment connector.
    """
    pose = MinifigPose() if pose is None else pose
    arm_color = torso_color if arm_color is None else arm_color
    wearing = None if bodywear_id is None else Element(bodywear_id, bodywear_color)
    _check_attachment(wearing, "neck_loop", "Bodywear")

    m = LegoBuild()
    torso_element = Element(torso_id, torso_color)
    _check_attachment(torso_element, "waist_socket", "Torso")
    _check_attachment(torso_element, "pin", "Torso")
    m.add_raw(torso_element, Pose.IDENTITY, name="torso")
    for side, arm_angle, hand_angle in (
        (Chirality.RIGHT, pose.right_arm, pose.right_hand),
        (Chirality.LEFT, -pose.left_arm, -pose.left_hand),
    ):
        arm_name = f"{side.name.lower()}_arm"
        m.connect(
            Element(_handed(_ARM, side).ldraw_id, arm_color),
            "shoulder_peg",
            to=_sided_of(torso_element, "shoulder_socket", side),
            mounting=Mounting(-arm_angle + _ARM_STAND),
            name=arm_name,
        )
        m.connect(
            Element(_HAND, hand_color),
            "wrist_peg",
            to=m.named(arm_name).find_connector("wrist_socket"),
            mounting=Mounting(-hand_angle),
            name=f"{side.name.lower()}_hand",
        )
    if wearing is not None:
        m.connect(
            wearing,
            _sided_of(wearing, "neck_loop", Chirality.RIGHT),
            to=_sided_of(torso_element, "neck_bracket", Chirality.RIGHT),
            name="bodywear",
            target_rotation=Pose.IDENTITY.rotation,
            target_position=Position.ZERO,
        )
    return m


def minifig_legs(
    leg_color: Color = Color.WHITE,
    hips_color: Color | None = None,
    pose: MinifigPose | None = None,
    *,
    hips_id: str | None = None,
    left_leg_id: str | None = None,
    right_leg_id: str | None = None,
    legs_id: str | None = None,
    footwear_id: str | None = None,
    footwear_color: Color = Color.WHITE,
) -> LegoBuild:
    """Assemble a minifigure lower body from catalog parts, with optional footwear.

    Choose separate ``hips_id``, ``left_leg_id``, and ``right_leg_id`` values,
    or a single-piece lower body with ``legs_id``. Omitted separate parts use
    the standard hips and articulated legs. Explicit leg ids are used in their
    given handedness, so select a left leg for ``left_leg_id``.

    ``hips_color`` defaults to ``leg_color``. A single-piece lower body uses
    ``leg_color``. Choose footwear with ``footwear_id`` and ``footwear_color``
    (white by default). It requires one sole on each leg, or two soles on the
    single-piece lower body.

    Raises:
        ValueError: if ``legs_id`` is combined with separate part ids, a pose
            articulates single-piece legs, or a part lacks attachment connectors.
    """
    pose = MinifigPose() if pose is None else pose
    hips_color = leg_color if hips_color is None else hips_color
    wearing = None if footwear_id is None else Element(footwear_id, footwear_color)
    _check_attachment(wearing, "stud", "Footwear")
    m = LegoBuild()
    if legs_id is not None:
        if any(part_id is not None for part_id in (hips_id, left_leg_id, right_leg_id)):
            raise ValueError("legs_id cannot be combined with separate hips or leg ids")
        if pose.left_leg or pose.right_leg:
            raise ValueError("single-piece legs cannot articulate")
        legs = Element(legs_id, leg_color)
        _check_attachment(legs, "waist_peg", "Lower body")
        m.add_raw(legs, Pose.IDENTITY, name="legs")
    else:
        hips = Element(_HIPS if hips_id is None else hips_id, hips_color)
        _check_attachment(hips, "waist_peg", "Hips")
        m.add_raw(hips, Pose(translation=Position(0, 0.0625, 5 * PLATE)), name="hips")
        for side, part_id, angle in (
            (Chirality.RIGHT, right_leg_id, pose.right_leg),
            (Chirality.LEFT, left_leg_id, -pose.left_leg),
        ):
            leg = Element(
                _handed(_LEG, side).ldraw_id if part_id is None else part_id, leg_color
            )
            m.connect(
                leg,
                "narrow_hole",
                to=_sided_of(hips, "narrow_pin", side).transformed(
                    m.named("hips").pose
                ),
                mounting=Mounting(angle=angle),
                name=f"{side.name.lower()}_leg",
            )
    if wearing is not None:
        _attach_footwear(m, wearing)
    return translate_to_ground(m)


# Some footwear is rotated outward to prevent the two in the pair from colliding.
_FOOTWEAR_OUTWARD_ROTATION: dict[str, float] = {
    "59275a": 5.0,
    "30284": 8.0,
}


def _attach_footwear(m: LegoBuild, item: Element) -> None:
    """Clip a copy of ``item`` under each foot of the planned lower body, oriented facing forward."""
    outward = _FOOTWEAR_OUTWARD_ROTATION.get(item.ldraw_id, 0.0)
    for side, (ref, foot) in zip(("right", "left"), _foot_antistuds(m), strict=True):
        sign = -1 if side == "right" else 1
        m.connect(
            item,
            "stud",
            to=foot.transformed(m.named(ref).pose),
            target_rotation=Pose.IDENTITY.rotation,
            target_position=Position.ZERO,
            mounting=Mounting(sign * outward) if outward else None,
            name=f"footwear_{side}",
        )


def _foot_antistuds(m: LegoBuild) -> list[tuple[str, Connector]]:
    """The two sole attachment points, ordered the figure's right foot first."""
    if "legs" in m.names:
        fused = m.named("legs").content
        assert isinstance(fused, Element)
        soles = sorted(_soles(fused), key=lambda c: c.position.x)
        if len(soles) != 2 or soles[0].position.x == soles[1].position.x:
            raise ValueError(
                f"footwear requires two separate sole connectors: {fused.spec.name}"
            )
        return [("legs", conn) for conn in soles]
    result = []
    for name in ("right_leg", "left_leg"):
        leg = m.named(name).content
        assert isinstance(leg, Element)
        soles = _soles(leg)
        if len(soles) != 1:
            raise ValueError(
                f"footwear requires one sole connector on {name}: {leg.spec.name}"
            )
        result.append((name, soles[0]))
    return result


def _soles(element: Element) -> list[Connector]:
    """The foot antistuds on a leg element: the upward-facing holes under the
    feet (a leg also carries side-facing antistuds that are not soles)."""
    antistuds = element.find_connectors("antistud")
    return [c for c in antistuds if c.axis.z > 0.5]


def minifig(
    *,
    head_id: str = _HEAD,
    torso_id: str = _TORSO,
    hips_id: str | None = None,
    left_leg_id: str | None = None,
    right_leg_id: str | None = None,
    legs_id: str | None = None,
    skin_color: Color = Color.YELLOW,
    torso_color: Color = Color.WHITE,
    arm_color: Color | None = None,
    hand_color: Color | None = None,
    leg_color: Color = Color.WHITE,
    hips_color: Color | None = None,
    headwear_id: str | None = None,
    headwear_color: Color = Color.WHITE,
    bodywear_id: str | None = None,
    bodywear_color: Color = Color.WHITE,
    footwear_id: str | None = None,
    footwear_color: Color = Color.WHITE,
    pose: MinifigPose | None = None,
) -> LegoBuild:
    """Assemble a minifigure as a :class:`LegoBuild`.

    Minifigures are typically 2 studs wide, 1 stud deep, and 4 bricks tall.
    Select printed faces and clothing with ``head_id`` and ``torso_id``. Use
    ``hips_id``, ``left_leg_id``, and ``right_leg_id`` for separate lower-body
    parts, or ``legs_id`` for a single-piece lower body. Find ids with
    ``search_parts``; the supplied parts must carry compatible connectors.
    Defaults assemble the standard smiling head, plain torso, and articulated legs.

    Select accessories with ``headwear_id``, ``bodywear_id``, and ``footwear_id``.
    Their ``headwear_color``, ``bodywear_color``, and ``footwear_color`` arguments
    default to white. ``pose`` controls the joints; single-piece legs cannot swing.

    The minifig is translated to the ground plane (z=0) after construction.
    Hence, if both legs are swung 90 degrees forward, the figure will end up sitting on the ground.

    Colors: ``skin_color`` is the head; ``arm_color`` defaults to ``torso_color``,
    ``hand_color`` to ``skin_color``, and ``hips_color`` to ``leg_color``.


    Raises:
        ValueError: if an accessory lacks the required attachment connector,
        ``pose`` articulates single-piece legs, separate and single-piece lower
        bodies are selected together, or footwear cannot attach to two soles.
    """
    pose = MinifigPose() if pose is None else pose
    hand_color = skin_color if hand_color is None else hand_color

    m = LegoBuild()
    lower = minifig_legs(
        leg_color=leg_color,
        hips_color=hips_color,
        pose=pose,
        footwear_id=footwear_id,
        footwear_color=footwear_color,
        hips_id=hips_id,
        left_leg_id=left_leg_id,
        right_leg_id=right_leg_id,
        legs_id=legs_id,
    )
    m.add_raw(lower, Pose.IDENTITY, name="legs")
    upper = minifig_body(
        torso_color=torso_color,
        arm_color=arm_color,
        hand_color=hand_color,
        pose=pose,
        torso_id=torso_id,
        bodywear_id=bodywear_id,
        bodywear_color=bodywear_color,
    )
    m.connect(
        upper,
        upper.find_connectors("waist_socket")[0],
        to=lower.find_connectors("waist_peg")[0],
        name="body",
    )
    neck_pin = upper.find_connector("pin")
    top = minifig_head(
        skin_color,
        head_id=head_id,
        headwear_id=headwear_id,
        headwear_color=headwear_color,
    )
    neck_socket = top.find_connectors("pin_hole")[0]
    m.connect(
        top,
        neck_socket,
        to=neck_pin.transformed(m.named("body").pose),
        mounting=Mounting(
            offset=_head_clearance(upper, top, neck_pin, neck_socket), angle=-pose.head
        ),
        name="head",
    )
    return m


def _head_clearance(
    upper: LegoBuild, head: LegoBuild, neck_pin: Connector, neck_socket: Connector
) -> float:
    """The neck joint's slide, in studs, that lifts ``head`` clear of ``upper``.

    The returned offset is signed along ``neck_pin.axis``, which points *down* the
    torso's neck, so lifting the head is a negative slide.
    """
    upper_leaves = {id(p.content) for p in upper.flattened_placements}
    rest = mate_pose(neck_socket, neck_pin)
    sign = 1.0 if neck_pin.axis.z > 0 else -1.0
    up = neck_pin.axis * sign

    def collides(rise: float) -> bool:
        lift = Pose(translation=Position.from_stud_units(up * rise))
        probe = LegoBuild()
        probe.add_raw(upper, Pose.IDENTITY, name="upper")
        probe.add_raw(head, lift.compose(rest), name="head")
        return any(
            (id(a.content) in upper_leaves) != (id(b.content) in upper_leaves)
            for a, b in probe.colliding_placements
        )

    if not collides(0.0):
        return 0.0
    # Rise only as far as the joint still grips: the two spans must keep
    # MIN_SLIDE_OVERLAP between them, and past that the head is a loose part.
    lo = 0.0
    hi = max(
        0.0, float(neck_pin.length) + float(neck_socket.length) - MIN_SLIDE_OVERLAP
    )
    if hi == 0.0 or collides(hi):
        # When no rise the joint allows clears the collision, keep the rest
        # pose and let is_valid() report the collision.
        return 0.0
    for _ in range(8):
        mid = (lo + hi) / 2
        if collides(mid):
            lo = mid
        else:
            hi = mid
    return sign * hi


def _handed(part_id: str, side: Chirality) -> PartSpec:
    """The ``side``-handed one of the handed part ``part_id`` and its mirror."""
    spec = PartSpec(part_id)
    return spec if spec.chirality is side else spec.mirrored


def _sided_of(
    geom: LegoGeometry, type_: ConnectorType | str, side: Chirality
) -> Connector:
    """The sided connector on ``geom``; the figure's right is the lower-x one."""
    connectors = geom.find_connectors(
        connector_type=type_, toward=_SIDE_DIRECTION[side]
    )
    if not connectors:
        raise ValueError(f"part requires a {type_} connector")
    return connectors[0]


def _check_attachment(item: Element | None, connector: str, label: str) -> None:
    if item is not None and not item.find_connectors(connector):
        raise ValueError(f"{label} requires a {connector} connector: {item.spec.name}")


_FACTORIES = (
    (minifig, lambda: None),
    (minifig_head, lambda: None),
    (minifig_body, lambda: None),
    (minifig_legs, lambda: None),
)

__all__ = ["MinifigPose"] + [factory.__name__ for factory, _ in _FACTORIES]
