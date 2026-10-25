"""Tests for NameRegistry, the name table LegoBuild keeps."""

import pytest

from bricklayer.modeling.names import NameRegistry


class _Item:
    """An identity-compared stand-in for a Placement."""

    def __init__(self, label: str = "") -> None:
        self.label = label

    def __repr__(self) -> str:
        return f"_Item({self.label!r})"


@pytest.fixture
def item():
    return _Item


@pytest.fixture
def registry(item):
    """A registry holding two distinct items under 'a' and 'b'."""
    reg: NameRegistry[_Item] = NameRegistry()
    reg.register("a", item("a"))
    reg.register("b", item("b"))
    return reg


class TestConstruction:
    def test_a_mapping_is_copied_in(self, item):
        source = {"a": item("a")}
        reg = NameRegistry(source)
        source["b"] = item("b")  # the registry copied, so this stays outside it
        assert list(reg.as_mapping()) == ["a"]

    def test_no_items_gives_an_empty_registry(self):
        assert not NameRegistry().as_mapping()

    def test_none_gives_an_empty_registry(self):
        assert not NameRegistry(None).as_mapping()


class TestRegister:
    def test_a_registered_item_is_retrievable(self, registry):
        assert registry["a"].label == "a"

    def test_a_duplicate_name_raises(self, registry, item):
        with pytest.raises(ValueError, match="a part named 'a' already exists"):
            registry.register("a", item("other"))

    def test_a_rejected_duplicate_leaves_the_original(self, registry, item):
        original = registry["a"]
        with pytest.raises(ValueError):
            registry.register("a", item("other"))
        assert registry["a"] is original

    def test_registration_order_is_preserved(self, registry):
        assert list(registry.as_mapping()) == ["a", "b"]


class TestUnregister:
    def test_frees_the_name_for_reuse(self, item):
        registry = NameRegistry()
        first = item("first")
        registry.register("arm", first)

        registry.unregister(first)

        assert "arm" not in registry.as_mapping()
        registry.register("arm", item("second"))
        assert registry["arm"] is not first

    def test_drops_every_name_an_item_was_registered_under(self, item):
        registry = NameRegistry()
        shared = item("shared")
        registry.register("arm", shared)
        registry.register("limb", shared)

        registry.unregister(shared)

        assert not registry.as_mapping()
        assert registry.name_of(shared) is None

    def test_leaves_other_items_alone(self, item):
        registry = NameRegistry()
        kept = item("kept")
        registry.register("arm", item("dropped"))
        registry.register("leg", kept)

        registry.unregister(registry["arm"])

        assert registry["leg"] is kept
        assert registry.name_of(kept) == "leg"

    def test_unregistering_an_unknown_item_is_a_no_op(self, item):
        registry = NameRegistry()
        registry.register("arm", item("kept"))

        registry.unregister(item("stranger"))

        assert len(registry.as_mapping()) == 1


class TestLookup:
    def test_an_unknown_name_raises_key_error(self, registry):
        with pytest.raises(KeyError, match="no part named 'nope'"):
            registry["nope"]

    def test_name_of_reverses_the_lookup(self, registry):
        assert registry.name_of(registry["b"]) == "b"

    def test_name_of_an_unregistered_item_is_none(self, registry, item):
        assert registry.name_of(item("stranger")) is None

    def test_equal_looking_items_are_tracked_separately(self, item):
        # Items are keyed by identity, so two look-alikes keep their own names.
        first, second = item("same"), item("same")
        reg: NameRegistry[_Item] = NameRegistry()
        reg.register("first", first)
        reg.register("second", second)
        assert (reg.name_of(first), reg.name_of(second)) == ("first", "second")

    def test_an_item_under_two_names_reports_the_first(self, item):
        shared = item("shared")
        reg: NameRegistry[_Item] = NameRegistry()
        reg.register("early", shared)
        reg.register("late", shared)
        assert reg.name_of(shared) == "early"
        assert reg["early"] is reg["late"] is shared


class TestViews:
    def test_as_mapping_exposes_the_entries(self, registry):
        assert dict(registry.as_mapping()) == {
            "a": registry["a"],
            "b": registry["b"],
        }

    def test_as_mapping_is_read_only(self, registry, item):
        with pytest.raises(TypeError):
            registry.as_mapping()["c"] = item("c")

    def test_as_mapping_tracks_later_registrations(self, registry, item):
        view = registry.as_mapping()
        registry.register("c", item("c"))
        assert "c" in view
