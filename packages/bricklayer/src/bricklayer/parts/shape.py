"""The :class:`PartShape` hierarchy: nominal dimensions for catalog discovery.

A shape describes a part's nominal dimensions -- a box's width, depth and
height, a disc's diameter -- and nothing else. It is derived from a part's LDraw
name and used by catalog search and size-based construction helpers.
"""

from __future__ import annotations

from abc import ABC
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, replace
from fractions import Fraction
from typing import Any, ClassVar

from ..geometry import HeightLike, to_exact_height


@dataclass(frozen=True, repr=False)
class PartShape(ABC):
    """A part's nominal dimensions, used in catalog search filters.

    Concrete shapes specify their units below. Missing shape information does not
    prevent construction; use an element's bounding box for its measured extent.
    """

    LABEL: ClassVar[str]

    # Per-field canonicalization, by field name.
    NORMALIZERS: ClassVar[Mapping[str, Callable[[Any], HeightLike]]] = {
        "height": to_exact_height,
        "length": Fraction,
    }

    def __post_init__(self) -> None:
        for field in fields(self):
            normalize = self.NORMALIZERS.get(field.name)
            if normalize is not None:
                object.__setattr__(
                    self, field.name, normalize(getattr(self, field.name))
                )

    @property
    def label(self) -> str:
        """The dimension string used in part names and error messages."""
        return self.LABEL.format(**self.field_values)

    @property
    def dimensions(self) -> tuple[HeightLike, ...]:
        """The field values in declaration order, for ordering and nearness."""
        return tuple(self.field_values.values())

    def transpose(self) -> PartShape:
        """The shape's width/depth mirror -- itself, for a shape with no
        meaningful axis swap, such as a round part."""
        return self

    @property
    def field_values(self) -> dict[str, Any]:
        """The shape's dataclass fields, by name, in declaration order."""
        return {field.name: getattr(self, field.name) for field in fields(self)}

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.label})"


@dataclass(frozen=True, repr=False)
class Box(PartShape):
    """A rectangular solid, ``width`` studs x ``depth`` studs x ``height`` bricks.

    ``height`` is quantized to whole plates (1/3 brick), so ``5/3`` and
    ``Fraction(5, 3)`` name the same box.
    """

    LABEL = "{width}x{depth}x{height}"

    width: int
    depth: int
    height: HeightLike

    def transpose(self) -> Box:
        return replace(self, width=self.depth, depth=self.width)


@dataclass(frozen=True, repr=False)
class Footprint(PartShape):
    """A flat part, ``width`` x ``depth`` studs, with a fixed height (e.g., a plate or tile)."""

    LABEL = "{width}x{depth}"

    width: int
    depth: int

    def transpose(self) -> Footprint:
        return replace(self, width=self.depth, depth=self.width)


@dataclass(frozen=True, repr=False)
class Rod(PartShape):
    """A round brick: ``diameter`` studs across and ``height`` bricks tall.

    ``height`` is quantized to whole plates (1/3 brick).
    """

    LABEL = "⌀{diameter}x{height}"

    diameter: int
    height: HeightLike


@dataclass(frozen=True, repr=False)
class Disc(PartShape):
    """A round flat part, ``diameter`` studs across, with a fixed height (e.g., a round plate or a dish)."""

    LABEL = "⌀{diameter}"

    diameter: int


@dataclass(frozen=True, repr=False)
class Pane(PartShape):
    """A thin standing sheet: ``width`` studs x ``height`` bricks.

    ``height`` is quantized to whole plates (1/3 brick).
    """

    LABEL = "{width}x{height}"

    width: int
    height: HeightLike


@dataclass(frozen=True, repr=False)
class Length(PartShape):
    """A part measured only along its own axis (e.g. Technic beams): ``length`` studs long.

    ``length`` is normalized to an exact ``Fraction``, so ``1.5`` and ``Fraction(3, 2)`` name the same length.
    """

    LABEL = "{length}L"

    length: HeightLike


@dataclass(frozen=True, repr=False)
class Ell(PartShape):
    """An L-shaped part: a flat plate with a studded SNOT flange along the front edge.

    The plate is ``width`` x ``depth`` studs; the flange is ``face_width`` studs
    across and ``face_height`` studs **tall**.

    A flange's height is measured in studs, so the part is not in general a whole number of plates tall.
    """

    LABEL = "{width}x{depth}-{face_width}x{face_height}"

    width: int
    depth: int
    face_width: int
    face_height: int


def shape_sort_key(shape: PartShape | None) -> tuple[HeightLike, ...]:
    """A size ordering key over any shape (an absent shape sorts as empty)."""
    return () if shape is None else shape.dimensions
