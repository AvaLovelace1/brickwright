"""Tests for finding catalog parts by keyword."""

import re
import subprocess
import sys
from itertools import pairwise

import numpy
import pytest

from bricklayer import Box, PartSpec, api_reference, search_parts
from bricklayer.ldraw import partdata
from bricklayer.parts.search import (
    _DEFAULT_FIELDS,
    _FILTERABLE_FIELDS,
    _OPT_IN_FIELDS,
    SEARCHABLE_FIELDS,
    _index_for,
    _public_properties,
    searchable_fields,
)

#: Source for a fresh interpreter: give `PartSpec` a `description` property
#: *before* `search` computes its module constants, then report which of them
#: picked it up. A subprocess because those constants are computed once at
#: import, so exercising the real import-time path in-process would leak a
#: reloaded module into the rest of the suite.
_EXTENSIBILITY_PROBE = """
import importlib

from bricklayer.parts import catalog, search


def description(self) -> str:
    return "a description"


catalog.PartSpec.description = property(description)
search = importlib.reload(search)
try:
    accepted = search._validated_fields(["description"]) == ("description",)
except ValueError:
    accepted = False
print(
    "description" in search.SEARCHABLE_FIELDS,
    "description" in search._DEFAULT_FIELDS,
    "description" in search._FILTERABLE_FIELDS,
    accepted,
)
"""


def _words(spec: PartSpec) -> set[str]:
    """The whole words a default keyword search matches ``spec`` on."""
    text = f"{spec.name} {spec.category} {spec.subcategory or ''}".lower()
    return set(re.findall(r"[a-z0-9]+", text))


class TestMatching:
    def test_every_term_must_match(self) -> None:
        """AND semantics: 'round plate' means both, or the result is noise.

        Asserted on the unclamped result set, because the top 20 cannot see
        this: BM25's additive scoring already ranks both-term documents above
        one-term ones, so removing the AND gate leaves the first 20 hits
        identical. What it changes is the set behind them -- dozens of round
        plates become thousands of parts that are merely round or merely a
        plate."""
        results = search_parts("round", "plate", limit=100_000)
        assert results
        for spec in results:
            words = _words(spec)
            assert "round" in words and "plate" in words

    def test_matching_ignores_case_and_extra_space(self) -> None:
        assert search_parts("BRICK") == search_parts("  brick  ")

    def test_a_phrase_means_the_same_as_its_words(self) -> None:
        """`*terms` invites a caller to pass a phrase, and an agent will. A
        term is split into words the same way a part's text is, so spaces and
        punctuation inside one are boundaries, not characters to match --
        otherwise this query answers `()`, which reads as "no such part" and
        invites an invented part id."""
        assert search_parts("brick 2 x 4") == search_parts("brick", "2", "x", "4")
        assert search_parts("brick,") == search_parts("brick")

    def test_searching_one_field_excludes_matches_from_others(self) -> None:
        """`fields=` is a restriction, and it has to bite. "Wheel 56 x 46
        Technic Racing" matches `technic` in its name while its category is
        "Wheel", so scoping to the category must drop it.

        The limit has to exceed both result sets or they both clamp to it and
        the comparison is vacuous -- an earlier draft used 200 and would have
        compared 200 against 200. Compare sets, not lengths, so this does not
        become a count that the catalog can invalidate."""
        everywhere = search_parts("technic", limit=100_000)
        by_category = search_parts("technic", fields=["category"], limit=100_000)
        assert by_category
        assert {s.ldraw_id for s in by_category} < {s.ldraw_id for s in everywhere}
        for spec in by_category:
            assert "technic" in spec.category.lower()

    def test_an_unknown_field_says_which_fields_exist(self) -> None:
        """Two fields, not all four in a fixed order: the point is that the
        message lists what is valid, and it must survive `PartSpec` gaining a
        property, which is the feature's whole purpose."""
        with pytest.raises(ValueError, match="colour.*category.*name"):
            search_parts("brick", fields=["colour"])

    def test_an_empty_field_list_is_a_library_error_not_a_bm25_crash(self) -> None:
        """`fields=[]` would index an empty corpus and die inside `bm25s`
        with `max() iterable argument is empty`, preceded by a numpy warning.
        The contract is this module's own ValueError, naming what is valid."""
        with pytest.raises(ValueError, match="no searchable field.*category.*name"):
            search_parts("brick", fields=[])

    def test_a_single_field_name_is_one_field_not_its_letters(self) -> None:
        assert search_parts("technic", fields="category") == search_parts(
            "technic", fields=["category"]
        )

    def test_no_match_is_empty_not_an_error(self) -> None:
        assert search_parts("zzzznotapart") == ()

    def test_a_document_holding_a_term_never_scores_zero(self) -> None:
        """`search_parts` runs its AND gate over the documents BM25 scored
        above zero, skipping the other ~14,000 rather than testing the whole catalog.
        That is only sound while a document containing a term always scores
        above zero on it -- true of BM25's Lucene IDF, `log(1 + (N-df+0.5) /
        (df+0.5))`, which is strictly positive.

        Checked over the whole vocabulary, not a sample: a term where it
        failed would silently vanish from every result set that needs it.
        """
        index = _index_for(_DEFAULT_FIELDS)
        vocabulary = {term for terms in index.doc_terms for term in terms}
        assert len(vocabulary) > 1000, "the corpus looks empty -- has it rotted?"
        for term in sorted(vocabulary):
            scored = set(numpy.flatnonzero(index.bm25.get_scores([term])).tolist())
            holders = {i for i, terms in enumerate(index.doc_terms) if term in terms}
            assert holders <= scored, term

    def test_zero_terms_orders_by_popularity_alone(self) -> None:
        """No search terms at all must not reach BM25 (`bm25s.get_scores([])`
        raises `IndexError`) -- a filter-only call routes through here.
        Ordering falls back to the popularity prior alone."""
        results = search_parts(limit=5)
        assert len(results) == 5
        popularities = [partdata.popularity(spec.ldraw_id) for spec in results]
        assert popularities == sorted(popularities, reverse=True)


class TestRanking:
    def test_a_pattern_is_not_the_answer_to_a_plain_query(self) -> None:
        """Someone searching `tree` wants a tree, not a slope with a palm tree
        printed on it. This is the query that pins the corpus decision: with
        `features` in the document its words count twice, and the patterned
        slope wins. `arch` does NOT discriminate here -- it gives the same
        answer either way -- so do not substitute it."""
        assert "pattern" not in search_parts("tree", limit=1)[0].name.lower()

    def test_the_structural_head_outranks_a_name_that_merely_contains_it(
        self,
    ) -> None:
        """The other half of the corpus decision. "Technic Axle 3" carries
        subcategory "Axle"; "Technic Connector (Axle) with Axle 1.5" carries
        "Connector (Axle)". Repeating subcategory into the document is what
        puts the real axle first -- drop it and the connector wins."""
        assert search_parts("axle", limit=1)[0].subcategory == "Axle"

    def test_a_feature_query_works_without_features_in_the_corpus(self) -> None:
        """The objection this design has to answer. `features` is a substring
        of `name` for all 11,562 parts that have one, so its words are still
        indexed -- via the name."""
        assert (
            "groove" in search_parts("brick", "with", "groove", limit=1)[0].name.lower()
        )

    def test_the_obvious_query_returns_the_obvious_part(self) -> None:
        """The canonical case, and the one that broke two draft rankings: a
        four-token name matching four terms must beat a fourteen-token one that
        merely contains the same words. `3001` is the test's subject here, so
        the id literal is legitimate."""
        assert search_parts("brick", "2", "x", "4", limit=1)[0].ldraw_id == "3001"

    def test_the_plain_head_beats_the_hundreds_of_novelty_ones(self) -> None:
        """Hundreds of `Minifig Head *` parts score identically on text --
        "Minifig Head Yeti", "Minifig Head Duck" and "Minifig Oar Head" all
        run to the same token count with the same two terms in it -- so BM25
        alone cannot separate them and the part id breaks the tie. Measured
        with ALPHA at 0: "Minifig Head Yeti", subcategory "Head Yeti". The
        popularity prior is the whole reason a query for a minifig head
        answers with a head, subcategory "Head", rather than a yeti's."""
        for spec in search_parts("minifig", "head", limit=5):
            assert spec.subcategory == "Head"

    def test_popularity_cannot_bury_a_rare_exact_match(self) -> None:
        """The risk a popularity prior introduces, pinned at the real bar.
        'Minifig Hand' (3820) is in 16 sets and competes with hand *tools* in
        far more, so it does not lead -- but it must stay within easy reach.

        Measured: rank 3 at ALPHA 0.25 and 0.5, rank 4 at 1.0, rank 6 at 2.0.
        Top-5 membership alone would still pass at ALPHA 1.0, so it cannot
        catch ALPHA being raised -- the bound is top 3, which passes at 0.25
        and 0.5 and fails at 1.0, so this is the assertion that actually fails
        first if ALPHA is raised."""
        results = search_parts("minifig", "hand", limit=3)
        assert "3820" in [spec.ldraw_id for spec in results]

    def test_a_whole_word_query_does_not_match_inside_a_longer_word(self) -> None:
        """'Minifig Handlebars' is in 665 sets -- 40x the plain hand -- so if
        matching were by prefix or substring, popularity would put it on top of
        a query for a hand. Whole-word matching excludes it outright."""
        found = search_parts("minifig", "hand", limit=20)
        assert found
        assert not any("handlebar" in spec.name.lower() for spec in found)

    def test_a_common_part_outranks_a_rare_one_that_matches_as_well(self) -> None:
        """The user's stated requirement: do not make them scan rare parts.

        `bracket` is the measured query. Every plain "Bracket A x B x C"
        scores alike on text, so the prior is the entire difference: with
        ALPHA at 0 the winner is "Bracket 4 x 7 x 3", in single-digit sets.
        `plate 1 x 2` does NOT discriminate -- BM25 alone already leads with
        a part in 9,000 sets -- so do not substitute it."""
        results = search_parts("bracket", limit=10)
        assert partdata.popularity(results[0].ldraw_id) > 100

    def test_hits_that_score_alike_come_back_in_id_order(self) -> None:
        """The tiebreak, which is what makes an ordering reproducible across
        processes rather than merely within one. Two identical calls in one
        process would agree whatever the sort key were, which is why that is
        not what this asserts.

        Scoping to `category` gives every hit the same one-word document, so
        BM25 scores every one of them identically -- the popularity prior and
        the id tiebreak are the only things left to order them by, and both
        are observable from out here, so the whole expected order can be
        recomputed rather than eyeballed."""
        results = search_parts("baseplate", fields=["category"], limit=100_000)
        keyed = [(-partdata.popularity(s.ldraw_id), s.ldraw_id) for s in results]
        assert any(a[0] == b[0] for a, b in pairwise(keyed)), "no tie to break"
        assert keyed == sorted(keyed)

    def test_limit_is_respected(self) -> None:
        assert len(search_parts("brick", limit=5)) == 5

    @pytest.mark.parametrize("terms", [(), ("brick",)])
    def test_a_negative_limit_is_rejected(self, terms: tuple[str, ...]) -> None:
        with pytest.raises(ValueError, match="limit"):
            search_parts(*terms, limit=-1)

    def test_a_part_without_a_factory_is_findable(self) -> None:
        """Part search is independent of convenience factories."""
        found = search_parts("ladder", limit=20)
        assert any("Ladder" in spec.name for spec in found)


class TestFilters:
    def test_a_filter_constrains_the_results(self) -> None:
        results = search_parts("round", category="Tile", limit=20)
        assert results
        for spec in results:
            assert spec.category == "Tile"

    def test_a_filter_works_with_no_search_terms(self) -> None:
        """Browsing a category is a search with no words in it."""
        results = search_parts(category="Baseplate", limit=10)
        assert results and all(s.category == "Baseplate" for s in results)

    def test_a_structured_filter_is_exact_not_textual(self) -> None:
        sized = search_parts(shape=Box(4, 2, 1), limit=20)
        assert sized and all(s.shape == Box(4, 2, 1) for s in sized)

    def test_an_unknown_filter_names_the_valid_ones(self) -> None:
        with pytest.raises(ValueError, match="colour.*category"):
            search_parts("brick", colour="red")

    def test_filters_do_not_leak_into_later_searches(self) -> None:
        assert search_parts(category="Tile", limit=5)
        results = search_parts("ladder", category="Ladder", limit=20)
        assert results and all(spec.category == "Ladder" for spec in results)


class TestDocumentation:
    def test_search_is_exported_for_agents(self) -> None:
        assert "search_parts" in api_reference()


class TestSearchableFields:
    def test_the_text_fields_are_discovered_not_listed(self) -> None:
        assert set(SEARCHABLE_FIELDS) == {"name", "category", "subcategory", "features"}

    def test_a_new_text_field_is_searchable_with_no_change_here(self) -> None:
        """The design's central promise: PartSpec grows a field, search finds
        it. Asserted against a real subclass rather than a comment."""

        class Described(PartSpec):
            @property
            def description(self) -> str:
                return "a test description"

        assert "description" in searchable_fields(Described)

    def test_the_module_constants_are_derived_not_written_out(self) -> None:
        """The subclass above pins the introspection helper; production
        extensibility runs through three module constants computed from
        `PartSpec` at import. Write any of them out as a literal and it goes
        stale the moment `PartSpec` gains a property."""
        assert SEARCHABLE_FIELDS == searchable_fields(PartSpec)
        assert _FILTERABLE_FIELDS == _public_properties(PartSpec)
        assert set(_DEFAULT_FIELDS) == set(SEARCHABLE_FIELDS) - _OPT_IN_FIELDS

    def test_a_new_text_field_reaches_every_module_constant(self) -> None:
        """The same promise end to end, at import time in a fresh interpreter:
        a `description` property on `PartSpec` has to reach all three
        constants and pass field validation with no edit to `search`. This is
        the assertion a literal spelling today's fields correctly would still
        fail -- the equalities above would not."""
        probe = subprocess.run(
            [sys.executable, "-c", _EXTENSIBILITY_PROBE],
            capture_output=True,
            text=True,
            check=True,
        )
        assert probe.stdout.split() == ["True"] * 4

    def test_a_structured_field_is_not_keyword_searchable(self) -> None:
        """Shapes and chirality are structured filters, not searchable text."""
        for field in ("shape", "chirality"):
            assert field not in SEARCHABLE_FIELDS
