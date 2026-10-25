"""Extract physical LDraw geometry for every selected BrickLayer part.

For each selected part it records ``bbox``: the min- and max-corners of the part's
bounding box in LDraw units (LDU), as two 3-tuples of floats.
"""

import sys
from collections.abc import Iterable
from pathlib import Path

from ...geometry import Mat3, Vec3
from ..meshes import DATA_DIR
from .library import Library, emit, extractor_parser, selected_part_ids

OUTPUT = DATA_DIR / "part_geometry.json"


class _Bounds:
    """A growing axis-aligned bounding box, held as six plain floats.

    :meth:`add` runs once per primitive vertex, so it updates scalars in place;
    :attr:`lo` and :attr:`hi` assemble the corners.
    """

    __slots__ = ("hx", "hy", "hz", "lx", "ly", "lz")

    def __init__(self) -> None:
        self.lx = self.ly = self.lz = float("inf")
        self.hx = self.hy = self.hz = float("-inf")

    def add(self, point: Vec3) -> None:
        x, y, z = point
        self.lx = min(self.lx, x)
        self.ly = min(self.ly, y)
        self.lz = min(self.lz, z)
        self.hx = max(self.hx, x)
        self.hy = max(self.hy, y)
        self.hz = max(self.hz, z)

    @property
    def lo(self) -> Vec3:
        return Vec3(self.lx, self.ly, self.lz)

    @property
    def hi(self) -> Vec3:
        return Vec3(self.hx, self.hy, self.hz)

    def empty(self) -> bool:
        return self.lx == float("inf")


def main(argv: list[str] | None = None) -> int:
    args = extractor_parser(__doc__, output=OUTPUT, ldraw=True).parse_args(argv)

    lib = Library.find(args.ldraw)
    print(f"Using LDraw library: {lib.root}")
    part_ids = selected_part_ids(lib)
    geometry = build_geometry(lib, part_ids)
    print(f"Measured {len(geometry)} of {len(part_ids)} selected parts.")
    if lib.missing:
        print(f"Unresolved sub-files (bbox may be incomplete): {sorted(lib.missing)}")

    unofficial = {
        part_id: reason
        for part_id in sorted(geometry)
        if (reason := lib.unofficial_reason(f"{part_id}.dat"))
    }
    if unofficial:
        print(
            f"WARNING: {len(unofficial)} selected part(s) are unofficial "
            "(geometry still included):",
            file=sys.stderr,
        )
        for part_id, reason in unofficial.items():
            print(f"  {part_id}: {reason}", file=sys.stderr)

    return emit(
        geometry,
        args.output,
        check=args.check,
        generated_by=_GENERATED_BY,
        note=_NOTE,
    )


def build_geometry(lib: Library, part_ids: Iterable[str]) -> dict[str, dict]:
    """Measure every part in ``part_ids``."""
    geometry: dict[str, dict] = {}
    for part_id in part_ids:
        bbox = part_bbox(lib, part_id)
        if bbox is None:
            print(f"  WARNING: no geometry found for {part_id}", file=sys.stderr)
            continue
        geometry[part_id] = {"bbox": bbox}
    return geometry


def part_bbox(
    lib: Library, part_id: str
) -> tuple[tuple[float, ...], tuple[float, ...]] | None:
    """The bounding box of ``part_id`` in LDraw units, or ``None`` if unresolved.

    Returned as ``((min_x, min_y, min_z), (max_x, max_y, max_z))``.
    """
    bounds = _Bounds()
    _accumulate(lib, f"{part_id}.dat", Mat3.IDENTITY, Vec3(0.0, 0.0, 0.0), bounds)
    if bounds.empty():
        return None
    lo = tuple(round(v, 2) for v in bounds.lo)
    hi = tuple(round(v, 2) for v in bounds.hi)
    return lo, hi


def _accumulate(
    lib: Library,
    name: str,
    m: Mat3,
    t: Vec3,
    bounds: _Bounds,
    depth: int = 0,
) -> None:
    """Walk ``name`` (and everything it references), adding every primitive
    vertex -- transformed into the top-level part's frame -- to ``bounds``."""
    if depth > 64:  # cycle / runaway guard; real parts nest only a few levels.
        return
    lines = lib.lines(name)
    if lines is None:
        return
    for line in lines:
        fields = line.split()
        if not fields:
            continue
        kind = fields[0]
        if kind == "1" and len(fields) >= 15:
            sub_t = Vec3(*map(float, fields[2:5]))
            sub_m = Mat3.from_flattened(tuple(map(float, fields[5:14])))
            sub_name = " ".join(fields[14:])
            cm, ct = _compose(m, t, sub_m, sub_t)
            _accumulate(lib, sub_name, cm, ct, bounds, depth + 1)
        elif kind in ("2", "3", "4"):
            count = int(kind)
            coords = list(map(float, fields[2 : 2 + 3 * count]))
            for v in range(count):
                bounds.add(_apply(m, t, Vec3(*coords[3 * v : 3 * v + 3])))


def _apply(m: Mat3, t: Vec3, p: Vec3) -> Vec3:
    """Transform point ``p`` by rotation ``m`` then offset ``t``."""
    return m @ p + t


def _compose(m1: Mat3, t1: Vec3, m2: Mat3, t2: Vec3) -> tuple[Mat3, Vec3]:
    """Compose two transforms.

    Composing ``m1 @ (m2 @ p + t2) + t1`` gives matrix ``m1 @ m2`` and translation
    ``m1 @ t2 + t1``.
    """
    return m1 @ m2, _apply(m1, t1, t2)


_GENERATED_BY = Path(__file__).name
_NOTE = (
    "Geometry measured from an LDraw library, in LDraw units. Do not edit by hand."
    " bbox gives the min- and max-corners of the part's bounding box in the LDraw part's local frame."
)


if __name__ == "__main__":
    raise SystemExit(main())
