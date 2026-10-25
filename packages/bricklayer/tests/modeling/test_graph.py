"""Connected components shared by model validation, motion, and export."""

import pytest

from bricklayer.modeling._graph import component_roots


@pytest.mark.parametrize(
    "count,edges,expected",
    [
        (0, [], set()),
        (3, [], {frozenset({0}), frozenset({1}), frozenset({2})}),
        (5, [(0, 2), (2, 4), (1, 3)], {frozenset({0, 2, 4}), frozenset({1, 3})}),
        (
            4,
            [(0, 1), (1, 2), (2, 0), (1, 0), (3, 3)],
            {frozenset({0, 1, 2}), frozenset({3})},
        ),
    ],
)
def test_component_roots(count, edges, expected):
    for ordered in (edges, list(reversed(edges))):
        roots = component_roots(count, ordered)
        groups = {
            frozenset(i for i, r in enumerate(roots) if r == root) for root in roots
        }
        assert groups == expected
