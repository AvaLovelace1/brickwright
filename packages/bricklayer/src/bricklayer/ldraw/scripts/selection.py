"""Which LDraw parts the catalog holds.

A part is in when a collision mesh and an LDraw description can be resolved.
Extraction resolves rigid redirects and decoration families before applying
this rule. Connector data is optional; obsolete and component parts can also
be imported and collision-checked.
"""

from collections.abc import Iterable, Mapping


def select_part_ids(
    *,
    mesh_ids: Iterable[str],
    descriptions: Mapping[str, str],
) -> list[str]:
    """The catalog's part ids, sorted and unique.

    Every input is passed in rather than read, so the selection rule can be
    tested without an LDraw library or a BrickNet checkout.
    """
    return sorted(part_id for part_id in set(mesh_ids) if descriptions.get(part_id))
