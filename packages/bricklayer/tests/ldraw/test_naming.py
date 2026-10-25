from fractions import Fraction

import pytest

from bricklayer.ldraw.naming import Chirality, TaxonomyRecord, parse_description


@pytest.mark.parametrize(
    ("desc", "expected"),
    [
        (
            "Brick  1 x  1",
            TaxonomyRecord(
                "Brick  1 x  1",
                "Brick",
                None,
                (Fraction(1), Fraction(1)),
                None,
                None,
            ),
        ),
        (
            "Slope Brick 18  4 x  1",
            TaxonomyRecord(
                "Slope Brick 18  4 x  1",
                "Slope",
                "Brick 18",
                (Fraction(4), Fraction(1)),
                None,
                None,
            ),
        ),
        (
            "Tile  1 x  1 with Groove",
            TaxonomyRecord(
                "Tile  1 x  1 with Groove",
                "Tile",
                None,
                (Fraction(1), Fraction(1)),
                "with Groove",
                None,
            ),
        ),
        (
            "Brick  1 x  1 Round with Hollow Stud",
            TaxonomyRecord(
                "Brick  1 x  1 Round with Hollow Stud",
                "Brick",
                "Round",
                (Fraction(1), Fraction(1)),
                "with Hollow Stud",
                None,
            ),
        ),
        (
            "Technic Beam  1",
            TaxonomyRecord(
                "Technic Beam  1", "Technic", "Beam", (Fraction(1),), None, None
            ),
        ),
        (
            "Technic Pin  1/2",
            TaxonomyRecord(
                "Technic Pin  1/2", "Technic", "Pin", (Fraction(1, 2),), None, None
            ),
        ),
        (
            "Technic Axle  2 Notched",
            TaxonomyRecord(
                "Technic Axle  2 Notched",
                "Technic",
                "Axle Notched",
                (Fraction(2),),
                None,
                None,
            ),
        ),
        (
            "Door  1 x  3 x  1 Left",
            TaxonomyRecord(
                "Door  1 x  3 x  1 Left",
                "Door",
                None,
                (Fraction(1), Fraction(3), Fraction(1)),
                None,
                Chirality.LEFT,
            ),
        ),
        (
            "Minifig Head",
            TaxonomyRecord("Minifig Head", "Minifig", "Head", None, None, None),
        ),
        (
            "Animal Bird Songbird",
            TaxonomyRecord(
                "Animal Bird Songbird", "Animal", "Bird Songbird", None, None, None
            ),
        ),
        (
            "Technic Pin with Friction and Slots",
            TaxonomyRecord(
                "Technic Pin with Friction and Slots",
                "Technic",
                "Pin",
                None,
                "with Friction and Slots",
                None,
            ),
        ),
        (
            "Minifig Hair with Large High Bun",
            TaxonomyRecord(
                "Minifig Hair with Large High Bun",
                "Minifig",
                "Hair",
                None,
                "with Large High Bun",
                None,
            ),
        ),
        (
            # A capitalised "With" opens the features clause too.
            "Plate  2 x  2 With Raised Grilles",
            TaxonomyRecord(
                "Plate  2 x  2 With Raised Grilles",
                "Plate",
                None,
                (Fraction(2), Fraction(2)),
                "With Raised Grilles",
                None,
            ),
        ),
        (
            "Cone 4 x  4 x  2 Hollow Without Studs",
            TaxonomyRecord(
                "Cone 4 x  4 x  2 Hollow Without Studs",
                "Cone",
                "Hollow",
                (Fraction(4), Fraction(4), Fraction(2)),
                "Without Studs",
                None,
            ),
        ),
        (
            "Brick 13.667 x 13.667 Round Fabuland Hollowed",
            TaxonomyRecord(
                "Brick 13.667 x 13.667 Round Fabuland Hollowed",
                "Brick",
                "Round Fabuland Hollowed",
                (Fraction("13.667"), Fraction("13.667")),
                None,
                None,
            ),
        ),
        (
            # A trailing unit, not a dimension run: 54821's real name. A bare
            # "16.5" followed by "mm" must not be read as a stud measurement.
            "Technic Bionicle Ball 16.5 mm",
            TaxonomyRecord(
                "Technic Bionicle Ball 16.5 mm",
                "Technic",
                "Bionicle Ball 16.5 mm",
                None,
                None,
                None,
            ),
        ),
    ],
)
def test_parses_real_ldraw_descriptions(desc: str, expected: TaxonomyRecord) -> None:
    assert parse_description(desc) == expected


@pytest.mark.parametrize(
    "desc",
    [
        # Real LDraw tyre descriptions using "NN.N/ NN" aspect-ratio notation
        # (18977, 92409, 42611, 51011, u9131, 2696): a decimal numerator makes
        # `Fraction` raise if the run is read as a stud dimension.
        "Tyre 11.2/ 28 x 17.6 Intermediate",
        "Tyre  6.4/ 75 x  8 Shallow Offset Tread with Centre Band",
        "Tyre  6.4/ 75 x  8 Shallow Offset Tread",
        "Tyre  7.2/ 45 x 8.8",
        "Tyre 12.7/ 51 x 30",
    ],
)
def test_an_aspect_ratio_tyre_size_is_not_read_as_a_dimension(desc: str) -> None:
    parsed = parse_description(desc)
    assert parsed.category == "Tyre"
    assert parsed.dimensions is None


@pytest.mark.parametrize(
    "marker", ["~Moved to 3665a", "=Glass for Window  1 x  4 x  3 Opening"]
)
def test_strips_leading_marker_from_name(marker: str) -> None:
    assert not parse_description(marker).name.startswith(("~", "="))


@pytest.mark.parametrize(
    ("desc", "expected"),
    [
        ("Brick  1 x  1", (Fraction(1), Fraction(1))),
        ("Slope Brick 18  4 x  1", (Fraction(4), Fraction(1))),
        ("Glass for Window  1 x  4 x  3", (Fraction(1), Fraction(4), Fraction(3))),
        ("Technic Beam  5 x  0.5", (Fraction(5), Fraction(1, 2))),
        ("Technic Pin  1/2", (Fraction(1, 2),)),
        (
            "Brick 13.667 x 13.667 Round Fabuland Hollowed",
            (Fraction("13.667"), Fraction("13.667")),
        ),
        ("Minifig Head", None),
        ("Technic Pin", None),
    ],
)
def test_dimensions_come_back_in_ldraw_order(desc, expected):
    assert parse_description(desc).dimensions == expected


def test_a_bracket_reads_both_of_its_dimension_runs():
    """ "Bracket  1 x  2 -  1 x  2 Down" is two runs, not one."""
    parsed = parse_description("Bracket  1 x  2 -  1 x  2 Down")
    assert parsed.dimensions == (
        Fraction(1),
        Fraction(2),
        Fraction(1),
        Fraction(2),
    )


def test_a_brackets_trailing_word_still_reaches_the_subcategory():
    parsed = parse_description("Bracket  1 x  2 -  2 x  2 Up")
    # Both runs are consumed as dimensions, so "Up" is all the subcategory is --
    # a containment check would also pass on the whole tail "- 2 x 2 Up".
    assert parsed.subcategory == "Up"


@pytest.mark.parametrize(
    "desc",
    [
        # A hair style swept left, not a handed part.
        "Minifig Hair Swept Left Tousled",
        # A staircase turning left, not a handed part.
        "Staircase  6 x  6 x  4 Quarter Turn Left Up Going",
        # A left hair parting, stated in the "with ..." clause itself.
        "Minifig Hair Short Combed Sideways with Left Parting",
    ],
)
def test_a_mid_name_left_right_word_is_not_chirality(desc: str) -> None:
    """Left/Right only means handedness in the trailing slot -- after any
    dimension run and before any "with ..." clause. Elsewhere it is
    descriptive and must not be read as chirality, nor cut out of the name."""
    parsed = parse_description(desc)
    assert parsed.chirality is None
    assert "Left" in (parsed.subcategory or "") + (parsed.features or "")


@pytest.mark.parametrize(
    ("desc", "chirality", "features"),
    [
        ("Wing  2 x  4 Right without Chamfer", Chirality.RIGHT, "without Chamfer"),
        (
            "Door  1 x  3 x  4 Left with Hollow Hinge",
            Chirality.LEFT,
            "with Hollow Hinge",
        ),
    ],
)
def test_a_trailing_chirality_word_is_read_even_before_a_features_clause(
    desc: str, chirality: Chirality, features: str
) -> None:
    """A real chirality word sits right after the dimension run, before any
    "with ..."/"without ..." clause -- not necessarily at the very end of the
    description."""
    parsed = parse_description(desc)
    assert parsed.chirality == chirality
    assert parsed.subcategory is None
    assert parsed.features == features
