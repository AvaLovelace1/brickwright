"""Tests for the CPU-only LDraw renderer, against a tiny fake parts library."""

import math
import tarfile
import zipfile
import zlib

import numpy as np
import pytest
from bricklayer import Color
from bricklayer.colors import hex2rgb
from bricklayer.parts.catalog import all_parts
from PIL import Image

from brickwright.tools import rendering, software_rendering
from brickwright.tools.software_rendering import (
    VIEW_DIRECTIONS,
    VIEW_ORDER,
    VIEW_UP_VECTORS,
    LDrawFileNotFound,
    PartLibrary,
    angle_to_view_dir,
    load_mesh,
    referenced_library_files,
    render_angle,
    render_views,
    tile_images,
)

RED = Color.RED.ldraw_id
BLUE = Color.BLUE.ldraw_id
YELLOW = Color.YELLOW.ldraw_id

_IDENTITY = "1 0 0 0 1 0 0 0 1"

# A unit cube [0,1]^3: five faces as quads, the y=0 face via a p/ primitive.
# The s\\ reference is upper-cased with a backslash to exercise normalization.
_CUBE_SUBPART = """\
1 16 0 0 0 1 0 0 0 1 0 0 0 1 topface.dat
4 16 0 1 0 1 1 0 1 1 1 0 1 1
4 16 0 0 0 0 0 1 0 1 1 0 1 0
4 16 1 0 0 1 0 1 1 1 1 1 1 0
4 16 0 0 0 1 0 0 1 1 0 0 1 0
4 16 0 0 1 1 0 1 1 1 1 0 1 1
"""

# LDraw y points down, so the y=0 face is the cube's top. It is always yellow
# (not color 16), giving views from above a distinct color to assert on.
_TOPFACE_PRIMITIVE = f"4 {YELLOW} 0 0 0 1 0 0 1 0 1 0 0 1\n"

# 20x24x20 LDU (one brick): the unit cube scaled, spanning y in [-24, 0].
_PART = "1 16 0 -24 0 20 0 0 0 24 0 0 0 20 S\\CUBE.DAT\n"


@pytest.fixture
def library_root(tmp_path):
    root = tmp_path / "lib"
    (root / "parts" / "s").mkdir(parents=True)
    (root / "p").mkdir()
    (root / "parts" / "9001.dat").write_text(_PART)
    (root / "parts" / "s" / "cube.dat").write_text(_CUBE_SUBPART)
    (root / "p" / "topface.dat").write_text(_TOPFACE_PRIMITIVE)
    return root


@pytest.fixture(params=["directory", "tar", "zip"])
def library(request, library_root, tmp_path):
    """The fake library in every supported form: a directory, and a tar or zip of
    one."""
    if request.param == "directory":
        return PartLibrary(library_root)
    entries = [p for p in sorted(library_root.rglob("*")) if p.is_file()]
    if request.param == "tar":
        bundle = tmp_path / "ldraw.tar"
        with tarfile.open(bundle, "w") as tf:
            for path in entries:
                tf.add(path, arcname=path.relative_to(library_root).as_posix())
    else:
        bundle = tmp_path / "ldraw.zip"
        with zipfile.ZipFile(bundle, "w") as zf:
            for path in entries:
                zf.write(path, path.relative_to(library_root).as_posix())
    return PartLibrary(bundle)


def write_ldr(tmp_path, lines):
    path = tmp_path / "build.ldr"
    path.write_text("".join(line + "\n" for line in lines))
    return path


def brick_line(color, x=0, y=0, z=0):
    return f"1 {color} {x} {y} {z} {_IDENTITY} 9001.dat"


def read_png(path):
    """Decode the renderer's PNG (8-bit RGB, no interlacing) with the stdlib."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width = int.from_bytes(data[16:20])
    height = int.from_bytes(data[20:24])
    start = data.index(b"IDAT") + 4
    length = int.from_bytes(data[start - 8 : start - 4])
    raw = zlib.decompress(data[start : start + length])
    rows = np.frombuffer(raw, dtype=np.uint8).reshape(height, 3 * width + 1)
    assert (rows[:, 0] == 0).all()  # filter type "none" on every row
    return rows[:, 1:].reshape(height, width, 3)


def color_mask(image, color):
    """Pixels whose hue matches ``color`` (ignoring the shading brightness)."""
    rgb = np.array(hex2rgb(color.rgb), dtype=float)
    brightness = image.sum(axis=-1, keepdims=True).clip(min=1)
    target = rgb / rgb.sum()
    return (np.abs(image / brightness - target).sum(axis=-1) < 0.2) & (
        image.sum(axis=-1) > 30
    )


class TestViews:
    def test_constants_cover_exactly_view_order(self):
        assert set(VIEW_DIRECTIONS) == set(VIEW_ORDER)
        assert set(VIEW_UP_VECTORS) == set(VIEW_ORDER)

    def test_direction_vectors_are_distinct(self):
        vecs = list(VIEW_DIRECTIONS.values())
        assert len({v for v in vecs}) == len(vecs)

    def test_principal_views_are_axis_aligned(self):
        # front and side must be horizontal (y == 0); top must be vertical (x == z == 0)
        _fx, fy, _fz = VIEW_DIRECTIONS["front"]
        assert math.isclose(fy, 0.0), "front should be horizontal"

        _sx, sy, _sz = VIEW_DIRECTIONS["side"]
        assert math.isclose(sy, 0.0), "side should be horizontal"

        tx, ty, tz = VIEW_DIRECTIONS["top"]
        assert math.isclose(tx, 0.0) and math.isclose(tz, 0.0), (
            "top should be on vertical axis"
        )
        assert ty < 0.0, "top should look downward (negative y)"

    def test_iso_is_off_every_axis(self):
        ix, iy, iz = VIEW_DIRECTIONS["iso"]
        assert not math.isclose(ix, 0.0), "iso x should be non-zero"
        assert not math.isclose(iy, 0.0), "iso y should be non-zero"
        assert not math.isclose(iz, 0.0), "iso z should be non-zero"

    def test_up_vectors_not_parallel_to_direction(self):
        """For each view, up and direction must not be collinear (cross product non-zero)."""
        for name in VIEW_ORDER:
            dx, dy, dz = VIEW_DIRECTIONS[name]
            ux, uy, uz = VIEW_UP_VECTORS[name]
            # cross product magnitude squared
            cx = dy * uz - dz * uy
            cy = dz * ux - dx * uz
            cz = dx * uy - dy * ux
            cross_sq = cx * cx + cy * cy + cz * cz
            assert cross_sq > 0.0, f"{name}: up vector is parallel to view direction"


class TestCameraContract:
    """The GPU pipeline and this renderer must agree on camera semantics."""

    def test_views_match_the_gpu_pipeline(self):
        assert rendering.VIEW_ORDER is VIEW_ORDER
        assert rendering.VIEW_DIRECTIONS is VIEW_DIRECTIONS
        assert rendering.VIEW_UP_VECTORS is VIEW_UP_VECTORS
        assert rendering.angle_to_view_dir is software_rendering.angle_to_view_dir


class TestAngleToViewDir:
    @pytest.mark.parametrize(
        "azimuth, elevation, expected",
        [
            (0.0, 0.0, VIEW_DIRECTIONS["front"]),
            (90.0, 0.0, VIEW_DIRECTIONS["side"]),
            (0.0, 90.0, VIEW_DIRECTIONS["top"]),
        ],
    )
    def test_matches_the_canonical_views(self, azimuth, elevation, expected):
        got = angle_to_view_dir(azimuth, elevation)
        assert all(math.isclose(g, e, abs_tol=1e-9) for g, e in zip(got, expected))

    def test_returns_a_unit_vector(self):
        x, y, z = angle_to_view_dir(37.0, -22.0)
        assert math.isclose(math.sqrt(x * x + y * y + z * z), 1.0, abs_tol=1e-9)


class TestPartLibrary:
    def test_resolves_across_trees_with_normalization(self, library):
        # resolve() returns a Path (directory library) or member name (zip);
        # both end with the library-relative location.
        def located_at(name):
            return str(library.resolve(name)).replace("\\", "/")

        assert located_at("9001.dat").lower().endswith("parts/9001.dat")
        assert located_at("S\\CUBE.DAT").lower().endswith("parts/s/cube.dat")
        assert located_at("topface.dat").lower().endswith("p/topface.dat")
        assert library.resolve("nope.dat") is None

    def test_find_prefers_explicit_root(self, library, monkeypatch):
        monkeypatch.setenv("LDRAW_LIBRARY_PATH", "/nonexistent")
        assert PartLibrary.find(library.root).root == library.root

    def test_find_uses_environment_variable(self, library, monkeypatch):
        monkeypatch.setenv("LDRAW_LIBRARY_PATH", str(library.root))
        assert PartLibrary.find().root == library.root

    def test_find_reports_tried_locations(self, monkeypatch):
        monkeypatch.delenv("LDRAW_LIBRARY_PATH", raising=False)
        monkeypatch.setattr(software_rendering, "_DEFAULT_LIBRARY_ROOTS", ())
        with pytest.raises(LDrawFileNotFound, match="LDRAW_LIBRARY_PATH"):
            PartLibrary.find()


class TestLoadMesh:
    @pytest.mark.parametrize("preamble", ["", "0 Generated model", "0 Author: Builder"])
    def test_multipart_preamble_does_not_hide_the_model(
        self, library, tmp_path, preamble
    ):
        ldr = write_ldr(tmp_path, [preamble, "0 FILE main.ldr", brick_line(RED)])
        mesh = load_mesh(ldr, library)
        assert len(mesh.part_vertices) == 1
        assert len(mesh.combined()[0]) == 12

    def test_tessellates_one_part(self, library, tmp_path):
        ldr = write_ldr(tmp_path, [brick_line(RED)])
        mesh = load_mesh(ldr, library)
        assert len(mesh.part_vertices) == 1
        vertices, colors = mesh.combined()
        assert len(vertices) == 12  # 6 quads -> 2 triangles each
        assert vertices.shape == (12, 3, 3)
        assert colors.shape == (12, 4)

    def test_inherited_and_direct_colors(self, library, tmp_path):
        ldr = write_ldr(tmp_path, [brick_line(RED)])
        _, colors = load_mesh(ldr, library).combined()
        red = np.array(hex2rgb(Color.RED.rgb)) / 255.0
        yellow = np.array(hex2rgb(Color.YELLOW.rgb)) / 255.0
        by_color = {tuple(np.round(rgb, 3)) for rgb in colors[:, :3]}
        assert tuple(np.round(red, 3)) in by_color  # color 16 faces inherit
        assert tuple(np.round(yellow, 3)) in by_color  # top face keeps its own

    def test_parts_are_inset_for_seams(self, library, tmp_path):
        ldr = write_ldr(tmp_path, [brick_line(RED)])
        vertices, _ = load_mesh(ldr, library).combined()
        flat = vertices.reshape(-1, 3)
        extent = flat.max(axis=0) - flat.min(axis=0)
        # 20x24x20 LDU shrunk by the 0.5 LDU gap on every side (y is negated).
        assert np.allclose(extent, [19.0, 23.0, 19.0])

    def test_multipart_documents_group_but_do_not_merge_parts(self, library, tmp_path):
        ldr = write_ldr(
            tmp_path,
            [
                "0 FILE main.ldr",
                f"1 {RED} 0 0 0 {_IDENTITY} tower.ldr",
                brick_line(BLUE, x=100),
                "0 FILE tower.ldr",
                f"1 16 0 0 0 {_IDENTITY} 9001.dat",
                f"1 16 0 -24 0 {_IDENTITY} 9001.dat",
            ],
        )
        mesh = load_mesh(ldr, library)
        assert len(mesh.part_vertices) == 3  # two in the submodel, one direct
        _, colors = mesh.combined()
        red = np.array(hex2rgb(Color.RED.rgb)) / 255.0
        # The submodel is placed in red; its color-16 parts inherit through it.
        assert (np.abs(colors[:, :3] - red).sum(axis=1) < 0.01).sum() >= 10

    def test_missing_parts_are_reported(self, library, tmp_path):
        ldr = write_ldr(tmp_path, [f"1 {RED} 0 0 0 {_IDENTITY} nope.dat"])
        with pytest.raises(LDrawFileNotFound, match="nope.dat"):
            load_mesh(ldr, library)

    def test_measured_part_missing_from_library_becomes_its_bounding_box(
        self, library, tmp_path
    ):
        # A real catalogued part is absent from the fake library, but has
        # measured geometry -- it renders as a placeholder box, not an error.
        part_id = all_parts()[0].ldraw_id
        ldr = write_ldr(tmp_path, [f"1 {RED} 0 0 0 {_IDENTITY} {part_id}.dat"])
        mesh = load_mesh(ldr, library)
        assert mesh.approximated == {f"{part_id}.dat"}
        assert len(mesh.part_vertices) == 1
        assert len(mesh.part_vertices[0]) == 12  # a box: 6 quads, 12 triangles


class TestReferencedLibraryFiles:
    def test_walks_the_reference_closure(self, library_root):
        files = referenced_library_files(["9001.dat"], PartLibrary(library_root))
        assert {s.lower() for s in files} == {
            "parts/9001.dat",
            "parts/s/cube.dat",
            "p/topface.dat",
        }
        assert all(path.is_file() for path in files.values())

    def test_missing_references_are_reported(self, library_root):
        with pytest.raises(LDrawFileNotFound, match="ghost.dat"):
            referenced_library_files(
                ["9001.dat", "ghost.dat"], PartLibrary(library_root)
            )

    def test_archive_libraries_are_rejected(self, tmp_path):
        bundle = tmp_path / "lib.zip"
        with zipfile.ZipFile(bundle, "w") as zf:
            zf.writestr("parts/9001.dat", _PART)
        with pytest.raises(ValueError, match="directory library"):
            referenced_library_files(["9001.dat"], PartLibrary(bundle))


class TestRenderViews:
    def test_contact_sheet_layout_and_content(self, library, tmp_path):
        ldr = write_ldr(tmp_path, [brick_line(RED)])
        out = render_views(ldr, tmp_path / "views.png", library=library, size=128)
        image = read_png(out)
        pad = 8
        assert image.shape == (2 * 128 + 3 * pad, 2 * 128 + 3 * pad, 3)
        assert (image[0, 0] == 255).all()  # white padding
        tiles = {
            name: image[
                pad + row * (128 + pad) : pad + row * (128 + pad) + 128,
                pad + column * (128 + pad) : pad + column * (128 + pad) + 128,
            ]
            for name, (row, column) in zip(VIEW_ORDER, [(0, 0), (0, 1), (1, 0), (1, 1)])
        }
        for name in ("front", "side", "iso"):
            assert color_mask(tiles[name], Color.RED).any(), name
        # Straight down, only the always-yellow top face is visible.
        assert color_mask(tiles["top"], Color.YELLOW).any()
        assert not color_mask(tiles["top"], Color.RED).any()

    def test_library_is_discovered_from_the_environment(
        self, library, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("LDRAW_LIBRARY_PATH", str(library.root))
        ldr = write_ldr(tmp_path, [brick_line(RED)])
        out = render_views(ldr, tmp_path / "views.png", size=64)
        assert out.is_file()


class TestRenderAngle:
    def test_writes_a_readable_png(self, library, tmp_path):
        ldr = write_ldr(tmp_path, [brick_line(RED)])
        out = render_angle(ldr, 0, 0, tmp_path / "view.png", library=library)
        image = read_png(out)
        assert image.shape == (512, 512, 3)
        assert color_mask(image, Color.RED).any()

    def test_front_view_orientation(self, library, tmp_path):
        # The camera at azimuth 0 sits on the model's front; +x runs screen-left.
        ldr = write_ldr(tmp_path, [brick_line(RED), brick_line(BLUE, x=100)])
        image = read_png(render_angle(ldr, 0, 0, tmp_path / "v.png", library=library))
        red_columns = np.nonzero(color_mask(image, Color.RED).any(axis=0))[0]
        blue_columns = np.nonzero(color_mask(image, Color.BLUE).any(axis=0))[0]
        assert red_columns.mean() > blue_columns.mean()

    def test_azimuth_swings_around_the_model(self, library, tmp_path):
        # Two bricks along x: each side view shows only the nearer one.
        ldr = write_ldr(tmp_path, [brick_line(RED), brick_line(BLUE, x=100)])
        left = read_png(render_angle(ldr, 90, 0, tmp_path / "l.png", library=library))
        right = read_png(render_angle(ldr, -90, 0, tmp_path / "r.png", library=library))
        assert color_mask(left, Color.RED).any()
        assert not color_mask(left, Color.BLUE).any()
        assert color_mask(right, Color.BLUE).any()
        assert not color_mask(right, Color.RED).any()

    def test_elevation_looks_down_on_the_top_face(self, library, tmp_path):
        ldr = write_ldr(tmp_path, [brick_line(RED)])
        image = read_png(
            render_angle(ldr, 0, 90, tmp_path / "top.png", library=library)
        )
        yellow = color_mask(image, Color.YELLOW)
        assert yellow.sum() > 100  # the always-yellow top face dominates
        assert not color_mask(image, Color.RED).any()

    def test_image_does_not_flip_as_the_camera_nears_the_pole(self, library, tmp_path):
        # Bricks along x read red-right-of-blue from the front; that must hold
        # at every elevation short of straight down.
        ldr = write_ldr(tmp_path, [brick_line(RED), brick_line(BLUE, x=100)])
        for elevation in (45, 88.9, 89.5):
            out = tmp_path / f"el{elevation}.png"
            image = read_png(render_angle(ldr, 0, elevation, out, library=library))
            red = np.nonzero(color_mask(image, Color.RED).any(axis=0))[0]
            blue = np.nonzero(color_mask(image, Color.BLUE).any(axis=0))[0]
            assert red.mean() > blue.mean(), elevation

    @pytest.mark.parametrize("elevation", [-90.5, 180])
    def test_rejects_an_elevation_past_the_pole(self, library, tmp_path, elevation):
        ldr = write_ldr(tmp_path, [brick_line(RED)])
        with pytest.raises(ValueError, match="elevation"):
            render_angle(ldr, 0, elevation, tmp_path / "v.png", library=library)

    def test_translucent_parts_blend_instead_of_covering(self, library, tmp_path):
        # Clear glass directly in front of a red brick: were it treated as
        # opaque the pixels would be near-white, so require a red tint.
        glass = Color.TRANS_CLEAR.ldraw_id
        ldr = write_ldr(
            tmp_path, [brick_line(RED), f"1 {glass} 0 0 -100 {_IDENTITY} 9001.dat"]
        )
        image = read_png(render_angle(ldr, 0, 0, tmp_path / "v.png", library=library))
        channels = image.astype(int)
        reddish = (channels[..., 0] > channels[..., 1] + 40) & (
            channels[..., 0] > channels[..., 2] + 40
        )
        assert reddish.any()


class TestTileImages:
    def test_creates_an_image_with_the_expected_grid_size(self, tmp_path):
        n_tiles = 6
        tile_size = 8
        columns = 2
        rows = (n_tiles + columns - 1) // columns
        pad = 4

        tile = np.zeros((tile_size, tile_size, 4), dtype=np.uint8)
        tiles = [tile] * n_tiles
        grid = tile_images(tiles, columns=columns, pad=pad)
        img = Image.fromarray(grid, "RGBA").convert("RGB")
        assert img.width == columns * tile_size + pad * (columns + 1)
        assert img.height == rows * tile_size + pad * (rows + 1)
