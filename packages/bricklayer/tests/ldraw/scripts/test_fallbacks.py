"""Resolve missing part data without changing a part's mould or local frame."""

import pytest

from bricklayer.geometry import Position
from bricklayer.ldraw.scripts.fallbacks import PartFallbacks, PartSource, pattern_base
from bricklayer.ldraw.scripts.library import Library


def _part(name="Brick  1 x  2"):
    return f"0 {name}\n"


def _redirect(target, transform="0 0 0 1 0 0 0 1 0 0 0 1"):
    return f"0 ~Moved to {target}\n1 16 {transform} {target}.dat\n"


class TestPartFallbacks:
    def test_direct_data_wins_over_a_redirect_or_pattern(self, ldraw_root):
        lib = Library(
            ldraw_root(
                {
                    "parts/3004.dat": _part(),
                    "parts/3004p01.dat": _part("Brick 1 x 2 with Pattern"),
                    "parts/old.dat": _redirect("3004p01"),
                }
            )
        )
        source = PartFallbacks(lib).resolve("3004p01", {"old", "3004", "3004p01"})
        assert source is not None
        assert source.part_id == "3004p01"

    def test_follows_redirects_in_both_directions_and_through_chains(self, ldraw_root):
        lib = Library(
            ldraw_root(
                {
                    "parts/old.dat": _redirect("middle"),
                    "parts/middle.dat": _redirect("new"),
                    "parts/new.dat": _part(),
                }
            )
        )
        resolver = PartFallbacks(lib)
        assert resolver.resolve("new", {"old"}) == PartSource("old")
        assert resolver.resolve("old", {"new"}) == PartSource("new")

    def test_redirect_transform_is_inverted_for_the_new_id(self, ldraw_root):
        lib = Library(
            ldraw_root(
                {
                    "parts/old.dat": _redirect("new", "20 0 0 0 0 1 0 1 0 -1 0 0"),
                    "parts/new.dat": _part(),
                }
            )
        )
        resolver = PartFallbacks(lib)
        forward = resolver.resolve("old", {"new"})
        inverse = resolver.resolve("new", {"old"})
        assert forward is not None and inverse is not None
        point = Position(2, 3, 4)
        assert forward.pose.apply(Position.ZERO) == Position(1, 0, 0)
        assert inverse.pose.apply(forward.pose.apply(point)) == point

    def test_prefers_redirect_data_to_a_patterned_sibling(self, ldraw_root):
        lib = Library(
            ldraw_root(
                {
                    "parts/3004.dat": _part(),
                    "parts/old.dat": _redirect("3004"),
                    "parts/3004p01.dat": _part("Brick 1 x 2 with Pattern"),
                }
            )
        )
        assert PartFallbacks(lib).resolve("3004", {"old", "3004p01"}) == PartSource(
            "old"
        )

    @pytest.mark.parametrize(
        "target,available,expected",
        [
            ("3004p01", {"3004", "3004p02"}, "3004"),
            ("3004", {"3004p01"}, "3004p01"),
            ("3004p01", {"3004p02"}, "3004p02"),
            ("3004d01", {"3004"}, "3004"),
        ],
    )
    def test_reuses_data_within_a_decoration_family(
        self, ldraw_root, target, available, expected
    ):
        lib = Library(
            ldraw_root(
                {
                    f"parts/{pid}.dat": _part()
                    for pid in ["3004", "3004p01", "3004p02", "3004d01"]
                }
            )
        )
        assert PartFallbacks(lib).resolve(target, available) == PartSource(expected)

    def test_missing_mesh_and_labels_can_choose_different_sources(self, ldraw_root):
        lib = Library(
            ldraw_root(
                {f"parts/{pid}.dat": _part() for pid in ["3004", "3004p01", "3004p02"]}
            )
        )
        resolver = PartFallbacks(lib)
        assert resolver.resolve("3004", {"3004p01"}) == PartSource("3004p01")
        assert resolver.resolve("3004", {"3004p02"}) == PartSource("3004p02")

    def test_mould_variants_and_assemblies_have_separate_families(self, ldraw_root):
        lib = Library(
            ldraw_root(
                {
                    f"parts/{pid}.dat": _part()
                    for pid in ["3004", "3004a", "3004b", "3004bp01", "3004p01c01"]
                }
            )
        )
        resolver = PartFallbacks(lib)
        assert resolver.resolve("3004a", {"3004", "3004b", "3004bp01"}) is None
        assert resolver.resolve("3004p01c01", {"3004"}) is None

    def test_cycles_and_unresolvable_families_return_none(self, ldraw_root):
        lib = Library(
            ldraw_root(
                {
                    "parts/a.dat": _redirect("b"),
                    "parts/b.dat": _redirect("a"),
                }
            )
        )
        assert PartFallbacks(lib).resolve("a", {"unrelated"}) is None

    @pytest.mark.parametrize(
        "matrix",
        [
            "0 0 0 2 0 0 0 1 0 0 0 1",
            "0 0 0 -1 0 0 0 1 0 0 0 1",
        ],
    )
    def test_nonrigid_or_reflected_wrappers_are_not_equivalences(
        self, ldraw_root, matrix
    ):
        lib = Library(
            ldraw_root(
                {
                    "parts/old.dat": _redirect("new", matrix),
                    "parts/new.dat": _part(),
                }
            )
        )
        assert PartFallbacks(lib).resolve("new", {"old"}) is None

    def test_a_wrapper_with_extra_geometry_is_not_an_equivalence(self, ldraw_root):
        lib = Library(
            ldraw_root(
                {
                    "parts/old.dat": _redirect("new") + "3 16 0 0 0 1 0 0 0 1 0\n",
                    "parts/new.dat": _part(),
                }
            )
        )
        assert PartFallbacks(lib).resolve("new", {"old"}) is None


class TestPatternBase:
    @pytest.mark.parametrize(
        "part_id,expected",
        [
            ("3004p01", "3004"),
            ("3068bp0c", "3068b"),
            ("3004p0100", "3004"),
            ("3004d01", "3004"),
            ("u123p01", "u123"),
            ("123c01p01", "123c01"),
            ("3004a", None),
            ("973p01c01", None),
            ("3004", None),
        ],
    )
    def test_preserves_the_undecorated_part_id(self, part_id, expected):
        assert pattern_base(part_id) == expected
