"""Share missing BrickNet data across LDraw redirects and decoration variants.

Exact data wins, then rigid redirects/aliases, then the unpatterned part or a
patterned sibling. Mould letters, assembly suffixes and posed forms stay intact.
The resulting source pose maps donor geometry into the requested part's frame.
"""

from __future__ import annotations

import heapq
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import count
from typing import TYPE_CHECKING

from ...geometry import Pose
from ..conversion import pose_from_type1

if TYPE_CHECKING:
    from .library import Library

# LDraw's p/d codes are two or three alphanumerics, or four digits.
# https://www.ldraw.org/part-number-spec.html
_DECORATION = re.compile(r"^(.+?)[pd](?:[a-z0-9]{2,3}|\d{4})$")


@dataclass(frozen=True)
class PartSource:
    """A donor id and the rigid pose taking it into the requested part's frame."""

    part_id: str
    pose: Pose = field(default_factory=Pose)

    @classmethod
    def from_ldraw(cls, part_id: str, values: list[float]) -> PartSource | None:
        """Decode a rigid type-1 transform; skip scaled or reflected donors."""
        try:
            pose = pose_from_type1(values)
        except ValueError:
            return None
        return cls(part_id, pose)


class PartFallbacks:
    """Deterministic data donors connected by redirects and p/d suffixes."""

    def __init__(
        self,
        lib: Library,
        aliases: Iterable[tuple[str, PartSource]] = (),
    ) -> None:
        self._edges: dict[str, list[tuple[str, Pose, int]]] = defaultdict(list)
        for part_id, description in lib.descriptions.items():
            if description.startswith(("~Moved to ", "=")):
                source = _wrapper(lib, part_id)
                if source is not None:
                    self._link(part_id, source, decoration=False)
            if not description.startswith("Sticker "):
                base = pattern_base(part_id)
                if base is not None:
                    self._link(part_id, PartSource(base), decoration=True)
        for part_id, source in aliases:
            self._link(part_id, source, decoration=False)
        for edges in self._edges.values():
            edges.sort(key=lambda edge: edge[0])

    def resolve(self, part_id: str, available: set[str]) -> PartSource | None:
        """Find a donor with data; avoid decoration changes when a redirect works.

        Search is cycle-safe. Ties prefer fewer links, then lexical traversal,
        so filesystem and input order cannot change the chosen donor.
        """
        order = count()
        pending = [(0, 0, next(order), part_id, Pose())]
        visited: set[str] = set()
        while pending:
            decorations, hops, _, current, pose = heapq.heappop(pending)
            if current in visited:
                continue
            if current in available:
                return PartSource(current, pose)
            visited.add(current)
            for target, transform, decorated in self._edges.get(current, ()):
                if target not in visited:
                    heapq.heappush(
                        pending,
                        (
                            decorations + decorated,
                            hops + 1,
                            next(order),
                            target,
                            pose.compose(transform),
                        ),
                    )
        return None

    def sources(
        self, part_ids: Iterable[str], available: Iterable[str]
    ) -> dict[str, PartSource]:
        """Resolve all requested ids independently against original donor data."""
        available = set(available)
        return {
            part_id: source
            for part_id in sorted(part_ids)
            if (source := self.resolve(part_id, available)) is not None
        }

    def _link(self, part_id: str, source: PartSource, *, decoration: bool) -> None:
        self._edges[part_id].append((source.part_id, source.pose, int(decoration)))
        self._edges[source.part_id].append(
            (part_id, source.pose.inverse, int(decoration))
        )


def pattern_base(part_id: str) -> str | None:
    """The same mould/assembly without its terminal pattern or sticker code."""
    match = _DECORATION.fullmatch(part_id)
    return match[1] if match else None


def _wrapper(lib: Library, part_id: str) -> PartSource | None:
    geometry = [
        fields
        for line in lib.lines(f"{part_id}.dat") or ()
        if (fields := line.split()) and fields[0] in {"1", "2", "3", "4", "5"}
    ]
    if len(geometry) != 1:
        return None
    fields = geometry[0]
    if fields[0] != "1" or len(fields) != 15 or fields[1] != "16":
        return None
    target = fields[14].removesuffix(".dat")
    if target not in lib.descriptions:
        return None
    return PartSource.from_ldraw(target, list(map(float, fields[2:14])))
