"""NameRegistry: the named-part table held by LegoBuild."""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from types import MappingProxyType
from typing import Generic, TypeVar

T = TypeVar("T", bound=Hashable)


class NameRegistry(Generic[T]):
    """A model's named parts: unique names, items tracked by identity.

    A :class:`~bricklayer.modeling.build.LegoBuild` names its placements, holding one
    of these. Names are unique -- registering a taken one raises -- and each
    item is indexed both ways, so :meth:`name_of` is a direct lookup.

    Items are keyed by identity (:class:`~bricklayer.modeling.placement.Placement`
    compares by identity), so two equal-looking parts placed separately keep
    their own names.
    """

    def __init__(self, items: Mapping[str, T] | None = None) -> None:
        self._by_name: dict[str, T] = {}
        self._name_of: dict[T, str] = {}
        for name, item in (items or {}).items():
            self.register(name, item)

    def register(self, name: str, item: T) -> None:
        """Register ``item`` under ``name``.

        Raises:
            ValueError: if the name is already taken.
        """
        if name in self._by_name:
            raise ValueError(f"a part named {name!r} already exists")
        self._by_name[name] = item
        # An item registered under several names reports the first.
        self._name_of.setdefault(item, name)

    def unregister(self, item: T) -> None:
        """Drop every name registered for ``item``. A no-op if it has none.

        An item may hold several names, and all of them go: a name left over
        would point at something its owner no longer holds.
        """
        for name in [n for n, held in self._by_name.items() if held is item]:
            del self._by_name[name]
        self._name_of.pop(item, None)

    def __getitem__(self, name: str) -> T:
        """The item registered under ``name``.

        Raises:
            KeyError: if no part has that name.
        """
        try:
            return self._by_name[name]
        except KeyError:
            raise KeyError(f"no part named {name!r}") from None

    def name_of(self, item: T) -> str | None:
        """The name ``item`` was registered under, or ``None`` if unnamed."""
        return self._name_of.get(item)

    def as_mapping(self) -> Mapping[str, T]:
        """A read-only view keyed by name, in registration order."""
        return MappingProxyType(self._by_name)


__all__ = ["NameRegistry"]
