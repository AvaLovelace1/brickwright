"""BrickNet collision meshes for catalogued parts.

They are stored Draco-compressed, one STORED zip per LDraw category, with an
``index.json`` mapping part id to category so a lookup opens exactly one archive.
Vertices are in raw LDraw units (LDU), which is the frame collision runs in.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from functools import cached_property, lru_cache
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

import DracoPy  # ty: ignore[unresolved-import] (compiled extension, ships no stubs)
import numpy as np

if TYPE_CHECKING:
    from collections.abc import Iterable

# Vertex quantization. 14 bits keeps the worst deviation across the whole LDraw
# library at 0.0845 LDU, roughly a sixth of
# :data:`~bricklayer.geometry.collision.MATING_CLEARANCE_LDU`, so encoding cannot
# eat into the clearance the inset provides.
QUANTIZATION_BITS = 14

# The package directory holding the committed part data and mesh store.
DATA_DIR = Path(str(resources.files("bricklayer.ldraw")))

_INDEX = "index.json"


class MeshUnavailable(LookupError):
    """No collision mesh is available for a part."""


@dataclass(frozen=True)
class Mesh:
    """A triangle mesh in a part's local LDraw frame, in LDU.

    ``vertices`` is ``(n, 3)`` float and ``faces`` is ``(m, 3)`` integer indices.
    """

    vertices: np.ndarray
    faces: np.ndarray

    def __post_init__(self) -> None:
        if self.vertices.ndim != 2 or self.vertices.shape[1] != 3:
            raise ValueError(f"vertices must be (n, 3), got {self.vertices.shape}")
        if self.faces.ndim != 2 or self.faces.shape[1] != 3:
            raise ValueError(f"faces must be (m, 3), got {self.faces.shape}")

    @cached_property
    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        """The mesh's own axis-aligned bounds ``(lo, hi)`` in LDU.

        Degenerate at the origin for an empty mesh.
        """
        if not len(self.vertices):
            return np.zeros(3), np.zeros(3)
        return self.vertices.min(axis=0), self.vertices.max(axis=0)

    @cached_property
    def extent(self) -> float:
        """The longest side of the mesh's axis-aligned bounding box, in LDU."""
        lo, hi = self.bounds
        return float((hi - lo).max())


def encode_mesh(mesh: Mesh, *, bits: int = QUANTIZATION_BITS) -> bytes:
    """``mesh`` as a Draco frame.

    Vertex order is not preserved; nothing downstream depends on it.
    """
    return DracoPy.encode(
        mesh.vertices,
        mesh.faces,
        quantization_bits=bits,
        compression_level=10,
        preserve_order=False,
    )


def decode_mesh(frame: bytes) -> Mesh:
    """The :class:`Mesh` in a Draco frame."""
    decoded = DracoPy.decode(frame)
    return Mesh(
        np.asarray(decoded.points, dtype=float),
        np.asarray(decoded.faces, dtype=np.int32),
    )


def quantization_bound(mesh: Mesh, *, bits: int = QUANTIZATION_BITS) -> float:
    """The largest distance a vertex of ``mesh`` can move under encoding, in LDU.

    Draco quantizes over the mesh's own bounding cube, so the bound scales with the
    part's longest side: half a step, in the worst direction.
    """
    step = mesh.extent / (2**bits - 1)
    return step * np.sqrt(3) / 2


class MeshStore:
    """Draco meshes on disk, sharded into one zip per LDraw category."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._cache: dict[str, Mesh] = {}
        self._archives: dict[str, zipfile.ZipFile] = {}

    def __contains__(self, part_id: str) -> bool:
        return part_id in self._index

    def part_ids(self) -> Iterable[str]:
        """Every part id the store indexes."""
        return self._index.keys()

    def category(self, part_id: str) -> str:
        """The LDraw category ``part_id`` is filed under."""
        try:
            return self._index[part_id]
        except KeyError:
            raise MeshUnavailable(f"no collision mesh for part {part_id!r}") from None

    def read(self, part_id: str) -> Mesh:
        """The mesh for ``part_id``, decoded once and cached."""
        if part_id not in self._cache:
            self._cache[part_id] = self._decode(part_id)
        return self._cache[part_id]

    def _decode(self, part_id: str) -> Mesh:
        category = self.category(part_id)
        try:
            frame = self._archive(category).read(f"{part_id}.drc")
        except KeyError:
            raise MeshUnavailable(
                f"part {part_id!r} is indexed under {category!r} but absent from"
                f" {self.root / f'{category}.zip'}"
            ) from None
        return decode_mesh(frame)

    def _archive(self, category: str) -> zipfile.ZipFile:
        """The open archive for ``category``, kept open across reads."""
        if category not in self._archives:
            path = self.root / f"{category}.zip"
            if not path.exists():
                raise MeshUnavailable(
                    f"category {category!r} is indexed, but {path} is missing"
                )
            self._archives[category] = zipfile.ZipFile(path)
        return self._archives[category]

    @cached_property
    def _index(self) -> dict[str, str]:
        path = self.root / _INDEX
        if not path.exists():
            return {}
        return json.loads(path.read_text())


def write_store(root: Path, meshes: dict[str, tuple[str, Mesh]]) -> None:
    """Write ``{part_id: (category, mesh)}`` to ``root`` as per-category archives.

    Frames are already compressed, so the zips are STORED: reads seek straight to a
    member without inflating anything around it.
    """
    root.mkdir(parents=True, exist_ok=True)
    by_category: dict[str, dict[str, Mesh]] = {}
    for part_id, (category, mesh) in meshes.items():
        by_category.setdefault(category, {})[part_id] = mesh
    for category, members in by_category.items():
        with zipfile.ZipFile(root / f"{category}.zip", "w", zipfile.ZIP_STORED) as zf:
            for part_id, mesh in sorted(members.items()):
                zf.writestr(f"{part_id}.drc", encode_mesh(mesh))
    index = {part_id: category for part_id, (category, _) in meshes.items()}
    (root / _INDEX).write_text(json.dumps(dict(sorted(index.items())), indent=0))


@lru_cache(maxsize=1)
def default_store() -> MeshStore:
    """The mesh store shipped inside the package."""
    return MeshStore(DATA_DIR / "meshes")


def mesh(part_id: str) -> Mesh:
    """The collision mesh for ``part_id``, from the packaged store."""
    return default_store().read(part_id)
