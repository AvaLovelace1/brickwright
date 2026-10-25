"""Unit tests for the doc-rendering helpers."""

import inspect
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction
from functools import cached_property
from types import ModuleType
from typing import ClassVar

import numpy as np
import pytest

from bricklayer._mixins import DocumentedEnum
from bricklayer.docs.utils import (
    ClassDoc,
    bullet,
    code_blocks,
    document_class,
    document_class_constants,
    document_class_name,
    document_classes,
    document_constant,
    document_constants,
    document_definitions,
    document_enum_members,
    document_function,
    document_functions,
    document_members,
    document_method,
    document_methods,
    document_module,
    document_operators,
    document_properties,
    document_property,
    heading,
    signature,
)


class _PlainClass:
    """
    A plain class with a docstring, class vars, properties, and methods.
    """

    CLASS_VAR: ClassVar[int] = 42
    DEFERRED_CLASS_VAR: ClassVar[str]
    _PRIVATE_CLASS_VAR: ClassVar[int] = 42

    def __init__(self, x: int = 42) -> None:
        self.x = x

    @property
    def property(self) -> int:
        """A property declared with @property.

        More detail here.
        """
        return 42

    @cached_property
    def cached_property(self) -> int:
        """A property declared with @cached_property.

        More detail here.
        """
        return 42

    def method1(self, x: int) -> None:
        """A method.

        More detail here.
        """

    def method2(self, y: str) -> None:
        """Another method."""

    def _private_method(self) -> None:
        """Skipped: private."""


_PlainClass.DEFERRED_CLASS_VAR = "deferred"


class _PlainChild(_PlainClass):
    """Inherits its properties and methods from _PlainClass."""

    @property
    def child_property(self) -> int:
        """A property defined on the child class."""
        return 42

    def child_method(self) -> None:
        """A method defined on the child class."""


class _OnlySetter:
    """A class with only a private setter; no public properties, class vars, or methods."""

    def _set(self, value: int) -> None: ...

    val = property(fset=_set)


class _MathyClass:
    """A type with arithmetic operators."""

    def __add__(self, other): ...

    def __sub__(self, other): ...

    def __mul__(self, k): ...

    def __neg__(self): ...

    def method(self) -> None:
        """A non-operator method."""


class _MathyChild(_MathyClass):
    """Inherits its operators from _MathyClass."""


class _PlainEnum(Enum):
    """A plain enum."""

    A = 1
    B = 2


class _DocEnum(DocumentedEnum):
    """A DocumentedEnum."""

    FOO = "the foo member"
    BAR_BAZ = "the bar baz member"


class _MethodEnum(Enum):
    """An enum that also defines a property and a method."""

    A = 1
    B = 2

    @property
    def property(self) -> int:
        """A property."""
        return 42

    def method(self, x: int) -> None:
        """A method."""


def _fn1(a: str, b: int = 42) -> None:
    """Example function.

    More details here.
    """


def _fn2(x: int) -> int:
    """Another example function.

    More details here.
    """
    return x


@dataclass
class _DataClass:
    """A dataclass with public fields, a private field, and a property."""

    beta: int
    alpha: str
    _private: int = 0

    @property
    def gamma(self) -> int:
        """A property alongside the fields."""
        return 42


@dataclass
class _DataChild(_DataClass):
    """A dataclass inheriting its fields from _DataClass."""

    delta: int = 0


@dataclass
class _DocumentedDataClass:
    """A dataclass whose fields carry ``metadata`` docstrings."""

    documented: int = field(metadata={"doc": "A documented field."})
    plain: int = 0


class TestHeading:
    def test_renders_a_markdown_heading_at_the_default_level(self):
        assert heading("Overview") == "# Overview"

    def test_renders_a_markdown_heading_at_a_custom_level(self):
        assert heading("Details", level=3) == "### Details"

    def test_strips_surrounding_whitespace(self):
        assert heading("  Padded Heading  ") == "# Padded Heading"

    @pytest.mark.parametrize("level", (0, 7))
    def test_rejects_levels_outside_the_markdown_range(self, level):
        with pytest.raises(ValueError, match="heading level must be 1-6"):
            heading("Oops", level=level)


class TestBullet:
    def test_renders_a_single_line_bullet(self):
        assert bullet("item") == "- item"

    def test_strips_surrounding_whitespace(self):
        assert bullet("  padded item  ") == "- padded item"

    def test_indents_continuation_lines(self):
        assert bullet("line 1\nline 2") == "- line 1\n  line 2"

    def test_preserves_blank_lines_between_paragraphs(self):
        assert bullet("line 1\n\nline 2") == "- line 1\n\n  line 2"


class TestCodeBlockIsComplete:
    def test_a_block_opening_with_an_import_is_complete(self):
        (block,) = code_blocks(
            "```python\nimport bricklayer as bl\n\nbl.plate(1, 1)\n```"
        )
        assert block.is_complete

    def test_a_block_opening_with_a_from_import_is_complete(self):
        (block,) = code_blocks(
            "```python\nfrom bricklayer import plate\n\nplate(1, 1)\n```"
        )
        assert block.is_complete

    def test_a_block_that_does_not_open_with_an_import_is_a_fragment(self):
        (block,) = code_blocks("```python\nmodel = bl.LegoBuild()\n```")
        assert not block.is_complete

    def test_an_empty_block_is_a_fragment(self):
        (block,) = code_blocks("```python\n```")
        assert not block.is_complete

    def test_a_non_python_block_is_never_complete(self):
        (block,) = code_blocks("```text\nimport bricklayer\n```")
        assert not block.is_complete


class TestCodeBlocks:
    def test_captures_the_language_and_contents(self):
        (block,) = code_blocks("```python\nx = 1\n```")
        assert (block.language, block.code) == ("python", "x = 1\n")

    def test_a_fence_without_a_language_gets_an_empty_one(self):
        (block,) = code_blocks("```\nx = 1\n```")
        assert block.language == ""

    def test_dedents_an_indented_block(self):
        # A docstring rendered into a Markdown bullet arrives indented.
        (block,) = code_blocks("- item\n\n  ```python\n  x = 1\n  ```")
        assert block.code == "x = 1\n"

    def test_attributes_the_nearest_heading_above(self):
        md = "# Far\n\n## Near\n\n```python\nx = 1\n```"
        (block,) = code_blocks(md)
        assert block.heading == "Near"

    def test_a_block_above_every_heading_has_no_heading(self):
        (block,) = code_blocks("```python\nx = 1\n```\n\n# Later\n")
        assert block.heading == ""

    def test_a_comment_inside_a_block_is_not_a_heading(self):
        md = "## Real\n\n```python\n# Not a heading\n```\n\n```python\nx = 1\n```"
        assert [b.heading for b in code_blocks(md)] == ["Real", "Real"]

    def test_finds_every_block_in_order(self):
        md = "```python\nfirst\n```\n\n```text\nsecond\n```"
        assert [b.language for b in code_blocks(md)] == ["python", "text"]


class TestDocumentModule:
    def test_module_title_and_body_are_rendered_from_its_docstring(self):
        module = ModuleType("example", "Example guide.\n\n    Keep this guidance.")
        assert document_module(module) == "## Example guide\n\nKeep this guidance."


class TestDocumentDefinitions:
    def test_routes_classes_functions_and_constants_into_sections(self):
        assert document_definitions((_PlainClass, _fn1, ("N", 42))) == "\n\n".join(
            (
                document_classes([_PlainClass]),
                document_functions([_fn1]),
                document_constants([("N", 42)]),
            )
        )

    def test_emits_only_the_sections_that_have_content(self):
        assert document_definitions([("N", 42)]) == document_constants([("N", 42)])

    def test_no_definitions_is_empty(self):
        assert document_definitions([]) == ""

    def test_class_selection_filters_methods_fields_and_constants(self):
        @dataclass
        class Example:
            """An example returned by the API."""

            CONSTANT: ClassVar[int] = 42
            kept: int
            omitted: str

            def internal(self):
                """Implementation machinery."""

            def useful(self):
                """Useful behavior."""

        rendered = document_definitions(
            [
                ClassDoc(Example, members=("kept", "useful"), constructor=False),
            ]
        )
        assert "An example returned by the API." in rendered
        assert "kept: int" in rendered
        assert "Useful behavior." in rendered
        assert "CONSTANT" not in rendered
        assert "omitted" not in rendered
        assert "Implementation machinery" not in rendered
        assert "Example(" not in rendered

    def test_class_selection_rejects_stale_member_names(self):
        with pytest.raises(ValueError, match="missing"):
            document_definitions([ClassDoc(_PlainClass, members=("missing",))])

    def test_selected_annotated_attributes_of_plain_classes_are_documented(self):
        class ReturnedObject:
            position: int
            internal: str

        rendered = document_definitions(
            [
                ClassDoc(ReturnedObject, members=("position",), constructor=False),
            ]
        )
        assert "position: int" in rendered
        assert "internal" not in rendered


class TestDocumentClasses:
    def test_wraps_each_class_under_a_classes_heading(self):
        assert document_classes((_PlainClass, _PlainEnum)) == "\n\n".join(
            (
                "# Classes",
                document_class(_PlainClass, heading_level=2),
                document_class(_PlainEnum, heading_level=2),
            )
        )

    @pytest.mark.parametrize("make_iterable", [list, tuple, iter])
    def test_no_classes_is_empty(self, make_iterable):
        assert document_classes(make_iterable(())) == ""

    def test_documents_a_generator(self):
        values = (_PlainClass, _PlainEnum)
        assert document_classes(value for value in values) == document_classes(values)


class TestDocumentClass:
    def test_documents_a_plain_class_with_signature_doc_and_members(self):
        doc = inspect.getdoc(_PlainClass)
        assert doc is not None
        assert document_class(_PlainClass) == "\n\n".join(
            (
                heading(document_class_name(_PlainClass)),
                f"`_PlainClass{signature(_PlainClass)}`",
                doc,
                document_members(_PlainClass),
            )
        )

    def test_documents_an_enum_class_with_doc_and_members(self):
        doc = inspect.getdoc(_MethodEnum)
        assert doc is not None
        assert document_class(_MethodEnum) == "\n\n".join(
            (
                heading(document_class_name(_MethodEnum)),
                doc,
                document_enum_members(_MethodEnum),
                document_members(_MethodEnum),
            )
        )

    def test_omits_docstring_when_none(self):
        class _NoDoc:
            def method(self) -> None: ...

        assert document_class(_NoDoc) == "\n\n".join(
            (
                heading(document_class_name(_NoDoc)),
                f"`_NoDoc{signature(_NoDoc)}`",
                document_members(_NoDoc),
            )
        )

    def test_omits_members_and_properties_when_none(self):
        doc = inspect.getdoc(_OnlySetter)
        assert doc is not None
        assert document_class(_OnlySetter) == "\n\n".join(
            (
                heading(document_class_name(_OnlySetter)),
                f"`_OnlySetter{signature(_OnlySetter)}`",
                doc,
            )
        )


class TestDocumentClassName:
    def test_class_with_no_bases(self):
        assert document_class_name(_PlainClass) == "class `_PlainClass`"

    def test_enum_with_no_bases(self):
        """The base `Enum` class itself is not listed."""
        assert document_class_name(_PlainEnum) == "enum `_PlainEnum`"

    def test_class_with_multiple_bases(self):
        class _Child(_PlainClass, _OnlySetter): ...

        assert document_class_name(_Child) == "class `_Child(_PlainClass, _OnlySetter)`"


class TestEnumMembers:
    def test_plain_enum_gets_a_compact_one_liner(self):
        assert document_enum_members(_PlainEnum) == "**Members:** `A`, `B`"

    def test_documented_enum_lists_each_member_with_its_doc(self):
        assert document_enum_members(_DocEnum) == "\n".join(
            (
                "**Members:**",
                bullet("`FOO` -- the foo member"),
                bullet("`BAR_BAZ` -- the bar baz member"),
            )
        )


class TestDocumentMembers:
    def test_groups_properties_and_methods_into_labelled_sections(self):
        assert document_members(_PlainClass) == "\n\n".join(
            (
                document_class_constants(_PlainClass),
                document_properties(_PlainClass),
                document_methods(_PlainClass),
            )
        )

    def test_documents_operators(self):
        assert document_members(_MathyClass) == "\n\n".join(
            (document_operators(_MathyClass), document_methods(_MathyClass)),
        )

    def test_documents_enum_methods_and_properties(self):
        assert document_members(_MethodEnum) == "\n\n".join(
            (document_properties(_MethodEnum), document_methods(_MethodEnum))
        )


class TestDocumentOperators:
    def test_lists_supported_arithmetic_operators(self):
        assert document_operators(_MathyClass) == (
            "**Operators**\n\nSupports `+`, `-`, `*`, unary `-`."
        )

    def test_includes_inherited_operators(self):
        assert document_operators(_MathyChild) == (
            "**Operators**\n\nSupports `+`, `-`, `*`, unary `-`."
        )


class TestDocumentClassConstants:
    def test_documents_public_class_constants(self):
        assert document_class_constants(_PlainClass) == "\n".join(
            (
                "**Class constants**\n",
                bullet(document_constant("CLASS_VAR", 42)),
                bullet(document_constant("DEFERRED_CLASS_VAR", "deferred")),
            )
        )

    def test_lists_constants_in_alphabetical_order(self):
        class _OutOfOrder:
            Z: ClassVar[int] = 1
            A: ClassVar[int] = 2

        assert document_class_constants(_OutOfOrder) == "\n".join(
            (
                "**Class constants**\n",
                bullet(document_constant("A", 2)),
                bullet(document_constant("Z", 1)),
            )
        )

    def test_returns_blank_when_no_class_constants_exist(self):
        assert document_class_constants(_OnlySetter) == ""


class TestDocumentProperties:
    def test_documents_public_properties_defined_on_the_class(self):
        assert document_properties(_PlainClass) == "\n".join(
            (
                "**Properties**\n",
                document_property("cached_property", _PlainClass.cached_property),
                document_property("property", _PlainClass.property),
            )
        )

    def test_lists_properties_in_alphabetical_order(self):
        class _OutOfOrder:
            @property
            def z(self) -> int:
                return 42

            @property
            def a(self) -> int:
                return 42

            @property
            def m(self) -> int:
                return 42

        assert document_properties(_OutOfOrder) == "\n".join(
            (
                "**Properties**\n",
                document_property("a", _OutOfOrder.a),
                document_property("m", _OutOfOrder.m),
                document_property("z", _OutOfOrder.z),
            )
        )

    def test_excludes_inherited_properties(self):
        assert document_properties(_PlainChild) == "\n".join(
            (
                "**Properties**\n",
                document_property("child_property", _PlainChild.child_property),
            )
        )

    def test_includes_public_dataclass_fields_sorted_with_properties(self):
        assert document_properties(_DataClass) == "\n".join(
            (
                "**Properties**\n",
                bullet("`alpha: str`"),
                bullet("`beta: int`"),
                document_property("gamma", _DataClass.gamma),
            )
        )

    def test_excludes_inherited_dataclass_fields(self):
        assert document_properties(_DataChild) == "\n".join(
            ("**Properties**\n", bullet("`delta: int`"))
        )

    def test_includes_dataclass_field_metadata_docs(self):
        assert document_properties(_DocumentedDataClass) == "\n".join(
            (
                "**Properties**\n",
                bullet("`documented: int` -- A documented field."),
                bullet("`plain: int`"),
            )
        )

    def test_returns_blank_when_no_public_properties_exist(self):
        assert document_properties(_OnlySetter) == ""


class TestDocumentProperty:
    def test_documents_a_single_property(self):
        assert document_property("property", _PlainClass.property) == (
            "- `property: int` -- A property declared with @property.\n\n  More detail here."
        )

    def test_documents_a_single_cached_property(self):
        assert document_property("cached_property", _PlainClass.cached_property) == (
            "- `cached_property: int` -- A property declared with @cached_property.\n\n  More detail here."
        )

    def test_property_without_doc_is_name_and_type(self):
        class UndocumentedProperty:
            @property
            def property(self) -> int:
                return 42

        assert (
            document_property("property", UndocumentedProperty.property)
            == "- `property: int`"
        )

    def test_property_without_return_annotation_is_name_only(self):
        class UnannotatedProperty:
            @property
            def property(self):
                return 42

        assert (
            document_property("property", UnannotatedProperty.property)
            == "- `property`"
        )

    def test_annotation_shortens_qualified_names(self):
        class QualifiedProperty:
            @property
            def property(self) -> Iterable[Fraction]:
                return []

        assert (
            document_property("property", QualifiedProperty.property)
            == "- `property: Iterable[Fraction]`"
        )


class TestDocumentMethods:
    def test_documents_public_methods_defined_on_the_class(self):
        assert document_methods(_PlainClass) == "\n".join(
            [
                "**Methods**\n",
                document_method("method1", _PlainClass.method1),
                document_method("method2", _PlainClass.method2),
            ]
        )

    def test_lists_methods_in_alphabetical_order(self):
        class _OutOfOrder:
            def z(self) -> None: ...

            def a(self) -> None: ...

            def m(self) -> None: ...

        assert document_methods(_OutOfOrder) == "\n".join(
            [
                "**Methods**\n",
                document_method("a", _OutOfOrder.a),
                document_method("m", _OutOfOrder.m),
                document_method("z", _OutOfOrder.z),
            ]
        )

    def test_excludes_inherited_methods(self):
        assert document_methods(_PlainChild) == "\n".join(
            [
                "**Methods**\n",
                document_method("child_method", _PlainChild.child_method),
            ]
        )

    def test_returns_blank_when_no_public_methods_exist(self):
        assert document_methods(_OnlySetter) == ""


class TestDocumentMethod:
    def test_documents_a_single_instance_method(self):
        assert document_method("method1", _PlainClass.method1) == (
            "- `method1(x: int) -> None` -- A method.\n\n  More detail here."
        )

    def test_documents_a_single_classmethod(self):
        class HasClassMethod:
            @classmethod
            def class_method(cls, x: int) -> None:
                """A classmethod."""

        text = document_method(
            "class_method",
            HasClassMethod.class_method,
            raw=HasClassMethod.__dict__["class_method"],
        )
        assert (
            text == "- `class_method(x: int) -> None` (classmethod) -- A classmethod."
        )

    def test_documents_a_single_staticmethod(self):
        class HasStaticMethod:
            @staticmethod
            def static_method(x: int) -> None:
                """A staticmethod."""

        text = document_method(
            "static_method",
            HasStaticMethod.static_method,
            raw=HasStaticMethod.__dict__["static_method"],
        )
        assert text == (
            "- `static_method(x: int) -> None` (staticmethod) -- A staticmethod."
        )

    def test_method_without_doc_is_name_only(self):
        class UndocumentedMethod:
            def method(self, x: int) -> None:
                return None

        assert (
            document_method("method", UndocumentedMethod.method)
            == "- `method(x: int) -> None`"
        )


class TestDocumentFunctions:
    def test_documents_each_function(self):
        assert document_functions((_fn1, _fn2)) == "\n\n".join(
            (
                heading("Functions"),
                document_function(_fn1, heading_level=2),
                document_function(_fn2, heading_level=2),
            )
        )

    @pytest.mark.parametrize("make_iterable", [list, tuple, iter])
    def test_no_functions_is_empty(self, make_iterable):
        assert document_functions(make_iterable(())) == ""

    def test_documents_a_generator(self):
        values = (_fn1, _fn2)
        assert document_functions(value for value in values) == document_functions(
            values
        )


class TestDocumentFunction:
    def test_renders_function_with_signature_and_doc(self):
        doc = inspect.getdoc(_fn1)
        assert doc is not None
        assert document_function(_fn1) == "\n\n".join(
            (heading("`_fn1(a: str, b: int = 42) -> None`"), doc)
        )

    def test_function_with_no_docstring_has_an_empty_body(self):
        def no_doc(x: int) -> int:
            return x

        assert document_function(no_doc) == "# `no_doc(x: int) -> int`"


class TestDocumentConstants:
    def test_documents_each_constant_with_document_constant(self):
        assert document_constants([("N", 3), ("S", "hi")]) == "\n".join(
            (
                "# Constants",
                "",
                bullet(document_constant("N", 3)),
                bullet(document_constant("S", "hi")),
            )
        )

    @pytest.mark.parametrize("make_iterable", [list, tuple, iter])
    def test_no_constants_is_empty(self, make_iterable):
        assert document_constants(make_iterable(())) == ""

    def test_documents_a_generator(self):
        values = (("N", 3), ("S", "hi"))
        assert document_constants(value for value in values) == document_constants(
            values
        )


class TestDocumentConstant:
    def test_constants_render_with_repr(self):
        assert document_constant("N", 3) == "`N` = `3`"
        assert document_constant("S", "hi") == "`S` = `'hi'`"
        assert document_constant("F", Fraction(1, 3)) == "`F` = `Fraction(1, 3)`"
        assert document_constant("U", int | str) == "`U` = `int | str`"

    def test_shortens_qualified_name(self):
        assert document_constant("H", int | Fraction) == "`H` = `int | Fraction`"

    def test_callables_render_by_name(self):
        # A function's or class's repr carries a module path or memory address.
        value = {"f": _fn1, "cls": Fraction, "builtin": len}
        assert (
            document_constant("M", value)
            == "`M` = `{'f': _fn1, 'cls': Fraction, 'builtin': len}`"
        )


class TestSignature:
    def test_real_signature_is_rendered(self):
        assert signature(_fn1) == "(a: str, b: int = 42) -> None"

    def test_drops_self_and_underscore_parameters(self):
        def _takes_self(self, x): ...

        def _takes_underscore(x, _y): ...

        assert signature(_takes_self) == "(x)"
        assert signature(_takes_underscore) == "(x)"

    def test_preserves_quotes_on_string_defaults(self):
        def _string_default(x="a"): ...

        assert signature(_string_default) == "(x='a')"

    def test_collapses_enum_member_defaults(self):
        def _enum_default(x=_PlainEnum.A): ...

        assert signature(_enum_default) == "(x=_PlainEnum.A)"

    def test_shortens_qualified_names(self):
        def _qualified(x: Iterable[Fraction] | None) -> Fraction:
            return Fraction(0)

        assert signature(_qualified) == "(x: Iterable[Fraction] | None) -> Fraction"

    def test_leaves_import_aliases_alone(self):
        def _aliased(x: "np.ndarray"): ...

        assert signature(_aliased) == "(x: np.ndarray)"

    @pytest.mark.parametrize(
        "default", ["3626bp01", "it's a part", "bricklayer.Element"]
    )
    def test_string_defaults_remain_valid_python_literals(self, default):
        def example(part_id: "str" = default) -> "str":
            return part_id

        rendered = signature(example)
        namespace = {}
        exec(f"def documented{rendered}: return part_id", namespace)
        assert namespace["documented"]() == default
        assert "part_id: str" in rendered
