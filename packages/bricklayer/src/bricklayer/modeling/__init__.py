"""Building a LEGO model.

Nested models are held by reference: editing a shared sub-model changes every
assembly that contains it.
`copy()` shares these sub-models; `deepcopy()` isolates them.

Relative placement reads the reference's geometry at call time. Later changes
to the reference do not move already placed parts.

Names can be paths: `model.named(["tower", "roof"])` returns the roof placement
in the outer model's coordinate frame. Returned placements can be used with
`relative_to` or `on`. Remove a placement and place another to change its pose.

Placement methods append by default; `index` inserts before a top-level position
(negative indices count from the end).
"""

from . import articulation, build, transforms
from .articulation import *
from .build import *
from .placement import Placement
from .transforms import *

__all__ = articulation.__all__ + build.__all__ + ["Placement"] + transforms.__all__
