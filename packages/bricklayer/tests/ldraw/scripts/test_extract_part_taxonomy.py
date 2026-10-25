"""Tests for the part-taxonomy extraction script."""

import pytest

from bricklayer.ldraw.scripts.extract_part_taxonomy import (
    build_taxonomy,
    resolve_redirect,
)
from bricklayer.ldraw.scripts.library import Library


class TestBuildTaxonomy:
    def test_descriptions_land_under_both_the_original_and_resolved_id(
        self, ldraw_root
    ):
        root = ldraw_root(
            {
                "parts/3665.dat": "0 ~Moved to 3665a\n",
                "parts/3665a.dat": "0 Slope Brick 45  2 x  1 Inverted\n",
            }
        )
        taxonomy = build_taxonomy(Library(root), ["3665"])
        assert taxonomy["3665"] == taxonomy["3665a"]
        assert taxonomy["3665a"] == "Slope Brick 45  2 x  1 Inverted"

    def test_skips_and_warns_about_an_unresolved_part(self, ldraw_root, capsys):
        root = ldraw_root({"parts/box.dat": "0 Brick  1 x  1\n"})
        taxonomy = build_taxonomy(Library(root), ["box", "ghost"])
        assert set(taxonomy) == {"box"}
        assert "ghost" in capsys.readouterr().err


class TestResolveRedirect:
    def test_resolves_a_plain_description_directly(self, ldraw_root):
        root = ldraw_root({"parts/3005.dat": "0 Brick  1 x  1\n"})
        assert resolve_redirect(Library(root), "3005") == ("3005", "Brick  1 x  1")

    def test_follows_a_single_redirect_hop(self, ldraw_root):
        root = ldraw_root(
            {
                "parts/3665.dat": "0 ~Moved to 3665a\n",
                "parts/3665a.dat": "0 Slope Brick 45  2 x  1 Inverted\n",
            }
        )
        assert resolve_redirect(Library(root), "3665") == (
            "3665a",
            "Slope Brick 45  2 x  1 Inverted",
        )

    def test_follows_multiple_redirect_hops(self, ldraw_root):
        root = ldraw_root(
            {
                "parts/a.dat": "0 ~Moved to b\n",
                "parts/b.dat": "0 ~Moved to c\n",
                "parts/c.dat": "0 Real Part\n",
            }
        )
        assert resolve_redirect(Library(root), "a") == ("c", "Real Part")

    def test_raises_on_a_redirect_cycle(self, ldraw_root):
        root = ldraw_root(
            {
                "parts/x.dat": "0 ~Moved to y\n",
                "parts/y.dat": "0 ~Moved to x\n",
            }
        )
        with pytest.raises(ValueError, match="exceeds"):
            resolve_redirect(Library(root), "x")

    def test_resolves_a_chain_of_exactly_the_hop_limit(self, ldraw_root):
        """5 redirects, then a real terminal description: the hop budget's edge."""
        root = ldraw_root(
            {
                "parts/h1.dat": "0 ~Moved to h2\n",
                "parts/h2.dat": "0 ~Moved to h3\n",
                "parts/h3.dat": "0 ~Moved to h4\n",
                "parts/h4.dat": "0 ~Moved to h5\n",
                "parts/h5.dat": "0 ~Moved to h6\n",
                "parts/h6.dat": "0 Real Terminal Part\n",
            }
        )
        assert resolve_redirect(Library(root), "h1") == ("h6", "Real Terminal Part")

    def test_raises_when_the_chain_exceeds_the_hop_limit(self, ldraw_root):
        """6 redirects; every id -- including the terminal -- is defined, so only
        the hop budget (not a missing file) can be the cause of the raise."""
        root = ldraw_root(
            {
                "parts/h1.dat": "0 ~Moved to h2\n",
                "parts/h2.dat": "0 ~Moved to h3\n",
                "parts/h3.dat": "0 ~Moved to h4\n",
                "parts/h4.dat": "0 ~Moved to h5\n",
                "parts/h5.dat": "0 ~Moved to h6\n",
                "parts/h6.dat": "0 ~Moved to h7\n",
                "parts/h7.dat": "0 Real Terminal Part\n",
            }
        )
        with pytest.raises(ValueError, match="exceeds"):
            resolve_redirect(Library(root), "h1")

    def test_missing_part_resolves_to_no_description(self, ldraw_root):
        assert resolve_redirect(Library(ldraw_root({})), "ghost") == ("ghost", None)
