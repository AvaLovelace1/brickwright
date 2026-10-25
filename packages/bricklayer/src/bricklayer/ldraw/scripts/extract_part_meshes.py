"""Extract BrickNet collision meshes for every catalogued BrickLayer part.

BrickNet ships one binary PLY per part under ``inset/``, watertighted and inset by
:data:`~bricklayer.geometry.collision.SURFACE_INSET_LDU` per surface -- the whole
collision tolerance. Point ``--meshes`` (or ``$BRICKNET_MESHES``, or
``$BRICKNET_DATA``) at that directory; ``python -m bricknet fetch-meshes`` downloads
it. The PLYs store Z negated relative to LDraw, which this script undoes.

Missing PLYs are resolved through rigid redirects and decoration variants;
donor geometry is transformed into the requested part's own LDraw frame.

Parts are filed by LDraw category, read from the official library at
``$LDRAW_LIBRARY_PATH``, and written as one Draco-compressed zip per category so
that no single archive approaches PyPI's per-file size limit.
"""

import sys
from pathlib import Path

import numpy as np

from ..conversion import pose_to_ldraw
from ..meshes import DATA_DIR, Mesh, MeshStore, write_store
from ..naming import part_name
from .fallbacks import PartSource
from .library import (
    Library,
    catalog_sources,
    extractor_parser,
    find_bricknet_meshes,
    mesh_part_ids,
    redirect_target,
    report_membership,
)

OUTPUT = DATA_DIR / "meshes"

# Categories that exist only as bookkeeping; nobody builds with them.
EXCLUDED_CATEGORIES = frozenset({"Moved", "Obsolete", "Sticker Shortcut"})

_PLY_TYPES = {
    "double": "<f8", "float": "<f4", "float32": "<f4", "float64": "<f8",
    "uchar": "u1", "uint8": "u1", "char": "i1", "int8": "i1",
    "ushort": "<u2", "uint16": "<u2", "short": "<i2", "int16": "<i2",
    "uint": "<u4", "uint32": "<u4", "int": "<i4", "int32": "<i4",
}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = extractor_parser(__doc__, output=OUTPUT, ldraw=True)
    parser.add_argument("--meshes", help="directory of BrickNet inset PLYs")
    parser.add_argument(
        "--all",
        action="store_true",
        help="extract every part BrickNet ships (default: the selected catalog only)",
    )
    args = parser.parse_args(argv)

    mesh_dir = find_bricknet_meshes(args.meshes)
    lib = Library.find(args.ldraw)
    print(f"Using BrickNet meshes: {mesh_dir}")
    print(f"Using LDraw library:   {lib.root}")

    if args.all:
        part_ids = mesh_part_ids(mesh_dir)
        sources = {part_id: PartSource(part_id) for part_id in part_ids}
    else:
        catalog = catalog_sources(lib, mesh_dir=mesh_dir)
        part_ids, sources = catalog.part_ids, catalog.meshes
    exclude = EXCLUDED_CATEGORIES if args.all else frozenset()
    categories, missing, uncategorized = categorize(
        lib, part_ids, sources, exclude=exclude
    )

    print(f"Extracted {len(categories)} of {len(part_ids)} parts.")
    if missing:
        print(f"  WARNING: no mesh for: {', '.join(missing)}", file=sys.stderr)
    if uncategorized:
        print(
            f"  WARNING: not in the LDraw library, skipped: {len(uncategorized)} parts",
            file=sys.stderr,
        )

    # --check compares which parts ship, so it stops before decoding any geometry.
    if args.check:
        return _report_against_committed(categories, args.output)

    write_store(args.output, _read_meshes(mesh_dir, categories, sources))
    print(f"Wrote {len(categories)} meshes to {args.output}")
    return 0


def categorize(
    lib: Library,
    part_ids: list[str],
    sources: dict[str, PartSource],
    *,
    exclude: frozenset[str] | set[str] = frozenset(),
) -> tuple[dict[str, str], list[str], list[str]]:
    """Which parts ship and under which category, without decoding any geometry.

    Returns ``{part_id: category}``, the ids with no donor, and the ids absent from
    the LDraw library (which cannot be categorized, so are skipped). Parts in an
    ``exclude``d category are dropped silently.
    """
    categories: dict[str, str] = {}
    missing: list[str] = []
    uncategorized: list[str] = []
    for part_id in part_ids:
        if part_id not in sources:
            missing.append(part_id)
            continue
        category = ldraw_category(lib, part_id)
        if category is None:
            uncategorized.append(part_id)
            continue
        if category not in exclude:
            categories[part_id] = category
    return categories, missing, uncategorized


def _read_meshes(
    mesh_dir: Path,
    categories: dict[str, str],
    sources: dict[str, PartSource],
) -> dict[str, tuple[str, Mesh]]:
    """Each categorized part's donor PLY, transformed into its own LDraw frame."""
    meshes = {}
    for part_id, category in categories.items():
        source = sources[part_id]
        mesh = read_ply(mesh_dir / f"{source.part_id}.ply")
        matrix, offset = pose_to_ldraw(source.pose)
        meshes[part_id] = (
            category,
            Mesh(mesh.vertices @ matrix.T + offset, mesh.faces),
        )
    return meshes


def read_ply(path: Path) -> Mesh:
    """The :class:`Mesh` in a binary-little-endian PLY, in the LDraw frame.

    BrickNet writes these with meshio, whose vertex property types vary between
    parts, so the layout is read from the header.
    """
    raw = path.read_bytes()
    end = raw.index(b"end_header\n") + len(b"end_header\n")

    element = None
    counts = {"vertex": 0, "face": 0}
    vertex_props: list[tuple[str, str]] = []
    face_prop: tuple[str, str] | None = None
    for line in raw[:end].decode().splitlines():
        words = line.split()
        match words:
            case ["format", encoding, *_] if encoding != "binary_little_endian":
                raise ValueError(f"{path.name}: unsupported PLY format {encoding!r}")
            case ["element", name, count]:
                element = name
                counts[name] = int(count)
            case ["property", kind, name] if element == "vertex":
                vertex_props.append((name, _PLY_TYPES[kind]))
            case ["property", "list", count_kind, index_kind, _] if element == "face":
                face_prop = (_PLY_TYPES[count_kind], _PLY_TYPES[index_kind])

    body = raw[end:]
    vertex_dtype = np.dtype(vertex_props)
    vertices = np.frombuffer(body, vertex_dtype, counts["vertex"])
    points = np.stack(
        [vertices["x"], vertices["y"], -vertices["z"]], axis=1, dtype=float
    )

    if not counts["face"]:
        return Mesh(points, np.zeros((0, 3), dtype=np.int32))
    if face_prop is None:
        raise ValueError(f"{path.name}: face element has no index list property")
    count_type, index_type = face_prop
    faces = np.frombuffer(
        body,
        np.dtype([("n", count_type), ("i", index_type, 3)]),
        counts["face"],
        counts["vertex"] * vertex_dtype.itemsize,
    )
    if (faces["n"] != 3).any():
        raise ValueError(f"{path.name}: faces are not all triangular")
    return Mesh(points, faces["i"].astype(np.int32))


def ldraw_category(lib: Library, part_id: str) -> str | None:
    """``part_id``'s LDraw category, or ``None`` if it is not in the library.

    The category is the ``!CATEGORY`` meta when a part declares one, and otherwise
    the first word of its description -- the LDraw convention.

    A ``~Moved to <part>`` stub files under the category of the part it became.
    """
    seen: set[str] = set()
    while part_id not in seen:
        seen.add(part_id)
        header = lib.header(part_id)
        if header is None:
            # A dangling redirect target: keep the stub's own category.
            return "Moved" if seen - {part_id} else None
        category, description = header
        if category is not None:
            return category
        words = part_name(description).split()
        if not words:
            return "Uncategorized"
        if (target := redirect_target(description)) is not None:
            part_id = target
            continue
        return words[0].strip(".,")
    return "Moved"  # a redirect cycle


def _report_against_committed(categories: dict[str, str], output: Path) -> int:
    """Diff the extracted parts against the committed store; don't write.

    Returns a shell exit code, so drift fails ``--check`` the way it does for the
    data-file extractors.
    """
    print(f"Comparison with committed {output.name}:")
    clean = report_membership(categories, MeshStore(output).part_ids())
    if clean:
        print(f"  committed store is up to date ({len(categories)} parts)")
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
