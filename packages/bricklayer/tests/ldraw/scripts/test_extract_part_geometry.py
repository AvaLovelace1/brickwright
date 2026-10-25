"""Tests for the part-geometry extraction script."""

from bricklayer.ldraw.scripts.extract_part_geometry import build_geometry, part_bbox
from bricklayer.ldraw.scripts.library import Library


class TestBuildGeometry:
    def test_build_geometry_warns_on_unmeasured_parts(self, ldraw_root, capsys):
        root = ldraw_root({"parts/box.dat": "4 16 0 0 0 1 0 0 1 0 1 0 0 1\n"})
        geometry = build_geometry(Library(root), ["box", "ghost"])
        assert set(geometry) == {"box"}
        assert geometry["box"]["bbox"] == ((0.0, 0.0, 0.0), (1.0, 0.0, 1.0))
        assert "ghost" in capsys.readouterr().err


class TestPartBbox:
    def test_part_bbox_accumulates_transformed_subfiles(self, ldraw_root):
        root = ldraw_root(
            {
                # A triangle, plus a sub-file offset by (10, 0, 0) and scaled 2x in x.
                "parts/box.dat": (
                    "3 16 0 0 0 4 0 0 0 2 0\n1 16 10 0 0 2 0 0 0 1 0 0 0 1 sub.dat\n"
                ),
                "parts/sub.dat": "2 16 0 0 0 1 5 -3\n",
            }
        )
        bbox = part_bbox(Library(root), "box")
        assert bbox == ((0.0, 0.0, -3.0), (12.0, 5.0, 0.0))

    def test_part_bbox_of_unresolved_part_is_none(self, ldraw_root):
        assert part_bbox(Library(ldraw_root({})), "ghost") is None
