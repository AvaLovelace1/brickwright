"""Exploring the catalog.

Use `search_parts` to find a part, then build `Element(spec.ldraw_id, color)`.
Keyword terms all have to match whole words; filters require exact property values.
Common parts rank higher using set counts from Rebrickable's catalogue.

```python
import bricklayer as bl

# Keywords may match "door" in any default text field; category is an exact filter.
doors = bl.search_parts("door", category="Door", limit=4)
assert all(spec.category == "Door" for spec in doors)
plates = bl.search_parts(category="Plate", shape=bl.Footprint(6, 2), limit=4)
assert all(spec.shape == bl.Footprint(6, 2) for spec in plates)
```

`PartSpec` describes a catalog part; unknown ids are rejected. Shape information
can be absent: use an element's measured bounding box for physical dimensions.

### Dimensions and names

API dimensions are **width-first** (x, then y); slopes run along their depth (y).
LDraw names are preserved verbatim and their dimension order varies by category.
For example, `Plate  2 x  6` has `Footprint(6, 2)`, but `Wing  2 x  6 Left`
has `Footprint(2, 6)`. Use `spec.shape` or measured geometry rather than inferring
API dimensions from a name. LEGO's "Slope 45 2 x 3" is a 3x2 slope in the API.
"""

from ..ldraw.naming import Chirality
from .catalog import InvalidPartError, PartSpec, part_exists
from .element import Element
from .search import search_parts
from .shape import Box, Disc, Ell, Footprint, Length, Pane, PartShape, Rod

CATALOG_TYPES = [
    PartSpec,
    PartShape,
    Box,
    Disc,
    Footprint,
    Pane,
    Ell,
    Length,
    Rod,
    Chirality,
]

DISCOVERY = [search_parts, part_exists]

__all__ = (
    ["Element", "InvalidPartError"]
    + [obj.__name__ for obj in CATALOG_TYPES]
    + [obj.__name__ for obj in DISCOVERY]
)
