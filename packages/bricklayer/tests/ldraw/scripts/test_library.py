"""Tests for the shared LDraw extraction-script plumbing."""

import json
import lzma
import os

import pytest

from bricklayer.ldraw import partdata
from bricklayer.ldraw.scripts.fallbacks import PartSource
from bricklayer.ldraw.scripts.library import (
    _LDRAW_ROOTS,
    Library,
    catalog_sources,
    load_alias_sources,
    load_labels,
    report_against_committed,
    selected_part_ids,
    write_parts_json,
)


class TestCatalogSources:
    def test_selects_missing_data_through_redirects_and_decorations(
        self, ldraw_root, tmp_path
    ):
        root = ldraw_root(
            {
                "parts/old.dat": "0 ~Moved to 3001\n1 16 0 0 0 1 0 0 0 1 0 0 0 1 3001.dat\n",
                "parts/3001.dat": "0 Brick 2 x 4\n",
                "parts/3001p01.dat": "0 Brick 2 x 4 with Pattern\n",
                "parts/3001b.dat": "0 Brick 2 x 4 Different Mould\n",
            }
        )
        meshes = tmp_path / "meshes"
        meshes.mkdir()
        (meshes / "old.ply").touch()
        data = tmp_path / "bricknet"
        data.mkdir()
        (data / "labels.json.xz").write_bytes(
            lzma.compress(
                json.dumps({"3001p01.dat": {"stud": {"stud": [[0, 0, 0]]}}}).encode()
            )
        )
        (data / "part_aliases.json.xz").write_bytes(lzma.compress(b'{"rows": []}'))
        catalog = catalog_sources(Library(root), mesh_dir=meshes, bricknet_data=data)
        assert catalog.part_ids == ["3001", "3001p01", "old"]
        assert catalog.meshes["3001p01"] == PartSource("old")
        assert catalog.connectivity["3001"] == PartSource("3001p01")
        assert set(catalog.labels) == {"3001p01"}

    def test_selects_colliders_without_connector_labels(
        self, ldraw_root, tmp_path, bricknet_data
    ):
        root = ldraw_root({"parts/52629.dat": "0 Technic Ball 19mm\n"})
        meshes = tmp_path / "meshes"
        meshes.mkdir()
        (meshes / "52629.ply").touch()
        catalog = catalog_sources(
            Library(root), mesh_dir=meshes, bricknet_data=bricknet_data
        )
        assert catalog.part_ids == ["52629"]
        assert catalog.meshes["52629"] == PartSource("52629")
        assert "52629" not in catalog.connectivity


class TestSelectedPartIDs:
    @pytest.mark.integration
    def test_selected_part_ids_covers_every_id_the_committed_data_was_extracted_for(
        self, ldraw_library
    ) -> None:
        """Every id represented by committed part data remains selected."""
        selected = set(selected_part_ids(ldraw_library))
        missing = sorted(partdata.part_ids() - selected)
        assert missing == []

    @pytest.mark.integration
    def test_selected_part_ids_preserves_catalog_size(self, ldraw_library) -> None:
        """Detect substantial coverage loss while allowing small catalog refreshes."""
        assert len(selected_part_ids(ldraw_library)) >= 0.99 * len(partdata.part_ids())

    @pytest.mark.integration
    def test_selected_part_ids_includes_obsolete_colliders(self, ldraw_library) -> None:
        assert {"3816b", "3817b"} <= set(selected_part_ids(ldraw_library))


class TestLoadLabels:
    def test_reads_all_labelled_stems(self, bricknet_data):
        assert set(load_labels(bricknet_data)) == {"3001", "30124b"}


class TestLoadAliasSources:
    def test_reads_aliases_with_their_transforms(self, bricknet_data):
        assert load_alias_sources(bricknet_data) == [("2446", PartSource("30124b"))]


class TestLibrary:
    def test_resolve_searches_official_and_unofficial_trees(self, ldraw_root):
        root = ldraw_root(
            {
                "parts/3005.dat": "official",
                "p/stud.dat": "primitive",
                "UnOfficial/parts/999.dat": "unofficial",
            }
        )
        lib = Library(root)
        assert lib.resolve("3005.dat") is not None
        assert lib.resolve("stud.dat") is not None
        assert lib.resolve("999.dat") is not None
        assert lib.resolve("nope.dat") is None

    def test_lines_records_missing_subfiles(self, ldraw_root):
        lib = Library(ldraw_root({}))
        assert lib.lines("ghost.dat") is None
        assert "ghost.dat" in lib.missing

    def test_description_strips_the_leading_marker(self, ldraw_root):
        root = ldraw_root({"parts/3005.dat": "0 Brick  1 x  1\n"})
        assert Library(root).description("3005") == "Brick  1 x  1"

    def test_description_of_a_missing_part_is_empty(self, ldraw_root):
        """``select_part_ids`` relies on this to reject an unresolved part rather
        than crash across 21,084 lookups -- it must never raise."""
        assert Library(ldraw_root({})).description("ghost") == ""

    def test_description_of_a_missing_part_records_it_as_missing(self, ldraw_root):
        lib = Library(ldraw_root({}))
        lib.description("ghost")
        assert "ghost.dat" in lib.missing

    def test_description_does_not_read_or_cache_the_whole_file(self, ldraw_root):
        """A part's ``.dat`` can run to thousands of lines; ``description`` only
        needs line 1, so it must not go through :meth:`Library.lines` (which
        reads and forever caches the full file) to get it."""
        root = ldraw_root({"parts/3005.dat": "0 Brick  1 x  1\nextra\nextra\n"})
        lib = Library(root)
        lib.description("3005")
        assert lib._lines == {}

    def test_repeated_description_lookups_reread_only_once(self, ldraw_root):
        root = ldraw_root({"parts/3005.dat": "0 Brick  1 x  1\n"})
        lib = Library(root)
        lib.description("3005")
        (path,) = root.glob("parts/*.dat")
        path.unlink()
        # The file is gone, so a second lookup that isn't cached would raise.
        assert lib.description("3005") == "Brick  1 x  1"

    def test_unofficial_reason(self, ldraw_root):
        root = ldraw_root(
            {
                "parts/1.dat": "0 !LDRAW_ORG Part UPDATE 2023-01\n",
                "parts/2.dat": "0 !LDRAW_ORG Unofficial_Part\n",
                "UnOfficial/parts/3.dat": "0 comment\n",
            }
        )
        lib = Library(root)
        assert lib.unofficial_reason("1.dat") is None
        assert lib.unofficial_reason("2.dat") == "marked unofficial in its header"
        assert (
            lib.unofficial_reason("3.dat")
            == "found only in the library's UnOfficial tree"
        )


class TestLibraryFind:
    def test_find_prefers_explicit_root(self, ldraw_root):
        root = ldraw_root({})
        assert Library.find(str(root)).root == root

    def test_find_searches_known_roots_in_order(self, ldraw_root, monkeypatch):
        root = ldraw_root({})
        monkeypatch.setattr(
            "bricklayer.ldraw.scripts.library._LDRAW_ROOTS",
            ("/no/such/dir", str(root)),
        )
        assert Library.find(None).root == root

    def test_find_without_library_exits(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "bricklayer.ldraw.scripts.library._LDRAW_ROOTS", (str(tmp_path),)
        )
        with pytest.raises(SystemExit):
            Library.find(None)

    def test_the_env_var_leads_the_root_list(self):
        assert _LDRAW_ROOTS[0] == os.environ.get("LDRAW_LIBRARY_PATH", "")
        assert not any("Studio" in root for root in _LDRAW_ROOTS)

    def test_find_error_names_the_env_var_it_searched(self, monkeypatch, tmp_path):
        missing = str(tmp_path / "nowhere")  # nonexistent -> nothing resolves
        monkeypatch.setenv("LDRAW_LIBRARY_PATH", missing)
        monkeypatch.setattr(
            "bricklayer.ldraw.scripts.library._LDRAW_ROOTS",
            (missing, "/no/such/dir"),
        )
        with pytest.raises(SystemExit, match=r"\$LDRAW_LIBRARY_PATH"):
            Library.find(None)


class TestWritePartsJson:
    def test_write_parts_json_is_stable_one_record_per_line(self, tmp_path):
        path = tmp_path / "out.json"
        write_parts_json(
            path,
            {"b": {"bbox": [[0, 0, 0], [1, 1, 1]]}, "a": {"boxes": []}},
            generated_by="x.py",
            note="a note",
        )
        data = json.loads(path.read_text())
        assert data["_generated_by"] == "x.py"
        assert data["_note"] == "a note"
        assert data["units"] == "LDU"
        assert list(data["parts"]) == ["a", "b"]
        lines = path.read_text().splitlines()
        assert any(line.strip().startswith('"a": {') for line in lines)
        assert any(line.strip().startswith('"b": {') for line in lines)


class TestReportAgainstCommitted:
    def test_report_against_committed_flags_added_removed_changed(
        self, tmp_path, capsys
    ):
        path = tmp_path / "committed.json"
        write_parts_json(
            path,
            {"kept": {"v": 1}, "gone": {"v": 1}, "moved": {"v": [1.0]}},
            generated_by="x",
            note="n",
        )
        fresh = {"kept": {"v": 1}, "new": {"v": 2}, "moved": {"v": (2.0,)}}
        assert report_against_committed(fresh, path) is False
        out = capsys.readouterr().out
        assert "+ new" in out
        assert "- gone" in out
        assert "~ moved" in out
        assert "kept" not in out

    def test_report_against_committed_normalizes_json_types(self, tmp_path, capsys):
        path = tmp_path / "committed.json"
        write_parts_json(path, {"a": {"v": [1.5]}}, generated_by="x", note="n")
        assert report_against_committed({"a": {"v": (1.5,)}}, path) is True
        assert "up to date" in capsys.readouterr().out

    def test_report_against_committed_without_file(self, tmp_path, capsys):
        assert report_against_committed({}, tmp_path / "nope.json") is False
        assert "no committed file" in capsys.readouterr().out
