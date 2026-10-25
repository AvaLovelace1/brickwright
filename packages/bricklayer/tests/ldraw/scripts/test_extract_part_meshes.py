"""Tests for the BrickNet collision mesh extraction script."""

import struct

import pytest

from bricklayer.ldraw.meshes import MeshStore
from bricklayer.ldraw.scripts.extract_part_meshes import (
    _read_meshes,
    categorize,
    ldraw_category,
    main,
    read_ply,
)
from bricklayer.ldraw.scripts.fallbacks import PartFallbacks, PartSource
from bricklayer.ldraw.scripts.library import Library


def _ply(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    *,
    vertex_type: str = "double",
) -> bytes:
    """A binary-little-endian PLY, in BrickNet's shape."""
    fmt = {"double": "<3d", "float": "<3f"}[vertex_type]
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {len(vertices)}\n"
        f"property {vertex_type} x\n"
        f"property {vertex_type} y\n"
        f"property {vertex_type} z\n"
        f"element face {len(faces)}\n"
        "property list uchar int vertex_indices\n"
        "end_header\n"
    ).encode()
    body = b"".join(struct.pack(fmt, *v) for v in vertices)
    body += b"".join(struct.pack("<B3i", 3, *f) for f in faces)
    return header + body


TRIANGLE = ([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)], [(0, 1, 2)])


@pytest.fixture
def library(tmp_path, ldraw_root):
    """A mesh directory and an LDraw library holding one brick and one sticker."""
    descriptions = {
        "3001": "Brick  2 x  4",
        "9999": "Sticker Shortcut  1 x  1",
    }
    root = ldraw_root(
        {
            f"parts/{part_id}.dat": f"0 {text}\n0 !CATEGORY {text.split('  ')[0]}\n"
            for part_id, text in descriptions.items()
        }
    )
    meshes = tmp_path / "inset"
    meshes.mkdir()
    for part_id in descriptions:
        (meshes / f"{part_id}.ply").write_bytes(_ply(*TRIANGLE))
    return meshes, root


class TestMain:
    def test_explicit_mesh_directory_is_used_for_selection_and_extraction(
        self, library, bricknet_data, tmp_path, monkeypatch
    ):
        meshes, ldraw = library
        monkeypatch.setenv("BRICKNET_DATA", str(bricknet_data))
        monkeypatch.setenv("BRICKNET_MESHES", str(tmp_path / "wrong-directory"))
        output = tmp_path / "store"
        assert (
            main(
                [
                    "--meshes",
                    str(meshes),
                    "--ldraw",
                    str(ldraw),
                    "--output",
                    str(output),
                ]
            )
            == 0
        )
        assert set(MeshStore(output).part_ids()) == {"3001", "9999"}


class TestCheck:
    """``--check`` is the CI gate: it must fail when the committed store drifts."""

    @staticmethod
    def _run(meshes, ldraw, output, *extra):
        return main(
            [
                "--meshes",
                str(meshes),
                "--ldraw",
                str(ldraw),
                "--output",
                str(output),
                "--all",
                *extra,
            ]
        )

    def test_fails_when_a_part_is_not_yet_committed(self, library, tmp_path):
        meshes, ldraw = library
        assert self._run(meshes, ldraw, tmp_path / "store", "--check") == 1

    def test_passes_when_the_committed_store_matches(self, library, tmp_path):
        meshes, ldraw = library
        store = tmp_path / "store"
        assert self._run(meshes, ldraw, store) == 0  # write it
        assert self._run(meshes, ldraw, store, "--check") == 0

    def test_fails_when_a_committed_part_is_no_longer_extracted(
        self, library, tmp_path
    ):
        meshes, ldraw = library
        store = tmp_path / "store"
        assert self._run(meshes, ldraw, store) == 0
        (meshes / "3001.ply").unlink()
        assert self._run(meshes, ldraw, store, "--check") == 1


class TestCategorize:
    """``main`` decides what ships from ``categorize`` alone, before decoding
    any geometry, so ``--check`` never pays to read a PLY."""

    @pytest.fixture
    def sources(self):
        return {p: PartSource(p) for p in ["3001", "9999"]}

    def test_keeps_every_part_when_nothing_is_excluded(self, library, sources):
        _, ldraw = library
        categories, _, _ = categorize(Library(ldraw), ["3001", "9999"], sources)
        assert set(categories) == {"3001", "9999"}

    def test_drops_excluded_categories(self, library, sources):
        _, ldraw = library
        categories, _, _ = categorize(
            Library(ldraw), ["3001", "9999"], sources, exclude={"Sticker Shortcut"}
        )
        assert set(categories) == {"3001"}

    def test_reports_parts_with_no_mesh(self, library, sources):
        _, ldraw = library
        _, missing, _ = categorize(Library(ldraw), ["3001", "absent"], sources)
        assert missing == ["absent"]

    def test_reports_parts_absent_from_the_ldraw_library(self, library):
        _, ldraw = library
        _, _, uncategorized = categorize(
            Library(ldraw), ["stray"], {"stray": PartSource("stray")}
        )
        assert uncategorized == ["stray"]

    def test_files_each_part_under_its_category(self, library, sources):
        _, ldraw = library
        categories, _, _ = categorize(Library(ldraw), ["3001"], sources)
        assert categories["3001"] == "Brick"


class TestReadMeshes:
    def test_reads_the_donor_mesh_under_its_assigned_category(self, library):
        meshes, _ = library
        category, mesh = _read_meshes(
            meshes, {"3001": "Brick"}, {"3001": PartSource("3001")}
        )["3001"]
        assert category == "Brick"
        assert len(mesh.faces) == 1

    def test_resolves_and_transforms_a_missing_mesh_from_a_redirect(
        self, tmp_path, ldraw_root
    ):
        root = ldraw_root(
            {
                "parts/old.dat": "0 ~Moved to new\n1 16 20 0 0 0 -1 0 1 0 0 0 0 1 new.dat\n",
                "parts/new.dat": "0 Brick 1 x 1\n",
            }
        )
        mesh_dir = tmp_path / "inset"
        mesh_dir.mkdir()
        (mesh_dir / "old.ply").write_bytes(_ply([(20, 1, 0)], []))
        lib = Library(root)
        sources = PartFallbacks(lib).sources(["new"], ["old"])
        categories, missing, uncategorized = categorize(lib, ["new"], sources)
        assert categories == {"new": "Brick"}
        assert missing == uncategorized == []
        category, mesh = _read_meshes(mesh_dir, categories, sources)["new"]
        assert category == "Brick"
        assert mesh.vertices[0] == pytest.approx([1, 0, 0])


class TestReadPly:
    def test_reads_vertices_and_faces(self, tmp_path):
        path = tmp_path / "3001.ply"
        path.write_bytes(_ply(*TRIANGLE))

        mesh = read_ply(path)

        assert mesh.faces.tolist() == [[0, 1, 2]]
        assert mesh.vertices.shape == (3, 3)

    def test_negates_z_into_the_ldraw_frame(self, tmp_path):
        """BrickNet's PLYs store Z negated relative to LDraw."""
        path = tmp_path / "3001.ply"
        path.write_bytes(_ply([(1.0, 2.0, 3.0)], []))

        mesh = read_ply(path)

        assert mesh.vertices[0].tolist() == [1.0, 2.0, -3.0]

    def test_reads_float32_vertices(self, tmp_path):
        path = tmp_path / "3001.ply"
        path.write_bytes(_ply(*TRIANGLE, vertex_type="float"))

        assert read_ply(path).vertices.shape == (3, 3)

    def test_rejects_ascii_ply(self, tmp_path):
        path = tmp_path / "3001.ply"
        path.write_bytes(b"ply\nformat ascii 1.0\nend_header\n")

        with pytest.raises(ValueError, match="ascii"):
            read_ply(path)

    def test_rejects_non_triangular_faces(self, tmp_path):
        path = tmp_path / "3001.ply"
        header = (
            b"ply\nformat binary_little_endian 1.0\n"
            b"element vertex 4\nproperty double x\nproperty double y\n"
            b"property double z\nelement face 1\n"
            b"property list uchar int vertex_indices\nend_header\n"
        )
        body = b"".join(struct.pack("<3d", i, 0, 0) for i in range(4))
        body += struct.pack("<B4i", 4, 0, 1, 2, 3)
        path.write_bytes(header + body)

        with pytest.raises(ValueError, match="triangular"):
            read_ply(path)


class TestLDrawCategory:
    def test_prefers_an_explicit_category_meta(self, ldraw_root):
        root = ldraw_root(
            {
                "parts/3001.dat": (
                    "0 Brick  2 x  4\n0 !CATEGORY Duplo Brick\n"
                    "1 16 0 0 0 1 0 0 0 1 0 0 0 1 x.dat\n"
                )
            }
        )
        assert ldraw_category(Library(root), "3001") == "Duplo Brick"

    def test_falls_back_to_the_first_word_of_the_description(self, ldraw_root):
        root = ldraw_root({"parts/3001.dat": "0 Brick  2 x  4\n0 Name: 3001.dat\n"})
        assert ldraw_category(Library(root), "3001") == "Brick"

    def test_follows_a_moved_redirect_to_the_real_part(self, ldraw_root):
        """LDraw keeps retired ids as ``~Moved to`` stubs. The catalog still uses
        some of them, and they should file under the target's category, not
        under "Moved"."""
        root = ldraw_root(
            {
                "parts/3665a.dat": "0 Slope Brick 45 2 x 1 Inverted\n",
                "parts/3665.dat": "0 ~Moved to 3665a\n",
            }
        )
        assert ldraw_category(Library(root), "3665") == "Slope"

    def test_unresolvable_redirect_falls_back_to_moved(self, ldraw_root):
        root = ldraw_root({"parts/x.dat": "0 ~Moved to nowhere\n"})
        assert ldraw_category(Library(root), "x") == "Moved"

    def test_redirect_cycle_does_not_hang(self, ldraw_root):
        root = ldraw_root(
            {"parts/a.dat": "0 ~Moved to b\n", "parts/b.dat": "0 ~Moved to a\n"}
        )
        assert ldraw_category(Library(root), "a") == "Moved"

    def test_strips_leading_description_markers(self, ldraw_root):
        root = ldraw_root({"parts/x.dat": "0 =Brick  1 x  1 Alias\n"})
        assert ldraw_category(Library(root), "x") == "Brick"

    def test_reports_parts_absent_from_the_library(self, ldraw_root):
        assert ldraw_category(Library(ldraw_root({})), "nope") is None

    def test_finds_parts_in_the_subparts_directory(self, ldraw_root):
        root = ldraw_root({"parts/s/3001s01.dat": "0 Brick  2 x  4 Subpart\n"})
        assert ldraw_category(Library(root), "3001s01") == "Brick"
