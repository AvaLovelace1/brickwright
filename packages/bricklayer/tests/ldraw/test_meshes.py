"""Tests for the Draco-compressed collision mesh store."""

import json
from importlib import resources

import numpy as np
import pytest

from bricklayer.geometry.collision import MATING_CLEARANCE_LDU
from bricklayer.ldraw.meshes import (
    Mesh,
    MeshStore,
    MeshUnavailable,
    decode_mesh,
    default_store,
    encode_mesh,
    quantization_bound,
    write_store,
)
from bricklayer.ldraw.partdata import part_ids


@pytest.fixture
def store(tmp_path, cube_mesh):
    """A store written by :func:`write_store`, so reads exercise the real writer.

    Defaults to two categories: ``Brick`` holds 3001, ``Plate`` holds 3020.
    """

    def _fn(parts: dict[str, tuple[str, Mesh]] | None = None) -> MeshStore:
        write_store(
            tmp_path,
            parts
            or {
                "3001": ("Brick", cube_mesh(40)),
                "3020": ("Plate", cube_mesh(8)),
            },
        )
        return MeshStore(tmp_path)

    return _fn


class TestCodec:
    def test_round_trip_preserves_geometry(self, cube_mesh):
        original = cube_mesh(40)
        restored = decode_mesh(encode_mesh(original))

        bound = quantization_bound(original)
        assert len(restored.faces) == len(original.faces)
        # Draco does not preserve vertex order, so compare the point sets.
        for vertex in original.vertices:
            nearest = np.abs(restored.vertices - vertex).max(axis=1).min()
            assert nearest <= bound

    def test_round_trip_preserves_extent(self, cube_mesh):
        original = cube_mesh(40, at=(100, -60, 12))
        restored = decode_mesh(encode_mesh(original))

        bound = quantization_bound(original)
        assert restored.vertices.min(axis=0) == pytest.approx(
            original.vertices.min(axis=0), abs=bound
        )
        assert restored.vertices.max(axis=0) == pytest.approx(
            original.vertices.max(axis=0), abs=bound
        )

    def test_quantization_stays_far_inside_the_inset_clearance(self, cube_mesh):
        """The inset is the whole collision tolerance, so quantization error must
        stay well inside it -- a fifth of the clearance, on the largest part."""
        assert quantization_bound(cube_mesh(1600)) < MATING_CLEARANCE_LDU / 5


class TestMeshStore:
    def test_reads_a_part_from_its_category(self, store):
        s = store()
        assert len(s.read("3001").faces) == 12

    def test_reports_the_category_of_a_part(self, store):
        s = store()
        assert s.category("3020") == "Plate"

    def test_contains_only_indexed_parts(self, store):
        s = store()
        assert "3001" in s
        assert "99999" not in s

    def test_unknown_part_raises_naming_the_part(self, store):
        s = store()
        with pytest.raises(MeshUnavailable, match="99999"):
            s.read("99999")

    def test_missing_category_archive_raises_naming_the_category(self, store, tmp_path):
        s = store()
        (tmp_path / "Brick.zip").unlink()
        with pytest.raises(MeshUnavailable, match="Brick"):
            s.read("3001")

    def test_reads_are_cached(self, store):
        s = store()
        assert s.read("3001") is s.read("3001")

    def test_part_ids_lists_everything_indexed(self, store):
        s = store()
        assert set(s.part_ids()) == {"3001", "3020"}


class TestCatalogCoverage:
    def test_every_catalogued_part_has_a_collision_mesh(self):
        """A part with no mesh cannot be collided, so it must not be catalogued."""
        store = default_store()
        missing = sorted({pid for pid in part_ids() if pid not in store})
        assert missing == []


class TestPackagedResources:
    def test_the_index_and_every_referenced_archive_are_discoverable_as_resources(
        self,
    ):
        """Resolves the mesh store through ``importlib.resources``, the same
        mechanism ``default_store()`` uses, and checks the index and every category
        archive it names are present. This suite runs against an editable install,
        which mirrors the source tree, so it cannot by itself catch a build backend
        that omits the data from a real wheel — that was verified by building the
        wheel and inspecting its contents directly (see the packaging task's
        report). What it does catch is the index and archives drifting apart, e.g. a
        category renamed or deleted without updating ``index.json``.
        """
        root = resources.files("bricklayer.ldraw") / "meshes"
        index_resource = root / "index.json"
        assert index_resource.is_file()

        index = json.loads(index_resource.read_text())
        categories = set(index.values())
        missing = sorted(c for c in categories if not (root / f"{c}.zip").is_file())
        assert missing == []
