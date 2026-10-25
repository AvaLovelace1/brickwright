"""Creating LEGO components.

A part is a LEGO piece; an `Element` adds its color. Construct any catalogued part
with `Element(part_id, color)`, including specialized parts without a size helper.
A `LegoBuild` groups elements into a reusable assembly.

```python
import bricklayer as bl

ladder = bl.Element("4175", bl.Color.RED)
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache

from ..colors import Color
from ..geometry import Connector, LegoGeometry, Position
from ..geometry.base import alignment_box_of
from ..ldraw import partdata
from ..ldraw.colors import LDrawColor
from .catalog import PartSpec


@cache
def _alignment_box(ldraw_id: str) -> tuple[Position, Position]:
    record = partdata.record(ldraw_id)
    return alignment_box_of(record.connector_set, record.bounding_box)


@dataclass(frozen=True, slots=True)
class Element(LegoGeometry):
    """A catalogued part in a color, constructed as `Element(part_id, color)`.

    Elements are immutable; matching part ids and colors compare equal.
    """

    ldraw_id: str = field(metadata={"doc": "The part's LDraw id."})
    color: Color | LDrawColor = field(metadata={"doc": "The element's color."})

    def __post_init__(self) -> None:
        PartSpec(self.ldraw_id)

    @property
    def spec(self) -> PartSpec:
        """The part's catalog identity, resolved from its id."""
        return PartSpec(self.ldraw_id)

    @property
    def connectors(self) -> frozenset[Connector]:
        """Points where a connection can be made, in the local frame."""
        return partdata.record(self.ldraw_id).connector_set

    @property
    def bounding_box(self) -> tuple[Position, Position]:
        """Physically-measured `(min, max)` box in the local frame."""
        return partdata.record(self.ldraw_id).bounding_box

    @property
    def alignment_box(self) -> tuple[Position, Position]:  # ty: ignore[invalid-property-type-override] (never assigned; typeshed calls cached_property settable)
        """See :attr:`LegoGeometry.alignment_box`; cached per part."""
        return _alignment_box(self.ldraw_id)

    @property
    def mirrored(self) -> Element:
        """This element in its part's opposite hand, keeping its color.

        ``element.mirrored is element`` when its part has no mirror image (see
        :attr:`PartSpec.mirrored`).
        """
        spec = self.spec.mirrored
        return (
            self
            if spec.ldraw_id == self.ldraw_id
            else Element(spec.ldraw_id, self.color)
        )

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.spec.name}, {self.color.display_name})"
