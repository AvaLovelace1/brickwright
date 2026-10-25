"""Connectivity primitives shared by validation, kinematics, and export."""

from collections.abc import Iterable


def component_roots(count: int, edges: Iterable[tuple[int, int]]) -> list[int]:
    """The representative of each node's connected component, by union-find."""
    parent = list(range(count))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = i = parent[parent[i]]
        return i

    for i, j in edges:
        parent[find(i)] = find(j)
    return [find(i) for i in range(count)]
