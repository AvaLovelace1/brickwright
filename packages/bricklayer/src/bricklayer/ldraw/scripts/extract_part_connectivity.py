"""Extract BrickNet connector labels for every part BrickNet covers.

BrickNet ships connector labels inside its package at ``_data/<version>``:

- ``labels.json.xz`` -- ``{stem.dat: {kind: {subtype: rows}}}``, with one more
  level for the polarized kinds (``hinge``/``ball``/``fixed``:
  ``{subtype: {"in"|"on": rows}}``). A row is
  ``[x, y, z, pitch_deg, roll_deg, extra]`` in the part's local LDraw frame (LDU),
  with trailing columns omitted when absent. ``extra`` is the frame yaw for a
  ``fixed`` connector and the slide span for an ``axle`` one.
- ``part_aliases.json.xz`` -- stem canonicalization for ids filed under another
  BrickNet stem.

A connector frame's **mating axis is its -Y**.

This script groups each original part's rows under its BrickLayer connector
type names and resolves missing labels through redirects and decoration variants.
Shifted or rotated donors use explicit connector frames in the target's coordinates.
Point ``--bricknet-data`` (or ``$BRICKNET_DATA``) at the ``_data/<version>`` directory.
"""

from collections.abc import Iterable, Iterator

from ...geometry import Pose
from ..connectivity import YAW_FAMILIES, frame_axes, resolve_name
from ..conversion import LDrawVec
from ..meshes import DATA_DIR
from ..partdata import connector_config
from .fallbacks import PartSource
from .library import (
    Library,
    catalog_sources,
    emit,
    extractor_parser,
    find_bricknet_data,
)

OUTPUT = DATA_DIR / "part_connectivity.json"

_NOTE = (
    "Connector rows per part, grouped by BrickLayer connector type name. A row is"
    " [x, y, z, pitch_deg, roll_deg, extra] in the part's local LDraw frame (LDU),"
    " with trailing columns omitted when absent; 'extra' is the frame yaw for a"
    " fixed connector and the slide span in LDU for an axle one. A connector's"
    " mating axis is its frame's -Y. Derived from BrickNet's labels.json.xz."
)


def main(argv: list[str] | None = None) -> int:
    parser = extractor_parser(__doc__, output=OUTPUT, ldraw=True)
    parser.add_argument("--bricknet-data", help="BrickNet's _data/<version> directory")
    args = parser.parse_args(argv)
    data_dir = find_bricknet_data(args.bricknet_data)
    print(f"Using BrickNet data: {data_dir}")

    # The registry the runtime itself loads, so a malformed or renamed field
    # fails here rather than silently emitting mis-keyed rows.
    type_aliases = connector_config().aliases
    lib = Library.find(args.ldraw)
    catalog = catalog_sources(lib, bricknet_data=data_dir)
    part_ids = sorted(catalog.labels.keys() | set(catalog.part_ids))
    parts, missing = build_connectivity(
        catalog.labels, catalog.connectivity, part_ids, type_aliases
    )

    print(f"Extracted {len(parts)} of {len(part_ids)} parts.")
    if missing:
        shown = ", ".join(missing[:20]) + (" ..." if len(missing) > 20 else "")
        print(f"No connector labels for {len(missing)} selected parts: {shown}")

    return emit(
        parts,
        args.output,
        check=args.check,
        generated_by="extract_part_connectivity.py (BrickNet labels)",
        note=_NOTE,
    )


def build_connectivity(
    labels: dict[str, dict],
    sources: dict[str, PartSource],
    part_ids: Iterable[str],
    type_aliases: dict[str, str],
) -> tuple[dict[str, dict], list[str]]:
    """Write resolved donor labels in each requested part's own LDraw frame.

    Identity transforms retain compact grouped rows. Rotated or shifted donors
    emit explicit positions and frame axes. Borrowed data names its donor in
    ``_source``; ids with no donor are returned separately.
    """
    parts: dict[str, dict] = {}
    missing: list[str] = []
    for part_id in part_ids:
        source = sources.get(part_id)
        if source is None:
            missing.append(part_id)
            continue
        entry = labels[source.part_id]
        parts[part_id] = {
            "connectors": (
                _grouped_rows(entry, type_aliases)
                if source.pose == Pose()
                else _transformed_rows(entry, type_aliases, source.pose)
            )
        }
        if source.part_id != part_id:
            parts[part_id]["_source"] = source.part_id
    return parts, missing


def _transformed_rows(entry: dict, aliases: dict[str, str], pose: Pose) -> list[dict]:
    connectors = []
    for family, subtype, polarity, rows in _triples(entry):
        for row in rows:
            x, y, z, pitch, roll, extra = (row + [0.0] * 6)[:6]
            yaw, length = (extra, 0) if family in YAW_FAMILIES else (0, extra)
            axis, side = frame_axes(pitch, roll, yaw)
            connectors.append(
                {
                    "type": resolve_name(family, subtype, polarity, aliases),
                    "pos": tuple(
                        LDrawVec.from_position(
                            pose.apply(LDrawVec(x, y, z).to_position())
                        )
                    ),
                    "axis": tuple(pose.rotation @ axis),
                    "side": tuple(pose.rotation @ side),
                    "length": length,
                }
            )
    return connectors


def _triples(entry: dict) -> Iterator[tuple[str, str, str | None, list[list[float]]]]:
    """Every ``(kind, subtype, polarity, rows)`` in one part's BrickNet entry.

    Only ``hinge``, ``ball``, and ``fixed`` nest a polarity under the subtype; the
    rest hold their rows directly.
    """
    for kind, subtypes in entry.items():
        for subtype, value in subtypes.items():
            if isinstance(value, dict):
                for polarity, rows in value.items():
                    yield kind, subtype, polarity, rows
            else:
                yield kind, subtype, None, value


def _grouped_rows(
    entry: dict, type_aliases: dict[str, str]
) -> dict[str, list[list[float]]]:
    """One part's rows, grouped under their resolved BrickLayer type name."""
    grouped: dict[str, list[list[float]]] = {}
    for kind, subtype, polarity, rows in _triples(entry):
        grouped.setdefault(
            resolve_name(kind, subtype, polarity, type_aliases), []
        ).extend(rows)
    return {name: grouped[name] for name in sorted(grouped)}


if __name__ == "__main__":
    raise SystemExit(main())
