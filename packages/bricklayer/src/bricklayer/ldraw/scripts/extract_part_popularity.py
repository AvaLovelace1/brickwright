"""How many LEGO sets each catalogued part appears in.

Search ranks equally-good textual matches by this, so the brick a builder
actually reaches for comes before a variant they have never seen.

Source: Rebrickable's daily catalogue downloads, which may be used for any
purpose including commercial provided Rebrickable is acknowledged as the
source. See https://rebrickable.com/downloads/.

Rebrickable numbers a part by its LEGO design id, where LDraw may split that
id into variants (``3069a`` without a groove, ``3069b`` with one) or supersede
it entirely (``3023`` is a redirect to ``3023b``). So a direct match reaches
only about a third of the catalog; falling back to the base id takes it to
roughly two thirds. The rest are the obscure tail, and scoring them 0 puts
them last, which is where they belong.
"""

import csv
import gzip
import re
import tempfile
import urllib.request
from collections import defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path

from ..meshes import DATA_DIR
from ..partdata import part_ids
from .library import emit, extractor_parser

OUTPUT = DATA_DIR / "part_popularity.json"

_BASE_URL = "https://cdn.rebrickable.com/media/downloads"
_INVENTORIES = "inventories.csv.gz"
_INVENTORY_PARTS = "inventory_parts.csv.gz"
_DEFAULT_CACHE = Path(tempfile.gettempdir()) / "bricklayer-rebrickable-cache"

# LDraw's variant letter (3069b) and its pattern (3069bp01), composite (4079c01)
# and ``d`` suffixes.
_VARIANT_SUFFIX = re.compile(r"^(\d+)[a-z]$")
_PATTERN_SUFFIXES = (
    re.compile(r"p[a-z]*\d+.*$"),
    re.compile(r"c\d+.*$"),
    re.compile(r"d\d+.*$"),
)

_GENERATED_BY = "extract_part_popularity.py (Rebrickable inventories)"
_NOTE = (
    "Distinct LEGO sets each part appears in, from Rebrickable's catalogue"
    " downloads (https://rebrickable.com/downloads/); used here under Rebrickable's"
    " terms, which require it be acknowledged as the source. A part absent from"
    " this file is unscored, not zero-popularity -- see partdata.popularity()."
)


def main(argv: list[str] | None = None) -> int:
    parser = extractor_parser(__doc__, output=OUTPUT)
    parser.add_argument(
        "--cache",
        help="directory to cache Rebrickable's downloads in (default: a temp dir)",
    )
    args = parser.parse_args(argv)
    cache = Path(args.cache) if args.cache else _DEFAULT_CACHE
    cache.mkdir(parents=True, exist_ok=True)
    print(f"Using cache: {cache}")

    inventory_sets = load_inventory_sets(fetch(_INVENTORIES, cache))
    grouped = sets_per_part(fetch(_INVENTORY_PARTS, cache), inventory_sets)
    counts = {part_num: len(sets) for part_num, sets in grouped.items()}

    ids = sorted(part_ids())
    scored = score_parts(ids, counts)
    print(f"Scored {len(scored)} of {len(ids)} catalogued parts.")

    return emit(
        scored,
        args.output,
        check=args.check,
        generated_by=_GENERATED_BY,
        note=_NOTE,
        units=None,
    )


def candidate_ids(part_id: str) -> Iterator[str]:
    """``part_id``, then its base ids with variant and pattern/composite suffixes
    stripped, in lookup order.

    A pattern base is tried as-is and with its own variant letter stripped
    (``3069bp01`` -> ``3069b`` -> ``3069``).
    """
    yield part_id
    yield from _variant_stripped(part_id)
    for pattern in _PATTERN_SUFFIXES:
        base = pattern.sub("", part_id)
        if base and base != part_id:
            yield base
            yield from _variant_stripped(base)


def _variant_stripped(part_id: str) -> Iterator[str]:
    """``part_id`` with its trailing LDraw variant letter removed, if it has one."""
    variant = _VARIANT_SUFFIX.match(part_id)
    if variant:
        yield variant.group(1)


def score_parts(ids: Iterable[str], counts: dict[str, int]) -> dict[str, int]:
    """Every id in ``ids`` that resolves (directly or via a fallback) to a
    count in ``counts``, mapped to that count. An id with no match is
    omitted, not zeroed -- :func:`~bricklayer.ldraw.partdata.popularity`
    supplies the 0 for whichever ids this leaves out.
    """
    scored: dict[str, int] = {}
    for part_id in ids:
        for candidate in candidate_ids(part_id):
            count = counts.get(candidate)
            if count is not None:
                scored[part_id] = count
                break
    return scored


def load_inventory_sets(path: Path) -> dict[str, str]:
    """Rebrickable's ``inventories.csv``: each inventory id's set number."""
    with gzip.open(path, "rt", newline="") as f:
        return {row["id"]: row["set_num"] for row in csv.DictReader(f)}


def sets_per_part(path: Path, inventory_sets: dict[str, str]) -> dict[str, set[str]]:
    """Rebrickable's ``inventory_parts.csv``, accumulated into each part's
    distinct set numbers (deduped: a part in several colors in one set counts
    as one set). A row whose inventory isn't in ``inventory_sets`` is skipped.
    """
    grouped: dict[str, set[str]] = defaultdict(set)
    with gzip.open(path, "rt", newline="") as f:
        for row in csv.DictReader(f):
            set_num = inventory_sets.get(row["inventory_id"])
            if set_num:
                grouped[row["part_num"]].add(set_num)
    return grouped


def fetch(filename: str, cache: Path) -> Path:
    """``filename`` cached under ``cache``, downloading it from Rebrickable
    first if not already present."""
    path = cache / filename
    if not path.is_file():
        print(f"Downloading {filename}...")
        urllib.request.urlretrieve(f"{_BASE_URL}/{filename}", path)
    return path


if __name__ == "__main__":
    raise SystemExit(main())
