"""The built-in construction factories and their documented argument choices."""

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

from . import angled, architecture, basic, minifigure
from ._factories import PartOptions

COMPONENT_FACTORIES: Mapping[Any, PartOptions | Callable] = MappingProxyType(
    {
        factory: options
        for module in (basic, angled, architecture, minifigure)
        for factory, options in module._FACTORIES
    }
)


def valid_part_kwarg_combos(
    factory: Callable,
) -> tuple[tuple[tuple[str, Any], ...], ...] | None:
    """The documented size and variant choices accepted by a convenience factory."""
    options = COMPONENT_FACTORIES[factory]
    if not isinstance(options, PartOptions):
        return options()
    return tuple(
        tuple(spec.shape.field_values.items())
        for spec in options.specs
        if spec.shape is not None
    )
