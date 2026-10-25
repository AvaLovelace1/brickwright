"""Shared plumbing for the LDraw extraction scripts.

Each ``extract_part_*`` script supplies only what is its own -- where its
inputs come from and how to build its records -- and reads the rest from here:
:func:`find_dir` locates an input directory, :func:`extractor_parser` declares
the common flags, and :func:`emit` performs the ``--check``-or-write tail.
:func:`catalog_sources` resolves the catalog and its data donors together.
"""

from __future__ import annotations

import argparse
import json
import lzma
import os
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property
from importlib import resources
from pathlib import Path
from typing import Any

from ..naming import part_name
from .fallbacks import PartFallbacks, PartSource
from .selection import select_part_ids

# Conventional system-wide LDraw library locations, in search order.
SYSTEM_LDRAW_ROOTS = (
    "~/ldraw",
    "~/.ldraw",
    "/usr/share/ldraw",
    "/usr/local/share/ldraw",
)

# Official LDraw library roots to try, in order, when --ldraw isn't given.
_LDRAW_ROOTS = (
    os.environ.get("LDRAW_LIBRARY_PATH", ""),
    *(os.path.expanduser(root) for root in SYSTEM_LDRAW_ROOTS),
)


def find_dir(
    candidates: Iterable[str | None],
    *,
    marker: str,
    subdirs: tuple[str, ...] = (),
    hint: str,
) -> Path:
    """The first of ``candidates`` that holds ``marker``, else ``SystemExit``.

    ``marker`` is a name to look for inside a candidate, or a glob when any
    matching file will do. ``subdirs`` names extra places to look under each
    candidate, so a caller may point at either the directory itself or its
    parent. ``hint`` leads the failure message, which lists what was tried.
    """
    tried: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        tried.append(candidate)
        base = Path(candidate)
        for root in (base, *(base / sub for sub in subdirs)):
            if _holds(root, marker):
                return root
    raise SystemExit(f"{hint}\nTried: {', '.join(tried) or '(none)'}")


def _holds(root: Path, marker: str) -> bool:
    if any(ch in marker for ch in "*?["):
        return root.is_dir() and any(root.glob(marker))
    return (root / marker).exists()


def find_bricknet_meshes(explicit: str | None = None) -> Path:
    """BrickNet's directory of inset PLYs."""
    return find_dir(
        (explicit, os.environ.get("BRICKNET_MESHES"), os.environ.get("BRICKNET_DATA")),
        marker="*.ply",
        subdirs=("inset",),
        hint=(
            "No BrickNet meshes found. Point --meshes or $BRICKNET_MESHES at the"
            " directory of inset PLYs (`python -m bricknet fetch-meshes` downloads"
            " them)."
        ),
    )


def find_bricknet_data(explicit: str | None = None) -> Path:
    """BrickNet's ``_data/<version>`` directory of connector labels."""
    packaged = None
    try:
        packaged = str(resources.files("bricknet") / "_data" / "v1")
    except ModuleNotFoundError:
        pass
    return find_dir(
        (explicit, os.environ.get("BRICKNET_DATA"), packaged),
        marker="labels.json.xz",
        subdirs=("_data/v1",),
        hint=(
            "No BrickNet connector labels found. Point --bricknet-data or"
            " $BRICKNET_DATA at BrickNet's _data/<version> directory (the one"
            " holding labels.json.xz and part_aliases.json.xz)."
        ),
    )


def load_alias_sources(bricknet_data: Path) -> list[tuple[str, PartSource]]:
    """BrickNet aliases with their source-to-wrapper coordinate transforms."""
    with lzma.open(bricknet_data / "part_aliases.json.xz") as f:
        rows = json.load(f)["rows"]
    return [
        (row["src"], source)
        for row in rows
        if (source := PartSource.from_ldraw(row["dst"], row["final_matrix_3x4"]))
        is not None
    ]


def load_labels(bricknet_data: Path) -> dict[str, dict]:
    """Original BrickNet connector labels, keyed by LDraw stem."""
    with lzma.open(bricknet_data / "labels.json.xz") as f:
        return {
            name.removesuffix(".dat"): entry for name, entry in json.load(f).items()
        }


def redirect_target(description: str) -> str | None:
    """The id a ``~Moved to <id>`` stub points at, or ``None`` for a real part."""
    words = part_name(description).split()
    return words[2] if words[:2] == ["Moved", "to"] and len(words) > 2 else None


def mesh_part_ids(mesh_dir: Path) -> list[str]:
    """Every part id BrickNet ships an inset PLY for."""
    return sorted(p.stem for p in mesh_dir.glob("*.ply"))


def extractor_parser(
    doc: str | None, *, output: Path, ldraw: bool = False
) -> argparse.ArgumentParser:
    """An extractor's argument parser, carrying the flags every one of them has.

    A script adds only its own input flags on top.
    """
    parser = argparse.ArgumentParser(description=doc)
    if ldraw:
        parser.add_argument("--ldraw", help="LDraw library root (contains parts/, p/)")
    parser.add_argument(
        "--output",
        type=Path,
        default=output,
        help=f"where to write (default: the committed {output.name})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=f"diff against the committed {output.name}; don't write it",
    )
    return parser


def emit(
    parts: dict[str, Any],
    path: Path,
    *,
    check: bool,
    generated_by: str,
    note: str,
    units: str | None = "LDU",
) -> int:
    """Write ``parts`` to ``path``, or under ``check`` only diff it.

    Returns the process exit code, so drift fails ``--check`` identically for
    every extractor.
    """
    if check:
        return 0 if report_against_committed(parts, path) else 1
    write_parts_json(path, parts, generated_by=generated_by, note=note, units=units)
    print(f"Wrote {len(parts)} parts to {path}")
    return 0


def selected_part_ids(
    lib: Library,
    *,
    mesh_dir: Path | None = None,
    bricknet_data: Path | None = None,
) -> list[str]:
    """Every selected catalog id, sorted; see :func:`catalog_sources` for donors."""
    return catalog_sources(lib, mesh_dir=mesh_dir, bricknet_data=bricknet_data).part_ids


@dataclass(frozen=True)
class CatalogSources:
    """Selected ids, resolved donors, and original labels for one extraction."""

    part_ids: list[str]
    meshes: dict[str, PartSource]
    connectivity: dict[str, PartSource]
    labels: dict[str, dict]


def catalog_sources(
    lib: Library,
    *,
    mesh_dir: Path | None = None,
    bricknet_data: Path | None = None,
) -> CatalogSources:
    """Resolve donors once, then select every described part with a collider.

    Meshes use LDraw redirects and decoration families; connector labels also
    use BrickNet aliases. Original label ids remain available for extraction
    even when they are absent from the selected catalog.
    """
    mesh_dir = mesh_dir or find_bricknet_meshes()
    bricknet_data = bricknet_data or find_bricknet_data()
    labels = load_labels(bricknet_data)
    meshes = PartFallbacks(lib).sources(lib.descriptions, mesh_part_ids(mesh_dir))
    connectivity = PartFallbacks(lib, load_alias_sources(bricknet_data)).sources(
        lib.descriptions.keys() | labels.keys(), labels
    )
    part_ids = select_part_ids(
        mesh_ids=meshes,
        descriptions=lib.descriptions,
    )
    return CatalogSources(part_ids, meshes, connectivity, labels)


class Library:
    """An LDraw parts library: resolves file references and caches their lines.

    Sub-files are looked up across the official ``parts/``, ``parts/s/``
    (subparts) and ``p/`` (primitives) trees and their unofficial counterparts.
    ``parts/s/`` is searched by name as well as through the ``s/`` prefix a
    sub-file reference carries, so a part id that is itself filed as a subpart
    still resolves.
    """

    def __init__(self, root: Path):
        self.root = root
        self.search_dirs = [
            root / "parts",
            root / "parts" / "s",
            root / "p",
            root / "UnOfficial" / "parts",
            root / "UnOfficial" / "parts" / "s",
            root / "UnOfficial" / "p",
        ]
        self._lines: dict[str, list[str] | None] = {}
        self._first_lines: dict[str, str | None] = {}
        self._headers: dict[str, tuple[str | None, str] | None] = {}
        self.missing: set[str] = set()

    @cached_property
    def descriptions(self) -> dict[str, str]:
        """Descriptions of every top-level part in the official library."""
        return {
            path.stem: self.description(path.stem)
            for path in sorted((self.root / "parts").glob("*.dat"))
        }

    def resolve(self, name: str) -> Path | None:
        rel = name.replace("\\", "/")
        for base in self.search_dirs:
            candidate = base / rel
            if candidate.is_file():
                return candidate
        return None

    def lines(self, name: str) -> list[str] | None:
        if name not in self._lines:
            path = self.resolve(name)
            if path is None:
                self._lines[name] = None
                self.missing.add(name)
            else:
                self._lines[name] = path.read_text(encoding="latin-1").splitlines()
        return self._lines[name]

    def description(self, part_id: str) -> str:
        """``part_id``'s LDraw description: its ``.dat``'s first line, with the
        leading ``"0 "`` stripped.

        Empty when the part isn't in the library, which
        :func:`~bricklayer.ldraw.scripts.selection.select_part_ids` reads as a
        rejection. Reads and caches only the first line: selection calls this
        for every mesh id.
        """
        name = f"{part_id}.dat"
        if name not in self._first_lines:
            path = self.resolve(name)
            if path is None:
                self._first_lines[name] = None
                self.missing.add(name)
            else:
                with path.open(encoding="latin-1") as f:
                    self._first_lines[name] = f.readline().rstrip("\r\n")
        first_line = self._first_lines[name]
        return first_line.removeprefix("0 ") if first_line else ""

    def header(self, part_id: str) -> tuple[str | None, str] | None:
        """``(explicit !CATEGORY, description)`` for a part, or ``None`` if absent.

        Reads and caches only the leading meta block.
        """
        name = f"{part_id}.dat"
        if name not in self._headers:
            self._headers[name] = self._read_header(name)
        return self._headers[name]

    def _read_header(self, name: str) -> tuple[str | None, str] | None:
        path = self.resolve(name)
        if path is None:
            return None
        description = ""
        with path.open(encoding="latin-1") as handle:
            for line in handle:
                line = line.strip()
                if line.startswith("0 !CATEGORY"):
                    return line.split(None, 2)[2].strip(), description
                if not description and line.startswith("0 "):
                    description = line[2:].strip()
                if line and not line.startswith("0"):
                    break
        return None, description

    def unofficial_reason(self, name: str) -> str | None:
        """Why ``name`` is an unofficial LDraw part, or ``None`` if it's official.

        A part counts as unofficial if its ``!LDRAW_ORG`` header marks it so, or
        -- failing an explicit marker -- if it lives only in the library's
        ``UnOfficial/`` tree rather than the official parts.
        """
        path = self.resolve(name)
        if path is None:
            return None
        for line in self.lines(name) or []:
            stripped = line.strip()
            if stripped.startswith("0 !LDRAW_ORG"):
                if "unofficial" in stripped.lower():
                    return "marked unofficial in its header"
                break  # explicit official marker; fall through to the location check
        if "UnOfficial" in path.parts:
            return "found only in the library's UnOfficial tree"
        return None

    @classmethod
    def find(cls, explicit: str | None = None) -> Library:
        """The official LDraw library: ``explicit``, else the first known location
        holding a ``parts/`` directory.
        """
        hint = "Could not find an LDraw library (a directory containing 'parts/')."
        if not explicit:
            hint += " Pass --ldraw PATH or set $LDRAW_LIBRARY_PATH."
        roots = [explicit] if explicit else list(_LDRAW_ROOTS)
        return cls(find_dir(roots, marker="parts", hint=hint))


def write_parts_json(
    path: Path,
    parts: dict[str, Any],
    *,
    generated_by: str,
    note: str,
    units: str | None = "LDU",
) -> None:
    """Write ``parts`` to ``path`` as stable JSON, one compact record per part.

    Each part is a single compact record on its own line, so adding a part or
    shifting its geometry makes a one-line diff. ``units`` is omitted from the
    header for a file that measures nothing.
    """
    header: dict[str, str] = {"_generated_by": generated_by, "_note": note}
    if units is not None:
        header["units"] = units
    header_lines = "".join(
        f"  {json.dumps(key)}: {json.dumps(value)},\n" for key, value in header.items()
    )
    # Manually lay each part on one line; ``json.dumps`` can't produce this
    records = ",\n".join(
        f"    {json.dumps(part_id)}: {json.dumps(record)}"
        for part_id, record in sorted(parts.items())
    )
    path.write_text(f'{{\n{header_lines}  "parts": {{\n{records}\n  }}\n}}\n')


def report_against_committed(parts: dict[str, Any], path: Path) -> bool:
    """Print how the freshly-extracted ``parts`` differ from the committed data
    file at ``path``. Returns ``True`` if they're identical."""
    print(f"Comparison with committed {path.name}:")
    if not path.is_file():
        print(f"  no committed file at {path} -- run without --check to create it")
        return False
    committed = json.loads(path.read_text())["parts"]
    fresh = json.loads(json.dumps(parts))  # normalize tuples etc. to JSON types
    clean = report_membership(fresh, committed)
    for part_id in sorted(set(fresh) & set(committed)):
        if fresh[part_id] != committed[part_id]:
            clean = False
            print(f"  ~ {part_id}: {_summarize(committed[part_id], fresh[part_id])}")
    if clean:
        print("  committed file is up to date")
    return clean


def report_membership(fresh: Iterable[str], committed: Iterable[str]) -> bool:
    """Print which ids were added and removed; ``True`` if the two sets match."""
    clean = True
    for part_id in sorted(set(fresh) - set(committed)):
        clean = False
        print(f"  + {part_id}: new part, not yet committed")
    for part_id in sorted(set(committed) - set(fresh)):
        clean = False
        print(f"  - {part_id}: committed but no longer extracted")
    return clean


def _summarize(was: Any, now: Any) -> str:
    text = f"{was} -> {now}"
    return text if len(text) <= 120 else "record changed"
