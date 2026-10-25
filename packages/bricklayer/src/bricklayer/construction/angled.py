"""Simple parts with a non-axis-aligned face."""

from ..colors import Color
from ..geometry import HeightLike
from ..parts.element import Element
from ..parts.shape import Box
from ._factories import PartOptions

_SLOPES = PartOptions(
    "Slope",
    Box,
    (
        # 18 deg slopes
        "60477",
        "30363",
        # 25 deg slopes
        "49618",
        # 33 deg slopes
        "4286",
        "3298",
        "4161",
        "3297",
        # 45 deg slopes
        "3040b",
        "3039",
        "3038",
        "3037",
        "23949",
        "4445",
        # 65 deg slopes
        "60481a",
        "3678b",
        # 75 deg slopes
        "4460b",
        "3684c",
    ),
)
_INVERTED_SLOPES = PartOptions(
    "Inverted Slope",
    Box,
    (
        # -33 deg inverted slopes
        "4287a",
        "3747b",
        # -45 deg inverted slopes
        "3665a",
        "3660b",
        # -75 deg inverted slopes
        "2449",
    ),
)


def slope(
    width: int, depth: int, height: HeightLike = 1, color: Color = Color.WHITE
) -> Element:
    """A brick with an angled top, ideal for roofs.

    The part has a base of ``width`` x ``depth`` studs and is ``height`` bricks tall.
    The slope runs along the Y-axis (depth). It starts at ground level at the
    front edge of the front row (y=0, z=0) and reaches `height` at the front edge
    of the back row (y=depth-1, z=height). Studs sit only on the back row's flat top;
    antistuds cover the underside.

    Raises:
        ValueError: if the given arguments do not yield a valid part.
    """
    return _SLOPES.element(Box(width, depth, height), color)


def inverted_slope(
    width: int, depth: int, height: HeightLike = 1, color: Color = Color.WHITE
) -> Element:
    """A brick with an angled underside.

    The part has a base of ``width`` x ``depth`` studs and is ``height`` bricks tall.
    The slope runs along the Y-axis (depth). It starts at `height` at the front
    edge of the front row (y=0, z=height) and reaches ground level at the front
    edge of the back row (y=depth-1, z=0). Studs cover the top; antistuds sit only
    on the underside of the back row.

    Raises:
        ValueError: if the given arguments do not yield a valid part.
    """
    return _INVERTED_SLOPES.element(Box(width, depth, height), color)


_FACTORIES = ((slope, _SLOPES), (inverted_slope, _INVERTED_SLOPES))

__all__ = [factory.__name__ for factory, _ in _FACTORIES]
