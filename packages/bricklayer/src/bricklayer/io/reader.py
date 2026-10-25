"""Read LDraw (.ldr) text into a :class:`LegoBuild`.

The inverse of :mod:`.writer`. Each *type-1* line becomes a placement, each
``0 STEP`` a build-step marker, and each ``0 FILE`` block of a multipart
document a sub-model.

BrickLayer does not catalog every LDraw part, and an LDraw file can hold
geometry no model can express. Anything unrepresentable is skipped with an
:class:`LDrawImportWarning`, so reading a file always yields a model.
"""

from __future__ import annotations

import os
import warnings
from collections import Counter
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path

from ..colors import Color
from ..geometry import Pose
from ..ldraw import partdata
from ..ldraw.colors import (
    LDrawColor,
    color_definition,
    direct_color,
    parse_color_code,
    parse_color_definition,
)
from ..ldraw.conversion import INHERIT_COLOR, pose_from_type1
from ..ldraw.library import ImportLibrary
from ..modeling.build import LegoBuild
from ..parts.catalog import part_exists
from ..parts.element import Element

_Palette = dict[int, Color | LDrawColor]
_COLORS: _Palette = {color.ldraw_id: color for color in Color}

#: The line types carrying raw geometry: a line, a triangle, a quad, and an
#: optional line. None of them is a part.
_PRIMITIVES = frozenset({"2", "3", "4", "5"})

#: The meta commands that close a build step. ``ROTSTEP`` also turns the
#: camera, which a model does not hold.
_STEP_COMMANDS = frozenset({"STEP", "ROTSTEP"})


class LDrawImportWarning(UserWarning):
    """Warns that :func:`from_ldraw` could not represent part of a file."""


def from_ldraw(text: str, *, ldraw_library: str | Path | None = None) -> LegoBuild:
    """Read LDraw ``text`` into a :class:`LegoBuild`.

    A multipart document's first ``0 FILE`` block is the model; the rest are
    its sub-models, shared when their inherited colors agree. Text
    with no ``0 FILE`` line is read as a single model.

    ``ldraw_library`` (or ``LDRAW_LIBRARY_PATH``) optionally supplies an official
    library's rigid aliases and ``LDConfig.ldr`` palette. Imported colors do not
    extend the construction :class:`Color` enum. Direct colors and scoped
    ``!COLOUR`` definitions are supported; an unknown code keeps its geometry
    and code, with neutral appearance and a warning.

    Catalogued parts have collision meshes; connector data is optional.
    Parts without connectors still participate in collisions and surface support,
    but cannot form connector-based attachments.

    Comments, meta commands other than ``STEP``/``ROTSTEP``/``!COLOUR``, and raw
    geometry (line types 2-5) are ignored. Uncatalogued parts, non-rotation
    matrices, and undeclared files are skipped with counted warnings. A model
    with skipped geometry cannot provide a complete validity assessment.
    """
    skips = _Skips()
    blocks = _split_blocks(text.removeprefix("\ufeff"), skips)
    location = (
        ldraw_library if ldraw_library is not None else os.getenv("LDRAW_LIBRARY_PATH")
    )
    library = ImportLibrary(Path(location).expanduser()) if location else None
    palette = _COLORS.copy()
    if library is not None:
        if not (library.root / "parts").is_dir():
            raise ValueError(f"LDraw library has no parts directory: {library.root}")
        for name in ("LDConfig.ldr", "ldconfig.ldr"):
            config = library.root / name
            if config.is_file():
                for line in config.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines():
                    color = _definition(line, skips)
                    if color is not None:
                        palette.setdefault(color.ldraw_id, color)
                break
    model = _Reader(blocks, skips, library).model_for(
        next(iter(blocks)), Color.LIGHT_BLUISH_GRAY, palette
    )
    skips.flush()
    return model


def read_ldraw(
    path: str | Path, *, ldraw_library: str | Path | None = None
) -> LegoBuild:
    """Read the LDraw file at ``path`` into a :class:`LegoBuild`.

    Read as UTF-8 with undecodable bytes replaced by U+FFFD: LDraw predates
    UTF-8 and a third-party header routinely carries Latin-1 bytes, and
    comments are discarded on read anyway, so a replacement character in one
    is harmless.

    ``ldraw_library`` is forwarded to :func:`from_ldraw`.
    """
    return from_ldraw(
        Path(path).read_text(encoding="utf-8", errors="replace"),
        ldraw_library=ldraw_library,
    )


@dataclass(frozen=True)
class _Block:
    """One ``0 FILE`` section: the name it was declared under, and its lines."""

    name: str
    lines: list[str] = field(default_factory=list)


@dataclass
class _Skips:
    """What a read could not represent, counted so each cause warns once."""

    counts: Counter[tuple[str, str]] = field(default_factory=Counter)

    def record(self, verb: str, cause: str) -> None:
        """Note one line that ``verb`` applied to, for the reason ``cause``."""
        self.counts[(verb, cause)] += 1

    def flush(self) -> None:
        """Warn once per distinct cause, with how many lines it covered."""
        for (verb, cause), count in self.counts.items():
            lines = "line" if count == 1 else "lines"
            warnings.warn(
                f"{verb} {count} {lines}: {cause}", LDrawImportWarning, stacklevel=3
            )


@dataclass
class _Reader:
    """Builds a model per block; a sub-file referenced twice resolves to one
    :class:`LegoBuild`, as the writer keys sub-files by identity."""

    blocks: dict[str, _Block]
    skips: _Skips
    library: ImportLibrary | None = None
    _models: dict[
        tuple[str, Color | LDrawColor, frozenset[tuple[int, Color | LDrawColor]]],
        LegoBuild,
    ] = field(default_factory=dict)
    _reading: set[str] = field(default_factory=set)

    def model_for(
        self, key: str, inherited: Color | LDrawColor, palette: _Palette
    ) -> LegoBuild:
        """The model block ``key`` describes, read once and memoized."""
        cache_key = (key, inherited, frozenset(palette.items()))
        if cache_key not in self._models:
            self._reading.add(key)
            model = LegoBuild()
            palette = palette.copy()
            for line in self.blocks[key].lines:
                self._read(line, model, inherited, palette)
            self._reading.discard(key)
            self._models[cache_key] = model
        return self._models[cache_key]

    def _read(
        self,
        line: str,
        model: LegoBuild,
        inherited: Color | LDrawColor,
        palette: _Palette,
    ) -> None:
        """Add whatever ``line`` contributes to ``model``."""
        fields = line.split(maxsplit=1)
        if not fields:
            return
        kind = fields[0]
        if kind == "0":
            if _is_step(fields):
                model.add_step()
            color = _definition(line, self.skips)
            if color is not None:
                palette[color.ldraw_id] = color
        elif kind == "1":
            self._read_reference(line, model, inherited, palette)
        elif kind not in _PRIMITIVES:
            self.skips.record("skipped", f"malformed line {line!r}")

    def _read_reference(
        self,
        line: str,
        model: LegoBuild,
        inherited: Color | LDrawColor,
        palette: _Palette,
    ) -> None:
        """Place what a type-1 ``line`` references, or record why it cannot be."""
        parsed = self._parse(line)
        if parsed is None:
            return
        code, pose, target = parsed
        color = (
            inherited
            if code == INHERIT_COLOR
            else palette.get(code) or direct_color(code)
        )
        if color is None:
            self.skips.record(
                "used neutral appearance for", f"unknown LDraw color {code}"
            )
            color = LDrawColor(code)
        if target in self.blocks:
            self._place_sub_model(model, target, pose, color, palette)
        else:
            self._place_element(model, target, pose, color)

    def _place_sub_model(
        self,
        model: LegoBuild,
        key: str,
        pose: Pose,
        color: Color | LDrawColor,
        palette: _Palette,
    ) -> None:
        """Place the sub-file ``key`` names, under that name where it is free.

        A host names a sub-model after its sub-file, so writing the model back
        out reproduces the same file name. Only the first reference takes the
        name: a name is unique within its host.
        """
        if key in self._reading:
            self.skips.record("skipped", f"a sub-file that references itself, {key!r}")
            return
        stem = _stem(self.blocks[key].name)
        name = None if stem in model.names else stem
        model.add_raw(self.model_for(key, color, palette), pose, name=name)

    def _parse(self, line: str) -> tuple[int, Pose, str] | None:
        """A type-1 line's color code, world pose, and target, or ``None``."""
        fields = line.split(maxsplit=14)
        if len(fields) < 15:
            self.skips.record("skipped", f"malformed line {line!r}")
            return None
        target = _normalized(fields[14])
        try:
            code = parse_color_code(fields[1])
            if code < 0:
                raise ValueError("negative color code")
            numbers = [float(value) for value in fields[2:14]]
            if not all(isfinite(value) for value in numbers):
                raise ValueError("coordinates must be finite")
        except ValueError:
            self.skips.record("skipped", f"malformed line {line!r}")
            return None
        try:
            pose = pose_from_type1(numbers)
        except ValueError:
            self.skips.record("skipped", f"a matrix that is not a rotation, {target!r}")
            return None
        return code, pose, target

    def _place_element(
        self, model: LegoBuild, target: str, pose: Pose, color: Color | LDrawColor
    ) -> None:
        """Place the part ``target`` names, undoing the writer's seating pose."""
        if not target.endswith(".dat"):
            self.skips.record("skipped", f"undeclared file {target!r}")
            return
        part_id = target.removesuffix(".dat")
        visited: set[str] = set()
        while (
            not part_exists(part_id)
            and self.library is not None
            and part_id not in visited
        ):
            visited.add(part_id)
            redirect = self.library.redirect(part_id)
            if redirect is None:
                break
            part_id, offset = redirect
            pose = pose.compose(offset)
        if not part_exists(part_id):
            self.skips.record(
                "skipped", f"uncatalogued part {target.removesuffix('.dat')!r}"
            )
            return
        element_pose = partdata.record(part_id).element_pose(pose)
        model.add_raw(Element(part_id, color), element_pose)


def _definition(line: str, skips: _Skips) -> Color | LDrawColor | None:
    fields = line.split(maxsplit=2)
    if len(fields) < 2 or fields[0] != "0" or fields[1].upper() != "!COLOUR":
        return None
    try:
        color = parse_color_definition(line)
        standard = _COLORS.get(color.ldraw_id)
        if standard is not None and color_definition(standard) == line.strip():
            return standard
        return color
    except ValueError:
        skips.record("ignored", f"malformed !COLOUR definition {line!r}")
        return None


def _split_blocks(text: str, skips: _Skips) -> dict[str, _Block]:
    """``text`` as its ``0 FILE`` blocks, keyed by normalized name, in order.

    Text with no ``0 FILE`` line is one block under the empty key. A name
    declared twice keeps the first block and skips the rest. Text ahead of
    the first ``0 FILE`` line is a preamble, not a block: it is dropped, and
    warned about if it held a placement or a step marker.

    A block's first line, if it is a type-0 line, is the file's title and is
    dropped unread, so a title such as ``0 Step 2`` or ``0 FILE x`` is not
    taken for the meta command it spells.
    """
    blocks = {"": _Block("")}
    preamble = blocks[""]
    current = preamble
    awaiting_title = False
    for raw in text.splitlines():
        line = raw.strip()
        if awaiting_title and line:
            awaiting_title = False
            if line.split(maxsplit=1)[0] == "0":
                continue
        name = _file_declaration(line)
        if name is None:
            current.lines.append(line)
            continue
        awaiting_title = True
        key = _normalized(name)
        current = _Block(name)
        if key in blocks:
            skips.record("skipped", f"a repeated sub-file declaration, {key!r}")
        else:
            blocks[key] = current
    if len(blocks) > 1:
        for line in preamble.lines:
            if _is_meaningful(line):
                skips.record("dropped", "a preamble before the first 0 FILE block")
        del blocks[""]
    return blocks


def _file_declaration(line: str) -> str | None:
    """The name a ``0 FILE <name>`` line declares, or ``None``."""
    fields = line.split(maxsplit=2)
    if len(fields) == 3 and fields[0] == "0" and fields[1].upper() == "FILE":
        return fields[2].strip()
    return None


def _is_step(fields: list[str]) -> bool:
    """Whether a meta line closes a build step."""
    return len(fields) > 1 and fields[1].split(maxsplit=1)[0].upper() in _STEP_COMMANDS


def _is_meaningful(line: str) -> bool:
    """Whether ``line`` would contribute a placement or a step marker."""
    fields = line.split(maxsplit=1)
    if not fields:
        return False
    return fields[0] == "1" or (fields[0] == "0" and _is_step(fields))


def _normalized(target: str) -> str:
    """A file name as a lookup key: forward slashes, lower case, no padding."""
    return target.strip().replace("\\", "/").lower()


def _stem(name: str) -> str:
    """A sub-file's name without its ``.ldr`` extension."""
    return name[: -len(".ldr")] if name.lower().endswith(".ldr") else name
