"""Available colors (pass any as a `color=` argument).

`Color` is a closed enum. The available colors below are grouped by surface finish.
"""

from ._mixins import DocumentedEnum, ReprEnum


def hex2rgb(hex_str: str) -> tuple[int, int, int]:
    """Convert a hex color string (e.g. "C91A09") to an ``(r, g, b)`` tuple."""
    if len(hex_str) != 6:
        raise ValueError(f"invalid hex color string: {hex_str!r}")
    r, g, b = bytes.fromhex(hex_str)
    return r, g, b


def linear_rgb(hex_str: str) -> tuple[float, float, float]:
    """A hex color's ``(r, g, b)`` converted from sRGB to linear light, each in ``[0, 1]``."""
    r, g, b = (
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        for c in (channel / 255 for channel in hex2rgb(hex_str))
    )
    return r, g, b


class Finish(DocumentedEnum):
    """The surface finish of a LEGO ``Color``.

    A finish describes how the plastic looks and catches the light, independent of hue.
    """

    SOLID = "Opaque plastic with a smooth surface -- the default for most bricks."
    TRANSPARENT = (
        "See-through, translucent plastic used for glass, water, and light effects."
    )
    OPALESCENT = "Translucent plastic with a milky opal sheen."
    GLITTER = "Translucent plastic infused with fine reflective flakes that sparkle."
    PEARL = "Opaque plastic with a pearlescent sheen, duller than Metallic."
    METALLIC = "Opaque plastic with a metallic shimmer, shinier than Pearl."
    CHROME = "A mirror-like metal coating electroplated onto the plastic. Even shinier and more reflective than Metallic."
    GLOW = "Phosphorescent plastic that absorbs light and glows in the dark."


class Color(ReprEnum):
    """A standard LEGO color.

    Members expose ``lego_id`` (official element color id), ``ldraw_id`` (the
    LDraw color code), ``rgb`` (an RGB hex code), ``finish`` (its surface
    :class:`Finish`), and ``display_name``.

    Colors are sourced from https://rebrickable.com/colors/, sorted by the number of
    sets they appear in. Only colors appearing in sets from 2021 onwards are included.
    """

    # NAME = (lego_id, ldraw_id, rgb, finish)

    BLACK = (26, 0, "05131D", Finish.SOLID)
    WHITE = (1, 15, "FFFFFF", Finish.SOLID)
    LIGHT_BLUISH_GRAY = (194, 71, "A0A5A9", Finish.SOLID)
    DARK_BLUISH_GRAY = (199, 72, "6C6E68", Finish.SOLID)
    RED = (21, 4, "C91A09", Finish.SOLID)
    YELLOW = (24, 14, "F2CD37", Finish.SOLID)
    BLUE = (23, 1, "0055BF", Finish.SOLID)
    REDDISH_BROWN = (192, 70, "582A12", Finish.SOLID)
    TAN = (5, 19, "E4CD9E", Finish.SOLID)
    GREEN = (28, 2, "237841", Finish.SOLID)
    ORANGE = (106, 25, "FE8A18", Finish.SOLID)
    DARK_TAN = (138, 28, "958A73", Finish.SOLID)
    DARK_BLUE = (140, 272, "0A3463", Finish.SOLID)
    LIME = (119, 27, "BBE90B", Finish.SOLID)
    DARK_RED = (154, 320, "720E0F", Finish.SOLID)
    MEDIUM_NOUGAT = (312, 84, "AA7D55", Finish.SOLID)
    MEDIUM_AZURE = (322, 322, "36AEBF", Finish.SOLID)
    BRIGHT_LIGHT_ORANGE = (191, 191, "F8BB3D", Finish.SOLID)
    BRIGHT_GREEN = (37, 10, "4B9F4A", Finish.SOLID)
    DARK_ORANGE = (38, 484, "A95500", Finish.SOLID)
    DARK_BROWN = (308, 308, "352100", Finish.SOLID)
    DARK_TURQUOISE = (107, 3, "008F9B", Finish.SOLID)
    DARK_GREEN = (141, 288, "184632", Finish.SOLID)
    BRIGHT_PINK = (222, 29, "E4ADC8", Finish.SOLID)
    LIGHT_NOUGAT = (283, 78, "F6D7B3", Finish.SOLID)
    DARK_PURPLE = (268, 85, "3F3691", Finish.SOLID)
    DARK_AZURE = (321, 321, "078BC9", Finish.SOLID)
    SAND_GREEN = (151, 378, "A0BCAC", Finish.SOLID)
    DARK_PINK = (221, 5, "C870A0", Finish.SOLID)
    MAGENTA = (124, 26, "923978", Finish.SOLID)
    BRIGHT_LIGHT_YELLOW = (226, 226, "FFF03A", Finish.SOLID)
    MEDIUM_BLUE = (102, 73, "5A93DB", Finish.SOLID)
    MEDIUM_LAVENDER = (324, 30, "AC78BA", Finish.SOLID)
    LIGHT_AQUA = (323, 323, "ADC3C0", Finish.SOLID)
    BRIGHT_LIGHT_BLUE = (212, 212, "9FC3E9", Finish.SOLID)
    SAND_BLUE = (135, 379, "6074A1", Finish.SOLID)
    OLIVE_GREEN = (330, 330, "9B9A5A", Finish.SOLID)
    LAVENDER = (325, 31, "E1D5ED", Finish.SOLID)
    CORAL = (353, 353, "FF698F", Finish.SOLID)
    NOUGAT = (18, 92, "D09168", Finish.SOLID)
    YELLOWISH_GREEN = (326, 326, "DFEEA5", Finish.SOLID)
    REDDISH_ORANGE = (402, 402, "CA4C0B", Finish.SOLID)
    VIBRANT_YELLOW = (368, 368, "EBD800", Finish.SOLID)
    WARM_TAN = (371, 371, "CCA373", Finish.SOLID)
    MEDIUM_BROWN = (370, 370, "755945", Finish.SOLID)
    BLUE_VIOLET = (431, 431, "A3A9FF", Finish.SOLID)
    SKY_BLUE = (232, 232, "7DBFDD", Finish.SOLID)
    SIENNA_BROWN = (422, 422, "915C3C", Finish.SOLID)
    WARM_PINK = (430, 430, "F6B7BF", Finish.SOLID)
    UMBER_BROWN = (423, 423, "5E3F33", Finish.SOLID)

    TRANS_CLEAR = (40, 47, "FCFCFC", Finish.TRANSPARENT)
    TRANS_LIGHT_BLUE = (42, 43, "AEEFEC", Finish.TRANSPARENT)
    TRANS_RED = (41, 36, "C91A09", Finish.TRANSPARENT)
    TRANS_ORANGE = (182, 57, "F08F1C", Finish.TRANSPARENT)
    TRANS_YELLOW = (44, 46, "F5CD2F", Finish.TRANSPARENT)
    TRANS_DARK_BLUE = (43, 33, "0020A0", Finish.TRANSPARENT)
    TRANS_BROWN = (111, 40, "635F52", Finish.TRANSPARENT)
    TRANS_NEON_GREEN = (49, 42, "F8F184", Finish.TRANSPARENT)
    TRANS_GREEN = (48, 34, "84B68D", Finish.TRANSPARENT)
    TRANS_DARK_PINK = (113, 37, "DF6695", Finish.TRANSPARENT)
    TRANS_NEON_ORANGE = (47, 38, "FF800D", Finish.TRANSPARENT)
    TRANS_BRIGHT_GREEN = (311, 35, "D9E4A7", Finish.TRANSPARENT)
    TRANS_PURPLE = (126, 52, "A5A5CB", Finish.TRANSPARENT)
    TRANS_BLACK = (375, 10375, "635F52", Finish.TRANSPARENT)

    OPAL_TRANS_LIGHT_BLUE = (362, 362, "68BCC5", Finish.OPALESCENT)
    OPAL_TRANS_CLEAR = (360, 360, "FCFCFC", Finish.OPALESCENT)
    OPAL_TRANS_PURPLE = (365, 365, "8320B7", Finish.OPALESCENT)
    OPAL_TRANS_DARK_PINK = (364, 364, "CE1D9B", Finish.OPALESCENT)
    OPAL_TRANS_DARK_BLUE = (366, 10366, "0020A0", Finish.OPALESCENT)
    OPAL_TRANS_BRIGHT_GREEN = (367, 367, "84B68D", Finish.OPALESCENT)
    OPAL_TRANS_BROWN = (363, 363, "583927", Finish.OPALESCENT)

    GLITTER_TRANS_PURPLE = (129, 129, "A5A5CB", Finish.GLITTER)
    GLITTER_TRANS_DARK_PINK = (114, 114, "DF6695", Finish.GLITTER)
    GLITTER_TRANS_LIGHT_BLUE = (302, 302, "68BCC5", Finish.GLITTER)
    GLITTER_TRANS_CLEAR = (117, 117, "FFFFFF", Finish.GLITTER)

    PEARL_GOLD = (297, 297, "AA7F2E", Finish.PEARL)
    PEARL_SILVER = (315, 179, "898788", Finish.PEARL)
    PEARL_TITANIUM = (316, 87, "3E3C39", Finish.PEARL)
    PEARL_WHITE = (183, 183, "F2F3F2", Finish.PEARL)

    METALLIC_GOLD = (335, 82, "DBAC34", Finish.METALLIC)
    METALLIC_SILVER = (336, 80, "A5A9B4", Finish.METALLIC)

    CHROME_GOLD = (310, 334, "BBA53D", Finish.CHROME)
    CHROME_SILVER = (309, 383, "E0E0E0", Finish.CHROME)

    GLOW_IN_DARK_WHITE = (329, 329, "D9D9D9", Finish.GLOW)

    def __init__(self, lego_id: int, ldraw_id: int, rgb: str, finish: Finish) -> None:
        # pragma: no mutate block, causes issues with mutmut
        self.lego_id = lego_id
        self.ldraw_id = ldraw_id
        self.rgb = rgb
        self.finish = finish
