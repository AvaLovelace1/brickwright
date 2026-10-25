"""Shared fixtures for the LDraw writer tests."""

import inspect
from collections.abc import Callable

import pytest

from bricklayer import (
    Color,
    Element,
    LegoBuild,
    minifig,
)
from bricklayer.construction._factories import PartOptions
from bricklayer.construction.registry import valid_part_kwarg_combos


@pytest.fixture
def components_in():
    """Every documented factory choice or part in a helper table."""

    def _components_in(
        factory: Callable[..., Element | LegoBuild] | PartOptions,
        color: Color = Color.WHITE,
    ) -> tuple[Element | LegoBuild, ...]:
        if isinstance(factory, PartOptions):
            return tuple(Element(spec.ldraw_id, color) for spec in factory.specs)
        color_arg_names = [
            name
            for name, _ in inspect.signature(factory).parameters.items()
            if name.endswith("color")
        ]
        result = [
            factory(**dict(kwargs), **{k: color for k in color_arg_names})
            for kwargs in valid_part_kwarg_combos(factory) or []
        ]
        return tuple(result)

    return _components_in


@pytest.fixture
def minifig_showcase():
    """The showcase minifig factory: ``minifig_showcase(color=...) -> list`` (one
    assembly per sample accessory or lower-body part).

    Pass ``color`` to build every figure in that single color; it defaults to
    the distinct per-part colors."""

    def _minifig_showcase(color: Color | None = None) -> list[LegoBuild]:
        figures = [_figure(color=color, headwear_id=hv) for hv in ("61183", "3878")]
        figures += [_figure(color=color, bodywear_id=bv) for bv in ("2587", "2526")]
        figures += [
            _figure(color=color, footwear_id=fv) for fv in ("11253", "59275a", "30284")
        ]
        figures += [_figure(color=color, legs_id=lv) for lv in ("41879a", "36036")]
        return figures

    def _figure(
        *,
        color: Color | None = None,
        legs_id: str | None = None,
        headwear_id: str | None = None,
        bodywear_id: str | None = None,
        footwear_id: str | None = None,
    ) -> LegoBuild:
        """A minifig assembly. When ``color`` is given every body part uses it;
        otherwise the parts take their distinct default colors."""
        return minifig(
            skin_color=color or Color.YELLOW,
            torso_color=color or Color.RED,
            arm_color=color or Color.RED,
            leg_color=color or Color.BLUE,
            legs_id=legs_id,
            headwear_id=headwear_id,
            headwear_color=color or Color.DARK_PURPLE,
            bodywear_id=bodywear_id,
            bodywear_color=color or Color.DARK_BLUISH_GRAY,
            footwear_id=footwear_id,
            footwear_color=color or Color.DARK_BROWN,
        )

    return _minifig_showcase
