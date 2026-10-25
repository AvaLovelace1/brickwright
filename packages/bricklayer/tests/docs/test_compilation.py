"""Tests for the generated docs."""

import ast
import inspect
import re
from collections import Counter
from fractions import Fraction

import pytest

import bricklayer
from bricklayer import (
    Color,
    Finish,
    FrameVariant,
    api_reference,
    colors,
    construction,
    geometry,
    modeling,
    parts,
)
from bricklayer.construction import fill, registry
from bricklayer.docs.compilation import (
    _list_available_colors,
    describe_component_factory,
    list_valid_kwarg_combos,
)
from bricklayer.docs.utils import (
    bullet,
    code_blocks,
    document_function,
    heading,
)
from bricklayer.geometry import connections
from bricklayer.modeling import articulation, transforms
from bricklayer.parts import element
from bricklayer.parts.catalog import all_parts


@pytest.fixture
def patch_factories(monkeypatch):
    def patch(factories):
        monkeypatch.setattr(registry, "COMPONENT_FACTORIES", dict(factories))

    return patch


@pytest.fixture
def ref():
    return api_reference()


@pytest.fixture(autouse=True)
def _clear_cache():
    api_reference.cache_clear()
    yield
    api_reference.cache_clear()


@pytest.fixture
def factory(patch_factories):
    """A registered custom factory whose valid kwargs are a fixed, known set."""

    def my_factory(width, depth, height, *, color=Color.WHITE):
        """Custom factory.

        A second paragraph with more detail.
        """

    def my_valid_kwargs():
        return (
            (("width", 2), ("depth", 1), ("height", 1), ("variant", None)),
            (
                ("width", 4),
                ("depth", 2),
                ("height", 1),
                ("variant", FrameVariant.ARCHED),
            ),
            (("width", 1), ("depth", 2), ("height", Fraction(5, 3)), ("variant", None)),
            (
                ("width", 1),
                ("depth", 2),
                ("height", Fraction(2)),
                ("variant", None),
            ),
        )

    patch_factories([(my_factory, my_valid_kwargs)])
    return my_factory


def snippet_params(blocks):
    """Parametrization for code blocks, identified by the heading each sits under."""
    params: list = []
    seen: Counter[str] = Counter()
    for block in blocks:
        slug = re.sub(r"\W+", "-", block.heading).strip("-").lower() or "untitled"
        seen[slug] += 1
        params.append(pytest.param(block, id=f"{slug}-{seen[slug]}"))
    return params


def run_snippet(block, tmp_path, monkeypatch):
    """Run a complete snippet in a scratch directory; skip a fragment after parsing it.

    The snippet is written out and compiled against that path so a failure's traceback
    shows the offending line.
    """
    ast.parse(block.code)  # even a fragment must be syntactically valid
    if not block.is_complete:
        pytest.skip(
            "fragment: does not open with an import, so it needs context to run"
        )
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "snippet.py"
    source.write_text(block.code)
    exec(compile(block.code, str(source), "exec"), {"__name__": "__snippet__"})


REFERENCE_SNIPPETS = [b for b in code_blocks(api_reference()) if b.language == "python"]


class TestAPIReference:
    @pytest.mark.parametrize(
        "module",
        [
            bricklayer,
            geometry,
            connections,
            parts,
            element,
            construction,
            modeling,
            colors,
            fill,
            articulation,
            transforms,
        ],
    )
    def test_module_docstrings_are_the_guide_source(self, module, monkeypatch):
        marker = "Unique guide text from the module docstring."
        monkeypatch.setattr(module, "__doc__", f"Reference section.\n\n{marker}")
        assert marker in api_reference()

    def test_method_docstring_changes_flow_into_reference(self, monkeypatch):
        marker = "Updated placement guidance from its method docstring."
        monkeypatch.setattr(bricklayer.LegoBuild.add, "__doc__", marker)
        assert marker in api_reference()

    def test_omits_file_io_and_simulation_instructions(self, ref):
        for name in bricklayer.io.__all__:
            assert name not in ref
        assert "USD" not in ref
        assert "0 STEP" not in ref

    def test_includes_every_factory_and_its_current_argument_choices(self, ref):
        for factory in registry.COMPONENT_FACTORIES:
            assert describe_component_factory(factory, heading_level=3) in ref

    def test_lists_enum_members(self, ref):
        assert "OPAL_TRANS_LIGHT_BLUE" in ref  # Color
        assert "FRONT" in ref  # Rotation aliases

    def test_includes_construction_helpers(self, ref):
        assert "mirror(" in ref
        assert "fill_box(" in ref

    def test_documents_catalog_identity_types(self, ref):
        # The catalog-exploration functions take and return PartSpec / PartShape
        # values; those types are documented so an agent can build and read them.
        exploring = ref.split("## Exploring the catalog", 1)[1]
        assert "class `PartSpec`" in exploring
        assert "class `Box(PartShape)`" in exploring
        assert "class `Footprint(PartShape)`" in exploring

    def test_factory_options_are_documented_with_the_helpers(self, ref):
        assert ref.index("Component factories") < ref.index("enum `FrameVariant")
        assert ref.index("class `Element") < ref.index("Component factories")

    def test_the_reference_presents_id_construction_as_the_main_path(self, ref):
        assert "Element(part_id, color)" in ref

    def test_the_reference_teaches_search_as_the_way_to_find_a_part(self, ref):
        exploring = ref.split("## Exploring the catalog", 1)[1]
        assert "search_parts(" in exploring
        assert "Element(spec.ldraw_id, color)" in exploring
        assert re.search(r"\bkeyword", exploring, re.IGNORECASE)
        assert re.search(r"\bfilter", exploring, re.IGNORECASE)
        assert re.search(r"popular", exploring, re.IGNORECASE)

    def test_every_ldraw_name_the_guides_quote_is_a_real_part(self, ref):
        """The guides quote LDraw names verbatim to teach how a part name states a
        dimension run, so a name that does not resolve teaches a lie. LEGO's
        own naming appears once, for contrast, and is deliberately not an LDraw
        name.
        """
        lego_naming = {"Slope 45 2 x 3"}
        catalogued = {spec.name for spec in all_parts()}
        quoted = set(re.findall(r'["`]([A-Z][^"`\n]*?\s+x\s+[^"`\n]*?)["`]', ref))

        assert quoted - lego_naming, "no LDraw names quoted -- has the regex rotted?"
        assert lego_naming <= quoted, "the LEGO-naming contrast went missing"
        for name in sorted(quoted - lego_naming):
            assert name in catalogued, f"the guides quote {name!r}, which no part has"


class TestConnectorsSection:
    def test_documents_the_connector_classes(self, ref):
        assert "class `Connector`" in ref
        assert "class `ConnectorType`" in ref

    def test_documents_the_joint_kinds_and_params(self, ref):
        assert "enum `JointKind`" in ref
        for params in ("Fixed", "Revolute", "Prismatic", "Cylindrical", "Ball"):
            assert f"class `{params}`" in ref

    def test_explains_connecting_parts(self, ref):
        connectors = ref.split("## Connections", 1)[1]
        assert "connect(" in connectors

    def test_the_guide_names_no_unexported_connection_function(self):
        """A reader can only call what ``bricklayer`` exports."""
        guide = inspect.getdoc(connections)
        assert guide is not None
        unexported = [
            name
            for name, obj in vars(connections).items()
            if inspect.isfunction(obj)
            and obj.__module__ == connections.__name__
            and not name.startswith("_")
            and name not in bricklayer.__all__
        ]
        assert unexported, "no unexported functions -- has the check rotted?"
        for name in unexported:
            assert f"`{name}" not in guide, f"the guide names {name!r}"


class TestReferenceSnippets:
    @pytest.mark.parametrize("block", snippet_params(REFERENCE_SNIPPETS))
    def test_every_snippet_runs(self, block, tmp_path, monkeypatch):
        run_snippet(block, tmp_path, monkeypatch)

    def test_the_reference_has_snippets_to_run(self, ref):
        assert any(b.is_complete for b in code_blocks(ref))

    def test_every_fence_uses_a_known_language(self, ref):
        """A typo'd info string would drop a snippet from the suite unnoticed."""
        assert {b.language for b in code_blocks(ref)} <= {"", "python", "text"}


class TestListAvailableColors:
    def test_lists_every_color_under_the_heading(self):
        text = _list_available_colors()
        assert text.startswith("### Available colors")
        for color in Color:
            assert color.name in text

    def test_describes_each_used_finish(self):
        text = _list_available_colors()
        for finish in Finish:
            if any(c.finish is finish for c in Color):
                assert f"{finish.display_name}" in text
                assert finish.__doc__ and finish.__doc__ in text


class TestDescribeComponentFactory:
    def test_prints_function_docs_followed_by_valid_kwarg_combos(self, factory):
        text = describe_component_factory(factory)
        assert text == "\n\n".join(
            (
                document_function(factory),
                list_valid_kwarg_combos(factory, heading_level=2),
            )
        )

    def test_excludes_valid_kwarg_combos_if_none_are_available(self, patch_factories):
        def my_factory():
            pass

        patch_factories([(my_factory, lambda: ())])
        assert describe_component_factory(my_factory) == document_function(my_factory)


class TestListValidKwargCombos:
    def test_lists_every_valid_kwarg_combination_as_a_value_tuple(self, factory):
        assert list_valid_kwarg_combos(factory) == "\n".join(
            (
                heading(
                    "Valid argument combinations `(width, depth, height, variant)`"
                ),
                "",
                bullet("`(2, 1, 1, None)`"),
                bullet(
                    "`(4, 2, 1, FrameVariant.ARCHED)`"
                ),  # Enums render with __repr__
                bullet("`(1, 2, 5/3, None)`"),  # Fractions render as a rational number
                bullet("`(1, 2, 2, None)`"),  # Integer-valued Fractions render as int
            )
        )

    @pytest.mark.parametrize("my_valid_kwargs", [lambda: (), lambda: None])
    def test_is_empty_for_a_factory_with_no_valid_kwarg_combos(
        self, patch_factories, my_valid_kwargs
    ):
        def my_factory():
            pass

        patch_factories([(my_factory, my_valid_kwargs)])
        assert list_valid_kwarg_combos(my_factory) == ""
