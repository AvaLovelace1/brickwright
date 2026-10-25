"""Extract the LDraw description of every selected BrickLayer part.

The description is the first line of the part's ``.dat`` file. One that redirects
(``~Moved to <target>``) is followed to its target and the resolved id's
description is used instead. Parsing happens at load, in
:func:`~bricklayer.ldraw.naming.parse_description`, so this file commits only
what the LDraw library states.
"""

import sys
from collections.abc import Iterable
from pathlib import Path

from ..meshes import DATA_DIR
from .library import (
    Library,
    emit,
    extractor_parser,
    redirect_target,
    selected_part_ids,
)

OUTPUT = DATA_DIR / "part_taxonomy.json"

_MAX_REDIRECT_HOPS = 5


def main(argv: list[str] | None = None) -> int:
    args = extractor_parser(__doc__, output=OUTPUT, ldraw=True).parse_args(argv)

    lib = Library.find(args.ldraw)
    print(f"Using LDraw library: {lib.root}")
    part_ids = selected_part_ids(lib)
    taxonomy = build_taxonomy(lib, part_ids)
    print(
        f"Resolved {len(part_ids)} selected parts into "
        f"{len(taxonomy)} descriptions (redirect targets included)."
    )

    return emit(
        taxonomy,
        args.output,
        check=args.check,
        generated_by=_GENERATED_BY,
        note=_NOTE,
        units=None,
    )


def build_taxonomy(lib: Library, part_ids: Iterable[str]) -> dict[str, str]:
    """Every part in ``part_ids``'s resolved LDraw description, by id.

    A redirected id (``~Moved to <target>``) contributes its target's description
    under both its own id and the target's, so either id can be looked up.
    """
    taxonomy: dict[str, str] = {}
    for part_id in part_ids:
        resolved_id, description = resolve_redirect(lib, part_id)
        if description is None:
            print(f"  WARNING: no description found for {part_id}", file=sys.stderr)
            continue
        taxonomy[part_id] = description
        taxonomy[resolved_id] = description
    return taxonomy


def resolve_redirect(lib: Library, part_id: str) -> tuple[str, str | None]:
    """``part_id``'s resolved id and description, following ``~Moved to`` redirects.

    A chain longer than :data:`_MAX_REDIRECT_HOPS` (or a cycle) raises
    ``ValueError``. The description is ``None`` if ``part_id`` (or the id it
    redirects to) isn't in the library.
    """
    current = part_id
    for _ in range(_MAX_REDIRECT_HOPS + 1):
        description = lib.description(current)
        if not description:
            return current, None
        target = redirect_target(description)
        if target is None:
            return current, description
        current = target
    raise ValueError(f"redirect chain from {part_id} exceeds {_MAX_REDIRECT_HOPS} hops")


_GENERATED_BY = Path(__file__).name
_NOTE = (
    "Each selected part's description, from the official LDraw library, parsed "
    "at load. Do not edit by hand -- fix a bad reading in naming.py instead."
)


if __name__ == "__main__":
    raise SystemExit(main())
