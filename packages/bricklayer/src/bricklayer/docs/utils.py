"""Utilities for constructing and parsing Markdown text, and documenting Python definitions in Markdown."""

import ast
import dataclasses
import inspect
import re
import sys
from abc import ABC
from collections.abc import Callable, Collection, Iterable
from enum import Enum
from functools import cached_property
from textwrap import dedent, indent
from types import ModuleType
from typing import Any, ClassVar, Generic, get_origin

from .._mixins import Cached, DocumentedEnum, Immutable, ReprEnum


def heading(text: str, level: int = 1) -> str:
    """A Markdown heading of the given level (1-6)."""
    if level < 1 or level > 6:
        raise ValueError(f"heading level must be 1-6, got {level}")
    return f"{'#' * level} {text.strip()}"


def bullet(text: str) -> str:
    """A Markdown bullet point."""
    indented = indent(text.strip(), "  ")
    return "-" + indented[1:]


def paragraphs(*blocks: str) -> str:
    """The non-empty Markdown ``blocks``, separated by blank lines."""
    return "\n\n".join(block for block in blocks if block)


_FENCE = re.compile(
    r"^(?P<indent>[ \t]*)```(?P<language>\S*)\n(?P<code>.*?)^(?P=indent)```",
    re.MULTILINE | re.DOTALL,
)
_HEADING = re.compile(r"^#+ +(.*)$", re.MULTILINE)


@dataclasses.dataclass(frozen=True)
class CodeBlock:
    """A fenced code block parsed out of Markdown text."""

    language: str
    """The fence's info string, e.g. ``python``. ``""`` when the fence gives none."""
    code: str
    """The block's contents, dedented."""
    heading: str
    """The nearest heading above the block, or ``""`` when it sits under none."""

    @property
    def is_complete(self) -> bool:
        """Whether the block is a standalone program rather than a fragment.

        A Python block qualifies when its first statement is an import: every complete
        example in these docs opens by importing the library it demonstrates.
        """
        if self.language != "python":
            return False
        body = ast.parse(self.code).body
        return bool(body) and isinstance(body[0], ast.Import | ast.ImportFrom)


def code_blocks(markdown: str) -> list[CodeBlock]:
    """The fenced code blocks in ``markdown``, in the order they appear."""
    # A block rendered into a bullet is indented, and a `#` comment inside a block is
    # not a heading, so headings are looked up in the text with the blocks blanked out.
    # The substitution keeps the line count, so line numbers still line up.
    outside = _FENCE.sub(lambda m: "\n" * m.group(0).count("\n"), markdown).split("\n")
    blocks = []
    for match in _FENCE.finditer(markdown):
        line = markdown[: match.start()].count("\n")
        above = _HEADING.findall("\n".join(outside[:line]))
        blocks.append(
            CodeBlock(
                language=match.group("language"),
                code=dedent(match.group("code")),
                heading=above[-1].strip() if above else "",
            )
        )
    return blocks


@dataclasses.dataclass(frozen=True)
class ClassDoc:
    """Select a class's agent-facing members without duplicating their docs.

    ``members=None`` includes all public members. An explicit tuple is an
    allowlist; unknown names fail rendering so renamed API cannot silently vanish.
    ``constructor=False`` documents objects obtained from other API calls.
    """

    cls: type
    members: tuple[str, ...] | None = None
    constructor: bool = True


def document_module(module: ModuleType, heading_level: int = 2) -> str:
    """Render a module docstring's first line as its title, followed by its body."""
    title, _, body = (inspect.getdoc(module) or "").partition("\n")
    return paragraphs(heading(title.rstrip("."), heading_level), body.strip())


def document_definitions(
    definitions: Iterable[type | ClassDoc | Callable | tuple[str, Any]],
    heading_level: int = 1,
) -> str:
    """Generate Markdown documentation for the given definitions,
    creating one section per definition type: classes, functions, and constants.

    Constants are provided as (name, value) tuples.
    """
    classes: list[type | ClassDoc] = []
    functions: list[Callable] = []
    constants: list[tuple[str, Any]] = []
    for obj in definitions:
        if isinstance(obj, ClassDoc) or inspect.isclass(obj):
            classes.append(obj)
        elif callable(obj):
            functions.append(obj)
        else:
            constants.append(obj)
    return paragraphs(
        document_classes(classes, heading_level),
        document_functions(functions, heading_level),
        document_constants(constants, heading_level),
    )


def document_classes(classes: Iterable[type | ClassDoc], heading_level: int = 1) -> str:
    """Generate Markdown documentation for the given classes, creating one section per class."""
    classes = tuple(classes)
    if not classes:
        return ""
    return "\n\n".join(
        (
            heading("Classes", heading_level),
            *(
                document_class(
                    c.cls,
                    heading_level + 1,
                    members=c.members,
                    constructor=c.constructor,
                )
                if isinstance(c, ClassDoc)
                else document_class(c, heading_level + 1)
                for c in classes
            ),
        )
    )


def document_class(
    cls: type,
    heading_level: int = 1,
    *,
    members: Collection[str] | None = None,
    constructor: bool = True,
) -> str:
    """Generate Markdown documentation for a single class, including its signature, docstring, and members."""
    if members is not None:
        available = {name for name, _ in _get_public_members(cls)}
        available.update(name for name, _ in _get_fields(cls))
        if missing := set(members) - available:
            raise ValueError(
                f"Unknown documented members of {cls.__name__}: {sorted(missing)}"
            )
    name = cls.__name__
    blocks = [heading(document_class_name(cls), heading_level)]
    if constructor and not issubclass(cls, Enum):
        blocks.append(f"`{name}{signature(cls)}`")
    doc = inspect.getdoc(cls)
    if doc and doc.strip():
        blocks.append(doc.strip())
    if issubclass(cls, Enum):
        blocks.append(document_enum_members(cls))
    if rendered_members := document_members(cls, members=members):
        blocks.append(rendered_members)
    return "\n\n".join(blocks)


_IGNORED_BASES = {
    object,
    Enum,
    ReprEnum,
    DocumentedEnum,
    Immutable,
    Cached,
    Generic,
    ABC,
}


def document_class_name(cls: type) -> str:
    """A class's name, with its bases in parentheses if any, and ``enum`` or ``class`` prepended.

    Ignores the bases in :data:`_IGNORED_BASES`: ``object``, the enum bases,
    and the shared mixins.
    """
    bases = [b.__name__ for b in cls.__bases__ if b not in _IGNORED_BASES]
    bases_str = "" if not bases else f"({', '.join(bases)})"
    class_type = "enum" if issubclass(cls, Enum) else "class"
    return f"{class_type} `{cls.__name__}{bases_str}`"


def document_enum_members(cls: type[Enum]) -> str:
    """List an enum's members.

    A :class:`DocumentedEnum` gets one line per member with its docstring; other enums get a compact one-liner.
    """
    members = cls.__members__.items()
    if issubclass(cls, DocumentedEnum):
        return "\n".join(
            (
                "**Members:**",
                *(bullet(f"`{name}` -- {m.__doc__}") for name, m in members),
            )
        )
    return "**Members:** " + ", ".join(f"`{name}`" for name, _ in members)


def document_members(cls: type, *, members: Collection[str] | None = None) -> str:
    """A class's own public members, split into labeled ``Operators``, ``Constants``, ``Properties`` and ``Methods`` sections.

    A section with no members is dropped.
    """
    return paragraphs(
        document_operators(cls),
        document_class_constants(cls, members=members),
        document_properties(cls, members=members),
        document_methods(cls, members=members),
    )


# The arithmetic operators worth advertising, in display order, each mapped to
# the symbol a reader would type.
_OPERATORS = {
    "__add__": "`+`",
    "__sub__": "`-`",
    "__mul__": "`*`",
    "__matmul__": "`@`",
    "__truediv__": "`/`",
    "__floordiv__": "`//`",
    "__neg__": "unary `-`",
}


def document_operators(cls: type) -> str:
    """The arithmetic operators a class supports (including inherited ones), or "" if none."""
    labels = [
        label
        for dunder, label in _OPERATORS.items()
        if getattr(cls, dunder, None) is not None
    ]
    if not labels:
        return ""
    return "**Operators**\n\nSupports " + ", ".join(labels) + "."


def document_class_constants(
    cls: type, *, members: Collection[str] | None = None
) -> str:
    """A class's own public class-level constants (``ClassVar``s), alphabetically, or ``""`` if none."""
    names = sorted(
        name
        for name, annotation in inspect.get_annotations(cls).items()
        if not name.startswith("_")
        and _is_class_var(annotation)
        and hasattr(cls, name)
        and (members is None or name in members)
    )
    if not names:
        return ""
    entries = (bullet(document_constant(name, getattr(cls, name))) for name in names)
    return "**Class constants**\n\n" + "\n".join(entries)


def _is_class_var(annotation: Any) -> bool:
    """Whether an annotation is a ``ClassVar``, handling both string and evaluated forms."""
    if isinstance(annotation, str):
        return annotation.startswith("ClassVar")
    return annotation is ClassVar or get_origin(annotation) is ClassVar


def document_properties(cls: type, *, members: Collection[str] | None = None) -> str:
    """A class's public properties and dataclass fields (in alphabetical order), or ``""`` if none.

    Iterates ``vars(cls)``, so user-defined methods and properties on ``Enum``
    subclasses are found.
    A dataclass field's docstring, if any, comes from its ``field(metadata={"doc": ...})``.
    """
    entries: list[tuple[str, str]] = []

    # A plain property needs a getter to document; a cached_property always has one.
    for name, raw in _get_public_members(cls):
        if members is not None and name not in members:
            continue
        if (isinstance(raw, property) and raw.fget is not None) or isinstance(
            raw, cached_property
        ):
            entries.append((name, document_property(name, raw)))

    documented = {name for name, _ in entries}
    field_types = inspect.get_annotations(cls)
    for name, doc in _get_fields(cls):
        if name not in documented and (members is None or name in members):
            label = _typed_label(name, field_types.get(name, _MISSING))
            entries.append((name, _member_line(label, doc)))

    if not entries:
        return ""
    return "**Properties**\n\n" + "\n".join(entry for _, entry in sorted(entries))


def document_property(name: str, member: property | cached_property) -> str:
    """Document a single property or cached_property."""
    fn = member.func if isinstance(member, cached_property) else member.fget
    doc = inspect.getdoc(fn) if fn else None
    annotations = inspect.get_annotations(fn) if fn else {}
    tp = annotations.get("return", _MISSING)
    return _member_line(_typed_label(name, tp), doc)


def document_methods(cls: type, *, members: Collection[str] | None = None) -> str:
    """A class's public methods (in alphabetical order), or ``""`` if none."""
    entries: list[str] = []

    for name, raw in _get_public_members(cls):
        if members is not None and name not in members:
            continue
        if isinstance(raw, (classmethod, staticmethod)):
            entries.append(document_method(name, getattr(cls, name), raw))
        elif inspect.isfunction(raw):
            entries.append(document_method(name, raw))
    if not entries:
        return ""
    return "**Methods**\n\n" + "\n".join(entries)


def document_method(name: str, member: Any, raw: Any | None = None) -> str:
    """Document a single method, including classmethod/staticmethod tags."""
    if isinstance(raw, classmethod):
        tag = " (classmethod)"
    elif isinstance(raw, staticmethod):
        tag = " (staticmethod)"
    else:
        tag = ""
    return _member_line(f"`{name}{signature(member)}`{tag}", inspect.getdoc(member))


def _get_public_members(cls: type) -> list[tuple[str, Any]]:
    """Get a class's own public members, sorted by name."""
    return sorted(
        ((name, raw) for name, raw in vars(cls).items() if not name.startswith("_")),
        key=lambda x: x[0],
    )


def _get_fields(cls: type) -> list[tuple[str, str | None]]:
    """A class's own annotated fields, including dataclass metadata docstrings.

    ``doc`` is the field's ``metadata["doc"]`` (``None`` if it carries none).
    ``ClassVar`` and ``InitVar`` pseudo-fields are already excluded by :func:`dataclasses.fields`.
    """
    own = inspect.get_annotations(cls)
    if not dataclasses.is_dataclass(cls):
        return [
            (name, None)
            for name, annotation in own.items()
            if not name.startswith("_") and not _is_class_var(annotation)
        ]
    return [
        (f.name, f.metadata.get("doc"))
        for f in dataclasses.fields(cls)
        if f.name in own and not f.name.startswith("_")
    ]


def _member_line(label: str, doc: str | None) -> str:
    """A member bullet: ``label`` followed by its full docstring, or just ``label`` when there is no docstring."""
    body = (doc or "").strip()
    return bullet(f"{label} -- {body}" if body else label)


_MISSING = object()


def _typed_label(name: str, annotation: object) -> str:
    """A member name, suffixed with ``: <type>`` when ``annotation`` is given."""
    if annotation is _MISSING:
        return f"`{name}`"
    return f"`{name}: {_annotation(annotation)}`"


def _annotation(tp: object) -> str:
    """Render a type annotation.

    Accepts both raw string annotations (from ``from __future__ import annotations``)
    and evaluated type objects, so it never has to resolve forward references.
    """
    text = tp if isinstance(tp, str) else inspect.formatannotation(tp)
    return _shorten_qualified_names(text)


def document_functions(functions: Iterable[Callable], heading_level: int = 1) -> str:
    """Markdown documentation for the given functions, one section each."""
    functions = tuple(functions)
    if not functions:
        return ""
    return "\n\n".join(
        (
            heading("Functions", heading_level),
            *(document_function(fn, heading_level + 1) for fn in functions),
        )
    )


def document_function(fn: Callable, heading_level: int = 1) -> str:
    """Document a single function, with its signature and docstring."""
    if not inspect.isfunction(fn):
        raise TypeError(f"Expected a function, got {type(fn)}")
    blocks = [heading(f"`{fn.__name__}{signature(fn)}`", heading_level)]
    doc = inspect.getdoc(fn)
    if doc and doc.strip():
        blocks.append(doc.strip())
    return "\n\n".join(blocks)


def document_constants(
    constants: Iterable[tuple[str, Any]], heading_level: int = 1
) -> str:
    """Document a list of constants, given as (name, value) tuples."""
    constants = tuple(constants)
    if not constants:
        return ""
    return "\n".join(
        (
            heading("Constants", heading_level),
            "",
            *(bullet(document_constant(name, value)) for name, value in constants),
        )
    )


def document_constant(name: str, value: Any) -> str:
    """Document a single constant."""
    return f"`{name}` = `{_clean_repr(repr(value))}`"


def signature(obj: Callable) -> str:
    """Render annotations without quotes, preserving string default literals."""
    sig = inspect.signature(obj)
    params = []
    for name, param in sig.parameters.items():
        if name == "self" or name.startswith("_"):
            continue
        if param.annotation is not inspect.Parameter.empty:
            param = param.replace(
                annotation=_SignatureText(_annotation(param.annotation))
            )
        if param.default is not inspect.Parameter.empty:
            literal = repr(param.default)
            if not isinstance(param.default, str):
                literal = _clean_repr(literal)
            param = param.replace(default=_SignatureText(literal))
        params.append(param)
    result = sig.return_annotation
    if result is not inspect.Signature.empty:
        result = _SignatureText(_annotation(result))
    return str(sig.replace(parameters=params, return_annotation=result))


class _SignatureText(str):
    """Already-formatted text for inspect's annotation/default repr hooks."""

    def __repr__(self) -> str:
        return str(self)


def _clean_repr(text: str) -> str:
    """``text`` with object and enum reprs collapsed and module paths dropped."""
    text = _ENUM_REPR.sub(r"\1", _OBJECT_REPR.sub(r"\1", text))
    return _shorten_qualified_names(text)


# Drop module path from evaluated annotations
_QUALIFIED = re.compile(r"\b(?:[a-z]\w*\.)+(\w+)")
# Drop ``<Enum.MEMBER: value>`` reprs from enum defaults
_ENUM_REPR = re.compile(r"<(\w+\.\w+): [^>]*>")
# Reduce ``<function f at 0x...>`` and ``<class 'm.C'>`` reprs to their name
_OBJECT_REPR = re.compile(
    r"<(?:class|function|built-in function) '?([\w.]+)'?(?: at 0x[0-9a-f]+)?>"
)


def _shorten_qualified_names(text: str) -> str:
    """Shorten fully-qualified names to their final component; e.g. ``collections.abc.Iterable`` -> ``Iterable``.

    Names whose prefix is not an imported module -- import aliases like ``np.ndarray``,
    or dotted strings -- are left alone.
    """

    def drop_module_path(match: re.Match[str]) -> str:
        module, _, name = match[0].rpartition(".")
        return name if module in sys.modules else match[0]

    return _QUALIFIED.sub(drop_module_path, text)
