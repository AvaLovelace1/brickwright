"""Window and door assemblies."""

from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from typing import Any

from ..colors import Color
from ..geometry import (
    Connector,
    Direction,
    HeightLike,
    Mat3,
    Mounting,
    Pose,
    Position,
)
from ..geometry.connections import mating_rule
from ..geometry.linalg import rotation_about
from ..modeling.build import LegoBuild
from ..parts.catalog import PartSpec
from ..parts.element import Element
from ..parts.shape import Box, Pane
from ._factories import PartOptions
from .variants import (
    DoorVariant,
    FrameVariant,
    PaneVariant,
    PartVariant,
)

_FRAMES = PartOptions(
    "Frame",
    Box,
    {
        "60592": None,
        "90195": FrameVariant.ARCHED,
        "60032": FrameVariant.AIRPLANE,
        "60593": None,
        "4035": FrameVariant.TRAIN,
        "6798": None,
        "51239": None,
        "73878": FrameVariant.ROUND_CORNER,
        "60594": None,
        "60598": None,
        "61345": FrameVariant.AIRPLANE,
        "60596": None,
        "57894": FrameVariant.THREE_PANES,
        "60599": None,
        "60806": FrameVariant.SLOPED,
        "28327": FrameVariant.ANGLED_CORNER,
        "42205": None,
    },
    FrameVariant,
)
_PANES = PartOptions(
    "Pane",
    Pane,
    {
        "60601": PaneVariant.SOLID,
        "60602": PaneVariant.SOLID,
        "7757": PaneVariant.SOLID,
        "51266": PaneVariant.SOLID,
        "86210": PaneVariant.SOLID,
        "57895": PaneVariant.SOLID,
        "42509": PaneVariant.SOLID,
        "38320": PaneVariant.LATTICE,
        "5032": PaneVariant.LATTICE,
        "62113": PaneVariant.GRILLE,
        "92589": PaneVariant.GRILLE,
    },
    PaneVariant,
)
_DOORS = PartOptions(
    "Door",
    Pane,
    {
        "60616a": DoorVariant.SOLID,
        "60797c04": DoorVariant.GLASS,
        "60623": DoorVariant.WINDOWED,
        "79730": DoorVariant.PET,
        "60621": DoorVariant.GRILLE,
    },
    DoorVariant,
)


# Looked up by attributes, so each key is a catalogued frame.
_LONG_AIRPLANE_FRAME = _FRAMES.find(Box(4, 1, 2), FrameVariant.AIRPLANE)
_SLOPED_FRAME = _FRAMES.find(Box(4, 4, 3), FrameVariant.SLOPED)
_ROUND_CORNER_FRAME = _FRAMES.find(Box(3, 3, 2), FrameVariant.ROUND_CORNER)
_ANGLED_CORNER_FRAME = _FRAMES.find(Box(4, 4, 6), FrameVariant.ANGLED_CORNER)


@dataclass(frozen=True)
class _Seating:
    """How a frame seats its inserts."""

    #: The insert's (width, height), when it differs from the frame's own.
    insert: tuple[int, HeightLike] | None = None
    #: How many inserts the frame holds.
    count: int = 1
    #: Degrees the insert is tilted back from upright.
    tilt: float = 0.0
    #: Degrees the insert is turned away from facing forward.
    turn: float = 0.0


_SEATING = {
    _ROUND_CORNER_FRAME: _Seating(insert=(2, 2), count=2),
    _LONG_AIRPLANE_FRAME: _Seating(insert=(2, 2), count=2),
    _SLOPED_FRAME: _Seating(tilt=45.0),
    _ANGLED_CORNER_FRAME: _Seating(turn=45.0),
}


def seating(frame_spec: PartSpec) -> _Seating:
    """How ``frame_spec`` seats its inserts."""
    return _SEATING.get(frame_spec, _Seating())


# Connector families that can seat an insert in a frame.
_SEATING_FAMILIES = frozenset({"hinge", "ball", "fixed", "authored"})

# Frame/insert combos whose meshes interpenetrate when seated, keyed
# (width, depth, height, insert variant, frame variant).
_COLLIDING_COMBOS: frozenset[
    tuple[int, int, HeightLike, PaneVariant | DoorVariant, FrameVariant | None]
] = frozenset(
    {
        (4, 1, 6, PaneVariant.GRILLE, FrameVariant.THREE_PANES),
        (4, 1, 6, PaneVariant.LATTICE, FrameVariant.THREE_PANES),
        (6, 1, 6, PaneVariant.SOLID, None),
        (4, 2, 6, PaneVariant.LATTICE, None),
        (4, 1, 6, PaneVariant.GRILLE, None),
        (4, 1, 6, PaneVariant.LATTICE, None),
        (4, 2, 3, PaneVariant.GRILLE, None),
        (4, 1, 3, PaneVariant.GRILLE, None),
        (4, 4, 3, PaneVariant.GRILLE, FrameVariant.SLOPED),
        (4, 4, 6, PaneVariant.GRILLE, FrameVariant.ANGLED_CORNER),
        (4, 4, 6, PaneVariant.LATTICE, FrameVariant.ANGLED_CORNER),
        (3, 1, 2, PaneVariant.SOLID, None),
        (3, 3, 2, PaneVariant.LATTICE, FrameVariant.ROUND_CORNER),
        (3, 3, 2, PaneVariant.SOLID, FrameVariant.ROUND_CORNER),
        (4, 1, 2, PaneVariant.LATTICE, FrameVariant.AIRPLANE),
        (4, 1, 2, PaneVariant.SOLID, FrameVariant.AIRPLANE),
    }
)


def insert_dimensions(frame_spec: PartSpec) -> tuple[int, HeightLike]:
    """The width and height of the insert that fits in a given frame."""
    if frame_spec.ldraw_id not in _FRAMES.parts:
        raise ValueError(f"must be a frame: {frame_spec}")
    special = seating(frame_spec).insert
    if special is not None:
        return special
    assert isinstance(frame_spec.shape, Box)
    return frame_spec.shape.width, frame_spec.shape.height


def frame_and_insert_compatible(frame_spec: PartSpec, insert_spec: PartSpec) -> bool:
    """Whether a given insert fits in a given frame."""
    dimensions = insert_dimensions(frame_spec)
    if (
        insert_spec.ldraw_id not in _PANES.parts
        and insert_spec.ldraw_id not in _DOORS.parts
    ):
        raise ValueError(f"must be a pane or door: {insert_spec}")

    if (
        _FRAMES.variant(frame_spec) is FrameVariant.THREE_PANES
        and insert_spec.ldraw_id in _DOORS.parts
    ):
        return False  # doors cannot fit in muntined frames

    assert isinstance(insert_spec.shape, Pane)
    if dimensions != (insert_spec.shape.width, insert_spec.shape.height):
        return False

    assert isinstance(frame_spec.shape, Box)
    combo = (
        frame_spec.shape.width,
        frame_spec.shape.depth,
        frame_spec.shape.height,
        (
            _PANES.variant(insert_spec)
            if insert_spec.ldraw_id in _PANES.parts
            else _DOORS.variant(insert_spec)
        ),
        _FRAMES.variant(frame_spec),
    )
    return combo not in _COLLIDING_COMBOS


@cache
def compatible_inserts(
    frame_spec: PartSpec, options: PartOptions
) -> dict[PartVariant, PartSpec]:
    """The ``options`` inserts that fit in a given frame, keyed by variant."""
    assert options.variant_enum is not None
    result = {}
    for variant in options.variant_enum:
        insert_spec = options.get(Pane(*insert_dimensions(frame_spec)), variant)
        if insert_spec is not None and frame_and_insert_compatible(
            frame_spec, insert_spec
        ):
            result[variant] = insert_spec
    return result


def window(
    width: int,
    depth: int,
    height: HeightLike,
    pane_variant: PaneVariant = PaneVariant.SOLID,
    frame_variant: FrameVariant | None = None,
    pane_color: Color = Color.WHITE,
    frame_color: Color = Color.WHITE,
) -> LegoBuild:
    """A filled window: a frame plus the window pane(s) inside it.

    The result is a small :class:`LegoBuild` assembly -- the frame element
    plus pane element(s) placed inside it. Certain frames carry multiple pane elements.

    Raises:
        ValueError: if the given arguments do not yield a valid frame, or a pane
            of the given variant is not available for the frame.
        TypeError: if ``pane_variant`` is not a :class:`PaneVariant`.
    """
    return _filled_frame(
        _PANES,
        Box(width, depth, height),
        pane_variant,
        frame_variant,
        pane_color,
        frame_color,
    )


def door(
    width: int,
    depth: int,
    height: HeightLike,
    door_variant: DoorVariant = DoorVariant.SOLID,
    frame_variant: FrameVariant | None = None,
    door_color: Color = Color.WHITE,
    frame_color: Color = Color.WHITE,
    open_angle: float = 0.0,
) -> LegoBuild:
    """A filled doorway: a frame plus the hinged door leaf inside it.

    The result is a small :class:`LegoBuild` assembly -- the frame element plus
    a door element (its own LDraw part and color) placed inside it.

    ``open_angle`` swings the leaf open on its hinge, in degrees from 0 (closed)
    to 90 (fully open). A door cannot go in a :attr:`~FrameVariant.THREE_PANES` frame,
    whose muntins block the swing.

    Raises:
        ValueError: if the given arguments do not yield a valid frame,
        a door of the given variant is not available for the frame,
        ``open_angle`` is outside 0-90 degrees, or the frame is
        muntined (a :attr:`~FrameVariant.THREE_PANES` variant).
        TypeError: if ``door_variant`` is not a :class:`DoorVariant`.
    """
    if not 0 <= open_angle <= 90:
        raise ValueError(
            f"open_angle must be between 0 and 90 degrees, got {open_angle}"
        )
    if frame_variant is FrameVariant.THREE_PANES:
        raise ValueError(
            f"a door cannot open through a {frame_variant.display_name} frame; "
            "use a plain frame or a window()"
        )
    return _filled_frame(
        _DOORS,
        Box(width, depth, height),
        door_variant,
        frame_variant,
        door_color,
        frame_color,
        mounting=Mounting(angle=open_angle),
    )


def _filled_frame(
    options: PartOptions,
    frame_shape: Box,
    variant: PaneVariant | DoorVariant,
    frame_variant: FrameVariant | None,
    color: Color,
    frame_color: Color,
    *,
    mounting: Mounting | None = None,
) -> LegoBuild:
    """A frame plus the ``options`` insert seated inside it."""
    noun = options.display_name.lower()
    variant_enum = options.variant_enum
    assert variant_enum is not None
    if not isinstance(variant, variant_enum):
        raise TypeError(
            f"{variant.display_name!r} is not a {noun} variant; {noun} variants: "
            f"{', '.join(v.display_name for v in variant_enum)}"
        )
    frame_spec = _FRAMES.find(frame_shape, frame_variant)
    inserts = compatible_inserts(frame_spec, options)
    insert_spec = inserts.get(variant)
    if insert_spec is None:
        available = ", ".join(v.display_name for v in inserts)
        where = _FRAMES.label(frame_shape)
        raise ValueError(
            f"{variant.display_name!r} is not an available {noun} for a {where}; "
            f"available {noun}s: {available}"
        )

    frame_elem = Element(frame_spec.ldraw_id, frame_color)
    insert_elem = Element(insert_spec.ldraw_id, color)

    seat = seating(frame_spec)
    towards: tuple[Direction | None, ...] = (
        (Direction.RIGHT, Direction.LEFT) if seat.count == 2 else (None,)
    )
    seats = [
        _find_seat_connectors(insert_elem, frame_elem, toward=toward)
        for toward in towards
    ]

    target_rotation = rotation_about(Direction.UP.value, seat.turn) @ rotation_about(
        Direction.RIGHT.value, seat.tilt
    )
    return _seat_inserts_in_frame(
        frame_elem, insert_elem, seats, target_rotation, mounting
    )


def _find_seat_connectors(
    insert: Element, frame_elem: Element, toward: Direction | Position | None = None
) -> tuple[Connector, Connector]:
    """The ``(insert, frame)`` connector pair that seats ``insert`` in ``frame_elem``.

    ``toward`` controls the frame connector search direction. If ``None``, uses the insert-connector's position.

    Raises:
        ValueError: if no connector pair mates the insert to the frame.
    """
    for insert_conn in insert.find_connectors(toward=Direction.DOWN):
        if insert_conn.type.family not in _SEATING_FAMILIES:
            continue
        toward_arg = (
            toward
            if toward is not None
            else frame_elem.center + (insert_conn.position - insert.center)
        )
        for frame_conn in frame_elem.find_connectors(toward=toward_arg):
            if (
                frame_conn.type.family in _SEATING_FAMILIES
                and mating_rule(insert_conn.type, frame_conn.type) is not None
            ):
                return insert_conn, frame_conn
    raise ValueError(
        f"no connector seats a {insert.spec.name} in a {frame_elem.spec.name}"
    )


def _seat_inserts_in_frame(
    frame_elem: Element,
    insert: Element,
    seats: Sequence[tuple[Connector, Connector]],
    target_rotation: Mat3,
    mounting: Mounting | None,
) -> LegoBuild:
    """``frame_elem`` with a copy of ``insert`` seated at each ``(insert, frame)`` pair."""
    m = LegoBuild()
    m.add_raw(frame_elem, Pose.IDENTITY, name="frame")
    for i, (insert_conn, frame_conn) in enumerate(seats, start=1):
        m.connect(
            insert,
            insert_conn,
            to=frame_conn,
            target_rotation=target_rotation,
            mounting=mounting,
            name="insert" if len(seats) == 1 else f"insert_{i}",
        )
    return m


def _valid_frame_factory_kwargs(
    options: PartOptions,
) -> tuple[tuple[tuple[str, Any], ...], ...]:
    noun = options.display_name.lower()

    def combined_kwargs(
        frame_spec: PartSpec, insert_variant: PartVariant
    ) -> tuple[tuple[str, Any], ...]:
        assert frame_spec.shape is not None
        return (
            *frame_spec.shape.field_values.items(),
            (f"{noun}_variant", insert_variant),
            ("frame_variant", _FRAMES.variant(frame_spec)),
        )

    return tuple(
        combined_kwargs(frame_spec, insert_variant)
        for frame_spec in _FRAMES.specs
        for insert_variant in compatible_inserts(frame_spec, options)
    )


_FACTORIES = (
    (window, lambda: _valid_frame_factory_kwargs(_PANES)),
    (door, lambda: _valid_frame_factory_kwargs(_DOORS)),
)

__all__ = [factory.__name__ for factory, _ in _FACTORIES]
