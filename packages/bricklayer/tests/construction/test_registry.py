"""The documented factory argument choices produce usable components."""

import pytest

from bricklayer import brick, inverted_slope, plate, slope, tile
from bricklayer.construction.registry import (
    COMPONENT_FACTORIES,
    valid_part_kwarg_combos,
)


def test_every_documented_argument_combination_builds():
    for factory in COMPONENT_FACTORIES:
        for kwargs in valid_part_kwarg_combos(factory) or ((),):
            factory(**dict(kwargs))


@pytest.mark.parametrize(
    ("factory", "fields"),
    [
        (brick, ("width", "depth", "height")),
        (slope, ("width", "depth", "height")),
        (inverted_slope, ("width", "depth", "height")),
        (plate, ("width", "depth")),
        (tile, ("width", "depth")),
    ],
)
def test_single_part_factory_choices_are_size_only(factory, fields):
    combos = valid_part_kwarg_combos(factory)
    assert combos
    assert all(tuple(dict(combo)) == fields for combo in combos)
