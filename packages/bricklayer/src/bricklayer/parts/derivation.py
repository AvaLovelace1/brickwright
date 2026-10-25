"""Read a part's :class:`~.shape.PartShape` out of its LDraw description.

:func:`derived_shape` is the entry point: a hand-authored override if the part
has one, else the dimension run its description states, read into the shape
class its LDraw category picks, then checked against the part's measured
geometry -- LDraw does not write every run in the same width/depth order.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from fractions import Fraction
from typing import Any, NamedTuple

from ..geometry import Position
from ..ldraw import partdata
from .shape import Box, Disc, Ell, Footprint, Length, Pane, PartShape, Rod


def derived_shape(part_id: str) -> PartShape | None:
    """``part_id``'s shape: its override if it has one, else its LDraw name,
    checked against what ``part_id`` actually measures."""
    if (override := overridden_shape(part_id)) is not None:
        return override
    record = partdata.taxonomy(part_id)
    if record is None:
        return None
    classification = _classify(record.category, record.subcategory)
    if classification.shape_type is None:
        return None
    shape = shape_from_name(part_id, classification.shape_type)
    if shape is None:
        return None
    return _measured_reading(part_id, shape, classification.qualified_round)


# The classes a keyword match's "qualified" flag applies to (see _classify).
_ROUND_SHAPE_TYPES = (Disc, Rod)


class _Classification(NamedTuple):
    """A category/subcategory's resolved shape, plus whether that shape (a
    round one) came from a *qualified* keyword match -- see :func:`_classify`."""

    shape_type: type[PartShape] | None
    qualified_round: bool


def _classify(category: str, subcategory: str | None) -> _Classification:
    """Which :class:`PartShape` a part of this LDraw category reads as, and
    whether -- for a round one -- the keyword that named it was qualified.

    A subcategory keyword in ``part_shape_classes.json`` wins over the
    category's ``default``; a ``null`` keyword or a missing default means no
    shape. A match is "qualified" when the keyword is a strict substring of
    the subcategory ("Round" in "Round Half Circle") and names a round class;
    :func:`_measured_reading` then checks the footprint is really round.
    """
    row = partdata.shape_classes().get(category)
    if row is None:
        return _Classification(None, False)
    for keyword, name in row.get("keywords", {}).items():
        if not subcategory or keyword not in subcategory:
            continue
        if name is None:
            return _Classification(None, False)
        shape_type = _shape_type_named(category, name)
        qualified = shape_type in _ROUND_SHAPE_TYPES and subcategory != keyword
        return _Classification(shape_type, qualified)
    default = row.get("default")
    shape_type = None if default is None else _shape_type_named(category, default)
    return _Classification(shape_type, False)


def _shape_type_named(category: str, name: str) -> type[PartShape]:
    """``name``'s :class:`PartShape` class, naming ``category`` if ``name`` is
    not one -- a typo in ``part_shape_classes.json`` should point back at the
    row it broke, the same way a bad :func:`overridden_shape` row points back
    at the part it belongs to."""
    try:
        return SHAPE_TYPES[name]
    except KeyError as e:
        raise KeyError(
            f"{category!r}'s row in part_shape_classes.json names an unknown "
            f"shape class: {e}"
        ) from e


def overridden_shape(part_id: str) -> PartShape | None:
    """The hand-authored shape for ``part_id``, or ``None`` if it has none.

    Raises:
        KeyError: if the override names no known shape class. Named with
            ``part_id``, so a bad row in a file that keeps growing points back
            to the part it belongs to.
        TypeError: if it does not name that class's fields. Named with
            ``part_id`` for the same reason.
    """
    raw = partdata.shape_override(part_id)
    if raw is None:
        return None
    fields: dict[str, Any] = dict(raw)
    try:
        shape_type = SHAPE_TYPES[fields.pop("type")]
        return shape_type(**{name: _exact(value) for name, value in fields.items()})
    except KeyError as e:
        raise KeyError(f"{part_id!r}'s shape override: {e}") from e
    except TypeError as e:
        raise TypeError(f"{part_id!r}'s shape override: {e}") from e


def shape_from_name(part_id: str, shape_type: type[PartShape]) -> PartShape | None:
    """``shape_type``'s shape, read out of ``part_id``'s LDraw dimension run.

    ``None`` when the description states no run, or a run too short, too
    fractional, or too long for the shape (a longer run states something
    else, such as an angle or tooth count).
    """
    entry = _SHAPE_READERS.get(shape_type)
    record = partdata.taxonomy(part_id)
    if (
        entry is None
        or record is None
        or not record.dimensions
        or len(record.dimensions) > entry.max_dimensions
    ):
        return None
    try:
        return entry.read(record.dimensions)
    except ValueError:
        # A height (or length) that does not sit on a plate boundary -- too
        # fractional a run for the shape it was read as.
        return None


def _measured_reading(
    part_id: str, shape: PartShape, qualified_round: bool
) -> PartShape | None:
    """``shape``, corrected for LDraw's inconsistent dimension order and
    checked against what ``part_id`` measures, or ``None`` if it misreads.

    :func:`_better_fit` picks the better-fitting orientation, then
    :func:`_overstates_measured_geometry` and (for a qualified round reading)
    :func:`_nonsquare_round_footprint` reject a misread. Unchanged for an
    unmeasured part (zero extents).
    """
    extents = partdata.measured_extents(part_id)
    if extents == Position.ZERO:
        return shape
    shape = _better_fit(shape, extents)
    if _overstates_measured_geometry(shape, extents):
        return None
    if qualified_round and _nonsquare_round_footprint(shape, extents):
        return None
    return shape


def _overstates_measured_geometry(shape: PartShape, extents: Position) -> bool:
    """Whether any axis ``shape`` states runs past ``extents`` by more than
    its class's slack.

    One-sided: a part commonly measures past its nominal shape (a protruding
    stud, a wheel pin), which is not a misread.
    """
    slack = _SHAPE_READERS[type(shape)].slack
    return any(
        derived - measured > slack for derived, measured in _axis_deltas(shape, extents)
    )


# How far a qualified round reading's measured x and y may differ, in studs.
# Across the catalog, genuinely round qualified readings differ by at most
# 0.78 and partial-round misreads ("Round Half Circle", "Rounded") by at
# least 1.00.
_ROUND_SQUARENESS_SLACK = 0.9


def _nonsquare_round_footprint(shape: PartShape, extents: Position) -> bool:
    """Whether round ``shape`` has a measured footprint too far from square to
    be round (a partial-round shape understates, so overstatement misses it)."""
    return isinstance(shape, _ROUND_SHAPE_TYPES) and abs(extents.x - extents.y) > (
        _ROUND_SQUARENESS_SLACK
    )


def _better_fit(shape: PartShape, extents: Position) -> PartShape:
    """``shape``, or ``shape.transpose()`` if that fits ``extents`` strictly
    better, summed over :func:`_axis_deltas`'s pairs.

    A no-op for a shape that is its own transpose, including
    :class:`~.shape.Ell`, whose flange is not a free rotation of its plate.
    """
    transposed = shape.transpose()
    if transposed == shape:
        return shape
    error = sum(abs(d - m) for d, m in _axis_deltas(shape, extents))
    transposed_error = sum(abs(d - m) for d, m in _axis_deltas(transposed, extents))
    return transposed if transposed_error < error else shape


def _axis_deltas(
    shape: PartShape, extents: Position
) -> tuple[tuple[float, float], ...]:
    """``(derived, measured)`` pairs for the axes ``shape``'s class checks
    (see :attr:`_ShapeReader.axes`)."""
    x, y, z = float(extents.x), float(extents.y), float(extents.z)
    measured = {"x": x, "y": y, "z": z, "span": max(x, y)}
    return tuple(
        (float(getattr(shape, name)), measured[axis])
        for name, axis in _SHAPE_READERS[type(shape)].axes
    )


def _read_footprint(run: Sequence[Fraction]) -> PartShape | None:
    # A trailing height (non-nominal thickness) is ignored.
    pair = _studs_pair(run, 0)
    return None if pair is None else Footprint(*pair)


def _read_box(run: Sequence[Fraction]) -> PartShape | None:
    pair = _studs_pair(run, 0)
    return None if pair is None else Box(*pair, _height(run))


def _read_pane(run: Sequence[Fraction]) -> PartShape | None:
    # A pane has no depth, so LDraw's leading number is dropped.
    run = run[1:]
    if len(run) < 2 or (width := _studs(run[0])) is None:
        return None
    return Pane(width, run[1])


def _read_disc(run: Sequence[Fraction]) -> PartShape | None:
    if not run:
        return None
    diameter = _studs(run[0])
    return None if diameter is None else Disc(diameter)


def _read_rod(run: Sequence[Fraction]) -> PartShape | None:
    if not run:
        return None
    diameter = _studs(run[0])
    return None if diameter is None else Rod(diameter, _height(run))


def _read_length(run: Sequence[Fraction]) -> PartShape | None:
    # "Technic Beam  5 x  0.5" is 5 long and 0.5 thick; a second number past
    # one stud ("Technic Beam  3 x  5 Bent 90") spans a second axis instead.
    if not run or (len(run) > 1 and run[1] > 1):
        return None
    return Length(run[0])


def _read_ell(run: Sequence[Fraction]) -> PartShape | None:
    # A bracket states its plate and its flange as two runs; both are
    # transposed the same way (see _studs_pair) since Ell has no transpose of
    # its own for _better_fit to correct a wrong one with.
    plate, flange = _studs_pair(run, 0), _studs_pair(run, 2)
    return None if plate is None or flange is None else Ell(*plate, *flange)


class _ShapeReader(NamedTuple):
    """How a shape class reads a dimension run and checks it against geometry."""

    read: Callable[[Sequence[Fraction]], PartShape | None]
    #: How many leading run numbers the reader accounts for, including ones
    #: it drops; a longer run states something else (see shape_from_name).
    max_dimensions: int
    #: ``(field, axis)`` pairs checked against measured extents; ``"span"``
    #: is the longer of x and y, for a class with one plan-view axis.
    #: An Ell's face_height is unchecked: its z depends on the bracket's orientation.
    axes: tuple[tuple[str, str], ...]
    #: How far a field may exceed its measured axis before the reading is
    #: rejected. A pane insert measures under nominal, so it gets more.
    slack: float = 0.3


_SHAPE_READERS: Mapping[type[PartShape], _ShapeReader] = {
    Box: _ShapeReader(_read_box, 3, (("width", "x"), ("depth", "y"), ("height", "z"))),
    Disc: _ShapeReader(_read_disc, 2, (("diameter", "x"), ("diameter", "y"))),
    Ell: _ShapeReader(
        _read_ell, 4, (("width", "x"), ("depth", "y"), ("face_width", "x"))
    ),
    Footprint: _ShapeReader(_read_footprint, 3, (("width", "x"), ("depth", "y"))),
    Length: _ShapeReader(_read_length, 2, (("length", "span"),)),
    Pane: _ShapeReader(_read_pane, 3, (("width", "span"), ("height", "z")), 0.6),
    Rod: _ShapeReader(
        _read_rod, 3, (("diameter", "x"), ("diameter", "y"), ("height", "z"))
    ),
}

# Every shape an override may name, by the ``"type"`` it is written under.
SHAPE_TYPES: Mapping[str, type[PartShape]] = {
    cls.__name__: cls for cls in _SHAPE_READERS
}


def _studs_pair(run: Sequence[Fraction], at: int) -> tuple[int, int] | None:
    """The width/depth pair starting at ``at``, transposed from how LDraw
    writes it (depth, then width) -- or ``None`` if the run is too short or
    states a fraction of a stud. A part already named width-first is
    corrected back by :func:`_better_fit`."""
    if len(run) < at + 2:
        return None
    first, second = _studs(run[at]), _studs(run[at + 1])
    if first is None or second is None:
        return None
    return (second, first)


def _height(run: Sequence[Fraction]) -> Fraction:
    """The run's height, the third number -- implicitly one brick without it."""
    return run[2] if len(run) > 2 else Fraction(1)


def _studs(value: Fraction) -> int | None:
    """``value`` as a whole number of studs, or ``None`` if it is not one."""
    return int(value) if value.denominator == 1 else None


def _exact(value: Any) -> Any:
    """An override's field value, with a written fraction made exact."""
    return Fraction(value) if isinstance(value, str) else value
