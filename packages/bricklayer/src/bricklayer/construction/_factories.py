"""Private size and variant lookup for convenience factories."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cached_property

from ..colors import Color
from ..ldraw.colors import LDrawColor
from ..parts.catalog import InvalidPartError, PartSpec
from ..parts.element import Element
from ..parts.shape import PartShape, shape_sort_key
from .variants import PartVariant


@dataclass(eq=False)
class PartOptions:
    """The choices one factory makes, independent of catalog identity."""

    display_name: str
    shape_type: type[PartShape]
    parts: Mapping[str, PartVariant | None] | Iterable[str]
    variant_enum: type[PartVariant] | None = None

    def __post_init__(self) -> None:
        self.parts = (
            dict(self.parts)
            if isinstance(self.parts, Mapping)
            else dict.fromkeys(self.parts)
        )
        seen = set()
        for spec in self.specs:
            if not isinstance(spec.shape, self.shape_type):
                raise TypeError(
                    f"{spec.name} does not have a {self.shape_type.__name__} shape"
                )
            variant = self.variant(spec)
            if variant is not None and type(variant) is not self.variant_enum:
                raise ValueError(f"{variant!r} is not a {self.display_name} variant")
            key = (spec.shape, variant)
            if key in seen:
                raise ValueError(f"duplicate {self.display_name} option: {key}")
            seen.add(key)

    @cached_property
    def specs(self) -> tuple[PartSpec, ...]:
        return tuple(
            sorted(
                (PartSpec(pid) for pid in self.parts),
                key=lambda s: (
                    *shape_sort_key(s.shape),
                    "" if (variant := self.variant(s)) is None else variant.name,
                ),
            )
        )

    def variant(self, spec: PartSpec) -> PartVariant | None:
        assert isinstance(self.parts, Mapping)
        return self.parts[spec.ldraw_id]

    def get(
        self, shape: PartShape, variant: PartVariant | None = None
    ) -> PartSpec | None:
        return next(
            (s for s in self.specs if s.shape == shape and self.variant(s) == variant),
            None,
        )

    def element(
        self,
        shape: PartShape,
        color: Color | LDrawColor,
        variant: PartVariant | None = None,
    ) -> Element:
        return Element(self.find(shape, variant).ldraw_id, color)

    def find(self, shape: PartShape, variant: PartVariant | None = None) -> PartSpec:
        spec = self.get(shape, variant)
        if spec is not None:
            return spec
        label = self.label(shape)
        if not isinstance(shape, self.shape_type):
            raise InvalidPartError(
                f"a {self.display_name} is not {type(shape).__name__}-shaped"
            )
        if any(d <= 0 for d in shape.dimensions):
            raise InvalidPartError(f"dimensions must be positive, got {shape.label}")
        sizes = {s.shape for s in self.specs}
        if shape not in sizes:
            swapped = shape.transpose()
            hint = (
                f" -- did you mean {swapped.label}? (dims are width-first; rotate parts if needed)"
                if swapped != shape and swapped in sizes
                else ""
            )
            raise InvalidPartError(
                f"{shape.label} is not a real {self.display_name}{hint}; "
                f"closest available dimensions: {self._nearest(shape)}"
            )
        nearest = self._nearest(shape, variant) if variant is not None else ""
        if nearest and variant is not None:
            details = (
                f"closest available {variant.display_name} {self.display_name} "
                f"dimensions: {nearest}"
            )
        else:
            available = sorted(
                "None" if (choice := self.variant(s)) is None else choice.display_name
                for s in self.specs
                if s.shape == shape
            )
            details = f"available variants: {available}"
        shown = "None" if variant is None else variant.display_name
        raise InvalidPartError(
            f"{shown!r} is not an available variant for a {label}; {details}"
        )

    def label(self, shape: PartShape) -> str:
        return f"{shape.label} {self.display_name}"

    def _nearest(self, target: PartShape, variant: PartVariant | None = None) -> str:
        shapes = dict.fromkeys(
            s.shape for s in self.specs if variant is None or self.variant(s) is variant
        )

        def distance(shape: PartShape) -> float:
            return min(
                sum((float(a) - float(b)) ** 2 for a, b in zip(target.dimensions, dims))
                for dims in (shape.dimensions, shape.transpose().dimensions)
            )

        return ", ".join(
            s.label
            for s in sorted((s for s in shapes if s is not None), key=distance)[:5]
        )
