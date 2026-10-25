"""Size and variant selection for convenience helpers."""

import pytest

from bricklayer import (
    Box,
    Color,
    Element,
    Footprint,
    FrameVariant,
    InvalidPartError,
    PaneVariant,
)
from bricklayer.construction._factories import PartOptions


@pytest.fixture
def options():
    return PartOptions(
        "Brick",
        Box,
        ("3001", "3004"),
    )


def test_table_rejects_wrong_shape_kind():
    with pytest.raises(TypeError, match="Footprint"):
        PartOptions("Plate", Footprint, {"3001": None})


def test_table_rejects_wrong_variant_kind():
    with pytest.raises(ValueError, match="variant"):
        PartOptions("Frame", Box, {"60592": PaneVariant.SOLID}, FrameVariant)


def test_lookup_returns_none_for_unavailable_choice(options):
    assert options.get(Box(7, 7, 7)) is None


def test_lookup_selects_a_size(options):
    assert options.find(Box(4, 2, 1)).ldraw_id == "3001"
    assert options.find(Box(2, 1, 1)).ldraw_id == "3004"


def test_lookup_returns_a_catalog_spec():
    options = PartOptions("Brick", Box, ("3001",))
    spec = options.find(Box(4, 2, 1))
    assert spec == Element("3001", Color.RED).spec


def test_invalid_size_suggests_transposed_dimensions(options):
    with pytest.raises(InvalidPartError, match="did you mean 4x2x1"):
        options.find(Box(2, 4, 1))


def test_assembly_variant_suggests_its_sizes():
    options = PartOptions(
        "Frame",
        Box,
        {"60592": None, "60596": None, "90195": FrameVariant.ARCHED},
        FrameVariant,
    )
    assert options.find(Box(2, 1, 2), FrameVariant.ARCHED).ldraw_id == "90195"
    with pytest.raises(
        InvalidPartError, match="closest available Arched Frame dimensions"
    ):
        options.find(Box(4, 1, 6), FrameVariant.ARCHED)


@pytest.mark.parametrize("shape", [Box(0, 1, 1), Box(-1, 1, 1)])
def test_nonpositive_sizes_are_rejected(shape, options):
    with pytest.raises(InvalidPartError, match="positive"):
        options.find(shape)
