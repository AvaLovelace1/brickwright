"""LDraw import colors, separate from the documented construction palette."""

from dataclasses import dataclass

from ..colors import Color, Finish, hex2rgb


@dataclass(frozen=True, slots=True)
class LDrawColor:
    """An imported color code with its appearance and optional !COLOUR definition."""

    ldraw_id: int
    rgb: str = "808080"
    display_name: str = "Unknown LDraw color"
    finish: Finish = Finish.SOLID
    alpha: int = 255
    definition: str | None = None


def parse_color_definition(line: str) -> LDrawColor:
    """Read a !COLOUR line, preserving material parameters for re-export."""
    fields = line.split()
    if len(fields) < 9 or [f.upper() for f in fields[:2]] != ["0", "!COLOUR"]:
        raise ValueError("malformed !COLOUR definition")
    tags = [f.upper() for f in fields[3:]]
    # MATERIAL has its own VALUE/ALPHA fields; they describe the inclusions.
    end = tags.index("MATERIAL") if "MATERIAL" in tags else len(tags)
    base = tags[:end]

    def value(tag: str, default: str | None = None) -> str:
        if tag not in base:
            if default is not None:
                return default
            raise ValueError(f"missing {tag}")
        index = base.index(tag) + 1
        if index >= end:
            raise ValueError(f"missing {tag} value")
        return fields[index + 3]

    code = int(value("CODE"))
    if code < 0:
        raise ValueError("negative color code")
    rgb = _rgb(value("VALUE"))
    edge = value("EDGE")
    if edge.startswith("#") or edge.lower().startswith("0x"):
        _rgb(edge)
    elif int(edge) < 0:
        raise ValueError("negative edge color code")
    alpha = int(value("ALPHA", "255"))
    luminance = int(value("LUMINANCE", "0"))
    if not 0 <= alpha <= 255 or not 0 <= luminance <= 255:
        raise ValueError("color byte outside 0..255")
    finish = Finish.TRANSPARENT if alpha < 255 else Finish.SOLID
    for tag, candidate in (
        ("CHROME", Finish.CHROME),
        ("PEARLESCENT", Finish.PEARL),
        ("MATTE_METALLIC", Finish.METALLIC),
        ("METAL", Finish.METALLIC),
        ("GLITTER", Finish.GLITTER),
    ):
        if tag in tags:
            finish = candidate
    if luminance:
        finish = Finish.GLOW
    return LDrawColor(
        code, rgb, fields[2].replace("_", " "), finish, alpha, line.strip()
    )


def direct_color(code: int) -> LDrawColor | None:
    """Decode the standard 0x2RRGGBB direct-color encoding."""
    if _is_direct(code):
        rgb = f"{code & 0xFFFFFF:06X}"
        return LDrawColor(code, rgb, f"Direct #{rgb}")
    return None


def format_color_code(code: int) -> str:
    """A type-1 line's color field: hexadecimal for a direct color, else decimal."""
    return f"0x{code:X}" if _is_direct(code) else str(code)


def parse_color_code(field: str) -> int:
    """A type-1 line's color field as an int, accepting direct colors' hexadecimal."""
    return int(field, 16) if field.lower().startswith("0x") else int(field)


def color_definition(color: Color | LDrawColor) -> str | None:
    """The definition needed to restore this appearance in an LDraw scope."""
    if isinstance(color, LDrawColor):
        return color.definition
    alpha = " ALPHA 128" if color.finish is Finish.TRANSPARENT else ""
    return (
        f"0 !COLOUR {color.name} CODE {color.ldraw_id} "
        f"VALUE #{color.rgb} EDGE #333333{alpha}"
    )


def _is_direct(code: int) -> bool:
    return code >> 24 == 2


def _rgb(value: str) -> str:
    if value.startswith("#"):
        rgb = value[1:]
    elif value.lower().startswith("0x"):
        rgb = value[2:]
    else:
        raise ValueError("RGB needs # or 0x prefix")
    hex2rgb(rgb)
    return rgb.upper()
