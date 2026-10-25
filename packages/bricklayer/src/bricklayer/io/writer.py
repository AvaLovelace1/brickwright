"""Write a :class:`LegoBuild` to LDraw (.ldr) text.

Each placed part becomes an LDraw *type-1* line::

    1 <color> x y z  a b c d e f g h i  <part>.dat

where ``x y z`` is the part's origin and ``a..i`` is its 3x3 orientation matrix,
converted from BrickLayer's axes by :mod:`bricklayer.ldraw.conversion`::

    LDraw X = BrickLayer  x   (width;  20 LDU per stud)
    LDraw Y = BrickLayer -z   (height;  8 LDU per plate, up is negative)
    LDraw Z = BrickLayer  y   (depth;  20 LDU per stud)
"""

from collections import Counter
from pathlib import Path

from ..ldraw import partdata
from ..ldraw.colors import LDrawColor, color_definition, format_color_code
from ..ldraw.conversion import INHERIT_COLOR, format_ldu, pose_to_ldraw
from ..modeling.build import LegoBuild
from ..parts.element import Element

# The main model's sub-file name in an MPD (it must come first).
_MAIN_NAME = "main.ldr"


def to_ldraw(model: LegoBuild) -> str:
    """Render ``model`` as LDraw text.

    With no sub-models, the result is a flat list of type-1 lines. When the model
    nests sub-models, the result is a multipart document: the main model and each
    distinct sub-model become a ``0 FILE`` block, and a nested model is drawn as a
    type-1 reference to its sub-file.

    A ``0 STEP`` is written wherever the model records a build-step marker (see
    :meth:`~bricklayer.modeling.build.LegoBuild.add_step`), including ahead of the first
    placement and repeated for an empty step. A model recording no markers gets
    none.
    """
    subfile_names: dict[int, str] = {}
    used_names: set[str] = {_MAIN_NAME}  # lower-cased; the main block claims this
    queue: list[LegoBuild] = []
    imported_codes = {
        p.content.color.ldraw_id
        for p in model.flattened_placements
        if isinstance(p.content.color, LDrawColor) and p.content.color.definition
    }

    def _claim(candidate: str) -> str:
        """``candidate`` if free, else ``<stem>_2.ldr``, ``<stem>_3.ldr``, ...

        LDraw file names are case-insensitive, so ``Wing.ldr`` and
        ``wing.ldr`` clash.
        """
        new_name = candidate
        stem = candidate.removesuffix(".ldr")
        suffix = 2
        while new_name.lower() in used_names:
            new_name = f"{stem}_{suffix}.ldr"
            suffix += 1
        used_names.add(new_name.lower())
        return new_name

    def reference(sub: LegoBuild, name: str | None) -> str:
        """The sub-file name for ``sub``, assigning (and queuing) one on first use.

        Keyed by identity, so the same sub-model placed more than once is defined
        once and referenced repeatedly (sub-models are held by reference). A named
        placement names its sub-file ``<name>.ldr``; unnamed ones get sequential
        ``submodel{n}.ldr``. Sub-file names that would clash are disambiguated.
        """
        key = id(sub)
        if key not in subfile_names:
            name = name or "submodel"
            subfile_names[key] = _claim(f"{name}.ldr")
            queue.append(sub)
        return subfile_names[key]

    def render(host: LegoBuild) -> list[str]:
        """Type-1 lines for one model's own placements, in its local frame,
        with a ``0 STEP`` wherever the model records a build-step marker."""
        markers = Counter(host.step_markers)
        definitions: dict[int, str] = {}
        lines = []
        for index, placement in enumerate(host.placements):
            lines.extend(["0 STEP"] * markers[index])
            content = placement.content
            if isinstance(content, Element):
                pose = partdata.record(content.ldraw_id).ldraw_pose(placement.pose)
                target = f"{content.ldraw_id}.dat"
                color = content.color.ldraw_id
                if color in imported_codes:
                    definition = color_definition(content.color)
                    if definition is not None and definitions.get(color) != definition:
                        lines.append(definition)
                        definitions[color] = definition
            else:
                pose = placement.pose
                target = reference(content, host.name_of(placement))
                color = INHERIT_COLOR
            rotation, translation = pose_to_ldraw(pose)
            matrix = " ".join(format_ldu(v) for v in rotation.flatten().tolist())
            coords = " ".join(format_ldu(v) for v in translation.tolist())
            lines.append(f"1 {format_color_code(color)} {coords} {matrix} {target}")
        lines.extend(["0 STEP"] * markers[len(host.placements)])
        return lines

    main = render(model)
    if not queue:
        return _join(main)

    out = _file_block(_MAIN_NAME, main)
    for sub in queue:  # rendering a sub-model can queue more
        out += _file_block(subfile_names[id(sub)], render(sub))
    return _join(out)


def write_ldraw(model: LegoBuild, path: str | Path) -> None:
    """Write ``model`` to ``path`` as an LDraw (.ldr) file."""
    Path(path).write_text(to_ldraw(model), encoding="utf-8")


def _file_block(name: str, lines: list[str]) -> list[str]:
    """``lines`` as an MPD ``0 FILE`` block; the title lines name it in Studio."""
    stem = name.removesuffix(".ldr")
    return [f"0 FILE {name}", f"0 {stem}", f"0 Name: {stem}", *lines]


def _join(lines: list[str]) -> str:
    return "".join(line + "\n" for line in lines)
