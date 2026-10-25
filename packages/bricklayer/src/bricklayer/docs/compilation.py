"""Generate Markdown documentation for BrickLayer."""

from collections.abc import Callable
from fractions import Fraction
from functools import cache
from typing import Any

from .. import colors, construction, geometry, modeling, parts
from ..colors import Color, Finish
from ..construction import COMPONENT_TYPES, CONSTRUCTION_HELPERS, VARIANT_ENUMS, fill
from ..construction.registry import COMPONENT_FACTORIES, valid_part_kwarg_combos
from ..geometry import PLATE, HeightLike, connections
from ..ldraw import get_connector_type
from ..modeling import articulation, transforms
from ..modeling.build import LegoBuild, NameRef
from ..modeling.placement import Placement
from ..modeling.transforms import BUILD_TRANSFORMATIONS
from ..parts import CATALOG_TYPES, DISCOVERY, Element, element
from .utils import (
    ClassDoc,
    bullet,
    document_definitions,
    document_function,
    document_module,
    heading,
    paragraphs,
)


@cache
def api_reference() -> str:
    """Compile the agent reference from module and API docstrings.

    This manifest selects sections and class members; prose belongs with its
    implementation. Factory choices and colors are read from their registries.
    """
    import bricklayer

    sections = [
        document_module(bricklayer, 1),
        document_module(geometry),
        document_definitions(
            [
                ClassDoc(geometry.Anchor, members=()),
                geometry.Axis,
                ClassDoc(
                    geometry.LegoGeometry,
                    members=(
                        "alignment_box",
                        "alignment_width",
                        "alignment_depth",
                        "alignment_height",
                        "center",
                        "width",
                        "depth",
                        "height",
                        "find_connector",
                        "find_connectors",
                        "rotated_footprint",
                    ),
                    constructor=False,
                ),
                geometry.Direction,
                ClassDoc(geometry.Mat3, members=("IDENTITY", "entries", "transpose")),
                ClassDoc(
                    geometry.Position,
                    members=(
                        "ZERO",
                        "align_to_grid",
                        "is_grid_aligned",
                        "to_stud_units",
                        "from_stud_units",
                    ),
                ),
                ClassDoc(
                    geometry.Pose,
                    members=(
                        "IDENTITY",
                        "rotation",
                        "translation",
                        "inverse",
                        "apply",
                        "compose",
                        "from_rotation",
                    ),
                ),
                ClassDoc(geometry.Rotation, members=("matrix", "rotate")),
                ClassDoc(geometry.Vec3, members=("x", "y", "z", "norm")),
                geometry.rotation_about,
                geometry.to_bricks,
                geometry.to_plates,
                ("PLATE", PLATE),
                ("HeightLike", HeightLike),
            ],
            3,
        ),
        document_module(connections),
        document_definitions(
            [
                ClassDoc(
                    geometry.Connector,
                    members=("type", "position", "axis", "side", "length"),
                    constructor=False,
                ),
                ClassDoc(geometry.ConnectorType, members=("name",), constructor=False),
                geometry.JointKind,
                ClassDoc(
                    geometry.Mounting,
                    members=("angle", "offset", "flip", "swing_x", "swing_y"),
                ),
                ClassDoc(geometry.Fixed, members=()),
                ClassDoc(geometry.Revolute, members=("angle",)),
                ClassDoc(geometry.Prismatic, members=("offset",)),
                ClassDoc(geometry.Cylindrical, members=("offset", "angle")),
                ClassDoc(geometry.Ball, members=("swing_x", "swing_y", "twist")),
                get_connector_type,
            ],
            3,
        ),
        document_module(parts),
        document_definitions(
            DISCOVERY
            + [
                ClassDoc(cls, members=(), constructor=False)
                if cls is parts.PartShape
                else ClassDoc(cls, members=())
                if issubclass(cls, parts.PartShape)
                else cls
                for cls in CATALOG_TYPES
            ],
            3,
        ),
        document_module(element),
        document_definitions(
            [
                ClassDoc(
                    Element,
                    members=("ldraw_id", "color", "spec", "bounding_box", "connectors"),
                )
            ],
            3,
        ),
        document_module(construction),
        *[
            describe_component_factory(f, heading_level=3)
            for f in sorted(COMPONENT_FACTORIES, key=lambda f: f.__name__)
        ],
        document_definitions(COMPONENT_TYPES + VARIANT_ENUMS, 3),
        _list_available_colors(),
        document_module(modeling),
        document_definitions(
            [
                ClassDoc(
                    Placement,
                    members=("bounding_box", "connectors", "pose", "to_world"),
                    constructor=False,
                ),
                ClassDoc(
                    LegoBuild,
                    members=(
                        "bounding_box",
                        "brick_count",
                        "colliding_placements",
                        "connected_components",
                        "connectors",
                        "flattened_placements",
                        "floating_placements",
                        "names",
                        "num_connected_components",
                        "placements",
                        "joints",
                        "flattened_joints",
                        "add",
                        "add_raw",
                        "connect",
                        "joint",
                        "set_motion",
                        "posed",
                        "check_motion",
                        "copy",
                        "deepcopy",
                        "extend",
                        "is_connected",
                        "is_valid",
                        "list_elements",
                        "name_of",
                        "named",
                        "remove",
                        "stack",
                    ),
                ),
                ("NameRef", NameRef),
            ],
            3,
        ),
        document_module(fill),
        document_definitions(CONSTRUCTION_HELPERS, 3),
        document_module(articulation),
        document_definitions(
            [
                ClassDoc(articulation.MotionRange, members=("lower", "upper")),
                ClassDoc(
                    articulation.Joint,
                    members=("kind", "motion"),
                    constructor=False,
                ),
                ClassDoc(
                    articulation.MotionReport,
                    members=(
                        "passed",
                        "samples_checked",
                        "collisions",
                        "disconnections",
                        "floating",
                    ),
                    constructor=False,
                ),
                ClassDoc(
                    articulation.MotionCollision,
                    members=("positions", "placements"),
                    constructor=False,
                ),
                ClassDoc(
                    articulation.MotionDisconnection,
                    members=("positions", "joint"),
                    constructor=False,
                ),
                ClassDoc(
                    articulation.MotionFloating,
                    members=("positions", "placements"),
                    constructor=False,
                ),
            ],
            3,
        ),
        document_module(transforms),
        document_definitions(BUILD_TRANSFORMATIONS, 3),
    ]
    return "\n\n".join(sections).rstrip() + "\n"


def _list_available_colors() -> str:
    """List every color, grouped into a subsection per surface finish."""
    blocks = [document_module(colors, 3)]
    for finish in Finish:
        names = [f"`{c!r}`" for c in Color if c.finish is finish]
        if not names:
            continue
        blocks.append(
            f"#### {finish.display_name}\n\n{finish.__doc__}\n\n{', '.join(names)}"
        )
    return "\n\n".join(blocks)


def describe_component_factory(factory: Callable, heading_level: int = 1) -> str:
    """Detailed description of a given component factory."""
    return paragraphs(
        document_function(factory, heading_level),
        list_valid_kwarg_combos(factory, heading_level + 1),
    )


def list_valid_kwarg_combos(factory: Callable, heading_level: int = 1) -> str:
    """The argument sets that produce valid parts: the shared kwarg names,
    then a tuple of values for each valid combination.

    Kwarg names and arguments are listed in the order given by :func:`valid_part_kwarg_combos`.
    """
    combos = tuple(dict(combo) for combo in valid_part_kwarg_combos(factory) or [])
    if not combos:
        return ""
    # Every combo carries the same keys in the same order.
    names = combos[0].keys()
    rows = tuple(tuple(combo[name] for name in names) for combo in combos)
    return "\n".join(
        (
            heading(
                f"Valid argument combinations `({', '.join(names)})`", heading_level
            ),
            "",
            *(
                bullet(f"`({', '.join(_format_kwarg(v) for v in row)})`")
                for row in rows
            ),
        )
    )


def _format_kwarg(value: Any) -> str:
    """Render an argument value as the literal a caller would type (so `Fraction(1,3)` becomes `1/3`)."""
    return str(value) if isinstance(value, Fraction) else repr(value)
