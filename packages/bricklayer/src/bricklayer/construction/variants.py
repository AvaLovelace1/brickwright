"""Named options for the small construction helpers.

These enums select helper behavior; PartSpec describes catalog parts using
LDraw metadata alone. ``None`` selects the plain form where supported.
"""

from .._mixins import DocumentedEnum


class PartVariant(DocumentedEnum):
    """Base class for every part-variant enum."""


# Architecture
class FrameVariant(PartVariant):
    """A window frame variant. ``None`` means a plain rectangular frame.

    Some variants (ARCHED, THREE_PANES, AIRPLANE, TRAIN) only change the shape of the opening,
    while others (SLOPED, ANGLED_CORNER, ROUND_CORNER) change the geometry of the frame itself.
    """

    ARCHED = "A window frame with a rounded (arched) top."
    THREE_PANES = "A window frame divided into three panes."
    AIRPLANE = "A rounded window frame, ideal for an airplane fuselage."
    TRAIN = "A rounded window frame, ideal for a train car."
    SLOPED = "Slopes down back to front, forming a 45-degree angle with the vertical."
    ANGLED_CORNER = "Forms a 45-degree corner."
    ROUND_CORNER = "Curves around a corner."


class PaneVariant(PartVariant):
    """A window pane: the insert that fills a frame in a :func:`window`."""

    SOLID = "A solid pane, typically in a transparent color to represent glass."
    LATTICE = "An elegant pane of crisscrossing diagonal strips."
    GRILLE = "A pane of vertical and horizontal slats, like a jail cell window."


class DoorVariant(PartVariant):
    """A door leaf: the insert that fills a frame in a :func:`door`."""

    SOLID = "A plain, solid hinged door."
    GLASS = "A glass door with three panes."
    WINDOWED = "A classic house door with a four-pane window."
    PET = "A door with a six-pane window and a pet flap at the bottom."
    GRILLE = "A hinged door with vertical and horizontal slats, like a jail cell."


# Every concrete variant enum.
__all__ = [cls.__name__ for cls in PartVariant.__subclasses__()]
