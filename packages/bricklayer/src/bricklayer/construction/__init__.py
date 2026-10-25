"""Component factories.

Optional helpers select basic parts by size or assemble windows, doors, and
minifigures. They return ordinary elements or models. Size helpers accept only
the generated argument combinations listed below; rotate a supported size when
needed. Use `Element(part_id, color)` for other catalog parts.
"""

from .angled import *
from .architecture import *
from .basic import *
from .fill import fill_box, fill_inverted_slope, fill_slope
from .minifigure import *
from .registry import COMPONENT_FACTORIES
from .variants import *

COMPONENT_TYPES = [MinifigPose]
VARIANT_ENUMS = [FrameVariant, PaneVariant, DoorVariant]
CONSTRUCTION_HELPERS = [fill_box, fill_inverted_slope, fill_slope]

__all__ = (
    [obj.__name__ for obj in COMPONENT_TYPES]
    + [obj.__name__ for obj in VARIANT_ENUMS]
    + [obj.__name__ for obj in COMPONENT_FACTORIES]
    + [obj.__name__ for obj in CONSTRUCTION_HELPERS]
)
