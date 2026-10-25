"""Run every LDraw extraction script in sequence, forwarding ``--check`` to each.

A failing script is reported but does not stop the others; the overall exit code is
non-zero if any script failed.
"""

import argparse

from bricklayer.ldraw.scripts import (
    extract_part_connectivity,
    extract_part_geometry,
    extract_part_meshes,
    extract_part_popularity,
    extract_part_taxonomy,
)

_SCRIPTS = (
    extract_part_geometry,
    extract_part_taxonomy,
    extract_part_connectivity,
    extract_part_meshes,
    extract_part_popularity,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="diff each data file against its committed copy; don't write",
    )
    args = parser.parse_args(argv)
    forwarded = ["--check"] if args.check else []

    failures = []
    for script in _SCRIPTS:
        name = script.__name__.rsplit(".", 1)[-1]
        print(f"\n=== {name} ===")
        try:
            code = script.main(forwarded)
        except SystemExit as exc:
            print(exc)
            code = exc.code if isinstance(exc.code, int) else 1
        if code:
            failures.append(name)

    if failures:
        print(f"\nFAILED: {', '.join(failures)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
