"""BrickLayer documentation.

Build and validate LEGO models with catalog parts and reusable assemblies.

## Basic workflow

Find parts with `search_parts`, construct `Element(part_id, color)`, and place
with `LegoBuild.add`, `stack`, or `connect`. Each returns a `Placement` immediately.
Pass that placement (or its registered name) to subsequent calls.

```python
import bricklayer as bl

assembly = bl.LegoBuild()
base = assembly.add(bl.Element("3001", bl.Color.RED), name="base")
assembly.stack(bl.Element("3001", bl.Color.BLUE), on=base)

model = bl.LegoBuild()
model.add(assembly, (0, 0, 0), name="tower")
assert model.is_valid()
assert model.is_connected()
```

`is_valid()` means no collisions or floating parts; `is_connected()` means all
parts join through compatible connectors. A supported model can be valid while
containing several disconnected assemblies. Inspect `colliding_placements`,
`floating_placements`, and `connected_components` to diagnose problems.
Motion annotations do not change `is_valid()`: opt into `check_motion()` to
sample their ranges for collisions, floating, and connector disengagement.
"""

from . import construction, docs, geometry, io, modeling, parts
from .colors import Color, Finish
from .construction import *
from .docs import *
from .geometry import *
from .io import *
from .ldraw import get_connector_type
from .modeling import *
from .parts import *

__all__ = (
    ["Color", "Finish", "get_connector_type"]
    + io.__all__
    + parts.__all__
    + construction.__all__
    + docs.__all__
    + geometry.__all__
    + modeling.__all__
)
