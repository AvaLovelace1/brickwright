"""Tests for part identity, metadata, and catalog membership."""

import pytest

from bricklayer import Box, InvalidPartError, PartSpec, part_exists
from bricklayer.ldraw import partdata
from bricklayer.ldraw.partdata import taxonomy
from bricklayer.parts.catalog import all_parts

UNCATALOGUED = "not-a-catalogued-part"
A_BRICK = "3005"
A_WIDE_BRICK = "3001"
A_RIGHT_WING = "3545"
A_LEFT_WING = "3544"


class TestPartSpec:
    def test_an_id_the_catalog_does_not_hold_is_not_a_part(self):
        with pytest.raises(
            InvalidPartError, match=f"{UNCATALOGUED}.*not a catalogued LDraw part"
        ):
            PartSpec(UNCATALOGUED)

    def test_spec_carries_its_ldraw_id(self):
        assert PartSpec("3005").ldraw_id == A_BRICK

    def test_specs_are_equal_exactly_when_their_ids_are(self):
        assert PartSpec(A_BRICK) == PartSpec("3005")
        assert PartSpec(A_BRICK) != PartSpec(A_WIDE_BRICK)
        assert len({PartSpec(A_BRICK), PartSpec("3005")}) == 1

    def test_an_id_alone_answers_for_every_attribute(self):
        spec = PartSpec(A_BRICK)
        taxon = taxonomy(A_BRICK)
        assert taxon is not None
        assert spec.shape == Box(1, 1, 1)
        assert spec.chirality is None
        assert spec.name == taxon.name

    def test_spec_derives_category_and_features(self):
        spec = PartSpec("3024")
        assert spec.category == "Plate"
        assert spec.features is None

    def test_category_and_subcategory_match_the_ldraw_description(self):
        spec = PartSpec("3005")
        assert spec.category == "Brick"
        assert spec.subcategory is None

    def test_subcategory_is_the_text_between_category_and_dimensions(self):
        # 3005 is "Brick  1 x  1": a bare category, no subcategory.
        assert PartSpec("3005").subcategory is None
        # 4286 is "Slope Brick 33  3 x  1": the pitch is the subcategory.
        assert PartSpec("4286").subcategory == "Brick 33"

    def test_features_include_the_ldraw_description_clause(self):
        # 3070b is "Tile  1 x  1 with Groove".

        spec = PartSpec("3070b")
        assert spec.features == "with Groove"

    def test_every_catalogued_spec_resolves_its_taxonomy(self):
        """Every derived property answers for every catalogued part."""
        subcategoried = 0
        featured = 0
        for spec in all_parts():
            assert spec.name.startswith(spec.category)
            if spec.subcategory is not None:
                assert spec.subcategory.strip() == spec.subcategory
                subcategoried += 1
            if spec.features is not None:
                # A features clause always reads "with ..." or "without ...",
                # in either case.
                assert spec.features.lower().startswith("with")
                featured += 1
        # Both optional properties are exercised by a good share of the catalog,
        # so a property that always answered None could not pass this sweep.
        assert subcategoried > len(all_parts()) // 2
        assert featured > len(all_parts()) // 4

    def test_mirrored_swaps_a_handed_part_for_its_counterpart(self):
        assert PartSpec(A_RIGHT_WING).mirrored == PartSpec(A_LEFT_WING)

    def test_mirroring_a_handed_part_twice_returns_it(self):
        right = PartSpec(A_RIGHT_WING)
        assert right.mirrored.mirrored == right

    def test_mirrored_leaves_an_achiral_part_alone(self):
        spec = PartSpec(A_BRICK)
        assert spec.chirality is None
        assert spec.mirrored is spec

    def test_the_catalog_holds_handed_parts_with_no_counterpart(self):
        # Some parts were only ever made in one hand; `mirrored` keeps those,
        # so a model using one still mirrors.
        assert any(
            spec.chirality is not None and spec.mirrored is spec for spec in all_parts()
        )

    def test_partspec_shows_id_and_ldraw_name(self):
        taxon = taxonomy(A_BRICK)
        assert taxon is not None
        assert repr(PartSpec("3005")) == f"PartSpec({A_BRICK}: {taxon.name})"


class TestMembership:
    def test_a_part_with_a_taxonomy_record_is_catalogued(self):
        assert PartSpec("4175").name == "Plate  1 x  2 with Ladder"

    def test_all_parts_ranges_over_the_whole_catalog(self) -> None:
        assert len(all_parts()) == len(partdata.part_ids())


class TestPartExists:
    def test_a_real_id_exists(self):
        # A_BRICK is a fixed, known-real id (not derived from part_ids(), which
        # is what part_exists() itself checks) -- unlike sweeping all_parts(),
        # this can actually fail if the two definitions of "real" disagree.
        assert part_exists(A_BRICK)

    def test_an_id_the_catalog_does_not_hold_does_not_exist(self):
        assert not part_exists(UNCATALOGUED)


@pytest.mark.parametrize(
    "part_id",
    [
        "2446",
        "2454",
        "2599",
        "30171",
        "32556",
        "3626p01",
        "3665",
        "41769",
        "41770",
        "43722",
        "43723",
        "60603",
    ],
)
def test_retired_ids_with_colliders_are_catalogued(part_id):
    assert part_exists(part_id)


def test_handed_counterpart_uses_original_among_same_suffix_aliases():
    right = PartSpec("3818")
    left = PartSpec("3819")
    assert right.mirrored == left
    assert left.mirrored == right


def test_handed_counterparts_preserve_variant_among_duplicate_alias_names(monkeypatch):
    descriptions = {
        "41769": "Wing  2 x  4 Right without Chamfer",
        "41769a": "Wing  2 x  4 Right without Chamfer",
        "41770": "Wing  2 x  4 Left without Chamfer",
        "41770a": "Wing  2 x  4 Left without Chamfer",
    }
    monkeypatch.setattr(partdata, "_parts", lambda _: descriptions)
    monkeypatch.setattr(partdata, "part_ids", lambda: frozenset(descriptions))
    caches = (partdata.taxonomy, partdata.mirrored_part_id, partdata._ids_by_name)
    for function in caches:
        function.cache_clear()
    try:
        for suffix in ("", "a"):
            right = PartSpec(f"41769{suffix}")
            left = PartSpec(f"41770{suffix}")
            assert right.mirrored == left
            assert left.mirrored == right
    finally:
        for function in caches:
            function.cache_clear()
