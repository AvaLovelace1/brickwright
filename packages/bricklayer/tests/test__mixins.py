"""Tests for the shared enum, immutability, and caching bases."""

import gc
import pickle
from functools import cached_property

import pytest

from bricklayer._mixins import Cached, DocumentedEnum, Immutable, ReprEnum


class _Node(Cached):
    """A minimal Cached adopter with one cached value."""

    def __init__(self, value: int = 1) -> None:
        self.value = value

    @cached_property
    def doubled(self) -> int:
        return self.value * 2


class _PicklableCached(Cached):
    """A module-level ``Cached`` subclass -- pickle needs a class it can
    look up by qualified name, which a fixture's local class is not."""

    def __init__(self) -> None:
        self.base = 1

    @cached_property
    def doubled(self) -> int:
        return self.base * 2


class TestReprEnum:
    def test_a_member_reprs_as_its_bare_name(self):
        class Color(ReprEnum):
            RED = 1

        assert repr(Color.RED) == "Color.RED"


class TestDocumentedEnum:
    def test_display_name_titles_the_member_name(self):
        class Part(DocumentedEnum):
            BRICK = "A brick."
            ROUND_TILE = "A round tile."

        assert Part.BRICK.display_name == "Brick"
        assert Part.ROUND_TILE.display_name == "Round Tile"

    def test_each_member_carries_its_own_doc(self):
        class Part(DocumentedEnum):
            """The class docstring."""

            BRICK = "A brick."
            PLATE = "A plate."

        assert Part.BRICK.__doc__ == "A brick."
        assert Part.PLATE.__doc__ == "A plate."
        assert Part.BRICK.__doc__ != Part.__doc__

    def test_values_are_auto_numbered_in_declaration_order(self):
        class Part(DocumentedEnum):
            BRICK = "A brick."
            PLATE = "A plate."

        assert [member.value for member in Part] == [1, 2]

    def test_a_member_may_carry_extra_fields_after_its_doc(self):
        class Sized(DocumentedEnum):
            SMALL = ("A small part.", 1)
            LARGE = ("A large part.", 8)

        assert Sized.SMALL.__doc__ == "A small part."
        assert Sized.LARGE.__doc__ == "A large part."
        assert Sized.SMALL.display_name == "Small"


class TestImmutable:
    @pytest.fixture
    def point(self):
        class Point(Immutable):
            def __init__(self, x: int):
                self.x = x
                self._initialized = True

        return Point(1)

    def test_reads_are_unaffected(self, point):
        assert point.x == 1

    def test_setting_an_attribute_after_init_is_rejected(self, point):
        with pytest.raises(AttributeError, match="Cannot modify 'x'"):
            point.x = 2

    def test_deleting_an_attribute_after_init_is_rejected(self, point):
        with pytest.raises(AttributeError, match="Cannot delete 'x'"):
            del point.x

    def test_attributes_are_writable_during_init(self):
        class Point(Immutable):
            def __init__(self, x: int):
                self.x = x
                self.x = x + 1
                self._initialized = True

        assert Point(1).x == 2


class TestCached:
    @pytest.fixture
    def counter(self):
        """A Cached class counting how often each derived value is computed."""

        class Counted(Cached):
            def __init__(self) -> None:
                self.computed = 0
                self.base = 1

            @cached_property
            def doubled(self) -> int:
                self.computed += 1
                return self.base * 2

        return Counted

    def test_a_cached_property_is_computed_once(self, counter):
        obj = counter()
        assert obj.doubled == 2
        assert obj.doubled == 2
        assert obj.computed == 1

    def test_invalidating_recomputes_from_the_new_input(self, counter):
        obj = counter()
        assert obj.doubled == 2
        obj.base = 5
        obj._invalidate()
        assert obj.doubled == 10
        assert obj.computed == 2

    def test_cached_properties_are_discovered_from_base_classes(self, counter):
        class Subclass(counter):
            @cached_property
            def tripled(self) -> int:
                return self.base * 3

        assert Subclass._CACHED == {"doubled", "tripled"}

    def test_a_class_with_no_cached_properties_has_an_empty_set(self):
        class Bare(Cached):
            pass

        assert Bare._CACHED == frozenset()

    def test_invalidation_reaches_a_dependent(self, counter):
        source, dependent = counter(), counter()
        dependent._depends_on(source)
        assert dependent.doubled == 2
        dependent.base = 5
        source._invalidate()
        assert dependent.doubled == 10

    def test_invalidation_reaches_a_dependent_of_a_dependent(self, counter):
        inner, middle, outer = counter(), counter(), counter()
        middle._depends_on(inner)
        outer._depends_on(middle)
        assert outer.doubled == 2
        outer.base = 7
        inner._invalidate()
        assert outer.doubled == 14

    def test_a_node_reached_by_two_paths_is_invalidated_once(self, counter):
        source, left, right, top = counter(), counter(), counter(), counter()
        left._depends_on(source)
        right._depends_on(source)
        top._depends_on(left)
        top._depends_on(right)
        assert top.doubled == 2
        source._invalidate()
        assert top.doubled == 2
        assert top.computed == 2

    def test_nothing_is_allocated_until_a_dependent_registers(self, counter):
        assert "_dependents" not in counter().__dict__

    def test_the_dependency_graph_survives_invalidation(self, counter):
        source, dependent = counter(), counter()
        dependent._depends_on(source)
        source._invalidate()
        assert dependent in source.__dict__["_dependents"]

    def test_a_dropped_dependent_does_not_keep_being_notified(self, counter):
        source, dependent = counter(), counter()
        dependent._depends_on(source)
        del dependent
        gc.collect()
        assert len(source.__dict__["_dependents"]) == 0

    def test_has_dependent_finds_the_node_itself(self, counter):
        obj = counter()
        assert obj._has_dependent(obj)

    def test_has_dependent_finds_a_transitive_dependent(self, counter):
        inner, middle, outer = counter(), counter(), counter()
        middle._depends_on(inner)
        outer._depends_on(middle)
        assert inner._has_dependent(outer)
        assert not outer._has_dependent(inner)

    def test_invalidation_terminates_on_a_cycle(self, counter):
        a, b = counter(), counter()
        a._depends_on(b)
        b._depends_on(a)
        a._invalidate()
        assert a.doubled == 2

    def test_getstate_excludes_cached_values(self, counter):
        obj = counter()
        assert obj.doubled == 2
        assert "doubled" not in obj.__getstate__()

    def test_getstate_excludes_dependents(self, counter):
        source, dependent = counter(), counter()
        dependent._depends_on(source)
        assert "_dependents" not in source.__getstate__()

    def test_a_node_with_dependents_pickles_despite_the_weak_reference(self):
        source, dependent = _PicklableCached(), _PicklableCached()
        dependent._depends_on(source)
        pickle.loads(pickle.dumps(source))  # does not raise


class TestUnlink:
    def test_stops_invalidation_flowing_from_the_source(self):
        source, dependent = _Node(), _Node()
        dependent._depends_on(source)
        assert dependent.doubled == 2

        dependent._unlink(source)
        source._invalidate()

        assert "doubled" in dependent.__dict__

    def test_drops_the_strong_reference_to_the_source(self):
        source, dependent = _Node(), _Node()
        dependent._depends_on(source)

        dependent._unlink(source)

        assert source not in dependent.__dict__.get("_sources", [])
        assert dependent not in source.__dict__.get("_dependents", set())

    def test_a_doubly_linked_source_survives_one_unlink(self):
        source, dependent = _Node(), _Node()
        dependent._depends_on(source)
        dependent._depends_on(source)

        dependent._unlink(source)
        assert dependent.doubled == 2
        source._invalidate()

        assert "doubled" not in dependent.__dict__

    def test_unlinking_an_unrelated_source_is_a_no_op(self):
        source, dependent, stranger = _Node(), _Node(), _Node()
        dependent._depends_on(source)

        dependent._unlink(stranger)

        assert dependent.doubled == 2
        source._invalidate()
        assert "doubled" not in dependent.__dict__
