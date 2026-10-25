"""Basic parts: bricks, plates, and tiles."""

from __future__ import annotations

from ..colors import Color
from ..geometry import HeightLike
from ..parts.element import Element
from ..parts.shape import Box, Footprint
from ._factories import PartOptions

_BRICKS = PartOptions(
    "Brick",
    Box,
    (
        "3005",
        "3004",
        "3622",
        "3010",
        "3009",
        "3008",
        "6111",
        "6112",
        "2465",
        "3003",
        "3002",
        "3001",
        "2456",
        "3007",
        "3006",
        "14716",
        "2453a",
        "3245a",
        "22886",
        "2454b",
        "30145",
        "49311",
    ),
)
_PLATES = PartOptions(
    "Plate",
    Footprint,
    (
        "3024",
        "3023b",
        "3623",
        "3710",
        "78329",
        "3666",
        "3460",
        "4477",
        "60479",
        "3022",
        "3021",
        "3020",
        "3795",
        "3034",
        "3832",
        "2445",
        "91988",
        "4282",
        "11212",
        "3031",
        "3032",
        "3035",
        "3030",
        "3029",
        "3958",
        "3036",
        "3033",
        "3028",
        "3456",
        "3027",
        "41539",
        "92438",
        "91405",
    ),
)
_TILES = PartOptions(
    "Tile",
    Footprint,
    (
        "3070b",
        "3069b",
        "63864",
        "2431",
        "6636",
        "4162",
        "3068b",
        "26603",
        "87079",
        "69729",
        "1751",
        "10202",
        "90498",
    ),
)


def brick(
    width: int,
    depth: int,
    height: HeightLike = 1,
    color: Color = Color.WHITE,
) -> Element:
    """A solid rectangular brick, the most basic LEGO part.

    The brick has a base of ``width`` x ``depth`` studs and is ``height`` bricks tall.
    Studs cover its top, and antistuds cover its bottom.

    Raises:
        ValueError: if the given arguments do not yield a valid part.
    """
    return _BRICKS.element(Box(width, depth, height), color)


def plate(
    width: int,
    depth: int,
    color: Color = Color.WHITE,
) -> Element:
    """A thin rectangular plate, one third of a brick tall.

    The plate has a base of ``width`` x ``depth`` studs and a height of one plate (1/3 of a brick).
    Like a brick, studs cover its top and antistuds cover its bottom.

    Raises:
        ValueError: if the given arguments do not yield a valid part.
    """
    return _PLATES.element(Footprint(width, depth), color)


def tile(
    width: int,
    depth: int,
    color: Color = Color.WHITE,
) -> Element:
    """A thin rectangular tile: like a plate, but with a smooth top (no studs). Ideal for finishing surfaces.

    Raises:
        ValueError: if the given arguments do not yield a valid part.
    """
    return _TILES.element(Footprint(width, depth), color)


_FACTORIES = ((brick, _BRICKS), (plate, _PLATES), (tile, _TILES))

__all__ = [factory.__name__ for factory, _ in _FACTORIES]
