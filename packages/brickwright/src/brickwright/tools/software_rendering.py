"""A CPU-only LDraw renderer: parse ``.ldr``/``.dat`` files and rasterize with numpy.

Renders build previews where there is no GPU stack. So it runs standalone,
without brickwright's render dependencies, it may import **only the stdlib,
numpy, and bricklayer**, and imports bricklayer lazily so the camera tables load
without it.

Cameras match the GPU pipeline: the same view names and directions, the same
``azimuth``/``elevation`` semantics, and the same bounding-sphere framing as
pygfx's ``show_object`` with a 50-degree perspective camera, so images from the
two pipelines are interchangeable for the critique loops. Rendering is a plain
z-buffer rasterizer with flat shading from a camera headlight; parts are shrunk
slightly toward their centers so seams between same-colored bricks stay visible
(the ``gaps`` option of the GPU pipeline).
"""

from __future__ import annotations

import math
import os
import struct
import tarfile
import zipfile
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import numpy as np

Vec3 = tuple[float, float, float]

# Unit view-direction vectors (camera looks *toward* the model along these), in
# the renderer's y-up frame (LDraw x, -y, -z).
VIEW_DIRECTIONS: dict[str, Vec3] = {
    "front": (0.0, 0.0, 1.0),
    "side": (1.0, 0.0, 0.0),
    "top": (0.0, -1.0, 0.0),
    "iso": (-1.0, -1.0, 1.0),
}

VIEW_ORDER: tuple[str, ...] = tuple(VIEW_DIRECTIONS)

# The steepest camera elevation, in degrees either way: straight down or up.
MAX_ELEVATION = 90.0

# Camera up-vectors, one per view.
VIEW_UP_VECTORS: dict[str, Vec3] = {
    "front": (0.0, 1.0, 0.0),
    "side": (0.0, 1.0, 0.0),
    "top": (0.0, 0.0, -1.0),
    "iso": (0.0, 1.0, 0.0),
}

_FOV_DEGREES = 50.0  # vertical field of view, as the GPU pipeline's camera

# Flat headlight shading: full color facing the camera, dimmer at grazing angles.
_AMBIENT = 0.35
_DIFFUSE = 0.65

# How far each part's surface is inset toward its center, in LDraw units, so
# adjacent same-colored parts keep a visible seam.
_PART_GAP_LDU = 0.5

_FALLBACK_COLOR = ((0.5, 0.5, 0.5), 1.0)

# LDraw's "current color" code: a line drawn in it takes its parent reference's color.
_INHERIT_COLOR = 16

# Sub-file nesting cutoff, a guard against self-referencing files; real ones nest
# only a few levels.
_MAX_DEPTH = 64

_HERE = Path(__file__).resolve().parent

# LDraw library roots to try, in order, when neither an explicit path nor
# $LDRAW_LIBRARY_PATH is given: a library or an archive of one in the working
# directory or next to this file, then the usual install locations.
_DEFAULT_LIBRARY_ROOTS = (
    "ldraw",
    "ldraw.tar",
    "ldraw.zip",
    str(_HERE / "ldraw"),
    str(_HERE / "ldraw.tar"),
    str(_HERE / "ldraw.zip"),
    "~/ldraw",
    "~/.ldraw",
    "/usr/share/ldraw",
    "/usr/local/share/ldraw",
)


class LDrawFileNotFound(FileNotFoundError):
    """An LDraw file referenced by the model could not be resolved."""


def angle_to_view_dir(azimuth: float, elevation: float) -> Vec3:
    """A unit view direction (camera -> model) for a spherical camera angle in degrees.

    ``azimuth`` rotates the camera horizontally (0 faces the model's front, positive
    swings the camera to the model's right); ``elevation`` tilts it vertically (0 is
    level, positive looks down from above). Consistent with the canonical views:
    ``(0, 0)`` is ``front``, ``(90, 0)`` is ``side``, ``(0, 90)`` is ``top``.
    """
    if not -MAX_ELEVATION <= elevation <= MAX_ELEVATION:
        raise ValueError(
            f"elevation must be within -{MAX_ELEVATION:g}..{MAX_ELEVATION:g} degrees,"
            f" got {elevation}"
        )
    a = math.radians(azimuth)
    e = math.radians(elevation)
    return (math.cos(e) * math.sin(a), -math.sin(e), math.cos(e) * math.cos(a))


def angle_up(elevation: float) -> Vec3:
    """Camera up-vector for an angled render: world-up, swapped at the poles where it
    would be parallel to the view direction."""
    return (0.0, 0.0, -1.0) if abs(elevation) >= MAX_ELEVATION else (0.0, 1.0, 0.0)


class _LibraryArchive:
    """Read-only view of an archived parts library (a zip or a tar of one)."""

    def __init__(self, path: Path):
        if zipfile.is_zipfile(path):
            self._zip: zipfile.ZipFile | None = zipfile.ZipFile(path)
            self._tar: tarfile.TarFile | None = None
            names = self._zip.namelist()
        elif tarfile.is_tarfile(path):
            self._zip = None
            self._tar = tarfile.open(path)  # noqa: SIM115 -- archive owns the handle
            names = [m.name for m in self._tar.getmembers() if m.isfile()]
        else:
            raise LDrawFileNotFound(f"{path} is neither a zip nor a tar archive")
        self.members = {name.lower(): name for name in names}

    def read(self, member: str) -> bytes:
        if self._zip is not None:
            return self._zip.read(member)
        assert self._tar is not None
        extracted = self._tar.extractfile(member)
        assert extracted is not None  # members only lists regular files
        return extracted.read()


class PartLibrary:
    """An LDraw parts library: resolves file references and caches their lines.

    The root is a library directory, or a tar/zip archive of one. Sub-files are
    looked up across the official ``parts/`` and ``p`` (primitives) trees and
    their unofficial counterparts. References are normalized (backslash
    separators, lowercase fallback) so files author-cased on disk still resolve.
    """

    _SEARCH_PREFIXES = ("parts", "p", "UnOfficial/parts", "UnOfficial/p")

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser()
        self._archive = _LibraryArchive(self.root) if self.root.is_file() else None
        self._lines: dict[str, list[str] | None] = {}

    @property
    def is_archive(self) -> bool:
        """Whether the library is a tar/zip archive rather than a directory."""
        return self._archive is not None

    def resolve(self, name: str) -> Path | str | None:
        """The file for a reference like ``3001.dat`` or ``s\\3001s01.dat``: an
        on-disk path for a directory library, a member name for an archived one."""
        rel = name.replace("\\", "/")
        for candidate_rel in (rel, rel.lower()):
            for prefix in self._SEARCH_PREFIXES:
                if self._archive is None:
                    candidate = self.root / prefix / candidate_rel
                    if candidate.is_file():
                        return candidate
                else:
                    member = f"{prefix}/{candidate_rel}".lower()
                    if member in self._archive.members:
                        return self._archive.members[member]
        return None

    def lines(self, name: str) -> list[str] | None:
        """The file's lines, or ``None`` when the reference doesn't resolve."""
        if name not in self._lines:
            located = self.resolve(name)
            if located is None:
                self._lines[name] = None
            elif self._archive is not None:
                assert isinstance(located, str)
                self._lines[name] = (
                    self._archive.read(located).decode("latin-1").splitlines()
                )
            else:
                assert isinstance(located, Path)
                self._lines[name] = located.read_text("latin-1").splitlines()
        return self._lines[name]

    @classmethod
    def find(cls, root: str | Path | None = None) -> PartLibrary:
        """Open the library at ``root``, ``$LDRAW_LIBRARY_PATH``, or the first
        default location that looks like one (a directory containing ``parts/``,
        or a tar/zip archive of one)."""
        candidates = (
            [root]
            if root
            else [
                os.environ.get("LDRAW_LIBRARY_PATH", ""),
                *_DEFAULT_LIBRARY_ROOTS,
            ]
        )
        for candidate in candidates:
            if candidate and _looks_like_library(Path(candidate).expanduser()):
                return cls(candidate)
        tried = ", ".join(str(c) for c in candidates if c)
        raise LDrawFileNotFound(
            "Could not find an LDraw parts library (a directory containing 'parts/'"
            f" or a tar/zip archive of one). Tried: {tried}."
            " Pass library=PATH or set $LDRAW_LIBRARY_PATH."
        )


def _looks_like_library(candidate: Path) -> bool:
    if (candidate / "parts").is_dir():
        return True
    if not candidate.is_file():
        return False
    if not (zipfile.is_zipfile(candidate) or tarfile.is_tarfile(candidate)):
        return False
    members = _LibraryArchive(candidate).members.values()
    return any(name.startswith("parts/") for name in members)


def _raise_missing(missing: set[str], library: PartLibrary) -> None:
    """Report unresolvable LDraw references, naming them all."""
    raise LDrawFileNotFound(
        f"missing LDraw file(s): {', '.join(sorted(missing))} (library: {library.root})"
    )


@dataclass
class Mesh:
    """Tessellated model triangles: per-part geometry with per-triangle colors."""

    # One entry per placed part: (n, 3, 3) float vertices in the y-up frame.
    part_vertices: list[np.ndarray] = field(default_factory=list)
    # Matching (n, 4) float RGBA per triangle, channels 0..1.
    part_colors: list[np.ndarray] = field(default_factory=list)
    missing: set[str] = field(default_factory=set)
    # Parts without an LDraw file, drawn as their catalog bounding box instead.
    approximated: set[str] = field(default_factory=set)

    def combined(self) -> tuple[np.ndarray, np.ndarray]:
        """All triangles and colors as two flat arrays (empty-safe)."""
        if not self.part_vertices:
            return np.zeros((0, 3, 3)), np.zeros((0, 4))
        return np.concatenate(self.part_vertices), np.concatenate(self.part_colors)


def load_mesh(ldr_path: str | Path, library: PartLibrary) -> Mesh:
    """Tessellate an ``.ldr`` model (flat or multipart) into a :class:`Mesh`.

    Each library part reached from the model becomes one gap-inset part entry;
    multipart-document sub-files group placements but are not parts themselves.
    Raises :class:`LDrawFileNotFound` when referenced library files are missing,
    naming them all.
    """
    text = Path(ldr_path).read_text("latin-1")
    documents = _split_multipart(text)
    mesh = Mesh()
    main = next(iter(documents), None)
    if main is None:
        return mesh

    def walk_document(
        name: str, matrix: np.ndarray, offset: np.ndarray, color: int, depth: int = 0
    ):
        if depth > _MAX_DEPTH:
            return
        for fields in _references(_parsed_lines(documents[name])):
            sub_name, sub_matrix, sub_offset, sub_color = _child(
                fields, matrix, offset, color
            )
            if sub_name.lower() in documents:
                walk_document(
                    sub_name.lower(), sub_matrix, sub_offset, sub_color, depth + 1
                )
            else:
                _emit_part(mesh, library, sub_name, sub_matrix, sub_offset, sub_color)

    walk_document(main, np.eye(3), np.zeros(3), _INHERIT_COLOR)
    if mesh.missing:
        _raise_missing(mesh.missing, library)
    return mesh


def referenced_library_files(
    part_names: list[str], library: PartLibrary
) -> dict[str, Path]:
    """Every library file reachable from ``part_names`` (e.g. ``["3001.dat"]``).

    Maps each file's path relative to the library root (e.g. ``parts/3001.dat``,
    ``p/stud.dat``) to its absolute on-disk path -- the exact set to copy when
    bundling a self-sufficient subset of the library. Requires a directory
    library (bundling reads real files). Raises :class:`LDrawFileNotFound` for
    unresolvable references, naming them all.
    """
    if library.is_archive:
        raise ValueError(
            "bundling a subset requires a directory library, not an archive"
        )
    files: dict[str, Path] = {}
    missing: set[str] = set()
    pending = list(part_names)
    seen: set[str] = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        path = library.resolve(name)
        if path is None:
            missing.add(name)
            continue
        assert isinstance(path, Path)  # guaranteed by the directory-library guard
        files[path.relative_to(library.root).as_posix()] = path
        for fields in _references(_parsed_lines(library.lines(name) or [])):
            pending.append(_reference_name(fields))
    if missing:
        _raise_missing(missing, library)
    return files


def render_views(
    ldr_path: str | Path,
    out_path: str | Path,
    *,
    library: str | Path | PartLibrary | None = None,
    size: int = 512,
) -> Path:
    """Render the four canonical views into one contact-sheet PNG at ``out_path``.

    The sheet is a 2x2 grid -- front, side, top, iso -- matching the GPU
    pipeline's multi-view render. Returns the written path.
    """
    triangles = _load(ldr_path, library).combined()
    tiles = [
        _rasterize(triangles, VIEW_DIRECTIONS[name], VIEW_UP_VECTORS[name], size)
        for name in VIEW_ORDER
    ]
    return _write_png(out_path, _flatten_rgba(tile_images(tiles)))


def render_angle(
    ldr_path: str | Path,
    azimuth: float,
    elevation: float,
    out_path: str | Path,
    *,
    library: str | Path | PartLibrary | None = None,
    size: int = 512,
) -> Path:
    """Render one view from a spherical camera angle (degrees) to ``out_path``.

    Angles follow :func:`angle_to_view_dir`: azimuth 0 faces the model's front
    and positive swings the camera to the model's right; elevation 0 is level
    and positive looks down from above. Returns the written path.
    """
    triangles = _load(ldr_path, library).combined()
    tile = _rasterize(
        triangles, angle_to_view_dir(azimuth, elevation), angle_up(elevation), size
    )
    return _write_png(out_path, _flatten_rgba(tile))


def _load(ldr_path: str | Path, library: str | Path | PartLibrary | None) -> Mesh:
    lib = library if isinstance(library, PartLibrary) else PartLibrary.find(library)
    return load_mesh(ldr_path, lib)


# --- Colors ----------------------------------------------------------------


@cache
def _ldraw_colors() -> dict[int, tuple[tuple[float, ...], float]]:
    """LDraw color code -> (rgb floats 0..1, alpha); unknown codes fall back to gray.

    See-through finishes get partial alpha, everything else is opaque.
    """
    from bricklayer import Color
    from bricklayer.colors import Finish, hex2rgb

    finish_alpha = {
        Finish.TRANSPARENT: 0.5,
        Finish.OPALESCENT: 0.7,
        Finish.GLITTER: 0.7,
    }
    return {
        color.ldraw_id: (
            tuple(channel / 255.0 for channel in hex2rgb(color.rgb)),
            finish_alpha.get(color.finish, 1.0),
        )
        for color in Color
    }


# --- LDraw parsing ---------------------------------------------------------


def _parsed_lines(lines: list[str]) -> list[list[str]]:
    return [fields for line in lines if (fields := line.split())]


def _is_reference(fields: list[str]) -> bool:
    """Whether a split line is a type-1 (sub-file reference) line."""
    return fields[0] == "1" and len(fields) >= 15


def _references(parsed: list[list[str]]) -> Iterator[list[str]]:
    return (fields for fields in parsed if _is_reference(fields))


def _split_multipart(text: str) -> dict[str, list[str]]:
    """Split ``0 FILE`` blocks of a multipart document; a flat file becomes a
    single anonymous block. The first block is the main model."""
    documents: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[0] == "0" and fields[1].upper() == "FILE":
            current = " ".join(fields[2:]).lower()
            documents.setdefault(current, [])
            continue
        documents.setdefault(current, []).append(line)
    if len(documents) > 1:
        documents.pop("", None)
    return documents


def _child(
    fields: list[str], matrix: np.ndarray, offset: np.ndarray, color: int
) -> tuple[str, np.ndarray, np.ndarray, int]:
    """A type-1 line's referenced name, with its pose and color resolved against
    the parent's ``matrix``, ``offset``, and ``color``."""
    sub_color = int(fields[1])
    sub_offset = np.array([float(v) for v in fields[2:5]])
    sub_matrix = np.array([float(v) for v in fields[5:14]]).reshape(3, 3)
    return (
        _reference_name(fields),
        matrix @ sub_matrix,
        matrix @ sub_offset + offset,
        color if sub_color == _INHERIT_COLOR else sub_color,
    )


def _reference_name(fields: list[str]) -> str:
    return " ".join(fields[14:])


def _emit_part(
    mesh: Mesh,
    library: PartLibrary,
    name: str,
    matrix: np.ndarray,
    offset: np.ndarray,
    color: int,
) -> None:
    """Tessellate one placed library part into the mesh, inset by the part gap.

    A part whose LDraw file is missing (a few catalog parts are unofficial and
    absent from libraries) is drawn as its catalog bounding box instead, so the
    preview keeps the mass; parts that are unknown entirely land in
    ``mesh.missing``.
    """
    if library.lines(name) is None:
        box = _placeholder_box(name)
        if box is None:
            mesh.missing.add(name)
            return
        rgb, alpha = _ldraw_colors().get(color, _FALLBACK_COLOR)
        vertices = _to_y_up(box @ matrix.T + offset)
        mesh.part_vertices.append(_inset_part(vertices))
        mesh.part_colors.append(np.tile((*rgb, alpha), (len(vertices), 1)))
        mesh.approximated.add(name)
        return

    triangles: list[np.ndarray] = []
    colors: list[tuple[float, ...]] = []
    palette = _ldraw_colors()

    def walk(name: str, matrix: np.ndarray, offset: np.ndarray, color: int, depth: int):
        if depth > _MAX_DEPTH:
            return
        lines = library.lines(name)
        if lines is None:
            mesh.missing.add(name)
            return
        for fields in _parsed_lines(lines):
            kind = fields[0]
            if _is_reference(fields):
                walk(*_child(fields, matrix, offset, color), depth + 1)
            elif kind in ("3", "4") and len(fields) >= 2 + 3 * int(kind):
                face_color = int(fields[1])
                rgb, alpha = palette.get(
                    color if face_color == _INHERIT_COLOR else face_color,
                    _FALLBACK_COLOR,
                )
                corners = np.array(
                    [float(v) for v in fields[2 : 2 + 3 * int(kind)]]
                ).reshape(-1, 3)
                corners = corners @ matrix.T + offset
                for tri in (
                    (corners[:3],) if kind == "3" else (corners[:3], corners[[0, 2, 3]])
                ):
                    triangles.append(tri)
                    colors.append((*rgb, alpha))

    walk(name, matrix, offset, color, 0)
    if not triangles:
        return
    vertices = _to_y_up(np.stack(triangles))
    mesh.part_vertices.append(_inset_part(vertices))
    mesh.part_colors.append(np.array(colors))


def _placeholder_box(name: str) -> np.ndarray | None:
    """Stand-in (12, 3, 3) triangles for a part whose LDraw file is missing:
    its measured bounding box from bricklayer's committed part geometry.
    ``None`` when the part was never measured (an unknown reference).

    ``ldraw_bounds`` shares the part geometry's local frame, which the
    placement transforms expect.
    """
    from bricklayer.ldraw import partdata

    part_id = name.replace("\\", "/").rsplit("/", 1)[-1]
    if not part_id.lower().endswith(".dat"):
        return None
    box = partdata.record(part_id[:-4]).ldraw_bounds
    if box is None:
        return None
    low, high = box
    (x0, y0, z0), (x1, y1, z1) = (low.x, low.y, low.z), (high.x, high.y, high.z)
    corners = np.array(
        [
            [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
            [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
        ]
    )  # fmt: skip
    quads = [
        (0, 1, 2, 3),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (3, 2, 6, 7),
        (1, 2, 6, 5),
        (0, 3, 7, 4),
    ]
    return np.stack(
        [corners[list(q[:3])] for q in quads]
        + [corners[[q[0], q[2], q[3]]] for q in quads]
    )


def _to_y_up(vertices: np.ndarray) -> np.ndarray:
    """LDraw coordinates (y down) to the render frame (y up): negate y and z."""
    return vertices * np.array([1.0, -1.0, -1.0])


def _inset_part(vertices: np.ndarray) -> np.ndarray:
    """Shrink a part's vertices toward its bounding-box center so touching parts
    keep a visible seam. The inset is capped at a tenth of each extent, keeping
    thin parts from collapsing."""
    flat = vertices.reshape(-1, 3)
    low, high = flat.min(axis=0), flat.max(axis=0)
    extent = high - low
    inset = np.minimum(_PART_GAP_LDU, extent / 10.0)
    scale = np.divide(extent - 2.0 * inset, extent, out=np.ones(3), where=extent > 0.0)
    center = (low + high) / 2.0
    return (vertices - center) * scale + center


# --- Rasterization ---------------------------------------------------------


def _rasterize(
    triangles: tuple[np.ndarray, np.ndarray], view_dir: Vec3, up: Vec3, size: int
) -> np.ndarray:
    """Render ``Mesh.combined()`` triangles from a camera direction into an
    (size, size, 4) RGBA array.

    Framing matches pygfx's ``show_object``: the camera sits back from the
    bounding-sphere center by ``diameter * 0.5 / tan(fov/2)`` along the view
    direction. Opaque triangles rasterize front-to-back into a z-buffer; the
    see-through ones then blend back-to-front against it.
    """
    vertices, colors = triangles
    canvas = np.zeros((size, size, 4))
    if not len(vertices):
        return (canvas * 255).astype(np.uint8)

    forward = np.array(view_dir, dtype=float)
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, np.array(up, dtype=float))
    right /= np.linalg.norm(right)
    true_up = np.cross(right, forward)

    flat = vertices.reshape(-1, 3)
    center = (flat.min(axis=0) + flat.max(axis=0)) / 2.0
    radius = float(np.linalg.norm(flat - center, axis=1).max()) or 1.0
    half = math.tan(math.radians(_FOV_DEGREES) / 2.0)
    eye = center - forward * (radius / half)

    # Camera space: x right, y up, z depth along the view direction.
    relative = vertices - eye
    cam = np.stack([relative @ right, relative @ true_up, relative @ forward], axis=-1)

    # Perspective projection to pixel coordinates (y down).
    depth = cam[..., 2]
    px = (cam[..., 0] / (depth * half) + 1.0) * (size / 2.0)
    py = (1.0 - cam[..., 1] / (depth * half)) * (size / 2.0)
    screen = np.stack([px, py], axis=-1)
    inv_depth = 1.0 / depth

    # Flat headlight shading: normals in camera space, lit along the view axis.
    edge1 = cam[:, 1] - cam[:, 0]
    edge2 = cam[:, 2] - cam[:, 0]
    normals = np.cross(edge1, edge2)
    lengths = np.linalg.norm(normals, axis=1)
    lit = np.abs(normals[:, 2]) / np.where(lengths > 0.0, lengths, 1.0)
    shade = np.clip(_AMBIENT + _DIFFUSE * lit, 0.0, 1.0)
    shaded = np.concatenate([colors[:, :3] * shade[:, None], colors[:, 3:]], axis=1)

    z_buffer = np.full((size, size), np.inf)
    opaque = colors[:, 3] >= 1.0
    mean_depth = depth.mean(axis=1)
    # Opaque near-to-far so the z-buffer fills early and occluded geometry is
    # rejected cheaply, then see-through triangles far-to-near so nearer glass
    # layers over farther.
    front_to_back = np.flatnonzero(opaque)[np.argsort(mean_depth[opaque])]
    back_to_front = np.flatnonzero(~opaque)[np.argsort(-mean_depth[~opaque])]

    # Per-triangle setup, vectorized over all triangles at once.
    lo = np.maximum(np.floor(screen.min(axis=1)).astype(int), 0)
    hi = np.minimum(np.ceil(screen.max(axis=1)).astype(int) + 1, size)
    ax, ay = screen[:, 0, 0], screen[:, 0, 1]
    bx, by = screen[:, 1, 0], screen[:, 1, 1]
    cx, cy = screen[:, 2, 0], screen[:, 2, 1]
    area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    nearest = 1.0 / inv_depth.max(axis=1)
    drawable = (hi > lo).all(axis=1) & (area != 0.0)

    for index in front_to_back.tolist() + back_to_front.tolist():
        if not drawable[index]:
            continue
        _draw_triangle(
            canvas,
            z_buffer,
            screen[index],
            inv_depth[index],
            shaded[index],
            lo[index],
            hi[index],
            float(area[index]),
            float(nearest[index]),
            write_depth=bool(opaque[index]),
        )
    return (np.clip(canvas, 0.0, 1.0) * 255).astype(np.uint8)


def _draw_triangle(
    canvas: np.ndarray,
    z_buffer: np.ndarray,
    corners: np.ndarray,
    inv_depth: np.ndarray,
    rgba: np.ndarray,
    lo: np.ndarray,
    hi: np.ndarray,
    area: float,
    nearest: float,
    *,
    write_depth: bool,
) -> None:
    """Rasterize one screen-space triangle with a z-test into the canvas.

    ``lo``/``hi`` bound the triangle's pixel window, ``area`` is its signed screen
    area and ``nearest`` its closest depth; :func:`_rasterize` computes all four
    across every triangle at once.
    """
    window = z_buffer[lo[1] : hi[1], lo[0] : hi[0]]
    if nearest >= window.max():  # everything in the window is already nearer
        return

    (ax, ay), (bx, by), (cx, cy) = corners
    xs = np.arange(lo[0], hi[0]) + 0.5
    ys = (np.arange(lo[1], hi[1]) + 0.5)[:, None]
    w0 = ((cx - bx) * (ys - by) - (cy - by) * (xs - bx)) / area
    w1 = ((ax - cx) * (ys - cy) - (ay - cy) * (xs - cx)) / area
    w2 = 1.0 - w0 - w1
    covered = (w0 >= 0.0) & (w1 >= 0.0) & (w2 >= 0.0)
    if not covered.any():
        return

    # 1/z interpolates linearly in screen space, so the z-test stays correct
    # under perspective. Only covered pixels need it.
    depth = 1.0 / (
        w0[covered] * inv_depth[0]
        + w1[covered] * inv_depth[1]
        + w2[covered] * inv_depth[2]
    )
    nearer = depth < window[covered]
    if not nearer.any():
        return
    visible = np.zeros_like(covered)
    visible[covered] = nearer
    if write_depth:
        window[visible] = depth[nearer]

    target = canvas[lo[1] : hi[1], lo[0] : hi[0]]
    alpha = rgba[3]
    target[visible, :3] = alpha * rgba[:3] + (1.0 - alpha) * target[visible, :3]
    target[visible, 3] = alpha + (1.0 - alpha) * target[visible, 3]


def tile_images(
    images: list[np.ndarray], *, columns: int = 2, pad: int = 8
) -> np.ndarray:
    """Combine the images into a single image, in a ``columns``-wide grid on a white background.

    All tiles are assumed to share the first tile's height and width.
    """
    h, w = images[0].shape[:2]
    rows = (len(images) + columns - 1) // columns

    grid = np.full(
        (rows * h + pad * (rows + 1), columns * w + pad * (columns + 1), 4),
        255,
        dtype=np.uint8,
    )
    for i, tile in enumerate(images):
        r, c = divmod(i, columns)
        y = pad + r * (h + pad)
        x = pad + c * (w + pad)
        grid[y : y + h, x : x + w] = tile

    return grid


# --- PNG output ------------------------------------------------------------


def _flatten_rgba(image: np.ndarray) -> np.ndarray:
    """Drop the alpha channel; drawing already blended onto the black canvas, so
    this matches the GPU pipeline's RGBA -> RGB conversion (black background)."""
    return np.ascontiguousarray(image[..., :3])


def _write_png(path: str | Path, image: np.ndarray) -> Path:
    """Write an (h, w, 3) uint8 array as a PNG using only the stdlib."""
    height, width = image.shape[:2]
    raw = b"".join(b"\x00" + row.tobytes() for row in image)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload))
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return out
