"""Part identities, metadata, and catalog membership queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache

from ..geometry.linalg import Axis
from ..ldraw import partdata
from ..ldraw.naming import Chirality
from ..ldraw.partdata import TaxonomyRecord
from .derivation import derived_shape
from .shape import PartShape

#: The plane a handed part's counterpart is reflected across: "Left" and
#: "Right" name the two sides of the left/right plane, whatever axis a given
#: reflection uses.
HANDEDNESS_AXIS = Axis.X


class InvalidPartError(ValueError):
    """Raised when a part is named that does not exist: an uncatalogued LDraw
    id, out of :class:`PartSpec`, or attributes no part carries, out of
    a convenience factory."""


@dataclass(frozen=True)
class PartSpec:
    """A catalog part identified by its LDraw id; unknown ids are rejected.

    Properties describe its LDraw name and nominal shape. `subcategory`, `features`,
    `chirality`, and `shape` can be `None` when that information is absent.
    Parts without connectors can rest on the ground but cannot attach to others.
    """

    ldraw_id: str

    #: The part's LDraw description, parsed -- resolved by :meth:`__post_init__`
    #: and stored, so no property here re-looks it up. Out of ``__init__``,
    #: ``__eq__`` and ``__hash__``: two specs are the same part when their ids
    #: match, and the row is a function of the id.
    _ldraw: TaxonomyRecord = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        """Resolve the part's LDraw description; reject an uncatalogued id."""
        record = partdata.taxonomy(self.ldraw_id)
        if record is None or not part_exists(self.ldraw_id):
            raise InvalidPartError(f"{self.ldraw_id!r} is not a catalogued LDraw part")
        object.__setattr__(self, "_ldraw", record)

    @property
    def name(self) -> str:
        """The part's LDraw name, e.g. "Brick  1 x  1"."""
        return self._ldraw.name

    @property
    def category(self) -> str:
        """The part category, e.g. "Brick" or "Minifig"."""
        return self._ldraw.category

    @property
    def subcategory(self) -> str | None:
        """The subtype around the name's dimensions, e.g. "Round Half Circle"."""
        return self._ldraw.subcategory

    @property
    def features(self) -> str | None:
        """The part's ``with ...`` clause, e.g. "with Groove"."""
        return self._ldraw.features

    @property
    def chirality(self) -> Chirality | None:
        """The part's handedness, or ``None`` if achiral."""
        return self._ldraw.chirality

    @property
    def mirrored(self) -> PartSpec:
        """This part's mirror image: the same part in the opposite :attr:`chirality`.

        ``spec.mirrored is spec`` when there is none -- the part is achiral, or
        the catalog holds only its one hand.
        """
        counterpart = partdata.mirrored_part_id(self.ldraw_id)
        return self if counterpart is None else PartSpec(counterpart)

    @property
    def shape(self) -> PartShape | None:
        """Nominal dimensions, or `None` if no reliable shape is known.

        Use the element's bounding box when you need its measured physical extent.
        """
        return _shape_of(self.ldraw_id)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.ldraw_id}: {self.name})"


# Pure in the part's own LDraw data, so never invalidated.
_shape_of = cache(derived_shape)


@cache
def all_parts() -> tuple[PartSpec, ...]:
    """Every catalogued part as a :class:`PartSpec`, in id order."""
    return tuple(PartSpec(p) for p in sorted(partdata.part_ids()))


def part_exists(part_id: str) -> bool:
    """Whether the catalog holds the LDraw part ``part_id``.

    The non-raising counterpart to ``PartSpec(part_id)``.
    """
    return part_id in partdata.part_ids()
