"""Shared bases: immutability, droppable caches, and documented enums."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from enum import Enum
from functools import cached_property
from typing import Any, ClassVar, Self
from weakref import WeakSet


class ReprEnum(Enum):
    """Enum base whose ``repr`` is the bare member name."""

    @property
    def display_name(self) -> str:
        """Human-readable name derived from the member, e.g. ``"Reddish Brown"``."""
        return self.name.replace("_", " ").title()

    def __repr__(self) -> str:
        return f"{type(self).__name__}.{self.name}"


class DocumentedEnum(ReprEnum):
    """An enum whose members each carry their own docstring.

    Define members as ``NAME = doc`` (subclasses may append extra fields:
    ``NAME = (doc, ...)``). The doc becomes the member's ``__doc__``, readable
    like any docstring. Values are auto-numbered.
    """

    def __new__(cls, doc: str, *extra: object) -> Self:
        member = object.__new__(cls)
        member._value_ = len(cls.__members__) + 1
        member.__doc__ = doc
        return member


class Immutable:
    """Makes any subclass immutable after __init__ completes."""

    def __setattr__(self, name, value):
        if getattr(self, "_initialized", False):
            raise AttributeError(
                f"Cannot modify '{name}'. {self.__class__.__name__} is immutable."
            )
        super().__setattr__(name, value)

    def __delattr__(self, name):
        if getattr(self, "_initialized", False):
            raise AttributeError(
                f"Cannot delete '{name}'. {self.__class__.__name__} is immutable."
            )
        super().__delattr__(name)


class Cached:
    """Mixin for a class whose ``cached_property`` values must be droppable.

    A subclass keeps plain :func:`functools.cached_property` definitions. Each
    stores its value in the instance ``__dict__`` under the property's own
    name, so dropping one is a dict removal -- the mechanism the standard
    library documents for invalidating a cached property. This mixin makes that
    disciplined: it discovers every cached property across the MRO at class
    creation, and :meth:`_invalidate` clears them all.

    Derived values often depend on *other* objects' derived values. A node
    registers with :meth:`_depends_on`, and invalidation then flows from a
    source to everything computed from it, however deep the chain. Each edge
    is recorded twice: weakly, from source to dependent (``_dependents``, what
    invalidation walks), and strongly, from dependent to source (``_sources``,
    what pickling preserves and :meth:`__setstate__` replays). A dependency
    never keeps its dependents alive; a dependent already holds its sources
    alive by construction (a ``Placement`` holds its ``content``, a
    ``LegoBuild`` its placements), so ``_sources`` adds no retention of its
    own.

    Dependents and sources live in ``__dict__``, so a frozen dataclass can hold
    them and a node with neither allocates nothing.

    Dependents are held in a ``WeakSet``, which finds them by ``__hash__`` and
    ``__eq__`` -- a class mixing in ``Cached`` must therefore hash by
    identity, and a dataclass adopter needs ``eq=False``.
    """

    #: Every cached property on this class, its own and inherited.
    _CACHED: ClassVar[frozenset[str]] = frozenset()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._CACHED = frozenset(
            name
            for klass in cls.__mro__
            for name, value in vars(klass).items()
            if isinstance(value, cached_property)
        )

    def __getstate__(self) -> dict[str, Any]:
        """Pickled state, excluding dependents and every cached value.

        A ``WeakSet`` cannot be pickled, and a cached value is cheap to
        recompute and would otherwise go stale across the pickle boundary.
        ``_sources`` survives -- it is a plain, strong collection -- so
        :meth:`__setstate__` can rebuild the ``_dependents`` links it drops.
        """
        return {
            key: value
            for key, value in self.__dict__.items()
            if key != "_dependents" and key not in self._CACHED
        }

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Restore state, then re-register as a dependent of every source in
        ``_sources`` -- the ``_dependents`` links :meth:`__getstate__` drops.

        Writes through ``__dict__``, so a frozen dataclass adopter works too.
        """
        self.__dict__.update(state)
        for source in self.__dict__.get("_sources", ()):
            _link(source, self)

    def _depends_on(self, source: Cached) -> None:
        """Recompute this node's cached values whenever ``source`` changes."""
        _link(source, self)
        self.__dict__.setdefault("_sources", []).append(source)

    def _unlink(self, source: Cached) -> None:
        """Stop recomputing this node's cached values when ``source`` changes.

        The counterpart to :meth:`_depends_on`, and symmetric with it: each
        call drops one recorded edge, so a node that registered the same
        source twice stays linked once. The weak back-edge goes only once no
        edge to that source is left.
        """
        sources = self.__dict__.get("_sources", [])
        if source in sources:
            sources.remove(source)
        if source in sources:
            return
        dependents = source.__dict__.get("_dependents")
        if dependents is not None:
            dependents.discard(self)

    def _invalidate(self) -> None:
        """Drop this node's cached values, and those of everything derived from it."""
        if "_dependents" in self.__dict__:
            for node in self._walk():
                node._drop_cached()
        else:
            self._drop_cached()

    def _drop_cached(self) -> None:
        """Drop this node's own cached values."""
        for name in self._CACHED & self.__dict__.keys():
            del self.__dict__[name]

    def _has_dependent(self, node: Cached) -> bool:
        """Whether ``node`` is this node, or derives from it at any depth."""
        return any(other is node for other in self._walk())

    def _walk(self) -> Iterator[Cached]:
        """This node and everything derived from it, each yielded once.

        Breadth-first over an explicit queue, so nesting depth costs no stack
        frames, and identity-deduplicated, so a source reached by several paths
        is visited once and a cyclic graph still terminates.
        """
        seen: set[int] = set()
        queue: deque[Cached] = deque([self])
        while queue:
            node = queue.popleft()
            if id(node) in seen:
                continue
            seen.add(id(node))
            yield node
            queue.extend(node.__dict__.get("_dependents", ()))


def _link(source: Cached, dependent: Cached) -> None:
    """Register ``dependent`` in ``source``'s weak set of dependents."""
    source.__dict__.setdefault("_dependents", WeakSet()).add(dependent)


__all__ = ["Cached", "DocumentedEnum", "Immutable", "ReprEnum"]
