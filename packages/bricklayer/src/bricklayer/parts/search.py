"""Finding a catalogued part by keyword.

Searchable fields are :class:`~.catalog.PartSpec`'s public properties typed
``str`` or ``str | None``, found by introspection.

Ranking is BM25 -- the standard lexical ranking function, via ``bm25s`` --
over one document per part, multiplied by a logarithm of how many LEGO sets
that part appears in. BM25 handles term weighting, saturation and name-length
normalization; the multiplier handles the one thing it cannot know, which is
that a builder reaches for a 2x4 brick far more often than for a variant with
a similar name.

A search with no terms at all skips BM25 entirely -- ``bm25s.get_scores([])``
raises ``IndexError`` -- and ranks the whole candidate set by the popularity
prior alone. That path exists for a filter-only call, which is how a caller
browses a whole category (``search_parts(category="Baseplate")``).
"""

from __future__ import annotations

import functools
import itertools
import re
from collections.abc import Iterable
from dataclasses import dataclass
from math import log10
from typing import TYPE_CHECKING, Any, get_type_hints

import numpy

from ..ldraw import partdata
from .catalog import PartSpec, all_parts

if TYPE_CHECKING:
    import bm25s

#: How hard popularity pushes. 0.5 spans 1.00x (a part in no catalogued set)
#: to 2.98x (the most common part there is). Raising it past ~1.0 starts to
#: swamp the text.
_ALPHA = 0.5

#: Fields a caller has to ask for by name; everything else is searched by
#: default. Derived fields repeat words of `name`, doubling their weight:
#: category and subcategory earn that (`axle` answers "Technic Axle 3"), but
#: `features` hurts ranking (`tree` answers a Palm Tree *Pattern* slope).
_OPT_IN_FIELDS = frozenset({"features"})

#: Whole words only -- "x" and single digits carry real meaning in a part
#: name, so tokenizing applies no stemming and no stopword removal.
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def search_parts(
    *terms: str,
    fields: str | Iterable[str] | None = None,
    limit: int = 20,
    **filters: Any,
) -> tuple[PartSpec, ...]:
    """Find catalog parts by keywords and exact property filters.

    All keyword terms must match whole words; phrases split into words.
    `fields` selects text fields: `name`, `category`, `subcategory` by default;
    `features` can be requested explicitly. Results favor common parts using
    Rebrickable set counts. With no keywords, rank by popularity alone.

    Filters accept any `PartSpec` property, e.g. `category="Tile"` or
    `shape=Box(4, 2, 1)`. Return at most `limit` results, best first.
    An unknown field/filter, empty `fields`, or negative `limit` raises `ValueError`.
    """
    if limit < 0:
        raise ValueError(f"limit must not be negative, got {limit}")
    field_set = _validated_fields(fields)
    _validate_filters(filters)
    cleaned = tuple(token for term in terms for token in _tokenize(term))
    if not cleaned:
        ranked: Iterable[PartSpec] = _by_popularity()
        if filters:
            ranked = (spec for spec in ranked if _matches_filters(spec, filters))
        return tuple(itertools.islice(ranked, limit))
    index = _index_for(field_set)
    scores = index.bm25.get_scores(list(cleaned))
    wanted = set(cleaned)
    matches = []
    # Only the documents BM25 scored above zero can survive the AND gate, so
    # the rest need never be looked at: IDF is strictly positive, so
    # a document that scores zero contains none of the terms, let alone all.
    for i in numpy.flatnonzero(scores).tolist():
        if not wanted <= index.doc_terms[i]:
            continue
        spec = index.specs[i]
        if filters and not _matches_filters(spec, filters):
            continue
        matches.append((scores[i] * _popularity_boost(spec.ldraw_id), spec))
    matches.sort(key=lambda pair: (-pair[0], pair[1].ldraw_id))
    return tuple(spec for _, spec in matches[:limit])


def searchable_fields(spec_type: type[PartSpec]) -> tuple[str, ...]:
    """Every public property of ``spec_type`` whose getter returns ``str`` or
    ``str | None`` -- the fields :func:`search_parts` can search by keyword.

    Structured fields such as ``shape`` are excluded by the ``str`` test. Every type :class:`PartSpec` names is importable at module
    scope, which is what lets these hints resolve at all.
    """
    found = []
    for name in _public_properties(spec_type):
        hints = get_type_hints(getattr(spec_type, name).fget)
        return_type = hints.get("return")
        if return_type is str or return_type == (str | None):
            found.append(name)
    return tuple(found)


def _public_properties(spec_type: type[PartSpec]) -> tuple[str, ...]:
    """Every public property ``spec_type`` exposes, text and structured alike
    -- the full introspected surface :func:`searchable_fields` narrows down
    and :func:`search_parts`'s ``**filters`` validates against."""
    found = []
    for name in dir(spec_type):
        if name.startswith("_"):
            continue
        attr = getattr(spec_type, name, None)
        if isinstance(attr, property) and attr.fget is not None:
            found.append(name)
    return tuple(sorted(found))


#: Every text field :class:`PartSpec` has, derived by introspection.
SEARCHABLE_FIELDS = searchable_fields(PartSpec)

#: Every field -- text and structured -- a filter can name. See
#: :func:`_public_properties`.
_FILTERABLE_FIELDS = _public_properties(PartSpec)

#: The fields a search corpus is built from when the caller names none --
#: every searchable field except the opt-in ones.
_DEFAULT_FIELDS = tuple(f for f in SEARCHABLE_FIELDS if f not in _OPT_IN_FIELDS)


def _validated_fields(fields: str | Iterable[str] | None) -> tuple[str, ...]:
    """``fields``, sorted (so equal sets share one cached index), or
    :data:`_DEFAULT_FIELDS` if ``None``.

    Raises:
        ValueError: naming what fields exist, if ``fields`` is empty or names
            anything outside :data:`SEARCHABLE_FIELDS`. An empty ``fields``
            would otherwise index an empty corpus and crash inside ``bm25s``.
    """
    if fields is None:
        return _DEFAULT_FIELDS
    field_tuple = (fields,) if isinstance(fields, str) else tuple(fields)
    if not field_tuple:
        raise _choose_from("fields names no searchable field", SEARCHABLE_FIELDS)
    for name in field_tuple:
        if name not in SEARCHABLE_FIELDS:
            raise _choose_from(f"{name!r} is not a searchable field", SEARCHABLE_FIELDS)
    return tuple(sorted(field_tuple))


def _validate_filters(filters: dict[str, Any]) -> None:
    """Raises ValueError naming the unknown filter and every valid field, if
    ``filters`` names anything outside :data:`_FILTERABLE_FIELDS`."""
    for name in filters:
        if name not in _FILTERABLE_FIELDS:
            raise _choose_from(
                f"{name!r} is not a filterable field", _FILTERABLE_FIELDS
            )


def _choose_from(complaint: str, options: Iterable[str]) -> ValueError:
    """The error for a field name this module will not accept: what is wrong,
    then every name that would have worked, sorted."""
    return ValueError(f"{complaint}; choose from {', '.join(sorted(options))}")


def _matches_filters(spec: PartSpec, filters: dict[str, Any]) -> bool:
    """Whether ``spec`` equals every named filter value (a plain loop: hot path)."""
    for name, value in filters.items():
        if getattr(spec, name) != value:
            return False
    return True


def _popularity_boost(part_id: str) -> float:
    """The multiplier BM25's score is scaled by: 1x for a part in no
    catalogued set, rising with `log10` of how many sets it is in."""
    return 1 + _ALPHA * log10(1 + partdata.popularity(part_id))


@dataclass(frozen=True)
class _Index:
    """One BM25 index over one field-set's documents, plus the per-document
    token sets the AND filter checks against -- a bag of words records no
    field provenance, so this is what lets ``fields=["category"]`` mean
    something despite everything being concatenated into one document."""

    specs: tuple[PartSpec, ...]
    bm25: bm25s.BM25
    doc_terms: tuple[frozenset[str], ...]


@functools.cache
def _by_popularity() -> tuple[PartSpec, ...]:
    """Every catalogued part, most-used first -- ordered once per process."""
    return tuple(
        sorted(
            all_parts(),
            key=lambda spec: (-partdata.popularity(spec.ldraw_id), spec.ldraw_id),
        )
    )


@functools.cache
def _index_for(fields: tuple[str, ...]) -> _Index:
    """The index over exactly ``fields``, built once and cached: the catalog
    does not change at runtime, so the cache never needs invalidating."""
    import bm25s

    specs = all_parts()
    corpus = [_tokenize(_document(spec, fields)) for spec in specs]
    bm25 = bm25s.BM25()
    bm25.index(corpus, show_progress=False)
    return _Index(specs, bm25, tuple(frozenset(tokens) for tokens in corpus))


def _document(spec: PartSpec, fields: tuple[str, ...]) -> str:
    """``spec``'s document: its text ``fields``, joined, blanks dropped."""
    return " ".join(
        value for field in fields if (value := getattr(spec, field)) is not None
    )


def _tokenize(text: str) -> list[str]:
    """``text`` as whole-word, lowercase tokens."""
    return _TOKEN_RE.findall(text.lower())
