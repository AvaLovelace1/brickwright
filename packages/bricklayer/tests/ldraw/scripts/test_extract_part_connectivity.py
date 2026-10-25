"""Extraction of resolved BrickNet labels into the committed data file."""

import json

import pytest

from bricklayer.ldraw.scripts import extract_part_connectivity as extract
from bricklayer.ldraw.scripts.fallbacks import PartSource
from bricklayer.ldraw.scripts.library import load_labels

_TYPE_ALIASES = {"stud/stud": "stud", "hole/hole": "antistud", "hole/tube": "tube"}


@pytest.fixture
def loaded(bricknet_data):
    return load_labels(bricknet_data), {
        "3001": PartSource("3001"),
        "30124b": PartSource("30124b"),
        "2446": PartSource("30124b"),
    }


@pytest.fixture
def mesh_dir(tmp_path, monkeypatch):
    path = tmp_path / "inset"
    path.mkdir()
    (path / "2446.ply").touch()
    monkeypatch.setenv("BRICKNET_MESHES", str(path))
    return path


class TestMain:
    @pytest.mark.parametrize("include_alias", [False, True])
    def test_writes_original_labels_and_selected_donors(
        self, bricknet_data, mesh_dir, tmp_path, ldraw_root, include_alias
    ):
        files = {"parts/2446.dat": "0 Minifig Helmet Visor\n"} if include_alias else {}
        output = tmp_path / "out.json"
        assert (
            extract.main(
                [
                    "--bricknet-data",
                    str(bricknet_data),
                    "--ldraw",
                    str(ldraw_root(files)),
                    "--output",
                    str(output),
                ]
            )
            == 0
        )
        written = json.loads(output.read_text())["parts"]
        expected = {"3001", "30124b"} | ({"2446"} if include_alias else set())
        assert set(written) == expected
        if include_alias:
            assert written["2446"]["_source"] == "30124b"

    def test_missing_data_directory_exits(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BRICKNET_DATA", raising=False)
        monkeypatch.setattr(
            "bricklayer.ldraw.scripts.library.resources.files",
            lambda _: tmp_path / "not-installed",
        )
        with pytest.raises(SystemExit, match="No BrickNet connector labels"):
            extract.main(
                [
                    "--bricknet-data",
                    str(tmp_path / "nope"),
                    "--output",
                    str(tmp_path / "out.json"),
                ]
            )


class TestBuildConnectivity:
    def test_groups_rows_under_resolved_type_names(self, loaded):
        labels, sources = loaded
        parts, missing = extract.build_connectivity(
            labels, sources, ["3001"], _TYPE_ALIASES
        )
        assert parts["3001"]["connectors"] == {
            "antistud": [[-30, 24, -10, 0.0, 0.0]],
            "stud": [[-30, 0, -10], [30, 0, 10]],
        }
        assert missing == []

    def test_records_the_resolved_donor(self, loaded):
        labels, sources = loaded
        parts, missing = extract.build_connectivity(
            labels, sources, ["2446"], _TYPE_ALIASES
        )
        assert "tube" in parts["2446"]["connectors"]
        assert parts["2446"]["_source"] == "30124b"
        assert missing == []

    def test_reports_ids_without_a_label_donor(self, loaded):
        labels, sources = loaded
        parts, missing = extract.build_connectivity(
            labels, sources, ["60601"], _TYPE_ALIASES
        )
        assert parts == {}
        assert missing == ["60601"]

    def test_unaliased_triple_keeps_its_mechanical_name(self, loaded):
        labels, sources = loaded
        parts, _ = extract.build_connectivity(
            labels, sources, ["30124b"], _TYPE_ALIASES
        )
        assert parts["30124b"]["connectors"]["hinge_5_in"] == [
            [0, 8, 0.7, 0.0, 90.0, 0]
        ]

    def test_type_groups_are_sorted(self, loaded):
        labels, sources = loaded
        parts, _ = extract.build_connectivity(labels, sources, ["3001"], _TYPE_ALIASES)
        keys = list(parts["3001"]["connectors"])
        assert keys == sorted(keys)

    def test_distinguishes_original_and_borrowed_data(self):
        labels = {"3001": {"stud": {"stud": [[0, 0, 0]]}}}
        sources = {p: PartSource("3001") for p in ["3001", "3001p01"]}
        parts, missing = extract.build_connectivity(
            labels, sources, list(sources), _TYPE_ALIASES
        )
        assert parts["3001"] == {"connectors": {"stud": [[0, 0, 0]]}}
        assert parts["3001p01"] == {
            "connectors": {"stud": [[0, 0, 0]]},
            "_source": "3001",
        }
        assert missing == []

    def test_transforms_connector_positions_axes_and_preserves_slide_length(self):
        source = PartSource.from_ldraw("new", [20, 0, 0, 0, -1, 0, 1, 0, 0, 0, 0, 1])
        assert source is not None
        labels = {"new": {"axle": {"axle": [[0, 0, 0, 0, 0, 16]]}}}
        parts, _ = extract.build_connectivity(labels, {"old": source}, ["old"], {})
        assert parts["old"]["connectors"] == [
            {
                "type": "axle_axle",
                "pos": (20, 0, 0),
                "axis": (1, 0, 0),
                "side": (0, 0, -1),
                "length": 16,
            }
        ]

    def test_transforms_fixed_frame_yaw_without_turning_it_into_length(self):
        source = PartSource.from_ldraw("new", [20, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1])
        assert source is not None
        labels = {"new": {"fixed": {"1": {"in": [[0, 0, 0, 0, 0, 90]]}}}}
        parts, _ = extract.build_connectivity(labels, {"old": source}, ["old"], {})
        connector = parts["old"]["connectors"][0]
        assert connector["axis"] == (0, 0, 1)
        assert connector["side"] == (0, -1, 0)
        assert connector["length"] == 0
