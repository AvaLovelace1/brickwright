"""Every catalogued shape derives from its LDraw description, or is overridden."""

from fractions import Fraction

import pytest

from bricklayer.geometry import Position
from bricklayer.ldraw import partdata
from bricklayer.parts.catalog import PartSpec, all_parts
from bricklayer.parts.derivation import (
    _SHAPE_READERS,
    _axis_deltas,
    _better_fit,
    _classify,
    _nonsquare_round_footprint,
    _overstates_measured_geometry,
    _read_disc,
    _read_length,
    _read_rod,
    derived_shape,
    overridden_shape,
    shape_from_name,
)
from bricklayer.parts.shape import Box, Disc, Ell, Footprint, Length, Pane, Rod


def _measured_shape_mismatches(spec: PartSpec) -> list[str]:
    """How ``spec``'s derived shape overstates its measured LDraw geometry,
    using :func:`~.derivation._axis_deltas` and each class's own slack, as
    :func:`~.derivation._overstates_measured_geometry` does. Catches shape
    overrides, which skip that check at derivation time.
    """
    shape = spec.shape
    if shape is None:
        return []
    extents = partdata.record(spec.ldraw_id).measured_extents
    slack = _SHAPE_READERS[type(shape)].slack
    return [
        f"{type(shape).__name__}[{i}] derived {derived:.3f} vs measured {measured:.3f}"
        for i, (derived, measured) in enumerate(_axis_deltas(shape, extents))
        if derived - measured > slack
    ]


def _a_nameless_part() -> str:
    """A real, catalogued id with nothing to give it a shape: its LDraw name
    states no dimension run, and it carries no override either -- which one it
    is does not matter, so it is found by query rather than pinned."""
    return next(
        pid
        for pid in sorted(partdata.part_ids())
        if (record := partdata.taxonomy(pid)) is not None
        and not record.dimensions
        and partdata.shape_override(pid) is None
    )


# A box-shaped part with known geometry.
A_BOX_SHAPED_PART = "3001"


class TestDerivedShape:
    @pytest.mark.parametrize(
        ("part_id", "expected"),
        [
            ("4476", Box(2, 4, 5)),
            ("14417", Footprint(2, 1)),
            ("14704", Footprint(2, 1)),
            ("3184", Footprint(4, 1)),
            ("98263", Footprint(4, 1)),
        ],
    )
    def test_support_and_towball_shapes_need_no_override(self, part_id, expected):
        assert partdata.shape_override(part_id) is None
        assert derived_shape(part_id) == expected

    def test_a_plate_transposes_ldraws_depth_first_run(self):
        """ "Plate  1 x  4" is depth 1, width 4."""
        assert PartSpec("3710").shape == Footprint(4, 1)

    def test_a_slope_fills_in_its_implied_height(self):
        """ "Slope Brick 18  4 x  1" carries no height; a Box needs one."""
        assert PartSpec("60477").shape == Box(1, 4, 1)

    def test_a_wing_is_already_width_first(self):
        """ "Wing  3 x  8 Left" is width 3, depth 8 -- unlike a plate."""
        assert PartSpec("3544").shape == Footprint(3, 8)

    def test_a_pane_drops_its_leading_depth(self):
        """ "Glass for Window  1 x  4 x  6" is width 4, height 6."""
        assert PartSpec("57895").shape == Pane(4, 6)

    def test_a_footprint_drops_its_trailing_height(self):
        """ "Plate  8 x 16 x  0.667" is width 16, depth 8 -- the trailing
        0.667 states a plate whose thickness is not the nominal one third of
        a brick, which a footprint (no height field) has nowhere to put, the
        same way a pane has nowhere to put its leading depth."""
        assert PartSpec("18922").shape == Footprint(16, 8)

    def test_a_bracket_transposes_both_of_its_runs(self):
        """ "Bracket  1 x  2 -  1 x  2 Down" is two depth-first runs."""
        assert PartSpec("99781").shape == Ell(2, 1, 2, 1)

    def test_a_cone_reads_its_height_past_the_diameter_pair(self):
        """ "Cone  4 x  4 x  2" is 4 across and 2 bricks tall."""
        assert PartSpec("3943a").shape == Rod(4, 2)

    def test_a_beam_takes_the_first_number_and_ignores_its_thickness(self):
        """ "Technic Beam  5 x  0.5" is 5 long; the 0.5 is its thickness."""
        assert PartSpec("32017").shape == Length(5)

    def test_a_two_dimensional_beam_is_not_a_length(self):
        """ "Technic Beam  3 x  5 Bent 90" spans two axes; no one length fits."""
        assert PartSpec("32526").shape is None

    def test_a_beam_drawn_along_y_still_reads_its_length(self):
        """The sticker variant of "Technic Beam 15" is modelled along y."""
        assert PartSpec("32278d02").shape == PartSpec("32278").shape == Length(15)

    def test_a_door_drawn_along_y_still_reads_as_a_pane(self):
        """ "Door  1 x  3 x  2 Left" is modelled 3 wide along y, not x."""
        assert PartSpec("3189").shape == Pane(3, 2)
        assert PartSpec("3821d01").shape == PartSpec("3821").shape

    def test_a_decimal_height_normalises_to_plate_thirds(self):
        """ "Brick  1 x  1 x  1.667" is five plates, not 1667/1000 of a brick."""
        assert PartSpec("32952").shape == Box(1, 1, Fraction(5, 3))

    def test_an_overridden_shape_wins(self):
        """ "Technic Pin" carries no run at all; its length is hand-authored."""
        assert PartSpec("3673").shape == Length(2)

    def test_girder_shape_uses_its_width_first_dimension_order(self):
        """ "Support  2 x  4 x  5" is the lone width-first girder."""
        assert PartSpec("4476").shape == Box(2, 4, 5)

    def test_every_shape_in_the_catalog_derives_or_is_overridden(self):
        """Every derived or overridden shape agrees with its source data and measurements."""
        wrong = []
        for spec in all_parts():
            wrong.extend(
                f"{spec.ldraw_id} ({spec.name}): {m}"
                for m in _measured_shape_mismatches(spec)
            )
        assert wrong == []


class TestShapeClassification:
    def test_most_parts_with_a_dimension_run_get_a_shape(self) -> None:
        """Not "most of the catalog" -- a minifig head or a sticker never
        carries a dimension run to begin with, so most of the catalog was
        never a candidate. The size-search payoff is in the population that
        *could* be read: most of what states a size gets one.
        """
        dimensioned = sum(
            1
            for pid in partdata.part_ids()
            if (record := partdata.taxonomy(pid)) is not None and record.dimensions
        )
        sized = sum(1 for s in all_parts() if s.shape is not None)
        assert sized > dimensioned / 2

    def test_a_round_brick_reads_as_a_rod_not_a_box(self) -> None:
        assert _classify("Brick", "Round").shape_type is Rod
        assert _classify("Brick", None).shape_type is Box

    def test_a_round_plate_reads_as_a_disc(self) -> None:
        assert _classify("Plate", "Round").shape_type is Disc
        assert _classify("Plate", None).shape_type is Footprint

    def test_a_door_frame_reads_as_a_box_not_a_pane(self) -> None:
        assert _classify("Door", "Frame").shape_type is Box
        assert _classify("Door", None).shape_type is Pane

    def test_an_unlisted_category_has_no_shape(self) -> None:
        assert _classify("Sticker", None).shape_type is None

    def test_inferred_shapes_fit_the_parts_measured_geometry(self):
        for spec in all_parts():
            if spec.shape is None or partdata.shape_override(spec.ldraw_id) is not None:
                continue
            extents = partdata.record(spec.ldraw_id).measured_extents
            assert _better_fit(spec.shape, extents) == spec.shape, spec.ldraw_id


class TestAKeywordCanResolveToNoShape:
    """A keyword's target is not always a shape class: it can name ``None``
    too, the same way a row with no ``default`` means "no shape outside my
    keywords" -- but scoped to one keyword rather than the whole row, for a
    subcategory that is a false positive on a *different* keyword only."""

    def test_a_cross_block_is_not_a_length_even_though_axle_is_in_its_name(
        self,
    ) -> None:
        """ "Technic Cross Block (Axle/Pin)" is a joint connector, not a
        length -- "Axle" is checked first for genuine axles, but "Cross
        Block" wins the keyword race and answers no shape at all."""
        assert _classify("Technic", "Cross Block (Axle/Pin)").shape_type is None

    def test_a_plain_axle_is_still_a_length(self) -> None:
        assert _classify("Technic", "Axle").shape_type is Length


class TestCornerRoundIsNotRound:
    """ "Corner Round" states a rounded *corner* on an otherwise square part
    -- its own bounding box is the full square, not a quarter-circle -- so it
    must not fall into the "Round" keyword meant for genuinely round parts.
    "Corner" is checked first and answers the row's own default, the same
    shape a non-round part of that category would get anyway."""

    def test_a_corner_round_tile_is_a_footprint_not_a_disc(self) -> None:
        assert _classify("Tile", "Corner Round").shape_type is Footprint

    def test_a_corner_round_brick_is_a_box_not_a_rod(self) -> None:
        assert _classify("Brick", "Corner Round").shape_type is Box

    def test_a_genuinely_round_tile_is_still_a_disc(self) -> None:
        assert _classify("Tile", "Round").shape_type is Disc

    def test_a_genuinely_round_brick_is_still_a_rod(self) -> None:
        assert _classify("Brick", "Round").shape_type is Rod


class TestAQualifiedRoundReadingNeedsANonsquareFootprintToo:
    """A keyword naming a round class (``Disc``/``Rod``) still matches as a
    substring, same as any other keyword -- "Round" inside "Round Half
    Circle" resolves to ``Rod`` just like a bare "Round" does. What a
    *qualified* match (the keyword is a strict substring, not the whole
    subcategory) adds is a second, later check: :func:`_measured_reading`
    only asks whether the footprint is square enough to be round
    (:data:`_ROUND_SQUARENESS_SLACK`) when the match was qualified.

    Neither signal is sufficient alone. A qualifier is not evidence of a
    partial shape by itself -- "Round Sphere" and "Round Reinforced" are
    qualified and fully round. Non-square geometry is not evidence of a
    misread by itself -- a bar, a clip, a handle, or a sculpted extension
    enlarges an otherwise-round box exactly the way a partial round shape's
    box would look enlarged. Only the *conjunction* -- qualified AND
    non-square -- means the reading is wrong: the qualifier raises the
    suspicion, the geometry confirms it.
    """

    # Qualified ("Round ..." states more than the bare word) AND
    # non-square: genuine partial-round misreads.
    MISREAD_ROUND_PARTS = (
        "47974",  # Brick  4 x  8 Round Half Circle
        "48147",  # Brick  4 x  8 Round Half Circle
        "22888",  # Plate  4 x  8 Round Semicircle
        "18646",  # Plate  3 x  6 Round Half
        "1746",  # Cone  4 x  8 x  6 Half
        "77845",  # Plate  1 x  4 Round Ends
        "48995",  # Tile  2 x  3 Rounded with Hole
        "48995pt1",  # Tile  2 x  3 Rounded with Hole
    )

    # Unqualified ("Round" exactly, or round by category for Dish/
    # Turntable) -- exempt from the geometry check no matter how a bar,
    # clip, handle, hinge, or sculpted extension stretches the footprint.
    UNQUALIFIED_ROUND_PARTS = (
        "18675",  # Dish  6 x  6 Inverted - No Studs with Handle
        "4508",  # Turntable  2 x  2 Plate Base with Hinge
        "3614a",  # Plate  1 x  1 Round with Towball
        "32828",  # Plate  1 x  1 Round with Bar
        "4735",  # Brick  1 x  1 x  0.667 Round with Bar and Clip Vertical
        "67361",  # Brick  2 x  2 Round with Tail/Neck Curved Extension ...
        "7508",  # Plate  1 x  2 Round with Horizontal Handle on Side
    )

    # Qualified, but square: a shape variant, orientation, structural
    # variant, angle, or decoration name -- not a partial shape, and the
    # geometry check confirms that rather than rejecting it.
    QUALIFIED_BUT_SQUARE_ROUND_PARTS = (
        "1871",  # Brick  1 x  1 x  1.333 Round Quarter Dome with Curved Top
        "20953",  # Brick  2 x  2 x  1.667 Round Sphere with Stud
        "20953p01",
        "20953p02",
        "3567",  # Tile  2 x  2 Round Inverted with Groove
        "6143",  # Brick  2 x  2 Round Reinforced
        "6143d01",
        "6143d02",
        "65473",  # Brick  2 x  2 Round Curved 45 Degrees
        "80677",  # Tile  2 x  2 Round Splat
    )

    @pytest.mark.parametrize("part_id", MISREAD_ROUND_PARTS)
    def test_a_qualified_nonsquare_reading_loses_its_shape(self, part_id: str) -> None:
        assert derived_shape(part_id) is None

    @pytest.mark.parametrize("part_id", UNQUALIFIED_ROUND_PARTS)
    def test_an_unqualified_reading_keeps_its_shape_regardless_of_geometry(
        self, part_id: str
    ) -> None:
        assert isinstance(derived_shape(part_id), Disc | Rod)

    @pytest.mark.parametrize("part_id", QUALIFIED_BUT_SQUARE_ROUND_PARTS)
    def test_a_qualified_but_square_reading_keeps_its_shape(self, part_id: str) -> None:
        assert isinstance(derived_shape(part_id), Disc | Rod)

    def test_classification_matches_a_qualified_keyword(self) -> None:
        # _classify alone only classifies; it does not reject a
        # qualified reading -- that needs the geometry check too.
        assert _classify("Brick", "Round Half Circle").shape_type is Rod
        assert _classify("Tile", "Rounded").shape_type is Disc

    def test_half_round_classification_is_rejected_for_nonsquare_geometry(self) -> None:
        # Half Round matches a round keyword, but these parts have nonsquare
        # footprints, so their geometry cannot support a round shape.
        assert _classify("Brick", "Half Round").shape_type is Rod
        for part_id in ("1745", "1748", "3386", "716a", "716b"):
            assert derived_shape(part_id) is None, part_id

    def test_a_qualifier_on_a_non_round_keyword_is_unaffected(self) -> None:
        # The geometry check is scoped to keywords naming a round class --
        # "Corner" (-> Box/Footprint) is never qualified in this sense.
        assert _classify("Tile", "Corner Round").shape_type is Footprint
        assert _classify("Brick", "Corner Round").shape_type is Box

    def test_a_qualified_category_default_is_unaffected_by_this_rule(self) -> None:
        # Dish/Turntable are round by category, not by keyword, so there is
        # no keyword to be "qualified" -- confirmed on real, qualified
        # subcategories that must NOT trip the geometry check.
        assert _classify("Dish", "Inverted - No Studs").shape_type is Disc
        assert _classify("Turntable", "Plate Base").shape_type is Disc

    def test_a_qualified_cone_is_excluded_by_its_own_keyword_row(self) -> None:
        # Cone is also round by category, but "Half" needs excluding the
        # same way Brick/Plate/Tile's own keywords exclude a qualifier --
        # not by this rule, which cannot see a category-default reading at
        # all. This exception is intentional: do not delete Cone's "Half":
        # null row, and do not try to make the qualified-round check reach
        # a category default -- there is no keyword there to qualify.
        assert _classify("Cone", "Half").shape_type is None
        assert _classify("Cone", None).shape_type is Rod


class TestOverriddenShape:
    """A malformed override fails on decode, long before :attr:`PartSpec.shape`
    can name the part it belongs to -- so the decode error must name it itself,
    or a bad row in a file that keeps growing gives no pointer back to it."""

    def test_an_unknown_shape_class_names_the_part(self, patch_shape_overrides):
        patch_shape_overrides({A_BOX_SHAPED_PART: {"type": "Cube", "width": 1}})
        with pytest.raises(KeyError, match=A_BOX_SHAPED_PART):
            overridden_shape(A_BOX_SHAPED_PART)

    def test_a_missing_field_names_the_part(self, patch_shape_overrides):
        patch_shape_overrides({A_BOX_SHAPED_PART: {"type": "Box", "width": 1}})
        with pytest.raises(TypeError, match=A_BOX_SHAPED_PART):
            overridden_shape(A_BOX_SHAPED_PART)


class TestShapeFromName:
    NAMELESS_RUN = _a_nameless_part()

    def test_the_adapter_reads_nothing_out_of_a_runless_name(self):
        assert shape_from_name(self.NAMELESS_RUN, Box) is None


class TestOverstatesMeasuredGeometry:
    def test_a_matching_footprint_is_not_rejected(self) -> None:
        assert not _overstates_measured_geometry(Disc(4), Position(4, 4, 0))

    def test_a_footprint_within_the_slack_is_not_rejected(self) -> None:
        assert not _overstates_measured_geometry(Box(1, 1, 1), Position(1, 1, 0.8))

    def test_a_footprint_past_the_slack_is_rejected(self) -> None:
        assert _overstates_measured_geometry(Box(1, 1, 1), Position(1, 1, 0.5))

    def test_understating_is_not_rejected(self) -> None:
        # A protruding stud, a wheel pin, a towball socket: understating the
        # measured box is not a misread, just an unfair comparison.
        assert not _overstates_measured_geometry(Disc(4), Position(4, 8, 0))


class TestNonsquareRoundFootprint:
    def test_a_square_footprint_is_not_rejected(self) -> None:
        assert not _nonsquare_round_footprint(Disc(4), Position(4, 4, 0))

    def test_a_footprint_within_the_slack_is_not_rejected(self) -> None:
        assert not _nonsquare_round_footprint(Rod(4, 1), Position(4, 4.85, 1))

    def test_a_footprint_past_the_slack_is_rejected(self) -> None:
        assert _nonsquare_round_footprint(Disc(4), Position(4, 5, 0))

    def test_a_non_round_shape_is_never_subject_to_this_check(self) -> None:
        # A Footprint of the same non-square proportions is fine: this
        # check only ever applies to a Disc/Rod reading in the first place.
        assert not _nonsquare_round_footprint(Footprint(4, 8), Position(4, 8, 0))


class TestAxisDeltas:
    """``Ell`` states four fields, but only two are plan-view lengths a
    bounding box can check without guessing a unit conversion -- see
    ``_axis_deltas``'s own docstring for why ``face_height`` is excluded."""

    EXTENTS = Position(2, 1, 1)

    def test_face_width_is_checked_against_the_same_axis_as_width(self) -> None:
        # 5 is unmistakably not width, depth, or height, so its presence
        # among the pairs can only be the (face_width, x) one.
        deltas = _axis_deltas(Ell(2, 1, 5, 1), self.EXTENTS)
        assert (5, 2.0) in deltas

    def test_face_height_is_not_checked_against_any_axis(self) -> None:
        deltas = _axis_deltas(Ell(2, 1, 2, 9), self.EXTENTS)
        assert 9 not in (derived for derived, _measured in deltas)
        assert len(deltas) == 3


class TestReadersGuardAgainstAnEmptyRun:
    """Private dimension readers return no shape for empty input."""

    def test_read_disc_returns_none_for_an_empty_run(self):
        assert _read_disc(()) is None

    def test_read_rod_returns_none_for_an_empty_run(self):
        assert _read_rod(()) is None

    def test_read_length_returns_none_for_an_empty_run(self):
        assert _read_length(()) is None
