"""Transparent connected-component diagnostics in the build's original frame."""

from __future__ import annotations

import colorsys
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bricklayer import LegoBuild

COMPONENT_ALPHA = 120
COMPONENT_COLOR_START = 100000


@dataclass(frozen=True)
class ConnectivityDiagnostic:
    ldraw: str
    components: tuple[tuple[int, ...], ...]
    colors: tuple[str, ...]

    @property
    def metadata(self) -> dict:
        return {
            "component_count": len(self.components),
            "alpha": COMPONENT_ALPHA / 255,
            "components": [
                {"index": i, "color": color, "part_indices": list(parts)}
                for i, (parts, color) in enumerate(
                    zip(self.components, self.colors, strict=True)
                )
            ],
        }


def connectivity_diagnostic(
    build: LegoBuild, *, components: tuple[tuple[int, ...], ...] | None = None
) -> ConnectivityDiagnostic:
    """Color each component uniformly, preserving flattened part order and poses."""
    from bricklayer import Element, LegoBuild, Placement, to_ldraw
    from bricklayer.ldraw.colors import LDrawColor

    leaves = build.flattened_placements
    if components is None:
        indices = {id(part): i for i, part in enumerate(leaves)}
        components = tuple(
            tuple(indices[id(part)] for part in group)
            for group in build.connected_components
        )
    if any(not group for group in components) or sorted(
        i for group in components for i in group
    ) != list(range(len(leaves))):
        raise ValueError("Components must partition all build placements exactly once")
    colors = component_colors(len(components))
    group_of = {i: group for group, parts in enumerate(components) for i in parts}
    recolored = LegoBuild(
        Placement(
            Element(
                leaf.content.ldraw_id, LDrawColor(COMPONENT_COLOR_START + group_of[i])
            ),
            leaf.pose,
        )
        for i, leaf in enumerate(leaves)
    )
    header = ["0 Connected components; original part positions preserved"]
    header.extend(
        f"0 !COLOUR Component_{i + 1} CODE {COMPONENT_COLOR_START + i} VALUE {color} EDGE #333333 ALPHA {COMPONENT_ALPHA}"
        for i, color in enumerate(colors)
    )
    ldraw = "\n".join(header) + "\n" + to_ldraw(recolored)
    return ConnectivityDiagnostic(ldraw, components, colors)


def component_colors(count: int) -> tuple[str, ...]:
    used = set()
    colors = []
    for i in range(count):
        rgb = colorsys.hsv_to_rgb((0.58 + i * 0.618033988749895) % 1, 0.78, 0.92)
        value = int.from_bytes(bytes(round(c * 255) for c in rgb))
        while value in used:
            value = (value + 1) % (1 << 24)
        used.add(value)
        colors.append(f"#{value:06X}")
    return tuple(colors)


def convert_connectivity_diagnostics(
    source: Path, target: Path, *, library: Path | None = None
) -> None:
    """Convert diagnostic LDraw, applying its custom transparent palette to prints too."""
    from bricklayer.colors import linear_rgb
    from ldraw2mesh import load_scene
    from ldraw2mesh.gltf import write_gltf
    from ldraw2mesh.scene import build_jobs

    palette = {}
    for name, code, rgb, alpha in re.findall(
        r"^0 !COLOUR (Component_\d+) CODE (\d+) VALUE #([0-9A-F]{6}) EDGE #[0-9A-F]{6} ALPHA (\d+)$",
        source.read_text(),
        flags=re.MULTILINE,
    ):
        rgba = (*linear_rgb(rgb), int(alpha) / 255)
        palette[int(code)] = _ComponentColor(name, rgba)
    jobs = build_jobs(load_scene(source, ldraw_library=library, gaps=True))
    for job in jobs:
        if job.color not in palette:
            raise ValueError("Missing connectivity diagnostic color")
        job.face_colors.fill(job.color)
    write_gltf(jobs, palette, target)


@dataclass(frozen=True)
class _ComponentColor:
    name: str
    rgba_linear: tuple[float, ...]
    finish_name: str = "Transparent"
