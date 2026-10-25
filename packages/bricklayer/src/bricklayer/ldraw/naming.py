"""Parse an official LDraw part description into its structural zones.

LDraw descriptions follow a loose grammar::

    Minifig  Head
    Technic  Beam    9
    Brick            2 x 2  Round with Pin Holes
    └catgry┘ └sub──┘ └dims┘ └───── features ────┘

Dimensions are returned **in LDraw order** (depth-first). Transposing them into
BrickLayer's width-first order is the caller's job.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from .._mixins import DocumentedEnum

#: LDraw's leading-character markers. In order: moved or obsolete, unofficial,
#: third-party, and an alias wrapper. None of them is a part you build with.
LDRAW_MARKERS = "~_|="

# A dimension run: "2 x 4", "1 x 3 x 1", a bare "9", a fraction "1/2", a decimal "13.667".
_NUMBER = r"\d+(?:\.\d+)?(?:\s*/\s*\d+)?"
_RUN = rf"{_NUMBER}(?:\s+x\s+{_NUMBER})*"
# A bracket part states two runs joined by "-", e.g. "1 x  2 -  1 x  2 Down".
_BRACKET_DIMENSIONS = re.compile(
    rf"(?<![\w.]){_RUN}\s*-\s*{_RUN}(?![\w.])", re.IGNORECASE
)
# Requires at least one "x" join, so a bare number elsewhere in the name (e.g. the "18"
# in "Slope Brick 18  4 x  1") isn't mistaken for the dimension run.
_MULTI_DIMENSIONS = re.compile(
    rf"(?<![\w.]){_NUMBER}(?:\s+x\s+{_NUMBER})+(?![\w.])", re.IGNORECASE
)
# A lone number is not a dimension when it states a unit instead, e.g. "16.5 mm"
# (54821's "Technic Bionicle Ball 16.5 mm") -- the only other numeric
# convention an LDraw description uses besides a stud/brick dimension run.
_SINGLE_DIMENSION = re.compile(
    rf"(?<![\w.]){_NUMBER}(?![\w.])(?!\s*mm\b)", re.IGNORECASE
)
# The joins inside a matched run, and the trailing ``with …`` clause.
_RUN_JOIN = re.compile(r"\s*-\s*")
_DIMENSION_JOIN = re.compile(r"\s+x\s+", re.IGNORECASE)
_FEATURES = re.compile(r"\bwith(?:out)?\b", re.IGNORECASE)


class Chirality(DocumentedEnum):
    """The handedness of a chiral part."""

    LEFT = "Left-handed variant."
    RIGHT = "Right-handed variant."

    @property
    def opposite(self) -> Chirality:
        """The other handedness."""
        return Chirality.LEFT if self is Chirality.RIGHT else Chirality.RIGHT


#: The words that name a handedness, in the trailing slot.
_CHIRALITY_WORDS = {handed.display_name: handed for handed in Chirality}

#: That same word where :func:`_pop_trailing_chirality` finds it: last, ahead
#: of any ``with ...`` clause.
_TRAILING_CHIRALITY = re.compile(rf"(?:{'|'.join(_CHIRALITY_WORDS)})(\s*)$")


@dataclass(frozen=True)
class TaxonomyRecord:
    """One part's LDraw description, parsed into its naming zones.

    ``chirality`` is ``None`` for an achiral part.
    """

    name: str
    category: str
    subcategory: str | None
    dimensions: tuple[Fraction, ...] | None
    features: str | None
    chirality: Chirality | None


def part_name(desc: str) -> str:
    """An LDraw description as the bare name a part is known by: leading
    markers dropped, padding trimmed."""
    return desc.lstrip(LDRAW_MARKERS).strip()


def mirrored_description(record: TaxonomyRecord) -> str | None:
    """``record``'s name with its handedness word swapped, or ``None`` if the
    part is achiral.

    Rewritten in place: LDraw pads its dimension runs ("Wing  2 x  3 Left")
    and a counterpart is looked up by its exact description.
    """
    if record.chirality is None:
        return None
    match = _FEATURES.search(record.name)
    cut = len(record.name) if match is None else match.start()
    word = record.chirality.opposite.display_name
    head = _TRAILING_CHIRALITY.sub(lambda m: word + m[1], record.name[:cut])
    return head + record.name[cut:]


def parse_description(desc: str) -> TaxonomyRecord:
    """Split an LDraw part description into its zones."""
    name = part_name(desc)
    body, features = _split_on_features(name)
    head, dimensions, tail = _split_on_dimensions(body)

    words = head.split()
    category = words[0] if words else ""
    subcategory_words, chirality = _pop_trailing_chirality([*words[1:], *tail.split()])
    subcategory = " ".join(subcategory_words) or None
    return TaxonomyRecord(name, category, subcategory, dimensions, features, chirality)


def _pop_trailing_chirality(words: list[str]) -> tuple[list[str], Chirality | None]:
    """A standalone Left/Right word means handedness only in the trailing slot
    -- after any dimension run and before any ``with …`` clause, e.g.
    "Door  1 x  3 x  1 Left" or "Wing  2 x  4 Right without Chamfer". The same
    word earlier in a name (hair swept left, a staircase turning left) is
    descriptive, not a handedness, and is left in place.
    """
    if words and (chirality := _CHIRALITY_WORDS.get(words[-1])):
        return words[:-1], chirality
    return words, None


def _split_on_dimensions(body: str) -> tuple[str, tuple[Fraction, ...] | None, str]:
    """Split into (text before dimensions, dimensions, text after).

    A bracket part (e.g. "Bracket  1 x  2 -  1 x  2 Down") states two runs
    joined by "-"; both are matched and concatenated into one tuple.
    """
    match = (
        _BRACKET_DIMENSIONS.search(body)
        or _MULTI_DIMENSIONS.search(body)
        or _SINGLE_DIMENSION.search(body)
    )
    if match is None:
        return body, None, ""
    try:
        numbers = tuple(
            Fraction(n.replace(" ", ""))
            for run in _RUN_JOIN.split(match.group())
            for n in _DIMENSION_JOIN.split(run)
        )
    except ValueError:
        # A tyre's "NN.N/ NN" aspect-ratio notation (e.g. "11.2/ 28 x 17.6")
        # matches the same shape as a dimension run, but its decimal numerator
        # makes Fraction reject it: it states a tyre size, not a stud
        # dimension, so it is read as ordinary descriptive text instead.
        return body, None, ""
    return body[: match.start()].strip(), numbers, body[match.end() :].strip()


def _split_on_features(body: str) -> tuple[str, str | None]:
    """Split off the trailing ``with …`` clause, before dimensions are located.

    Done before dimension-splitting so a dimension-less description's ``with …``
    text (e.g. "Technic Pin with Friction and Slots") isn't swallowed into the
    subcategory: dimension-splitting would otherwise see the whole remainder as
    trailing text with nowhere else to send it.
    """
    match = _FEATURES.search(body)
    if match is None:
        return body, None
    return body[: match.start()].strip(), body[match.start() :].strip() or None
